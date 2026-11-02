"""``molab init`` — ergonomic top-level shortcut for workspace initialization.

The canonical command is ``molab workspace <TARGET> init``, but the
single-arg ``molab init [PATH]`` form is so common we expose it at the
top level too.  Both paths converge on ``Workspace(path, name=...)``.

Behavior:
- ``molab init <path>`` — create or adopt the workspace at *path*
- ``molab init host:/remote/path`` — same, over SSH transport
- ``molab init`` — same, on the current working directory
- An existing directory is adopted. A legacy meta file (``workspace.json``,
  ``project.json``, ``experiment.json``, ``run.json``, ``meta.json``) or an
  ``index.md`` that does not match the current record is rewritten, and the
  meta file is removed. A record that already matches is kept, id included.
  The narrative body is kept. The derived ``index:`` block is rebuilt.
- Idempotent: re-running leaves child state (e.g. ``projects/``) intact.
- A ``Workspace`` handle writes nothing on its own, so init materializes it
  (the root ``index.md`` record, id minted once) and, on a local disk, starts the git
  history with its ignore rules and, last, runs ``molab agents sync`` (the
  ``AGENTS.md`` guide block, the ``CLAUDE.md`` import, the validation baseline).
"""

from __future__ import annotations

from typing import Annotated

import typer

from molab.cli._common import rprint


def init(
    path: Annotated[
        str | None,
        typer.Argument(
            help="Workspace path (local path, cluster:/path, or cluster:/path; default: cwd)"
        ),
    ] = None,
    name: Annotated[
        str | None,
        typer.Option("--name", "-n", help="Workspace name (derived from path if omitted)"),
    ] = None,
) -> None:
    """Initialize a new workspace, or adopt an existing directory, at PATH.

    Defaults to the current directory. A legacy meta file or an ``index.md``
    that is not the current record is rewritten and the meta file is removed.
    """
    from molab.cli._target import open_workspace, resolve_workspace_target
    from molab.services.agent_guide import sync_agent_files
    from molab.workspace.fs_local import LocalFS
    from molab.workspace.history import GitHistory
    from molab.workspace.rewrite import rewrite_records

    spec = path if path is not None else "."
    rprint(f"[bold]Initializing workspace at:[/bold] {spec}")
    try:
        target, fs = resolve_workspace_target(spec)
        rewrite_records(target.path, fs=fs, name=name)
        _target, _fs, ws = open_workspace(spec, require_existing=False, name=name)
        ws.materialize()
        if isinstance(ws.fs, LocalFS):
            GitHistory(ws.root).init()
            # Last: the agent guide, ignore rules, validation baseline, and the
            # derived index blocks (a wrong ``index:`` is rewritten here).
            sync_agent_files(ws)
            from molab.services.index_sync import sync as sync_index_blocks

            sync_index_blocks(ws)
        else:
            from molab.workspace.index_projection import sync_index

            sync_index(ws)
    except Exception as exc:
        rprint(f"[red]Failed to initialize workspace:[/red] {exc}")
        raise typer.Exit(1) from exc

    rprint(f"[green]OK[/green] Workspace ready: {ws.root}")
    rprint("\n[bold]Next steps:[/bold]")
    rprint("  • Write a script ending in ws.add_project(...).add_experiment(...)")
    rprint("    .define(workflow, params=...), then: [bold]molab run script.py[/bold]")
    rprint("  • Or open the web UI: [bold]molab serve[/bold]")
