"""``molab scratch clean`` — empty old entries of experiment ``scratch/`` dirs (D90).

``scratch/`` holds quick tests only, so it is emptied by age. The clean is a
plan/apply pair (:mod:`molab.workspace.scratch`): the plan lists what would go,
``--dry-run`` stops there, and apply removes exactly the planned entries.
"""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Annotated

import typer

from molab.cli._common import rprint
from molab.cli._target import TargetOption, open_workspace

scratch_app = typer.Typer(help="Experiment scratch: quick tests only", no_args_is_help=True)

_DURATION = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([smhdw]?)\s*$")
_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800, "": 86400}


def parse_age(text: str) -> timedelta:
    """``7d`` / ``12h`` / ``30m`` / ``2w`` / ``90s``; a bare number is days.

    Raises:
        ValueError: *text* is not such a duration.
    """
    match = _DURATION.match(text)
    if match is None:
        raise ValueError(f"not a duration: {text!r} (use e.g. 7d, 12h, 30m, 2w)")
    return timedelta(seconds=float(match.group(1)) * _UNITS[match.group(2)])


@scratch_app.command("clean")
def scratch_clean(
    older_than: Annotated[
        str, typer.Option("--older-than", help="Age past which an entry goes (7d, 12h, 2w).")
    ] = "7d",
    project: Annotated[
        str | None, typer.Option("--project", "-p", help="Only this project.")
    ] = None,
    experiment: Annotated[
        str | None, typer.Option("--experiment", "-e", help="Only this experiment (needs -p).")
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="List what would go; delete nothing.")
    ] = False,
    target_spec: TargetOption = ".",
) -> None:
    """Delete top-level scratch entries untouched for longer than --older-than."""
    from molab.workspace.scratch import apply_scratch_clean, plan_scratch_clean

    try:
        age = parse_age(older_than)
    except ValueError as exc:
        rprint(f"[red]Error:[/red] {exc}")
        raise typer.Exit(2) from None
    if experiment is not None and project is None:
        rprint("[red]Error:[/red] --experiment needs --project")
        raise typer.Exit(2)
    _target, _fs, ws = open_workspace(target_spec)
    experiments = None
    try:
        if project is not None:
            owner = ws.get_project(project)
            experiments = (
                [owner.get_experiment(experiment)]
                if experiment is not None
                else owner.list_experiments()
            )
    except Exception as exc:
        rprint(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1) from None
    plan = plan_scratch_clean(ws, older_than=age, experiments=experiments)
    if not plan.entries:
        rprint("[dim]No scratch entries older than the cutoff.[/dim]")
        return
    for entry in plan.entries:
        print(f"{entry.modified_at:%Y-%m-%d %H:%M}\t{entry.path}")
    if dry_run:
        rprint(f"[yellow]dry run[/yellow]: {len(plan.entries)} entr(y/ies) would be removed")
        return
    removed = apply_scratch_clean(ws, plan)
    rprint(f"[green]OK[/green] removed {removed} scratch entr(y/ies)")
