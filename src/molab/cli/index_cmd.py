"""``molab index sync`` — rebuild the derived ``index:`` block of every record.

Each Folder's ``index.md`` carries an ``index:`` block the owner derives from
the tree (D89): the children of a workspace, project or experiment, and the
attempts of a run. The owner refreshes it on every write; ``sync`` is the full
rebuild, for a tree edited by hand or by an older molab. It rewrites only the
reserved keys and keeps every other section verbatim.
"""

from __future__ import annotations

import typer

from molab.cli._common import rprint
from molab.cli._target import TargetOption, open_workspace

index_app = typer.Typer(help="Derived index.md navigation blocks", no_args_is_help=True)


@index_app.command("sync")
def index_sync(target_spec: TargetOption = ".") -> None:
    """Rebuild the derived ``index:`` block of every record in the workspace."""
    from molab.workspace.index_projection import sync_index

    _target, _fs, ws = open_workspace(target_spec)
    visited = sync_index(ws)
    rprint(f"[green]OK[/green] index sync {ws.root}: {visited} record(s)")
