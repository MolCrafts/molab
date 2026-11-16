"""``molab runs prune`` — interactive hierarchical cleanup.

Walks project → experiment → run → execution step-by-step, letting the user
pick which executions (attempts at a run) to prune. Once the run is chosen,
its zombie attempts are reaped before the attempts are listed. A zombie is an
attempt still recorded as ``running`` after its owning process has died, and
reaping seals it as ``failed``. Pruning removes bulk directories only
(``out/``, ``work/``, ``jobs/``, ``checkpoints/``) and keeps every execution
record: ``execution.json`` and the ``executions/<id>/`` directory itself stay.
The selection UI lives here. The pruning itself goes through the two-phase
core (:func:`molab.workspace.prune.plan_execution_prune` →
:func:`~molab.workspace.prune.apply_execution_prune`). ``POST …/runs/{id}/prune``
calls those same two functions.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from molab.workspace.run import Run

from ._common import console, reap_zombie_run, rprint, status_color


def _select_one(
    title: str,
    rows: Sequence[tuple[str, ...]],
    headers: tuple[str, ...],
) -> int | None:
    """Render a numbered table and prompt for a single choice.

    Returns the zero-based index of the chosen row, or ``None`` if the
    user aborted with empty input.
    """
    if not rows:
        rprint(f"[yellow]{title}: nothing to select.[/yellow]")
        return None

    table = Table(title=title)
    table.add_column("#", style="cyan", justify="right")
    for h in headers:
        table.add_column(h)
    for idx, row in enumerate(rows, start=1):
        table.add_row(str(idx), *row)
    console.print(table)

    raw = typer.prompt("Enter # (empty to abort)", default="", show_default=False)
    raw = raw.strip()
    if not raw:
        return None
    if not raw.isdigit() or not (1 <= int(raw) <= len(rows)):
        rprint(f"[red]Invalid choice:[/red] {raw!r}")
        return None
    return int(raw) - 1


def _select_many(
    title: str,
    rows: Sequence[tuple[str, ...]],
    headers: tuple[str, ...],
    *,
    status_values: Sequence[str] | None = None,
) -> list[int]:
    """Multi-select prompt.

    Accepts comma-separated numbers, ranges ``a-b``, ``all``, or
    status keywords (``failed``/``cancelled``/...) matched against
    ``status_values`` — plain, un-coloured status strings the caller
    supplies alongside the rendered rows.  Returns zero-based indices.
    """
    if not rows:
        rprint(f"[yellow]{title}: nothing to select.[/yellow]")
        return []

    table = Table(title=title)
    table.add_column("#", style="cyan", justify="right")
    for h in headers:
        table.add_column(h)
    for idx, row in enumerate(rows, start=1):
        table.add_row(str(idx), *row)
    console.print(table)

    rprint("[dim]Formats: 1,3,5  |  2-4  |  all  |  failed,cancelled[/dim]")
    raw = typer.prompt(
        "Select executions to prune (empty to abort)",
        default="",
        show_default=False,
    )
    raw = raw.strip().lower()
    if not raw:
        return []

    if raw == "all":
        return list(range(len(rows)))

    keyword_map = {"failed", "cancelled", "running", "succeeded", "pending"}
    tokens = [t.strip() for t in raw.split(",") if t.strip()]
    if status_values and tokens and all(t in keyword_map for t in tokens):
        return [i for i, sv in enumerate(status_values) if sv.lower() in tokens]

    chosen: set[int] = set()
    for tok in tokens:
        if "-" in tok:
            a, _, b = tok.partition("-")
            if a.isdigit() and b.isdigit():
                lo, hi = int(a), int(b)
                if lo > hi:
                    lo, hi = hi, lo
                chosen.update(range(lo - 1, hi))
                continue
        if tok.isdigit() and 1 <= int(tok) <= len(rows):
            chosen.add(int(tok) - 1)
            continue
        rprint(f"[red]Ignoring invalid token:[/red] {tok!r}")

    return sorted(i for i in chosen if 0 <= i < len(rows))


def _execution_rows(run: Run) -> list[tuple[str, ...]]:
    rows: list[tuple[str, ...]] = []
    for rec in run.executions:
        finished = rec.finished_at.strftime("%Y-%m-%d %H:%M") if rec.finished_at else "—"
        started = rec.started_at.strftime("%Y-%m-%d %H:%M") if rec.started_at else "—"
        status = rec.status or "running"
        rows.append(
            (
                rec.id,
                status,
                started,
                finished,
            )
        )
    return rows


def prune_runs(
    path: Annotated[
        Path | None,
        typer.Option("--path", "-p", help="Workspace path (default: cwd)."),
    ] = None,
    superseded: Annotated[
        bool,
        typer.Option(
            "--superseded",
            help=(
                "Non-interactive: in every run, delete each attempt but the newest, with "
                "its record, logs and the assets only it registered. One commit per run."
            ),
        ),
    ] = False,
    failed: Annotated[
        bool,
        typer.Option(
            "--failed",
            help=(
                "Non-interactive: in every run, delete each attempt that did not succeed, "
                "with its record, logs and the assets only it registered. Every succeeded "
                "attempt and what it was seeded from stay; a run with no success keeps its "
                "newest attempt. One commit per run."
            ),
        ),
    ] = False,
    scratch: Annotated[
        bool,
        typer.Option(
            "--scratch",
            help=(
                "Non-interactive: bring home what each run left on a remote target (a failed "
                "attempt's out/ and work/), delete the run's staged namespace there, and "
                "empty every experiment's scratch/."
            ),
        ),
    ] = False,
    env: Annotated[
        bool,
        typer.Option(
            "--env",
            help=(
                "Non-interactive: delete the environment directories in the workspace "
                "(.venv, .venv-*, __pycache__ and tool caches); the experiment stays."
            ),
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            "-n",
            help="With a sweep (--superseded, --failed, --scratch, --env): list, delete nothing.",
        ),
    ] = False,
) -> None:
    """Interactively prune bulk directories of a run's executions; records are kept.

    With a sweep flag the walk is replaced by sweeps of the whole workspace,
    run in this order: ``--superseded`` or ``--failed`` (every run keeps only
    its newest attempt, or only its succeeded ones), ``--scratch`` (nothing of
    a run stays on a remote target, experiment ``scratch/`` is emptied) and
    ``--env`` (environment directories go). ``--dry-run`` lists them without
    deleting.

    Descends project → experiment → run → executions, letting the user
    pick at each step. After the run is picked, its zombie attempts are
    reaped: an attempt still ``running`` after its owner process died is
    sealed as ``failed``. The attempts are listed only after that. The
    plan step refuses any attempt that is not sealed, and it exits with
    code 1 when it does. After a ``y`` confirmation, only the prunable bulk
    directories of the selected executions are removed: ``out/``,
    ``work/``, ``jobs/`` and ``checkpoints/``, which include solver logs and
    scheduler stdout/stderr. The records are kept. That means
    ``execution.json``, the node journal ``workflow.json``, ``run.log`` and
    ``metrics.mlp.jsonl``. A registered asset lives outside the attempt.
    Each pruned record is stamped ``pruned_at`` /
    ``pruned_dirs``.
    """
    from . import _common

    if superseded and failed:
        rprint("[red]--failed and --superseded are exclusive: pick one sweep.[/red]")
        raise typer.Exit(2)
    if dry_run and not (superseded or failed or scratch or env):
        rprint(
            "[red]--dry-run lists a sweep: add --superseded, --failed, --scratch or --env.[/red]"
        )
        raise typer.Exit(2)
    ws = _common.get_workspace(path)
    if superseded or failed or scratch or env:
        refused = 0
        if superseded or failed:
            refused += _sweep(ws, failed=failed, dry_run=dry_run)
        if scratch:
            refused += _sweep_scratch(ws, dry_run=dry_run)
        if env:
            _sweep_env(ws, dry_run=dry_run)
        if refused:
            raise typer.Exit(1)
        return

    # Layer 1: project
    projects = ws.list_projects()
    if not projects:
        rprint("[yellow]Workspace has no projects.[/yellow]")
        raise typer.Exit(0)
    proj_rows = [(p.id, p.metadata.name, f"{len(p.list_experiments())} exp") for p in projects]
    i = _select_one("Projects", proj_rows, ("ID", "Name", "Exp count"))
    if i is None:
        rprint("[dim]Aborted.[/dim]")
        raise typer.Exit(0)
    project = projects[i]

    # Layer 2: experiment
    experiments = project.list_experiments()
    if not experiments:
        rprint(f"[yellow]Project {project.id!r} has no experiments.[/yellow]")
        raise typer.Exit(0)
    exp_rows = [(e.id, e.metadata.name, f"{len(e.list_runs())} runs") for e in experiments]
    i = _select_one(
        f"Experiments in {project.id!r}",
        exp_rows,
        ("ID", "Name", "Run count"),
    )
    if i is None:
        rprint("[dim]Aborted.[/dim]")
        raise typer.Exit(0)
    experiment = experiments[i]

    # Layer 3: run
    runs = experiment.list_runs()
    if not runs:
        rprint(f"[yellow]Experiment {experiment.id!r} has no runs.[/yellow]")
        raise typer.Exit(0)

    run_rows: list[tuple[str, ...]] = []
    for r in runs:
        status = r.status_label
        n_exec = len(r.executions)
        run_rows.append(
            (
                r.id,
                status,
                str(n_exec),
                r.metadata.created_at.strftime("%Y-%m-%d %H:%M"),
            )
        )
    i = _select_one(
        f"Runs in {project.id}/{experiment.id}",
        run_rows,
        ("Run ID", "Status", "# exec", "Created"),
    )
    if i is None:
        rprint("[dim]Aborted.[/dim]")
        raise typer.Exit(0)
    run = runs[i]
    # The prune core refuses any active record, so a dead owner's stale
    # ``running`` Execution must be reaped before listing — callers reap first.
    reap_zombie_run(run)

    # Layer 4: execution records
    rows = _execution_rows(run)
    if not rows:
        rprint(f"[yellow]Run {run.id!r} has no execution history.[/yellow]")
        raise typer.Exit(0)

    colored = [
        (
            rec_id,
            f"[{status_color(status)}]{status}[/{status_color(status)}]",
            started,
            finished,
        )
        for rec_id, status, started, finished in rows
    ]
    indices = _select_many(
        f"Executions of {run.id}",
        colored,
        ("Execution ID", "Status", "Started", "Finished"),
        status_values=[status for _, status, _, _ in rows],
    )
    if not indices:
        rprint("[dim]Nothing selected — aborted.[/dim]")
        raise typer.Exit(0)

    # Two-phase core: plan (where the live-record refusal lives) → confirm → apply.
    from molab.workspace import LivePruneRefusedError
    from molab.workspace.prune import apply_execution_prune, plan_execution_prune

    history = run.executions
    selected_ids = [history[i].id for i in indices]
    try:
        plan = plan_execution_prune(run, execution_ids=selected_ids)
    except LivePruneRefusedError as exc:
        rprint(f"[red]Refusing:[/red] {exc}")
        raise typer.Exit(1) from exc

    confirm = typer.prompt(
        f"Prune bulk of {len(plan.entries)} execution(s) from run {run.id!r}? "
        "Records are kept. [y/N]",
        default="N",
        show_default=False,
    )
    if confirm.strip().lower() not in ("y", "yes"):
        rprint("[dim]Aborted.[/dim]")
        raise typer.Exit(0)

    for entry in plan.entries:
        if not entry.dirs:
            rprint(f"  [dim]skip[/dim]  {entry.execution_id} (no bulk directories)")
        for name in entry.dirs:
            rprint(f"  [green]OK[/green] removed executions/{entry.execution_id}/{name}")
    removed_dirs = apply_execution_prune(run, plan)

    remaining = len(run.executions)
    rprint(
        f"[green]Done.[/green] Removed {removed_dirs} dir(s) from "
        f"{len(plan.entries)} execution(s); records are kept. "
        f"{remaining} record(s) remain."
    )


def _sweep(ws: object, *, failed: bool, dry_run: bool) -> int:
    """One pass over every run: discard (or, dry, list) what the sweep does not keep.

    Returns:
        How many runs were refused because an attempt is still active.
    """
    from molab.workspace import LivePruneRefusedError
    from molab.workspace.prune import (
        discard_failed_attempts,
        discard_superseded_attempts,
        plan_failed_discard,
        plan_superseded_discard,
    )

    refused = 0
    total = 0
    for project in ws.list_projects():  # ty: ignore[unresolved-attribute]
        for experiment in project.list_experiments():
            for run in experiment.list_runs():
                label = f"{experiment.metadata.name}/{run.path.name}"
                try:
                    if dry_run:
                        dropped = (plan_failed_discard if failed else plan_superseded_discard)(run)
                    elif failed:
                        dropped = discard_failed_attempts(run)
                    else:
                        dropped = discard_superseded_attempts(run)
                except LivePruneRefusedError as exc:
                    refused += 1
                    rprint(f"  [yellow]skip[/yellow]  {label}: {exc}")
                    continue
                if dropped:
                    total += len(dropped)
                    verb = "would discard" if dry_run else "discarded"
                    rprint(f"  [green]OK[/green] {label}: {verb} {', '.join(dropped)}")
    verb = "Would discard" if dry_run else "Discarded"
    rprint(f"{verb} {total} attempt(s).")
    return refused


def _sweep_scratch(ws: object, *, dry_run: bool) -> int:
    """Bring each run home from its remote target, release it there, empty experiment scratch.

    Returns:
        How many runs were refused: an attempt is active, or the target failed.
    """
    from datetime import timedelta

    from molq import MolqError

    from molab.plugins.submit_molq.staging import bring_home_staged_run, staged_target
    from molab.workspace.domain import ACTIVE_EXECUTION_STATUSES
    from molab.workspace.scratch import apply_scratch_clean, plan_scratch_clean

    refused = 0
    released = 0
    for project in ws.list_projects():  # ty: ignore[unresolved-attribute]
        for experiment in project.list_experiments():
            for run in experiment.list_runs():
                executions = run.executions
                if not any(staged_target(item.executor) for item in executions):
                    continue
                label = f"{experiment.metadata.name}/{run.path.name}"
                if any(item.status in ACTIVE_EXECUTION_STATUSES for item in executions):
                    refused += 1
                    rprint(f"  [yellow]skip[/yellow]  {label}: an attempt is still active")
                    continue
                if dry_run:
                    rprint(f"  [green]OK[/green] {label}: would bring home and release")
                    continue
                try:
                    if bring_home_staged_run(run):
                        released += 1
                        rprint(f"  [green]OK[/green] {label}: brought home and released")
                except (MolqError, OSError, ValueError) as exc:
                    refused += 1
                    rprint(f"  [yellow]skip[/yellow]  {label}: {exc}")
    if not dry_run:
        rprint(f"Released {released} run namespace(s) on remote targets.")
    plan = plan_scratch_clean(ws, older_than=timedelta(0))  # ty: ignore[invalid-argument-type]
    if dry_run:
        for entry in plan.entries:
            rprint(f"  would remove {entry.path}")
        return refused
    removed = apply_scratch_clean(ws, plan)  # ty: ignore[invalid-argument-type]
    rprint(f"Removed {removed} scratch entr{'y' if removed == 1 else 'ies'}.")
    return refused


def _sweep_env(ws: object, *, dry_run: bool) -> None:
    """Delete (or, dry, list) the environment directories of the workspace."""
    from molab.workspace.env_clean import apply_env_clean, plan_env_clean

    plan = plan_env_clean(ws)  # ty: ignore[invalid-argument-type]
    if dry_run:
        for rel in plan:
            rprint(f"  would remove {rel}")
        return
    removed = apply_env_clean(ws, plan)  # ty: ignore[invalid-argument-type]
    rprint(f"Removed {removed} environment director{'y' if removed == 1 else 'ies'}.")


def register(run_app: typer.Typer) -> None:
    run_app.command("prune")(prune_runs)
