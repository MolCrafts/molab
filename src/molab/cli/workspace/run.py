"""``molab {run,exec,shell}`` — execution commands."""

from __future__ import annotations

import os
import subprocess
import sys
import traceback
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, NamedTuple, Protocol

import typer
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from molab._typing import JSONValue
from molab.cli._app import app
from molab.cli._common import console, deterministic_run_id, reap_zombie_run, rprint
from molab.cli._target import TargetOption, resolve_workspace_target
from molab.profile import MolCfg, ProfileConfig, load_molcfg
from molab.profile.loader import find_default_config
from molab.workflow import default_binding_registry
from molab.workspace.domain import ExecutionMode
from molab.workspace.execution_context import profile_config_hash
from molab.workspace.run import RunStatus
from molab.workspace.source_snapshot import SourceCaptureError
from molab.workspace.target import LocalTarget, RemoteTarget

if TYPE_CHECKING:
    from molab.workspace.experiment import Experiment
    from molab.workspace.models import ComputeTarget
    from molab.workspace.project import Project
    from molab.workspace.run import Run
    from molab.workspace.workspace import Workspace


class RunHandler(Protocol):
    """Dispatch one selected run: execute it in-process or submit it.

    The dispatcher creates the run's QUEUED Execution record immediately
    before the call and hands its id as *execution_id*. ``--resume`` creates
    a new RESUME record based on the latest attempt; it does not reopen one.
    The molq ``SubmitHandler`` satisfies this structurally.
    """

    def __call__(
        self,
        script: Path,
        mol_run: Run,
        experiment: Experiment,
        project: Project,
        /,
        *,
        execution_id: str,
    ) -> None: ...


class RunCandidate(NamedTuple):
    """One prospective run of an experiment, before the skip/create rules.

    Attributes:
        existing_run: The run already on disk for this candidate, if any.
        run_params: The run's parameters.
        config_hash: The profile's identity contribution (``None`` for
            declared runs, which are not profile-keyed).
        seed_label: The replica seed shown to the user, if any.
    """

    existing_run: Run | None
    run_params: dict[str, JSONValue]
    config_hash: str | None
    seed_label: str | None


_SCRIPT_ARG = Annotated[
    Path,
    typer.Argument(
        help="Python script with me.entry(ws) call.",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
    ),
]


# ── Config helpers ────────────────────────────────────────────────────────────


def _coerce_value(raw: str) -> JSONValue:
    if raw.lower() == "true":
        return True
    if raw.lower() == "false":
        return False
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    return raw


def _set_nested(d: dict[str, JSONValue], key_path: str, value: JSONValue) -> None:
    parts = key_path.split(".")
    node: dict[str, JSONValue] = d
    for part in parts[:-1]:
        existing = node.get(part)
        if isinstance(existing, dict):
            node = existing
            continue
        new_child: dict[str, JSONValue] = {}
        node[part] = new_child
        node = new_child
    node[parts[-1]] = value


def _apply_overrides(profile_cfg: ProfileConfig, overrides: list[str]) -> ProfileConfig:
    if not overrides:
        return profile_cfg
    data = profile_cfg.to_dict()
    for item in overrides:
        if "=" not in item:
            rprint(f"[red]Error:[/red] --set value {item!r} is not in KEY=VALUE format.")
            raise typer.Exit(1)
        key, _, raw = item.partition("=")
        key = key.strip()
        if not key:
            rprint(f"[red]Error:[/red] --set value {item!r} has an empty key.")
            raise typer.Exit(1)
        _set_nested(data, key, _coerce_value(raw))
    return ProfileConfig(data, name=profile_cfg.name)


def _resolve_profile(config_path: Path | None, profile: str | None) -> ProfileConfig:
    resolved_path: Path | None
    if config_path is not None:
        resolved_path = config_path
    else:
        resolved_path = find_default_config()
    if resolved_path is None:
        if profile is not None:
            rprint(
                f"[red]Error:[/red] --profile {profile!r} was requested but no config file found."
            )
            raise typer.Exit(1)
        return ProfileConfig({}, name=None)
    try:
        cfg: MolCfg = load_molcfg(resolved_path)
    except Exception as exc:
        rprint(f"[red]Error:[/red] failed to load config {resolved_path}: {exc}")
        raise typer.Exit(1)  # noqa: B904
    try:
        return cfg.resolve(profile)
    except KeyError as exc:
        rprint(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)  # noqa: B904


# ── Replica dispatch ──────────────────────────────────────────────────────────


def _watch_path_for(workspace_arg: Path | None, submitted: list[Run]) -> str:
    root: Path | None = None
    if workspace_arg is not None:
        root = Path(workspace_arg)
    elif submitted:
        try:
            root = Path(submitted[0].experiment.project.workspace.root)
        except AttributeError:
            root = None
    if root is None:
        return "."
    root = root.resolve()
    cwd = Path.cwd().resolve()
    if root == cwd:
        return "."
    try:
        return str(root.relative_to(cwd))
    except ValueError:
        return str(root)


def _load_script_workspaces(
    script: Path, workspace: Path | None, explicit_workspace: bool
) -> tuple[list[Workspace], Path | None]:
    """Import *script* and collect its ``me.entry()`` workspaces.

    Root precedence: an explicit -ws flag is a STRONG override (wins over a
    script-hardcoded root); otherwise infer the entry-script directory as a
    WEAK override (only fills a rootless Workspace), falling back to cwd.
    """
    from molab.entry import infer_workspace_root, load_workspaces
    from molab.workspace.workspace import set_cli_root_override

    if explicit_workspace and workspace is not None:
        override_path = Path(workspace).resolve()
        set_cli_root_override(override_path, explicit=True)
    else:
        try:
            override_path = infer_workspace_root(script)
        except ValueError:
            override_path = Path.cwd().resolve()
        set_cli_root_override(override_path, explicit=False)
    try:
        workspaces = load_workspaces(script)
    except Exception as exc:
        rprint(f"[red]Error importing {script.name}:[/red] {exc}")
        rprint(traceback.format_exc(), end="")
        raise typer.Exit(1)  # noqa: B904
    finally:
        set_cli_root_override(None)

    if not workspaces:
        rprint(
            "[red]Error:[/red] No me.entry() call found in script. Add [bold]me.entry(workspace)[/bold] at module level."
        )
        raise typer.Exit(1)
    return workspaces, override_path


def _legacy_replica_run(
    existing_by_id: Mapping[str, Run],
    run_params: dict[str, JSONValue],
    profile_cfg: ProfileConfig,
) -> Run | None:
    """Find a replica run created under the pre-UUIDv7 16-hex id scheme.

    Read-only compatibility for older workspaces: the id is derived exactly as
    ``molab run`` used to derive it (the run params, plus ``_profile`` and
    ``_config_hash`` for a named profile) and matched against existing run ids.
    It never reads or computes a definition hash.

    Args:
        existing_by_id: The experiment's runs keyed by id.
        run_params: The replica's parameters (``seed`` / ``replica`` included).
        profile_cfg: The active profile.

    Returns:
        The legacy run with that id, or ``None``.
    """
    id_seed = dict(run_params)
    if profile_cfg.name is not None:
        id_seed["_profile"] = profile_cfg.name
        id_seed["_config_hash"] = profile_config_hash(profile_cfg)
    return existing_by_id.get(deterministic_run_id(id_seed))


def _experiment_candidates(
    exp: Experiment, profile_cfg: ProfileConfig
) -> tuple[list[RunCandidate], bool, int]:
    """Build the prospective run list for one experiment.

    Declared runs (any run without a ``replica`` parameter) are taken as they
    are. Otherwise one candidate per seed is built; its identity is the
    replica params plus :func:`profile_config_hash` of *profile_cfg*, looked up
    first as a legacy 16-hex id (:func:`_legacy_replica_run`) and then through
    :meth:`Experiment.find_run`. Nothing is created here.

    Args:
        exp: The experiment to dispatch.
        profile_cfg: The active profile.

    Returns:
        ``(candidates, use_declared_runs, total)``.
    """
    existing_runs = sorted(exp.list_runs(), key=lambda item: item.id)
    # A run auto-generated by the replica path carries a "replica"
    # marker in its parameters; only genuinely user-declared runs
    # count as "declared". Without this, a prior replica invocation
    # would make a later profile reuse that run instead of creating
    # its own profile-distinct replica run.
    declared_runs = [r for r in existing_runs if "replica" not in r.parameters]
    use_declared_runs = len(declared_runs) > 0
    seeds = exp.get_seeds()
    total = len(declared_runs) if use_declared_runs else exp.n_replicas

    candidates: list[RunCandidate]
    if use_declared_runs:
        candidates = [RunCandidate(run, dict(run.parameters), None, None) for run in declared_runs]
    else:
        existing_by_id = {r.id: r for r in existing_runs}
        config_hash = profile_config_hash(profile_cfg)
        candidates = []
        for replica_idx, seed in enumerate(seeds):
            run_params: dict[str, JSONValue] = {**exp.params, "seed": seed, "replica": replica_idx}
            # Legacy id first: an old run's definition does not fold the
            # config in, so a hash lookup first would let a config-less call
            # adopt an old profile-keyed run.
            existing = _legacy_replica_run(existing_by_id, run_params, profile_cfg)
            if existing is None:
                existing = exp.find_run(run_params, config_hash=config_hash)
            candidates.append(RunCandidate(existing, run_params, config_hash, str(seed)))
    return candidates, use_declared_runs, total


def _select_candidate_runs(
    candidates: list[RunCandidate],
    *,
    exp: Experiment,
    continue_verb: str | None,
) -> list[tuple[Run, str]]:
    """Apply the verb-specific skip/create rules and report each decision.

    A plain run creates a missing replica run through
    :meth:`Experiment.ensure_run` with the candidate's ``config_hash``;
    ``--resume`` / ``--rerun`` never create one.

    Args:
        candidates: Output of :func:`_experiment_candidates`.
        exp: The experiment the candidates belong to.
        continue_verb: ``None`` (plain run), ``"resume"`` or ``"rerun"``.

    Returns:
        ``(run, label)`` for every run to dispatch.
    """
    selected_runs: list[tuple[Run, str]] = []
    for existing, run_params, config_hash, seed_label in candidates:
        mol_run = existing
        status = mol_run.status_label if mol_run is not None else RunStatus.PENDING.value
        if mol_run is not None and mol_run.status_summary.active > 0 and reap_zombie_run(mol_run):
            status = RunStatus.FAILED.value
            rprint(
                f"  [yellow]![/yellow] {exp.name}  {mol_run.name} (stale 'running' run reaped -> failed)"
            )
        if continue_verb is not None:
            # Neither verb creates a run. Resume keeps the retryable domain
            # (a failed/cancelled/interrupted attempt, nothing active). Rerun
            # opens a fresh attempt on any finished run, including one whose
            # latest attempt succeeded; a live attempt still blocks it.
            if mol_run is None:
                rprint(f"  [dim]- {exp.id}  seed={seed_label} (no existing run, skipped)[/dim]")
                continue
            if continue_verb == "rerun":
                if not mol_run.executions or mol_run.status_summary.active > 0:
                    rprint(
                        f"  [dim]- {exp.name}  {mol_run.name} ({status}, skipped — "
                        "rerun needs a finished attempt and no active one)[/dim]"
                    )
                    continue
            elif not mol_run.is_retryable:
                rprint(
                    f"  [dim]- {exp.name}  {mol_run.name} ({status}, skipped — "
                    "resume only retries failed/cancelled runs)[/dim]"
                )
                continue
        elif mol_run is not None:
            # plain run: run only what has not run yet (pending).
            # Leave succeeded / running / failed / cancelled alone —
            # retrying a failure is an explicit --resume / --rerun.
            if not mol_run.status_summary.not_started:
                rprint(
                    f"  [dim]- {exp.name}  {mol_run.name} ({status}, skipped — "
                    "use --resume or --rerun to retry)[/dim]"
                )
                continue
        else:
            mol_run = exp.ensure_run(run_params, config_hash=config_hash)
        label_text = f"seed={seed_label}" if seed_label is not None else mol_run.name
        selected_runs.append((mol_run, label_text))
        icon = "[cyan]>[/cyan]" if continue_verb is not None else "[dim]o[/dim]"
        rprint(f"  {icon} {exp.name}  {label_text}")
    return selected_runs


def _create_dispatch_execution(
    mol_run: Run,
    *,
    continue_verb: str | None,
    fresh: bool,
    profile_cfg: ProfileConfig,
    script: Path,
    submit_cwd: str,
) -> str:
    """Create the QUEUED Execution record one dispatched run will start.

    The only place ``molab run`` creates a record. A plain run opens an
    ``initial`` attempt (only not-started runs are selected); ``--rerun``
    opens a ``rerun`` attempt based on the run's latest one; ``--resume``
    opens a ``resume`` attempt based on that same latest attempt. Completed
    nodes are seeded later, from the predecessor's journal, by
    ``execution.execute``.

    Args:
        mol_run: The run about to be dispatched.
        continue_verb: ``None`` (plain run), ``"resume"`` or ``"rerun"``.
        fresh: Record that the attempt bypasses the workflow node cache.
            Ignored for ``--resume``, which always records ``bypass_cache``
            false.
        profile_cfg: The profile the attempt runs under; recorded as its
            ``profile`` / ``config`` / ``config_hash``.
        script: The defining script; recorded as ``environment.script`` and
            captured as the attempt's source entrypoint.
        submit_cwd: The directory ``molab run`` was invoked from.

    Returns:
        The new attempt's id (``e01``, ``e02``, …).

    Raises:
        ValueError: The workspace refuses this mode for this run (for
            example a RESUME based on an attempt that already succeeded).
            The dispatcher turns that into a skip.
        typer.Exit: The script's source could not be captured (the attempt
            is sealed FAILED by the workspace and the batch stops).
    """
    if continue_verb == "resume":
        mode = ExecutionMode.RESUME
        based_on: str | None = mol_run.executions[-1].id
        bypass_cache = False
    elif continue_verb == "rerun":
        mode = ExecutionMode.RERUN
        based_on = mol_run.executions[-1].id
        bypass_cache = fresh
    else:
        mode = ExecutionMode.INITIAL
        based_on = None
        bypass_cache = fresh
    entrypoint = script.resolve()
    try:
        record = mol_run._create_execution(
            mode=mode,
            predecessor=based_on,
            bypass_cache=bypass_cache,
            profile_config=profile_cfg,
            environment={"script": str(entrypoint), "submit_cwd": submit_cwd},
            source_entrypoint=entrypoint,
        )
    except SourceCaptureError as exc:
        rprint(
            f"[red]Error:[/red] could not capture the source of "
            f"{script.name} for run {mol_run.id}: {exc}"
        )
        raise typer.Exit(1) from exc
    return record.id


def _execute_selected(
    all_replicas: list[tuple[Run, Experiment, Project]],
    run_handler: RunHandler,
    script: Path,
    *,
    show_progress: bool,
    continue_verb: str | None,
    fresh: bool,
    profile_cfg: ProfileConfig,
    submit_cwd: str,
) -> list[Run]:
    """Run *run_handler* over every selected run, with optional progress bar.

    Each run's Execution record is created on the line right before its
    handler call, so a batch interrupted part-way leaves no QUEUED record on
    the runs it never reached. A ``ValueError`` from creation (the workspace
    refuses the mode) prints a skip line and does not call the handler; the
    progress bar still advances. A source-capture ``RuntimeError`` is not
    caught and still aborts the batch.

    Args:
        all_replicas: ``(run, experiment, project)`` for every selected run.
        run_handler: Executes or submits one run.
        script: The defining script.
        show_progress: Draw a progress bar instead of per-run lines.
        continue_verb: ``None`` (plain run), ``"resume"`` or ``"rerun"``.
        fresh: Record that each attempt bypasses the workflow node cache.
        profile_cfg: The profile each attempt runs under.
        submit_cwd: The directory ``molab run`` was invoked from.

    Returns:
        The runs that were handed to *run_handler*, in order.
    """

    def _dispatch_one(mol_run: Run, exp: Experiment, project: Project) -> bool:
        try:
            execution_id = _create_dispatch_execution(
                mol_run,
                continue_verb=continue_verb,
                fresh=fresh,
                profile_cfg=profile_cfg,
                script=script,
                submit_cwd=submit_cwd,
            )
        except ValueError as exc:
            rprint(f"  [dim]- {exp.name}  {mol_run.name} (skipped — {exc})[/dim]")
            return False
        run_handler(script, mol_run, exp, project, execution_id=execution_id)
        return True

    dispatched_runs: list[Run] = []
    if show_progress and all_replicas:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task_id = progress.add_task("running workflows", total=len(all_replicas))
            for mol_run, exp, project in all_replicas:
                progress.update(task_id, description=f"{exp.id} / {mol_run.id}")
                if _dispatch_one(mol_run, exp, project):
                    dispatched_runs.append(mol_run)
                progress.advance(task_id)
    else:
        for mol_run, exp, project in all_replicas:
            if _dispatch_one(mol_run, exp, project):
                dispatched_runs.append(mol_run)
                rprint(f"  [cyan]>[/cyan] dispatched {exp.name}  {mol_run.name}")
    return dispatched_runs


def _refuse_unrecoverable(replicas: list[tuple[Run, Experiment, Project]]) -> None:
    """Exit before submitting when a worker could not rebuild a run's workflow."""
    from molab.workflow import can_recover_workflow

    stuck = sorted({exp.name for run, exp, _project in replicas if not can_recover_workflow(run)})
    if not stuck:
        return
    rprint(
        "[red]Error:[/red] a scheduler worker re-imports the workflow, and these experiments "
        f"record no importable locator: {', '.join(stuck)}.\n"
        "  Keep the Workflow (or its compiled object) in a module-level variable of the "
        "script, e.g. [bold]wf = Workflow(...)[/bold], and pass that to define()."
    )
    raise typer.Exit(1)


def _dispatch_runs(
    *,
    script: Path,
    profile_cfg: ProfileConfig,
    continue_verb: str | None,
    workspace: Path | None,
    explicit_workspace: bool,
    run_handler: RunHandler | None,
    mode_label: str,
    suppress_ok: bool = False,
    dry_run: bool = False,
    show_progress: bool = False,
    fresh: bool = False,
    require_recoverable: bool = False,
) -> tuple[int, list[Run]]:
    """Select the runs of every bound experiment in *script* and dispatch them.

    Args:
        script: The defining script (imported for its ``me.entry`` workspaces).
        profile_cfg: The active profile.
        continue_verb: ``None`` (plain run), ``"resume"`` or ``"rerun"``.
        workspace: The ``-ws`` root, if any.
        explicit_workspace: Whether ``-ws`` was given explicitly.
        run_handler: Executes or submits one run; ``None`` only selects.
        mode_label: Human label for the dispatch mode.
        suppress_ok: Leave the final OK line to the caller.
        dry_run: Select (and create missing runs) but create no Execution.
        show_progress: Draw a progress bar while dispatching.
        fresh: Record that each new attempt bypasses the workflow node cache.
        require_recoverable: Refuse, before any attempt is created, a run whose
            workflow another process could not rebuild (a scheduler worker
            re-imports the script; it cannot use this process's binding).

    Returns:
        ``(count, runs)``. Dry-run and select-only return the selected count.
        A live dispatch returns how many runs were actually handed to the
        handler; a creation skip is not counted.
    """
    workspaces, override_path = _load_script_workspaces(script, workspace, explicit_workspace)

    total_dispatched = 0
    all_replicas: list[tuple[Run, Experiment, Project]] = []

    for ws in workspaces:
        if override_path is not None and ws.root == override_path:
            rprint(f"[dim]--workspace override active: {ws.root}[/dim]")
        for project in ws.list_projects():
            for exp in project.list_experiments():
                if default_binding_registry.for_experiment(exp) is None:
                    continue
                candidates, use_declared_runs, total = _experiment_candidates(exp, profile_cfg)
                label = (
                    f"[cyan]{continue_verb}[/cyan] + {mode_label}"
                    if continue_verb is not None
                    else mode_label
                )
                profile_display = profile_cfg.name or "(defaults)"
                rprint(
                    f"\n[bold]Experiment:[/bold] {exp.name}"
                    f"\n  Script:    {script}"
                    f"\n  Workspace: {ws.root}"
                    f"\n  Project:   {project.name}"
                    f"\n  Profile:   {profile_display}"
                    f"\n  Runs:      {total} {'declared' if use_declared_runs else 'replicas'}"
                    f"\n  Mode:      {label}"
                )
                selected_runs = _select_candidate_runs(
                    candidates, exp=exp, continue_verb=continue_verb
                )
                all_replicas.extend((mol_run, exp, project) for mol_run, _label in selected_runs)
                total_dispatched += len(selected_runs)

    if dry_run or run_handler is None:
        if not suppress_ok:
            rprint(f"\n[green]OK[/green] compiled workflow plan: {total_dispatched} run(s) ready.")
        return total_dispatched, [mol_run for mol_run, _exp, _project in all_replicas]

    if require_recoverable:
        _refuse_unrecoverable(all_replicas)

    dispatched_runs = _execute_selected(
        all_replicas,
        run_handler,
        script,
        show_progress=show_progress,
        continue_verb=continue_verb,
        fresh=fresh,
        profile_cfg=profile_cfg,
        submit_cwd=str(Path.cwd().resolve()),
    )
    dispatched_count = len(dispatched_runs)
    if not suppress_ok:
        verb = {"resume": "resumed", "rerun": "reran"}.get(continue_verb or "", "completed")
        rprint(f"\n[green]OK[/green] {dispatched_count} runs {verb}.")
    return dispatched_count, dispatched_runs


def _make_local_inprocess_handler() -> RunHandler:
    """Build the handler that executes one run in this process.

    The handler starts the QUEUED record the dispatcher created.
    ``execute_run`` reads that record's config, ``bypass_cache`` and, for a
    RESUME record, the predecessor journal. A failed attempt is persisted
    and swallowed here so the rest of the batch still runs; the result
    report reads the record afterwards.

    Returns:
        A :class:`RunHandler`.
    """

    def _handler(
        _script: Path,
        mol_run: Run,
        experiment: Experiment,
        _project: Project,
        /,
        *,
        execution_id: str,
    ) -> None:
        from molab.workflow import RunFailedError, compiled_workflow_for_experiment
        from molab.workflow.execute import execute_run

        spec = compiled_workflow_for_experiment(experiment)
        try:
            execute_run(spec, mol_run, execution_id=execution_id)
        except RunFailedError:
            return

    return _handler


@app.command(name="execute", hidden=True)
def execute(
    run_dir: Annotated[
        Path,
        typer.Argument(
            help="Run directory to execute (…/runs/<params>).",
            exists=True,
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
        ),
    ],
    execution_id: Annotated[
        str,
        typer.Option(
            "--execution-id",
            help="QUEUED Execution to start (created by the submitter).",
        ),
    ],
    config: Annotated[
        Path | None,
        typer.Option(
            "--config", "-c", help="Refused: the Execution record holds the config.", exists=True
        ),
    ] = None,
    profile: Annotated[
        str | None,
        typer.Option("--profile", "-p", help="Refused: the Execution record holds the profile."),
    ] = None,
) -> None:
    """Worker entry point — start one pre-created Execution in this process.

    This is what the molq submit plugin launches on the scheduler:
    ``python -m molab.cli execute <run_dir> --execution-id <eid>``. It starts
    the QUEUED record the submitter created — workflow via
    :func:`molab.workflow.compiled_workflow_for_run`, config / profile /
    ``bypass_cache`` from the record; a RESUME record seeds completed nodes
    from its ``based_on`` attempt. ``--config`` / ``--profile`` are refused,
    because the config that runs is the recorded one.

    Args:
        run_dir: The run's directory.
        execution_id: The QUEUED attempt to start.
        config: Refused when given.
        profile: Refused when given.

    Raises:
        typer.Exit: Exit code 1 when the run cannot be found, an override is
            given, the workflow cannot be recovered, the record is not a
            startable QUEUED attempt, or the attempt does not succeed.
    """
    from molab.workflow import (
        RunFailedError,
        RunNotExecutableError,
        WorkflowRecoveryError,
        compiled_workflow_for_run,
    )
    from molab.workflow.execute import execute_run

    run_obj, experiment = _open_run(Path(run_dir))
    if config is not None or profile is not None:
        rprint(
            f"[red]Error:[/red] execution {execution_id} already records its config; "
            "the config that runs is the recorded one."
        )
        raise typer.Exit(1)

    try:
        spec = compiled_workflow_for_run(run_obj)
    except WorkflowRecoveryError as exc:
        rprint(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1) from exc
    default_binding_registry.bind(experiment, spec)

    rprint(f"[dim]execute[/dim] run={run_obj.id} execution={execution_id}")
    try:
        execute_run(spec, run_obj, execution_id=execution_id)
    except (RunNotExecutableError, ValueError) as exc:
        rprint(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1) from None
    except RunFailedError:
        status = run_obj.execution(execution_id).status.value
        rprint(
            f"[red]FAILED[/red] execute run={run_obj.id} execution={execution_id} status={status}"
        )
        raise typer.Exit(1) from None
    status = run_obj.execution(execution_id).status.value
    rprint(
        f"[green]OK[/green] execute complete run={run_obj.id} "
        f"execution={execution_id} status={status}"
    )


def _open_run(run_dir: Path) -> tuple[Run, Experiment]:
    """Open the run stored at *run_dir* and its experiment.

    Delegates to :meth:`molab.workspace.run.Run.load`. A missing workspace,
    a ``run.json`` with no id, or a run the workspace does not hold is exit 1.

    Args:
        run_dir: The run's directory.

    Returns:
        ``(run, experiment)``.

    Raises:
        typer.Exit: Exit code 1 when ``Run.load`` cannot open the run.
    """
    from pydantic import ValidationError

    from molab.workspace.errors import RunNotFoundError
    from molab.workspace.run import Run

    run_dir = Path(run_dir).resolve()
    try:
        run = Run.load(run_dir)
    except FileNotFoundError as exc:
        if "workspace.json" in str(exc):
            rprint(f"[red]Error:[/red] no workspace.json above {run_dir}.")
        else:
            rprint(f"[red]Error:[/red] run.json under {run_dir} has no run id.")
        raise typer.Exit(1) from None
    except ValidationError:
        rprint(f"[red]Error:[/red] run.json under {run_dir} has no run id.")
        raise typer.Exit(1) from None
    except RunNotFoundError as exc:
        root = run_dir
        for candidate in (run_dir, *run_dir.parents):
            if (candidate / "workspace.json").is_file():
                root = candidate
                break
        rprint(f"[red]Error:[/red] could not locate run {exc.entity_id} under {root}.")
        raise typer.Exit(1) from None
    return run, run.experiment


def _spawn_background_local_run(
    *,
    script: Path,
    target_path: Path,
    config: Path | None,
    profile: str | None,
    overrides: list[str],
    resume: bool,
    rerun: bool,
    fresh: bool = False,
) -> None:
    """Spawn a detached local ``molab run`` worker for long-running jobs."""
    log_dir = target_path / ".molab" / "background"
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = log_dir / f"{script.stem}-{stamp}.log"
    cmd = [
        sys.executable,
        "-c",
        "from molab.cli import app; app()",
        "run",
        str(script),
        "--local",
        "-t",
        str(target_path),
    ]
    if config is not None:
        cmd.extend(["--config", str(config)])
    if profile is not None:
        cmd.extend(["--profile", profile])
    for item in overrides:
        cmd.extend(["--override", item])
    if resume:
        cmd.append("--resume")
    if rerun:
        cmd.append("--rerun")
    if fresh:
        cmd.append("--fresh")

    with log_path.open("ab") as log:
        process = subprocess.Popen(
            cmd,
            cwd=Path.cwd(),
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    rprint(f"[green]OK[/green] background run started pid={process.pid}")
    rprint(f"[dim]Log: {log_path}[/dim]")


def _select_backend(
    *,
    target_path: Path,
    local: bool,
    scheduler: str | None,
    target_cli: str | None,
) -> tuple[ComputeTarget | None, str | None, bool]:
    """Resolve the execution backend from the mutually exclusive flags.

    Returns ``(selected_target, selected_scheduler, is_local)``.
    """
    backend_flags = sum(1 for f in (local, scheduler is not None, target_cli is not None) if f)
    if backend_flags > 1:
        rprint(
            "[red]Error:[/red] Specify at most one backend flag (--local, --scheduler, --target)."
        )
        raise typer.Exit(1)

    selected_target = None
    if target_cli is not None:
        from molab.workspace import Workspace

        ws = Workspace(target_path)
        try:
            selected_target = ws.get_target(target_cli)
        except KeyError as exc:
            rprint(f"[red]{exc}[/red] — see `molab target list`.")
            raise typer.Exit(1) from exc

    selected_scheduler = selected_target.scheduler if selected_target is not None else scheduler
    is_local = selected_scheduler is None and selected_target is None
    return selected_target, selected_scheduler, is_local


def _profile_mode_label(profile_cfg: ProfileConfig, backend: str) -> str:
    profile_label = (
        f"[cyan]{profile_cfg.name}[/cyan]" if profile_cfg.name else "[dim](defaults)[/dim]"
    )
    return f"{backend} profile={profile_label}"


def _run_dry_run(
    *,
    script: Path,
    profile_cfg: ProfileConfig,
    continue_verb: str | None,
    target_path: Path,
    explicit_ws: bool,
) -> None:
    """Compile/materialize the run plan without executing tasks."""
    mode_label = "[blue]dry-run[/blue] compile-only"
    n, runs = _dispatch_runs(
        script=script,
        profile_cfg=profile_cfg,
        continue_verb=continue_verb,
        workspace=target_path,
        explicit_workspace=explicit_ws,
        run_handler=None,
        mode_label=mode_label,
        dry_run=True,
    )
    if runs:
        watch_arg = _watch_path_for(target_path, runs)
        rprint(f"[dim]Preview with: molab serve -ws {watch_arg}[/dim]")
    elif n == 0:
        rprint("[dim]No runnable bound experiments found.[/dim]")


def _failure_detail(run: Run) -> str | None:
    """One line naming the latest attempt's recorded error and its evidence.

    Args:
        run: A run this invocation dispatched.

    Returns:
        ``None`` when the run has no attempt. Otherwise the evidence
        directory, prefixed by ``type: message`` when the latest attempt
        recorded an error. Missing keys print as ``?``.
    """
    if not run.executions:
        return None
    latest = run.executions[-1]
    evidence = f"Execution evidence under {run.execution_dir(latest.id)}"
    err = latest.error
    if not err:
        return evidence
    kind = err.get("type", "?")
    message = err.get("message", "?")
    return f"{kind}: {message} ({evidence})"


def _report_local_results(dispatched: list[tuple[Run, str]], continue_verb: str | None) -> None:
    """Print an honest terminal-status summary and set the process exit code.

    Each dispatched run is judged by :attr:`Run.status_label`, the latest
    attempt's status — the attempt this invocation created. A successful
    resume after an earlier failure therefore exits 0. Skipped runs never
    enter *dispatched*.

    Args:
        dispatched: ``(run, execution_id)`` for each attempt this invocation
            started.
        continue_verb: ``None`` (plain run), ``"resume"`` or ``"rerun"``.

    Raises:
        typer.Exit: Exit code 1 when any dispatched run's latest attempt did
            not succeed.
    """
    verb = {"resume": "resumed", "rerun": "reran"}.get(continue_verb or "", "completed")
    if not dispatched:
        rprint(f"\n[dim]No runs {verb}.[/dim]")
        return
    failed = [
        mol_run for mol_run, _execution_id in dispatched if mol_run.status_label != "succeeded"
    ]
    if failed:
        rprint("")
        for mol_run in failed:
            rprint(f"  [red]x[/red] run={mol_run.id}  status={mol_run.status_label}")
            detail = _failure_detail(mol_run)
            if detail is not None:
                rprint(f"    [dim]{detail}[/dim]")
        rprint(f"\n[red]FAILED[/red] {len(failed)} of {len(dispatched)} runs did not succeed.")
        rprint(
            "[dim]Retry: molab run <script> --resume (continue) or --rerun (from the top).[/dim]"
        )
        raise typer.Exit(1)
    rprint(f"\n[green]OK[/green] {len(dispatched)} runs {verb}.")


def _run_local_inprocess(
    *,
    script: Path,
    profile_cfg: ProfileConfig,
    continue_verb: str | None,
    target_path: Path,
    explicit_ws: bool,
    fresh: bool = False,
) -> None:
    """Execute the run plan in-process, with a progress bar.

    Each attempt is judged by the id the dispatcher handed its handler, so
    the handler is wrapped to collect ``(run, execution_id)`` as it runs.
    """
    mode_label = _profile_mode_label(profile_cfg, "[green]local[/green]")
    execute_one = _make_local_inprocess_handler()
    dispatched: list[tuple[Run, str]] = []

    def _collecting_handler(
        run_script: Path,
        mol_run: Run,
        experiment: Experiment,
        project: Project,
        /,
        *,
        execution_id: str,
    ) -> None:
        execute_one(run_script, mol_run, experiment, project, execution_id=execution_id)
        dispatched.append((mol_run, execution_id))

    _dispatch_runs(
        script=script,
        profile_cfg=profile_cfg,
        continue_verb=continue_verb,
        workspace=target_path,
        explicit_workspace=explicit_ws,
        run_handler=_collecting_handler,
        mode_label=mode_label,
        suppress_ok=True,
        show_progress=True,
        fresh=fresh,
    )
    _report_local_results(dispatched, continue_verb)


def _submit_to_scheduler(
    *,
    script: Path,
    profile_cfg: ProfileConfig,
    continue_verb: str | None,
    target_path: Path,
    explicit_ws: bool,
    selected_target: ComputeTarget | None,
    selected_scheduler: str | None,
    cluster: str | None,
    resources: dict[str, JSONValue],
    scheduling: dict[str, JSONValue],
    block: bool,
    fresh: bool = False,
    worker_python: str | None = None,
    preamble: list[str] | None = None,
) -> None:
    """Submit the run plan through molq and report (or monitor) the result."""
    from molab.plugins.submit_molq.metadata import supported_schedulers
    from molab.plugins.submit_molq.submit import make_submit_handler

    available_schedulers = supported_schedulers()
    if available_schedulers and selected_scheduler not in available_schedulers:
        supported_text = ", ".join(available_schedulers)
        rprint(
            f"[red]Error:[/red] Unsupported molq scheduler: {selected_scheduler!r}. Available: {supported_text}"
        )
        raise typer.Exit(1)

    assert selected_scheduler is not None
    submit_handler = make_submit_handler(
        scheduler=selected_scheduler,
        cluster=cluster,
        resources=resources,
        scheduling=scheduling,
        target=selected_target,
        preamble=preamble or None,
        python=worker_python,
    )
    handler: RunHandler = submit_handler
    mode_label = _profile_mode_label(profile_cfg, f"[magenta]{selected_scheduler}[/magenta]")

    n, submitted = _dispatch_runs(
        script=script,
        profile_cfg=profile_cfg,
        continue_verb=continue_verb,
        workspace=target_path,
        explicit_workspace=explicit_ws,
        run_handler=handler,
        mode_label=mode_label,
        suppress_ok=True,
        fresh=fresh,
        require_recoverable=True,
    )
    if n == 0:
        verb = {"resume": "resumed", "rerun": "reran"}.get(continue_verb or "", "submitted")
        rprint(f"\n[dim]No runs {verb}.[/dim]")
        return

    watch_arg = _watch_path_for(target_path, submitted)
    if block and submitted:
        from molab.cli.tui import RunMonitor

        rprint(f"\n[dim]Submitted {n} runs. Opening monitor… (press q to close)[/dim]")
        RunMonitor(title=f"{script.stem}  [{mode_label}]").watch(submitted)
        rprint(f"\n[dim]Monitor closed. {n} runs are still executing (if any).[/dim]")
        rprint(f"[dim]Reopen with:  molab monitor -t {watch_arg}[/dim]")
    else:
        verb = {"resume": "resumed", "rerun": "reran"}.get(continue_verb or "", "submitted")
        rprint(f"\n[green]OK[/green] {n} runs {verb}.")
        if submitted:
            rprint(f"[dim]Monitor runs with:  molab monitor -t {watch_arg}[/dim]")


# ── Commands ──────────────────────────────────────────────────────────────────


@app.command()
def run(
    script: _SCRIPT_ARG,
    local: Annotated[
        bool,
        typer.Option(
            "--local", help="Run in-process, no scheduler.", rich_help_panel="Execution Backend"
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Compile/materialize the workspace and run plan without executing tasks.",
        ),
    ] = False,
    bg: Annotated[
        bool,
        typer.Option(
            "--bg",
            help="Run local workflows in a detached background process.",
            rich_help_panel="Execution Backend",
        ),
    ] = False,
    scheduler: Annotated[
        str | None,
        typer.Option(
            "--scheduler",
            help="molq scheduler backend (local, slurm, pbs, lsf).",
            rich_help_panel="Execution Backend",
        ),
    ] = None,
    config: Annotated[
        Path | None,
        typer.Option(
            "--config",
            "-c",
            help="Path to molcfg file.",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
        ),
    ] = None,
    profile: Annotated[str | None, typer.Option("--profile", help="Named molcfg profile.")] = None,
    overrides: Annotated[
        list[str] | None,
        typer.Option("--override", help="Override config key (KEY=VALUE, repeatable)."),
    ] = None,
    resume: Annotated[
        bool,
        typer.Option(
            "--resume",
            help=(
                "Open a new RESUME Execution based on each failed/cancelled run's "
                "latest attempt; completed nodes are seeded from that attempt's "
                "journal, the rest recompute. Mutually exclusive with --rerun."
            ),
        ),
    ] = False,
    rerun: Annotated[
        bool,
        typer.Option(
            "--rerun",
            help=(
                "Open a new RERUN execution on each finished run, including one "
                "whose latest attempt succeeded (no seed). A run with an active "
                "attempt is skipped. Deterministic tasks may still be served from "
                "the content-addressed cache — add --fresh to bypass cache reads. "
                "Mutually exclusive with --resume."
            ),
        ),
    ] = False,
    fresh: Annotated[
        bool,
        typer.Option(
            "--fresh",
            help=(
                "With --rerun: bypass content-addressed cache reads so every task "
                "body actually re-runs (results are still written back to the cache)."
            ),
        ),
    ] = False,
    cpus: Annotated[
        int | None, typer.Option("--cpus", help="CPU cores per job.", rich_help_panel="HPC Options")
    ] = None,
    mem: Annotated[
        str | None,
        typer.Option("--mem", help="Memory per job (e.g. 8G).", rich_help_panel="HPC Options"),
    ] = None,
    time: Annotated[
        str | None,
        typer.Option("--time", help="Wall-clock time limit.", rich_help_panel="HPC Options"),
    ] = None,
    gpus: Annotated[
        int | None, typer.Option("--gpus", help="GPUs per job.", rich_help_panel="HPC Options")
    ] = None,
    gpu_type: Annotated[
        str | None,
        typer.Option(
            "--gpu-type", help="GPU type constraint (e.g. a100).", rich_help_panel="HPC Options"
        ),
    ] = None,
    account: Annotated[
        str | None,
        typer.Option(
            "--account", "-A", help="Account / project name.", rich_help_panel="HPC Options"
        ),
    ] = None,
    cluster: Annotated[
        str | None,
        typer.Option("--cluster", help="molq cluster name.", rich_help_panel="HPC Options"),
    ] = None,
    target_cli: Annotated[
        str | None,
        typer.Option(
            "--compute-target",
            help="Named compute target from workspace.",
            rich_help_panel="Execution Backend",
        ),
    ] = None,
    partition: Annotated[
        str | None,
        typer.Option("--partition", "-p", help="SLURM partition.", rich_help_panel="SLURM Options"),
    ] = None,
    qos: Annotated[
        str | None, typer.Option("--qos", help="SLURM QOS.", rich_help_panel="SLURM Options")
    ] = None,
    queue: Annotated[
        str | None,
        typer.Option(
            "--queue", "-q", help="PBS/LSF queue name.", rich_help_panel="PBS / LSF Options"
        ),
    ] = None,
    block: Annotated[
        bool,
        typer.Option(
            "--block", help="Block and open monitor after submit.", rich_help_panel="HPC Options"
        ),
    ] = False,
    worker_python: Annotated[
        str | None,
        typer.Option(
            "--python",
            help=(
                "Interpreter that runs the worker on the compute node (default: this "
                "process's). Needed when the nodes have another architecture or venv."
            ),
            rich_help_panel="HPC Options",
        ),
    ] = None,
    preamble: Annotated[
        list[str] | None,
        typer.Option(
            "--preamble",
            help="Shell line run in the job before the worker (repeatable): module load …",
            rich_help_panel="HPC Options",
        ),
    ] = None,
    target_spec: TargetOption = ".",
) -> None:
    """Execute the workflow(s) defined by *script*."""
    # An explicit -ws/--workspace flag (anything other than the "." cwd default)
    # is a strong root override; absence means infer the script's directory.
    explicit_ws = target_spec != "."
    target, _transport, _fs = resolve_workspace_target(target_spec)
    if not isinstance(target, LocalTarget):
        # ``molab run`` drives a workflow *in this process* against a local
        # workspace root.  Opening/managing a remote workspace (info, list,
        # cancel, …) is supported via ``-ws host:/path``; executing a local
        # script against a remote root still needs a remote-side driver
        # (submit / exec).  Keep the split explicit.
        rprint(
            "[red]Error:[/red] ``molab run`` executes the workflow in this process "
            "and requires a local workspace root."
        )
        rprint(
            "  To work with a remote workspace use "
            "[bold]molab info/project/runs … -ws host:/path[/bold], "
            "or [bold]molab exec/shell -ws host:/path[/bold] to drive commands on the host."
        )
        raise typer.Exit(1)

    if dry_run and bg:
        rprint("[red]Error:[/red] --dry-run and --bg cannot be combined.")
        raise typer.Exit(1)

    if resume and rerun:
        rprint("[red]Error:[/red] --resume and --rerun are mutually exclusive.")
        raise typer.Exit(1)
    if fresh and not rerun:
        rprint(
            "[red]Error:[/red] --fresh only applies together with --rerun "
            "(it bypasses cache reads for the new execution)."
        )
        raise typer.Exit(1)
    continue_verb = "resume" if resume else ("rerun" if rerun else None)

    selected_target, selected_scheduler, is_local = _select_backend(
        target_path=target.path,
        local=local,
        scheduler=scheduler,
        target_cli=target_cli,
    )

    profile_cfg = _resolve_profile(config, profile)
    profile_cfg = _apply_overrides(profile_cfg, overrides or [])

    if bg:
        if not is_local:
            rprint("[red]Error:[/red] --bg is only supported for local execution.")
            raise typer.Exit(1)
        _spawn_background_local_run(
            script=script,
            target_path=Path(target.path),
            config=config,
            profile=profile,
            overrides=overrides or [],
            resume=resume,
            rerun=rerun,
            fresh=fresh,
        )
        return

    if dry_run:
        _run_dry_run(
            script=script,
            profile_cfg=profile_cfg,
            continue_verb=continue_verb,
            target_path=target.path,
            explicit_ws=explicit_ws,
        )
        return

    if is_local:
        _run_local_inprocess(
            script=script,
            profile_cfg=profile_cfg,
            continue_verb=continue_verb,
            target_path=target.path,
            explicit_ws=explicit_ws,
            fresh=fresh,
        )
        return

    selected_queue = partition if partition is not None else queue
    _submit_to_scheduler(
        script=script,
        profile_cfg=profile_cfg,
        continue_verb=continue_verb,
        target_path=target.path,
        explicit_ws=explicit_ws,
        selected_target=selected_target,
        selected_scheduler=selected_scheduler,
        cluster=cluster,
        resources={"cpus": cpus, "mem": mem, "gpus": gpus, "gpu_type": gpu_type, "time": time},
        scheduling={"queue": selected_queue, "account": account, "qos": qos},
        block=block,
        fresh=fresh,
        worker_python=worker_python,
        preamble=preamble or [],
    )


@app.command(name="exec")
def exec_cmd(
    command: Annotated[
        list[str] | None, typer.Argument(help="Command to execute on the target")
    ] = None,
    cwd: Annotated[
        str | None, typer.Option("--cwd", help="Working directory on the target")
    ] = None,
    timeout: Annotated[float | None, typer.Option("--timeout", help="Timeout in seconds")] = None,
    target_spec: TargetOption = ".",
) -> None:
    """Execute a command on the workspace target (local or remote transport)."""
    target, transport, _fs = resolve_workspace_target(target_spec)

    cmd: list[str] = list(command) if command else []
    if not cmd:
        rprint("[red]Error:[/red] No command provided.")
        raise typer.Exit(1)

    if isinstance(target, RemoteTarget):
        remote_cwd = cwd or target.path
    else:
        remote_cwd = cwd or str(target.path)

    rprint(f"[dim]{'[' + str(target) + ']'} {' '.join(cmd)}[/dim]")
    try:
        result = transport.run(cmd, cwd=remote_cwd, timeout=timeout)
    except Exception as exc:
        rprint(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1) from exc

    if result.stdout:
        rprint(result.stdout, end="")
    if result.stderr:
        from rich import print as _rprint

        _rprint(f"[yellow]{result.stderr}[/yellow]", end="")
    if result.returncode != 0:
        raise typer.Exit(result.returncode)


@app.command()
def shell(target_spec: TargetOption = ".") -> None:
    """Open an interactive shell on the target (SSH for remote, $SHELL for local)."""
    target, _transport, _fs = resolve_workspace_target(target_spec)

    if isinstance(target, RemoteTarget):
        import subprocess

        if not target.host:
            rprint("[red]Error:[/red] remote target has no host to ssh into")
            raise typer.Exit(1)
        user_host = f"{target.user}@{target.host}" if target.user else target.host
        ssh_cmd = ["ssh", "-t", user_host, f"cd {target.path} && exec ${{SHELL:-bash}}"]
        if target.port:
            ssh_cmd.insert(1, "-p")
            ssh_cmd.insert(2, str(target.port))
        rprint(f"[dim]Opening shell to {user_host}...[/dim]")
        subprocess.run(ssh_cmd)
    else:
        import subprocess

        shell_bin = os.environ.get("SHELL", "bash")
        rprint(f"[dim]Opening shell in {target.path}...[/dim]")
        subprocess.run([shell_bin], cwd=str(target.path))
