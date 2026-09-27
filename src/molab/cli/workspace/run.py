"""``molab {run,exec,shell}`` — execution commands."""

from __future__ import annotations

import os
import subprocess
import sys
import traceback
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, NamedTuple, Protocol, cast

import typer
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from molab._typing import JSONValue, TaskOutput
from molab.cli._app import app
from molab.cli._common import console, deterministic_run_id, reap_zombie_run, rprint
from molab.cli._target import TargetOption, resolve_workspace_target
from molab.profile import MolCfg, ProfileConfig, load_molcfg
from molab.profile.loader import find_default_config
from molab.workflow import default_binding_registry
from molab.workspace.domain import ExecutionMode, ExecutionStatus
from molab.workspace.execution_context import profile_config_hash
from molab.workspace.run import RunStatus
from molab.workspace.source_snapshot import SourceCaptureError
from molab.workspace.target import LocalTarget, RemoteTarget

if TYPE_CHECKING:
    from molab.workflow.protocols import RunContextLike
    from molab.workspace.experiment import Experiment
    from molab.workspace.models import ComputeTarget
    from molab.workspace.project import Project
    from molab.workspace.run import Run
    from molab.workspace.workspace import Workspace


class RunHandler(Protocol):
    """Dispatch one selected run: execute it in-process or submit it.

    The dispatcher creates the run's QUEUED Execution record immediately
    before the call and hands its id as *execution_id* (``None`` only for
    ``--resume``, whose reopen path still picks its own attempt). The molq
    ``SubmitHandler`` satisfies this structurally.
    """

    def __call__(
        self,
        script: Path,
        mol_run: Run,
        experiment: Experiment,
        project: Project,
        /,
        *,
        execution_id: str | None,
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
                f"  [yellow]![/yellow] {exp.id}  run={mol_run.id} (stale 'running' run reaped -> failed)"
            )
        if continue_verb is not None:
            # resume / rerun own exactly the finished-but-not-succeeded runs
            # (failed / cancelled / interrupted). pending is plain run's job,
            # succeeded is done, and a live running run must never get a
            # second execution — all skipped, which keeps the three verbs
            # orthogonal. The retryable domain is the shared workspace policy.
            if mol_run is None:
                rprint(f"  [dim]- {exp.id}  seed={seed_label} (no existing run, skipped)[/dim]")
                continue
            if not mol_run.is_retryable:
                rprint(
                    f"  [dim]- {exp.id}  run={mol_run.id} ({status}, skipped — "
                    f"{continue_verb} only retries failed/cancelled runs)[/dim]"
                )
                continue
        elif mol_run is not None:
            # plain run: run only what has not run yet (pending).
            # Leave succeeded / running / failed / cancelled alone —
            # retrying a failure is an explicit --resume / --rerun.
            if not mol_run.status_summary.not_started:
                rprint(
                    f"  [dim]- {exp.id}  run={mol_run.id} ({status}, skipped — "
                    "use --resume or --rerun to retry)[/dim]"
                )
                continue
        else:
            mol_run = exp.ensure_run(run_params, config_hash=config_hash)
        label_text = f"seed={seed_label}" if seed_label is not None else f"run={mol_run.id}"
        selected_runs.append((mol_run, label_text))
        icon = "[cyan]>[/cyan]" if continue_verb is not None else "[dim]o[/dim]"
        rprint(f"  {icon} {exp.id}  {label_text}")
    return selected_runs


def _create_dispatch_execution(
    mol_run: Run,
    *,
    continue_verb: str | None,
    fresh: bool,
    profile_cfg: ProfileConfig,
    script: Path,
    submit_cwd: str,
) -> str | None:
    """Create the QUEUED Execution record one dispatched run will start.

    The only place ``molab run`` creates a record. A plain run opens an
    ``initial`` attempt (only not-started runs are selected); ``--rerun``
    opens a ``rerun`` attempt based on the run's latest, terminal one.
    ``--resume`` creates nothing: its handler still reopens the last attempt
    itself (arch-own-03 replaces that).

    Args:
        mol_run: The run about to be dispatched.
        continue_verb: ``None`` (plain run), ``"resume"`` or ``"rerun"``.
        fresh: Record that the attempt bypasses the workflow node cache.
        profile_cfg: The profile the attempt runs under; recorded as its
            ``profile`` / ``config`` / ``config_hash``.
        script: The defining script; recorded as ``environment.script`` and
            captured as the attempt's source entrypoint.
        submit_cwd: The directory ``molab run`` was invoked from.

    Returns:
        The new attempt's id (``e01``, ``e02``, …), or ``None`` for
        ``--resume``.

    Raises:
        typer.Exit: The script's source could not be captured (the attempt
            is sealed FAILED by the workspace and the batch stops).
    """
    if continue_verb == "resume":
        return None
    if continue_verb == "rerun":
        mode = ExecutionMode.RERUN
        based_on: str | None = mol_run.executions[-1].id
    else:
        mode = ExecutionMode.INITIAL
        based_on = None
    entrypoint = script.resolve()
    try:
        record = mol_run.create_execution(
            mode=mode,
            based_on_execution_id=based_on,
            bypass_cache=fresh,
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
    the runs it never reached.

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

    def _dispatch_one(mol_run: Run, exp: Experiment, project: Project) -> None:
        execution_id = _create_dispatch_execution(
            mol_run,
            continue_verb=continue_verb,
            fresh=fresh,
            profile_cfg=profile_cfg,
            script=script,
            submit_cwd=submit_cwd,
        )
        run_handler(script, mol_run, exp, project, execution_id=execution_id)

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
                _dispatch_one(mol_run, exp, project)
                dispatched_runs.append(mol_run)
                progress.advance(task_id)
    else:
        for mol_run, exp, project in all_replicas:
            _dispatch_one(mol_run, exp, project)
            dispatched_runs.append(mol_run)
            rprint(f"  [cyan]>[/cyan] dispatched {exp.id}  run={mol_run.id}")
    return dispatched_runs


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

    Returns:
        ``(number of selected runs, runs dispatched or selected)``.
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
    if not suppress_ok:
        verb = {"resume": "resumed", "rerun": "reran"}.get(continue_verb or "", "completed")
        rprint(f"\n[green]OK[/green] {total_dispatched} runs {verb}.")
    return total_dispatched, dispatched_runs


async def _execute_compiled(
    spec: object,
    *,
    run_context: RunContextLike,
    execution_id: str | None = None,
    seed_outputs: Mapping[str, TaskOutput] | None = None,
    bypass_cache: bool = False,
) -> object:
    """Execute a compiled workflow on the workflow layer's own runtime.

    No plugin host is involved: the only load-bearing effect a host profile
    contributed on this path was the mlp metrics writer, and ``import molab``
    already wires that onto :mod:`molab.workspace.metrics_seam`.
    """
    from molab.workflow import WorkflowRuntime
    from molab.workflow.compiled import CompiledWorkflow

    if not isinstance(spec, CompiledWorkflow):
        raise TypeError("spec must be a CompiledWorkflow")
    return await WorkflowRuntime().execute(
        spec,
        run_context=run_context,
        execution_id=execution_id,
        seed_outputs=seed_outputs,
        bypass_cache=bypass_cache,
    )


def _make_local_inprocess_handler(
    profile_cfg: ProfileConfig, *, verb: str | None = None
) -> RunHandler:
    """Build the handler that executes one run in this process.

    The handler starts the QUEUED record the dispatcher created; whether the
    node cache is bypassed is read back from that record
    (``ctx.bypass_cache``), never passed alongside it. ``--resume`` still
    reopens the run's last attempt and seeds its completed nodes
    (arch-own-03 replaces that path).

    Args:
        profile_cfg: The profile the attempts run under.
        verb: ``None`` (plain run), ``"resume"`` or ``"rerun"``.

    Returns:
        A :class:`RunHandler`.
    """
    import asyncio

    from molab.workflow._engine.persistence import seed_from_execution
    from molab.workspace.run import RunContext

    def _handler(
        _script: Path,
        mol_run: Run,
        experiment: Experiment,
        _project: Project,
        /,
        *,
        execution_id: str | None,
    ) -> None:
        spec = default_binding_registry.for_experiment(experiment)
        if spec is None:
            raise RuntimeError(f"Experiment {experiment.name!r} has no workflow attached.")
        seed_outputs = None
        if verb == "resume":
            # Reopen the last failed/interrupted execution and seed its
            # completed nodes; the no-fallback semantics live with the
            # workflow layer (see ``seed_from_execution``).
            execution_id, seed_outputs = seed_from_execution(mol_run)
        with RunContext(
            mol_run,
            profile_config=profile_cfg,
            execution_id=execution_id,
        ) as ctx:
            asyncio.run(
                _execute_compiled(
                    spec,
                    run_context=cast("RunContextLike", ctx),
                    execution_id=execution_id,
                    seed_outputs=seed_outputs,
                    bypass_cache=ctx.bypass_cache,
                )
            )

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
    the QUEUED record the submitter created. The workflow comes only from
    :func:`molab.workflow.compiled_workflow_for_run` (the record's
    ``environment.script`` is provenance, never imported); the config, the
    profile and ``bypass_cache`` come from the record. ``--config`` /
    ``--profile`` are refused, because the config that runs is the recorded
    one.

    Args:
        run_dir: The run's directory.
        execution_id: The QUEUED attempt to start.
        config: Refused when given.
        profile: Refused when given.

    Raises:
        typer.Exit: Exit code 1 when the run or the attempt cannot be found,
            an override is given, the workflow cannot be recovered, or the
            attempt does not succeed.
    """
    import asyncio

    from molab.workflow import WorkflowRecoveryError, compiled_workflow_for_run
    from molab.workflow._engine.persistence import read_node_outputs
    from molab.workspace.run import RunContext

    run_obj, experiment = _open_run(Path(run_dir))
    try:
        record = run_obj.execution(execution_id)
    except KeyError as exc:
        rprint(
            f"[red]Error:[/red] run {run_obj.id} has no execution {execution_id!r}; "
            "the submitter must create it first with Run.create_execution."
        )
        raise typer.Exit(1) from exc
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

    environment = record.environment
    recorded_config = environment.get("config")
    recorded_profile = environment.get("profile")
    profile_cfg = ProfileConfig(
        dict(recorded_config) if isinstance(recorded_config, dict) else {},
        name=recorded_profile if isinstance(recorded_profile, str) else None,
    )

    seed_outputs = read_node_outputs(run_obj.run_dir, execution_id)
    rprint(f"[dim]execute[/dim] run={run_obj.id} execution={execution_id}")
    with RunContext(run_obj, profile_config=profile_cfg, execution_id=execution_id) as ctx:
        asyncio.run(
            _execute_compiled(
                spec,
                run_context=cast("RunContextLike", ctx),
                execution_id=execution_id,
                seed_outputs=seed_outputs,
                bypass_cache=ctx.bypass_cache,
            )
        )
    # Judge this attempt, not the run: ``Run.status_label`` is the *latest*
    # attempt's status, and ``execution_id`` need not be the latest — a sibling
    # attempt may have been dispatched after it. The exit code must describe
    # the attempt this worker ran.
    status = run_obj.execution(execution_id).status
    if status is not ExecutionStatus.SUCCEEDED:
        # The scheduler reads this exit code to mark the job failed; a failed run
        # reported as success would strand the whole pipeline.
        rprint(f"[red]FAILED[/red] execute run={run_obj.id} status={status.value}")
        raise typer.Exit(1)
    rprint(f"[green]OK[/green] execute complete run={run_obj.id} status={status.value}")


def _open_run(run_dir: Path) -> tuple[Run, Experiment]:
    """Open the run stored at *run_dir* and its experiment.

    The workspace root is the nearest ancestor holding ``workspace.json``; the
    run id is the ``id`` in ``run.json``; the experiment is the one whose
    directory contains *run_dir*, found by walking the workspace tree. No
    directory name is parsed.

    Args:
        run_dir: The run's directory.

    Returns:
        ``(run, experiment)``.

    Raises:
        typer.Exit: Exit code 1 when there is no workspace above *run_dir*,
            ``run.json`` has no string ``id``, or no experiment of the
            workspace holds that run.
    """
    from molab._run_display import read_run_json
    from molab.workspace import RunNotFoundError, Workspace
    from molab.workspace.naming import workspace_root

    run_dir = Path(run_dir).resolve()
    root = workspace_root(run_dir)
    if root is None:
        rprint(f"[red]Error:[/red] no workspace.json above {run_dir}.")
        raise typer.Exit(1)
    run_id = read_run_json(run_dir).get("id")
    if not isinstance(run_id, str) or not run_id:
        rprint(f"[red]Error:[/red] run.json under {run_dir} has no run id.")
        raise typer.Exit(1)

    ws = Workspace.load(root)
    for project in ws.list_projects():
        for experiment in project.list_experiments():
            if not run_dir.is_relative_to(Path(experiment.path).resolve()):
                continue
            try:
                return experiment.get_run(run_id), experiment
            except RunNotFoundError:
                continue
    rprint(f"[red]Error:[/red] could not locate run {run_id} under {root}.")
    raise typer.Exit(1)


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


def _latest_error_txt(run: Run) -> str | None:
    """Path of the newest execution's ``error.txt``, if one was written."""
    try:
        exec_id = run.current_execution_id
        candidates = []
        if exec_id:
            candidates.append(Path(str(run.run_dir)) / "executions" / exec_id / "error.txt")
        executions_dir = Path(str(run.run_dir)) / "executions"
        if executions_dir.is_dir():
            candidates.extend(sorted(executions_dir.glob("*/error.txt"), reverse=True))
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)
    except Exception:  # a missing sidecar must never mask the failure report
        return None
    return None


def _report_local_results(
    dispatched: list[tuple[Run, str | None]], continue_verb: str | None
) -> None:
    """Print an honest terminal-status summary and set the process exit code.

    In-process execution settles each dispatched attempt to a terminal status
    synchronously, so an attempt that did not reach ``succeeded`` (``failed`` /
    ``cancelled``) must make ``molab run`` exit non-zero — scripts, CI steps,
    and schedulers read that exit code, and reporting "OK ... completed" over a
    failed run is a silent-failure trap. Only runs that actually executed are
    inspected (skipped runs never enter *dispatched*), and each is judged by
    the attempt this dispatch created — its own record, ``run.execution(eid)``
    — never by the run's other attempts. ``--resume`` creates no record
    (``eid`` is ``None``) and reopens the run's last attempt, so that is the
    one it is judged by.

    Args:
        dispatched: ``(run, execution_id)`` for each attempt this invocation
            executed; ``execution_id`` is ``None`` for ``--resume``.
        continue_verb: ``None`` (plain run), ``"resume"`` or ``"rerun"``.

    Raises:
        typer.Exit: Exit code 1 when any dispatched attempt did not succeed.
    """
    verb = {"resume": "resumed", "rerun": "reran"}.get(continue_verb or "", "completed")
    if not dispatched:
        rprint(f"\n[dim]No runs {verb}.[/dim]")
        return
    failed: list[tuple[Run, ExecutionStatus]] = []
    for mol_run, execution_id in dispatched:
        record = (
            mol_run.execution(execution_id) if execution_id is not None else mol_run.executions[-1]
        )
        if record.status is not ExecutionStatus.SUCCEEDED:
            failed.append((mol_run, record.status))
    if failed:
        rprint("")
        for mol_run, status in failed:
            rprint(f"  [red]x[/red] run={mol_run.id}  status={status.value}")
            error_txt = _latest_error_txt(mol_run)
            if error_txt is not None:
                rprint(f"    [dim]error: {error_txt}[/dim]")
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
    execute_one = _make_local_inprocess_handler(profile_cfg, verb=continue_verb)
    dispatched: list[tuple[Run, str | None]] = []

    def _collecting_handler(
        run_script: Path,
        mol_run: Run,
        experiment: Experiment,
        project: Project,
        /,
        *,
        execution_id: str | None,
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
                "Reopen each non-succeeded run's last execution and continue at "
                "workflow-node granularity (seed already-completed nodes from disk, "
                "recompute the rest). Mutually exclusive with --rerun."
            ),
        ),
    ] = False,
    rerun: Annotated[
        bool,
        typer.Option(
            "--rerun",
            help=(
                "Re-execute failed/cancelled runs in a new execution (no seed). "
                "Deterministic tasks may still be served from the content-addressed "
                "cache — add --fresh to bypass cache reads. Mutually exclusive with "
                "--resume."
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
