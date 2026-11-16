"""``molab index {show,write,sync}`` — read and write a record's ``index.md``.

Each Folder's ``index.md`` is its record: the frontmatter is molab's (the
canonical fields, and the ``index:`` block the owner derives from the tree,
D89) and the body is the narrative a person or an agent writes.

* ``show`` prints one ``index.md``: whole, its frontmatter, or its body.
* ``write`` replaces the body only (``Folder.write_index``); the frontmatter
  is kept. Text that carries a frontmatter differing from the record is
  refused.
* ``sync`` is the full rebuild of every derived block, for a tree edited by
  hand or by an older molab: the reserved keys and the ``index.knowledges``
  sections (:func:`molab.services.index_sync.sync`). Other sections are kept.

With no ``-p`` / ``-e`` / ``--run``, ``show`` and ``write`` address the
workspace root.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer

from molab.cli._common import rprint
from molab.cli._target import TargetOption, open_workspace

if TYPE_CHECKING:
    from molab.workspace import Folder, Workspace

index_app = typer.Typer(help="Read and write a record's index.md", no_args_is_help=True)

ProjectOption = Annotated[str | None, typer.Option("--project", "-p", help="Project.")]
ExperimentOption = Annotated[str | None, typer.Option("--experiment", "-e", help="Experiment.")]
RunOption = Annotated[str | None, typer.Option("--run", help="Run (its directory name or id).")]


def _folder(ws: Workspace, project: str | None, experiment: str | None, run: str | None) -> Folder:
    """The Folder the flags name; exit 2 on a flag without its parent, 1 when missing."""
    if experiment is not None and project is None:
        rprint("[red]Error:[/red] --experiment needs --project")
        raise typer.Exit(2)
    if run is not None and experiment is None:
        rprint("[red]Error:[/red] --run needs --project and --experiment")
        raise typer.Exit(2)
    try:
        if project is None:
            return ws
        found: Folder = ws.get_project(project)
        if experiment is not None:
            found = found.get_experiment(experiment)
        if run is not None:
            found = found.get_run(run)  # ty: ignore[unresolved-attribute]
    except Exception as exc:
        rprint(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1) from None
    return found


@index_app.command("show")
def index_show(
    project: ProjectOption = None,
    experiment: ExperimentOption = None,
    run: RunOption = None,
    frontmatter_only: Annotated[
        bool, typer.Option("--frontmatter", help="Print only the frontmatter (the record).")
    ] = False,
    body_only: Annotated[bool, typer.Option("--body", help="Print only the body.")] = False,
    target_spec: TargetOption = ".",
) -> None:
    """Print one record's index.md (whole, --frontmatter, or --body)."""
    from molab import frontmatter
    from molab.workspace.entity_record import INDEX_FILENAME

    if frontmatter_only and body_only:
        rprint("[red]Error:[/red] pass at most one of --frontmatter, --body")
        raise typer.Exit(2)
    _target, _fs, ws = open_workspace(target_spec)
    folder = _folder(ws, project, experiment, run)
    path = folder.fs.join(folder.resolve(), INDEX_FILENAME)
    try:
        text = folder.fs.read_text(path)
    except FileNotFoundError:
        rprint(f"[red]Error:[/red] no {INDEX_FILENAME} at {folder.resolve()}")
        raise typer.Exit(1) from None
    meta, body = frontmatter.split(text)
    if frontmatter_only:
        out = frontmatter.dump(meta, "") if meta else ""
    elif body_only:
        out = body
    else:
        out = text
    sys.stdout.write(out)


@index_app.command("write")
def index_write(
    source: Annotated[
        str, typer.Option("--from", help="File holding the new body, or - for stdin.")
    ],
    project: ProjectOption = None,
    experiment: ExperimentOption = None,
    run: RunOption = None,
    target_spec: TargetOption = ".",
) -> None:
    """Replace the body of one record's index.md; its frontmatter is kept."""
    from molab import frontmatter
    from molab.workspace.entity_record import read_record

    text = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
    _target, _fs, ws = open_workspace(target_spec)
    folder = _folder(ws, project, experiment, run)
    record = read_record(folder.fs, folder.resolve())
    if record is None:
        rprint(f"[red]Error:[/red] no record at {folder.resolve()}")
        raise typer.Exit(1)
    meta, body = frontmatter.split(text)
    if meta:
        current = dict(record.canonical)
        if record.index:
            current["index"] = record.index
        if meta != current:
            rprint(
                "[red]Error:[/red] the text carries a frontmatter that differs from the "
                "record; the frontmatter is molab's — pass the body only."
            )
            raise typer.Exit(1)
    else:
        body = text
    path = folder.write_index(body)
    rprint(f"[green]OK[/green] wrote the body of {path}")


@index_app.command("sync")
def index_sync(target_spec: TargetOption = ".") -> None:
    """Rebuild every derived block (index: keys and knowledge sections) in the workspace."""
    from molab.services.index_sync import sync

    _target, _fs, ws = open_workspace(target_spec)
    result = sync(ws)
    rprint(
        f"[green]OK[/green] index sync {ws.root}: {result.records} record(s), "
        f"{result.sections} knowledge section(s) rewritten"
    )
