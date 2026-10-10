"""``molab explore`` — interactive workspace explorer (TUI)."""

from __future__ import annotations

from typing import Annotated

import typer

from molab.cli._app import app
from molab.cli._common import rprint
from molab.cli._target import TargetOption, open_workspace


@app.command()
def explore(
    project: Annotated[
        str | None,
        typer.Option("--project", "-p", help="Filter by project name or ID."),
    ] = None,
    experiment: Annotated[
        str | None,
        typer.Option("--experiment", "-e", help="Filter by experiment name or ID."),
    ] = None,
    refresh: Annotated[
        float,
        typer.Option("--refresh", "-r", help="Refresh interval in seconds."),
    ] = 2.0,
    target_spec: TargetOption = ".",
) -> None:
    """Open the full-screen workspace explorer.

    Navigate with arrows / Enter to expand, Space to select,
    a/A to select all/clear, d to open delete confirmation.

    Works for local and remote (``-ws host:/path``) workspaces — tree data
    is loaded through the target FileSystem.
    """
    try:
        _target, _transport, _fs, ws = open_workspace(target_spec, prefetch=True)
    except FileNotFoundError as exc:
        rprint(f"[red]Error:[/red] {exc}")
        rprint("  Run [bold]molab init[/bold] to create one.")
        raise typer.Exit(1) from exc

    from molab.cli.tui import TreeMonitor

    monitor = TreeMonitor(
        project_filter=project,
        experiment_filter=experiment,
        refresh_interval=refresh,
    )
    warnings = monitor.watch(ws)

    rprint("\n[dim]Explorer closed.[/dim]")
    for msg in warnings:
        rprint(f"[yellow]warning:[/yellow] {msg}")
