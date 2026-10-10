"""``molab init`` — ergonomic top-level shortcut for workspace initialization.

The canonical command is ``molab workspace <TARGET> init``, but the
single-arg ``molab init [PATH]`` form is so common we expose it at the
top level too.  Both paths converge on ``Workspace(path, name=...)``.

Behavior:
- ``molab init <path>`` — create or refresh the workspace at *path*
- ``molab init host:/remote/path`` — same, over SSH transport
- ``molab init`` — same, on the current working directory
- Idempotent: re-running on an existing workspace leaves child state
  (e.g. ``projects/``) intact and only refreshes ``workspace.json``.
- A ``Workspace`` handle writes nothing on its own, so init materializes it
  (``workspace.json``, id minted once) and, on a local disk, starts the git
  history with its ignore rules.
"""

from __future__ import annotations

from typing import Annotated

import typer

from molab.cli._common import rprint


def init(
    path: Annotated[
        str | None,
        typer.Argument(
            help="Workspace path (local path, host:/path, or user@host:/path; default: cwd)"
        ),
    ] = None,
    name: Annotated[
        str | None,
        typer.Option("--name", "-n", help="Workspace name (derived from path if omitted)"),
    ] = None,
) -> None:
    """Initialize (or refresh) a workspace at PATH (defaults to current dir)."""
    from molab.cli._target import open_workspace
    from molab.workspace.fs_local import LocalFileSystem
    from molab.workspace.history import GitHistory

    spec = path if path is not None else "."
    rprint(f"[bold]Initializing workspace at:[/bold] {spec}")
    try:
        _target, _transport, _fs, ws = open_workspace(spec, require_existing=False, name=name)
        ws.materialize()
        if isinstance(ws.fs, LocalFileSystem):
            GitHistory(ws.root).init()
    except Exception as exc:
        rprint(f"[red]Failed to initialize workspace:[/red] {exc}")
        raise typer.Exit(1) from exc

    rprint(f"[green]OK[/green] Workspace ready: {ws.root}")
    rprint("\n[bold]Next steps:[/bold]")
    rprint("  • Write a script ending in ws.add_project(...).add_experiment(...)")
    rprint("    .define(workflow, params=...), then: [bold]molab run script.py[/bold]")
    rprint("  • Or open the web UI: [bold]molab serve[/bold]")
