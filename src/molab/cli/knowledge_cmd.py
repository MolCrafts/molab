"""``molab knowledge`` — notes and literature (OKF Concepts) from the CLI.

The group is thin plumbing over the workspace knowledge surface: everything a
command does here routes through the same :class:`molab.workspace.Bundle`
verbs Python callers use (the Python == UI/CLI invariant). ``import-zotero``
links a local Zotero library read-only via :meth:`Bundle.import_zotero` /
:func:`molab.workspace.read_zotero_items` — each item becomes a
``ReferenceConcept`` directory whose ``meta.json`` carries the bib record and
whose PDF is *pointed at* in place, never copied.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer

from molab.cli._common import rprint

if TYPE_CHECKING:
    from molab.workspace import Workspace

knowledge_app = typer.Typer(
    name="knowledge",
    help="Notes and literature (OKF Concepts).",
    no_args_is_help=True,
)

_ZOTERO_DB_FILENAME = "zotero.sqlite"


def _resolve_zotero_db(database: Path) -> Path:
    """Resolve *database* to a zotero.sqlite file, failing with a human message.

    Accepts either the ``zotero.sqlite`` file itself or the Zotero data
    directory that contains it (the way Zotero presents its library on disk).

    Raises:
        typer.Exit: code 1 when nothing readable exists at the location.
    """
    db = database / _ZOTERO_DB_FILENAME if database.is_dir() else database
    if not db.is_file():
        rprint(f"[red]Error:[/red] Zotero database not found: {db}")
        rprint(
            "Point at the [bold]zotero.sqlite[/bold] file inside your Zotero data "
            "directory (or at the directory itself)."
        )
        raise typer.Exit(1)
    return db


def _load_dest_workspace(dest: Path) -> Workspace:
    """Load the destination workspace, failing with a human message.

    Raises:
        typer.Exit: code 1 when *dest* holds no ``workspace.json``.
    """
    from molab.workspace import Workspace

    try:
        return Workspace.load(dest)
    except FileNotFoundError:
        rprint(f"[red]Error:[/red] Destination is not a molab workspace: {dest}")
        rprint(f"Initialise one first with [bold]molab init {dest}[/bold].")
        raise typer.Exit(1) from None


@knowledge_app.command("import-zotero")
def import_zotero(
    database: Annotated[
        Path,
        typer.Argument(
            help="Path to Zotero's zotero.sqlite (or the Zotero data directory containing it).",
        ),
    ],
    dest: Annotated[
        Path,
        typer.Option(
            "--dest",
            help="Destination workspace root (default: current directory).",
        ),
    ] = Path(),
) -> None:
    """Link a local Zotero library as reference Concepts (read-only import).

    Each Zotero item becomes a ``ReferenceConcept`` directory under
    ``<dest>/references/`` — bib fields in ``meta.json``, PDFs pointed at in
    place (never copied). Re-running is idempotent: an item updates its
    existing directory instead of duplicating it.
    """
    from molab.workspace import Bundle

    db = _resolve_zotero_db(database)
    ws = _load_dest_workspace(dest)

    bundle = Bundle(ws.root)
    try:
        refs = bundle.import_zotero(db)
    except sqlite3.Error as exc:
        if "locked" in str(exc).lower():
            rprint(
                f"[red]Error:[/red] {db} is locked — close Zotero and retry "
                "(the import only ever reads the database)."
            )
        else:
            rprint(f"[red]Error:[/red] {db} is not a Zotero database ({exc}).")
            rprint(
                "Expected the [bold]zotero.sqlite[/bold] library file from your "
                "Zotero data directory."
            )
        raise typer.Exit(1) from exc

    rprint(f"[green]OK[/green] Imported {len(refs)} reference(s) into {bundle.root}")
    for ref in refs:
        meta = ref.read_reference_meta()
        title = meta.title or "(untitled)"
        year = f" ({meta.year})" if meta.year else ""
        rprint(f"  {bundle.rel_path(ref)}  [dim]{title}{year}[/dim]")


sources_app = typer.Typer(
    name="sources",
    help="Registered knowledge bases (group wikis).",
    no_args_is_help=True,
)
knowledge_app.add_typer(sources_app, name="sources")


def _workspace_root(path: Path | None) -> Path | None:
    """The workspace root to use as the upper config tier, if there is one.

    A knowledge command must work from anywhere — inside a workspace, or in a
    plain shell asking about the lab wiki — so a missing workspace is a normal
    condition here, not an error.
    """
    root = (path or Path.cwd()).resolve()
    return root if (root / "workspace.json").is_file() else None


@sources_app.command("list")
def sources_list(
    path: Annotated[
        Path | None, typer.Option("--path", help="Workspace root; defaults to cwd.")
    ] = None,
) -> None:
    """List every registered knowledge base and where it lives."""
    from rich import print as _rich_print
    from rich.table import Table

    from molab.knowledge.sources import KnowledgeSourceStore

    entries = KnowledgeSourceStore(_workspace_root(path)).list()
    if not entries:
        rprint("[dim]No knowledge sources registered.[/dim]")
        rprint("Add one with [bold]molab knowledge sources add <name> <dir>[/bold].")
        return
    table = Table(title="knowledge sources")
    table.add_column("Name", style="bold")
    table.add_column("Root")
    table.add_column("Scope", style="dim")
    table.add_column("Status")
    for source, scope in entries:
        root = source.path()
        status = "[green]ok[/green]" if root.is_dir() else "[yellow]missing[/yellow]"
        table.add_row(source.name, str(root), str(scope), status)
    _rich_print(table)


@sources_app.command("add")
def sources_add(
    name: Annotated[str, typer.Argument(help="Handle for the wiki, e.g. 'lab-wiki'.")],
    root: Annotated[Path, typer.Argument(help="The OKF bundle directory.")],
    description: Annotated[str, typer.Option("--description", help="What this wiki covers.")] = "",
    workspace_scope: Annotated[
        bool,
        typer.Option(
            "--workspace",
            help="Register for this workspace only, instead of the current user.",
        ),
    ] = False,
    path: Annotated[
        Path | None, typer.Option("--path", help="Workspace root; defaults to cwd.")
    ] = None,
) -> None:
    """Register a knowledge base so searches can reach it by name."""
    from pydantic import ValidationError

    from molab.knowledge.sources import KnowledgeScope, KnowledgeSourceStore, WikiSource

    ws_root = _workspace_root(path)
    scope = KnowledgeScope.WORKSPACE if workspace_scope else KnowledgeScope.USER
    if scope is KnowledgeScope.WORKSPACE and ws_root is None:
        rprint("[red]Error:[/red] --workspace needs a molab workspace; none found here.")
        raise typer.Exit(1)
    try:
        source = WikiSource(name=name, root=str(root.expanduser()), description=description)
    except ValidationError:
        rprint(f"[red]Error:[/red] invalid source name {name!r}.")
        rprint("Use lowercase letters, digits, '-' or '_' (max 64 chars).")
        raise typer.Exit(1) from None

    resolved = source.path()
    if not resolved.is_dir():
        # Registering a path that is not there yet is legal (a wiki on a share
        # that is not mounted right now), but it is worth saying out loud.
        rprint(f"[yellow]Note:[/yellow] {resolved} does not exist yet.")
    elif not (resolved / "meta.json").is_file() and not any(resolved.glob("*/meta.json")):
        rprint(f"[yellow]Note:[/yellow] {resolved} holds no OKF concepts yet.")
        rprint("Create one with [bold]molab knowledge init[/bold], or add a meta.json.")

    KnowledgeSourceStore(ws_root).add(source, scope=scope)
    rprint(f"[green]OK[/green] Registered [bold]{name}[/bold] -> {resolved} ({scope})")


@sources_app.command("remove")
def sources_remove(
    name: Annotated[str, typer.Argument(help="The registered source name.")],
    workspace_scope: Annotated[
        bool, typer.Option("--workspace", help="Remove the workspace-scoped entry.")
    ] = False,
    path: Annotated[
        Path | None, typer.Option("--path", help="Workspace root; defaults to cwd.")
    ] = None,
) -> None:
    """Unregister a knowledge base. The wiki's files are never touched."""
    from molab.knowledge.sources import (
        KnowledgeScope,
        KnowledgeSourceStore,
        SourceNotFoundError,
    )

    scope = KnowledgeScope.WORKSPACE if workspace_scope else KnowledgeScope.USER
    try:
        KnowledgeSourceStore(_workspace_root(path)).remove(name, scope=scope)
    except (SourceNotFoundError, ValueError):
        rprint(f"[red]Error:[/red] no {scope} knowledge source named {name!r}.")
        raise typer.Exit(1) from None
    rprint(f"[green]OK[/green] Unregistered [bold]{name}[/bold] ({scope}). Files left in place.")


@knowledge_app.command("init")
def knowledge_init(
    directory: Annotated[Path, typer.Argument(help="Directory to turn into an OKF bundle.")],
    title: Annotated[str, typer.Option("--title", help="Title for the bundle's index.md.")] = "",
) -> None:
    """Create a minimal OKF bundle — a group wiki needs no workspace.

    Writes the two files that make a directory a Concept: a ``meta.json`` marker
    and an ``index.md`` narrative. Idempotent: an existing bundle is left alone.
    """
    from molab.knowledge.concept import Concept

    target = directory.expanduser().resolve()
    concept = Concept(target, type="bundle.root")
    if (target / "meta.json").is_file():
        rprint(f"[dim]Already an OKF bundle: {target}[/dim]")
        return
    concept.write_meta()
    if not (target / "index.md").is_file():
        concept.set_body(f"# {title or target.name}\n\nNotes in this wiki.\n")
    rprint(f"[green]OK[/green] Initialised OKF bundle at [bold]{target}[/bold]")
    rprint(
        "Register it with "
        f"[bold]molab knowledge sources add <name> {target}[/bold] to make it searchable."
    )


@knowledge_app.command("search")
def knowledge_search(
    query: Annotated[str, typer.Argument(help="What you want to know, in words.")],
    source: Annotated[
        list[str] | None,
        typer.Option("--source", help="Restrict to these sources (repeatable)."),
    ] = None,
    concept_type: Annotated[
        str | None, typer.Option("--type", help="Exact Concept type filter.")
    ] = None,
    tag: Annotated[str | None, typer.Option("--tag", help="Only concepts with this tag.")] = None,
    limit: Annotated[int, typer.Option("--limit", help="Maximum hits to show.")] = 10,
    path: Annotated[
        Path | None, typer.Option("--path", help="Workspace root; defaults to cwd.")
    ] = None,
) -> None:
    """Search the knowledge bases — every registered wiki plus this workspace.

    Keyword-ranked (BM25F), so a question in your own words finds the document
    that answers it; Chinese works without a segmenter. Read a hit in full with
    ``molab knowledge read <ref>``.
    """
    from rich import print as _rich_print
    from rich.table import Table

    from molab.knowledge.sources import search_sources
    from molab.workspace.bundle import Bundle as WorkspaceBundle

    ws_root = _workspace_root(path)
    hits = search_sources(
        query,
        sources=source or None,
        workspace_root=ws_root,
        include_workspace=ws_root is not None,
        limit=limit,
        concept_type=concept_type,
        tag=tag,
        # The workspace is searched through its own (layout-pruned) bundle —
        # the same one the server and the agent tool use.
        workspace_searcher=(
            (
                lambda: WorkspaceBundle(ws_root).search(
                    query, concept_type=concept_type, tag=tag, limit=limit
                )
            )
            if ws_root is not None
            else None
        ),
    )
    if not hits:
        rprint(f"[dim]No knowledge matches for {query!r}.[/dim]")
        _hint_when_nothing_registered(ws_root)
        return
    table = Table(title=f"knowledge search: {query!r}")
    # A ref is meant to be copied straight into `molab knowledge read`, so it
    # must wrap rather than be ellipsized on a narrow terminal — a truncated ref
    # is worse than useless.
    table.add_column("Ref", style="bold", overflow="fold")
    table.add_column("Title", overflow="fold")
    table.add_column("Source", style="dim")
    table.add_column("Score", justify="right", style="dim")
    table.add_column("Match")
    for sourced in hits:
        entry = sourced.hit.entry
        table.add_row(
            sourced.ref,
            entry.title or entry.path,
            sourced.source or "(workspace)",
            f"{sourced.hit.score:.2f}",
            sourced.hit.snippet or ", ".join(sourced.hit.matched_fields),
        )
    _rich_print(table)


def _hint_when_nothing_registered(ws_root: Path | None) -> None:
    """Say why a search could not match when there is nothing to search."""
    from molab.knowledge.sources import KnowledgeSourceStore

    if not KnowledgeSourceStore(ws_root).list() and ws_root is None:
        rprint("No knowledge sources are registered and this is not a workspace.")
        rprint("Register a wiki with [bold]molab knowledge sources add <name> <dir>[/bold].")


@knowledge_app.command("read")
def knowledge_read(
    ref: Annotated[
        str,
        typer.Argument(help="A '<source>:<path>' ref from search, or a workspace-relative path."),
    ],
    path: Annotated[
        Path | None, typer.Option("--path", help="Workspace root; defaults to cwd.")
    ] = None,
) -> None:
    """Print one knowledge document in full — its metadata, body and edges."""
    from molab.knowledge.bundle import Bundle
    from molab.knowledge.errors import ConceptNotFoundError
    from molab.knowledge.sources import KnowledgeSourceStore, SourceNotFoundError
    from molab.workspace.bundle import Bundle as WorkspaceBundle

    ws_root = _workspace_root(path)
    source_name, _, rel = ref.partition(":") if ":" in ref else ("", "", ref)
    if source_name:
        try:
            root = KnowledgeSourceStore(ws_root).get(source_name).path()
        except SourceNotFoundError:
            rprint(f"[red]Error:[/red] no knowledge source named {source_name!r}.")
            raise typer.Exit(1) from None
        bundle: Bundle = Bundle(root)
    elif ws_root is not None:
        root = ws_root
        bundle = WorkspaceBundle(root)
    else:
        rprint("[red]Error:[/red] not a workspace — use a '<source>:<path>' ref.")
        raise typer.Exit(1)

    try:
        concept = bundle.get(rel)
    except (ConceptNotFoundError, FileNotFoundError):
        rprint(f"[red]Error:[/red] no knowledge concept at {ref!r}.")
        rprint("Find valid refs with [bold]molab knowledge search[/bold].")
        raise typer.Exit(1) from None

    rprint(f"[bold]{ref}[/bold]  [dim]{concept.type()}[/dim]")
    if tags := concept.tags():
        rprint(f"[dim]tags: {', '.join(tags)}[/dim]")
    rprint(f"[dim]file: {concept.path / 'index.md'}[/dim]")
    rprint("")
    # The body is markdown the user wrote; print it verbatim rather than letting
    # rich reinterpret its brackets as markup.
    print(concept.body())
    if edges := concept.typed_out_edges():
        rprint("[dim]links:[/dim]")
        for edge in edges:
            rprint(f"  [dim][{edge.role}][/dim] {edge.target}")
