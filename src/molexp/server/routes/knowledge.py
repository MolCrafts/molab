"""Knowledge routes — browse + author the workspace's OKF Concepts.

Notes (``Note``) and literature references (``ReferenceConcept``) are OKF
Concept ``Folder``s mounted anywhere under the workspace, reached through the
:class:`~molexp.workspace.bundle.Bundle` façade. These routes expose them over
HTTP for the UI's Knowledge tab; the legacy per-scope ``/api/library`` surface
was removed in wsokf-11, so this is the greenfield read API for OKF knowledge.

The mutating document endpoints (create / edit-body / rename-move / delete /
backlinks / export) are **thin delegators** to the workspace-owned ``Bundle``
verbs (``create_note`` / ``rename_note`` / ``move_note`` / ``delete_note`` /
``backlinks`` / ``export_markdown``) — CLI and server call the same verbs, so
the CRUD logic lives in one place (the Python==UI invariant), never re-built at
the HTTP boundary. Each mutating handler is gated by :func:`_require_writable`
(405 against a remote/read-only served workspace); every path-addressed handler
maps :class:`ConceptNotFoundError` (and a non-``Note`` concept) to a 404.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path as _StdPath
from typing import TYPE_CHECKING, Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from molexp.server.dependencies import get_workspace
from molexp.services.workspace_read_model import WorkspaceReadModel
from molexp.workspace.edges import EdgeRole

from ..deps.read_model import get_read_model
from ..deps.served import active_served_key, assert_workspace_writable
from ..http_cache import not_modified, weak_etag
from ..mutations import after_mutation
from ..schemas import MessageResponse

if TYPE_CHECKING:
    from molexp.workspace import Bundle, Workspace
    from molexp.workspace.assets.base import Asset
    from molexp.workspace.concepts import Note
    from molexp.workspace.experiment import Experiment
    from molexp.workspace.folder import Folder
    from molexp.workspace.note_meta import NoteMeta
    from molexp.workspace.run import Run

__all__ = ["router"]

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

_EXCERPT_CHARS = 320


class NoteSummary(BaseModel):
    name: str
    relPath: str
    excerpt: str
    tags: list[str] = []
    status: str | None = None


class ReferenceSummary(BaseModel):
    name: str
    relPath: str
    title: str | None = None
    authors: list[str] = []
    year: int | None = None
    doi: str | None = None
    venue: str | None = None
    url: str | None = None
    source: str = "manual"


class KnowledgeListResponse(BaseModel):
    notes: list[NoteSummary]
    references: list[ReferenceSummary]
    total: int


class EntityCard(BaseModel):
    """A clickable summary card for an entity a document embeds (05 resolver)."""

    kind: str
    id: str
    title: str
    relPath: str | None = None
    status: str | None = None


class NoteDetailResponse(BaseModel):
    name: str
    relPath: str
    body: str
    links: list[str]
    cards: list[EntityCard] = []


class EmbedRequest(BaseModel):
    """Embed a live workspace entity into a document as one typed provenance edge."""

    target_kind: Literal["run", "asset", "experiment", "reference"]
    target: str
    # ``None`` = defer to ``knowledge_mount.embed``'s per-kind default (run/experiment ->
    # records, reference -> cites, asset/other -> references), so an HTTP embed
    # with no explicit role writes the SAME edge a CLI ``knowledge_mount.embed`` call
    # would — the Python==UI invariant. An explicit role overrides.
    role: EdgeRole | None = None
    text: str | None = None


class EmbedResponse(BaseModel):
    """Echo of the written embed edge."""

    srcPath: str
    target: str
    role: EdgeRole


class DocCreateRequest(BaseModel):
    name: str
    body: str = ""
    parentPath: str | None = None


class DocBodyUpdate(BaseModel):
    body: str


class DocMoveRequest(BaseModel):
    name: str | None = None
    parentPath: str | None = None


class DocMetaUpdate(BaseModel):
    """Partial update of a note's ``meta.yaml`` tags/status.

    Each field is independently optional; ``None`` means "leave untouched", which
    maps onto ``Note.set_tags`` / ``Note.set_status`` each preserving the sibling
    field. A request with both ``None`` is a no-op that returns the current summary.
    """

    tags: list[str] | None = None
    status: str | None = None


class BacklinksResponse(BaseModel):
    backlinks: list[NoteSummary]


class _Partition:
    """The :class:`~molexp.knowledge.bundle.ConceptPartition` shape, snapshot-backed.

    Lets the list handler stay written against one structure whether it was
    produced by a live walk or lifted from the read model's cached scan.
    """

    __slots__ = ("items", "metas", "notes", "references")

    def __init__(self, snapshot) -> None:  # noqa: ANN001
        self.notes = list(snapshot.notes)
        self.references = list(snapshot.references)
        self.items = list(snapshot.items)
        self.metas = snapshot.metas


def _bundle(workspace: Workspace) -> Bundle:
    from molexp.workspace import Bundle

    return Bundle(workspace.root)


def _require_writable(request: Request) -> None:
    """Reject a mutating request against a remote (read-only) served workspace.

    The flat ``/knowledge`` router is not under the ``/workspaces/{ws}`` scoped
    router, so it carries its own write-gate: it 405s a mutating verb against a
    remote served workspace (via :func:`assert_workspace_writable`); a local /
    unmanaged workspace stays writable. Safe methods pass through untouched.
    """
    assert_workspace_writable(active_served_key() or "", request.method)


def _note_meta_of(note: Note, meta: Mapping[str, object] | None) -> NoteMeta:
    """*note*'s typed :class:`NoteMeta` — parsed from an already-read *meta* when given.

    A bundle walk has just parsed every ``meta.yaml`` to type its Concepts;
    re-reading it per note to learn ``tags`` / ``status`` would double the
    file traffic of the list endpoint. A bare legacy marker reads back with
    the additive defaults exactly as :meth:`Note.read_note_meta` does.
    """
    from molexp.workspace.note_meta import NoteMeta

    if meta is None:
        return note.read_note_meta()
    return NoteMeta.model_validate(dict(meta) or {"type": note.type(), "id": note.name})


def _note_summary(
    bundle: Bundle, note: Note, *, meta: Mapping[str, object] | None = None
) -> NoteSummary:
    """Build a :class:`NoteSummary` for *note* (identity + excerpt + tags/status).

    ``tags``/``status`` come from the 05 :class:`~molexp.workspace.note_meta.NoteMeta`
    helpers (an untagged note reads back ``[]`` / ``"active"``); *meta* is the
    ``meta.yaml`` the caller's walk already parsed, so it is not read again.
    """
    body = note.body() or ""
    note_meta = _note_meta_of(note, meta)
    return NoteSummary(
        name=note.name,
        relPath=bundle.rel_path(note),
        excerpt=body[:_EXCERPT_CHARS],
        tags=list(note_meta.tags),
        status=note_meta.status,
    )


def _note_detail(bundle: Bundle, workspace: Workspace, note: Note, path: str) -> NoteDetailResponse:
    """Build a :class:`NoteDetailResponse` for *note* at its identity *path*.

    Enriches the response with ``cards`` — one :class:`EntityCard` per typed
    out-edge that resolves to a live entity (Run / Experiment / Reference / Note
    / Asset), each projected by the 05 entity-summary resolver
    (:meth:`~molexp.workspace.bundle.Bundle.entity_summary`).
    """
    return NoteDetailResponse(
        name=note.name,
        relPath=path,
        body=note.body(),
        links=list(note.out_edges()),
        cards=_resolve_cards(bundle, workspace, note),
    )


def _resolve_cards(bundle: Bundle, workspace: Workspace, note: Note) -> list[EntityCard]:
    """Resolve *note*'s typed out-edges to :class:`EntityCard` summary cards.

    Each edge target is resolved back to its live entity; an edge that resolves
    to no entity is skipped (it cannot be summarized as a card).
    """
    from molexp.workspace import knowledge_mount

    cards: list[EntityCard] = []
    for edge in note.typed_out_edges():
        entity = _resolve_edge_entity(bundle, workspace, edge.target)
        if entity is None:
            continue
        summary = knowledge_mount.entity_summary(entity, root=bundle.root)
        cards.append(
            EntityCard(
                kind=summary.kind,
                id=summary.id,
                title=summary.title,
                relPath=_entity_rel_path(bundle, entity),
                status=_entity_status(entity),
            )
        )
    return cards


def _resolve_edge_entity(
    bundle: Bundle, workspace: Workspace, target: str
) -> Folder | Asset | None:
    """Resolve a typed out-edge *target* path back to its live entity, or ``None``.

    A Concept dir (``meta.yaml`` present) resolves to its typed ``Folder`` via
    the bundle; an asset record dir (``<scope>/assets/<asset_id>/``) resolves to
    its :class:`~molexp.workspace.assets.base.Asset` via the manifest scanner.
    """
    from molexp.workspace.assets.scan import get_asset
    from molexp.workspace.errors import ConceptNotFoundError

    abs_path = _StdPath(str(target))
    try:
        rel = abs_path.relative_to(bundle.root).as_posix()
    except ValueError:
        return None
    try:
        return bundle.get(rel)
    except ConceptNotFoundError:
        pass
    if abs_path.parent.name == "assets":
        return get_asset(workspace.root, abs_path.name)
    return None


def _entity_rel_path(bundle: Bundle, entity: Folder | Asset) -> str | None:
    """A ``Folder`` entity's bundle-relative identity path; ``None`` for an ``Asset``."""
    from molexp.workspace.assets.base import Asset

    if isinstance(entity, Asset):
        return None
    return bundle.rel_path(entity)


def _entity_status(entity: Folder | Asset) -> str | None:
    """A ``Note`` entity's lifecycle status; ``None`` for anything else."""
    from molexp.workspace.concepts import Note

    return entity.status() if isinstance(entity, Note) else None


def _resolve_embed_target(
    bundle: Bundle, workspace: Workspace, target_kind: str, target: str
) -> Folder | Asset:
    """Resolve an embed ``(target_kind, target)`` to a live ``Folder`` / ``Asset``.

    Mirrors :func:`_resolve_note`'s not-found → 404 policy: an unknown run /
    experiment / asset / reference (or a target that resolves to no entity) is a
    404, never a silent miss.
    """
    from molexp.workspace.errors import ConceptNotFoundError

    if target_kind == "reference":
        try:
            return bundle.get(target)
        except ConceptNotFoundError as exc:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, f"reference {target!r} not found"
            ) from exc

    entity: Folder | Asset | None
    if target_kind == "run":
        entity = _find_run(workspace, target)
    elif target_kind == "experiment":
        entity = _find_experiment(workspace, target)
    else:  # "asset" — the Literal on EmbedRequest guarantees no other value
        from molexp.workspace.assets.scan import get_asset

        entity = get_asset(workspace.root, target)
    if entity is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{target_kind} {target!r} not found")
    return entity


def _find_run(workspace: Workspace, run_id: str) -> Run | None:
    """Find a ``Run`` by id across every project/experiment, or ``None``."""
    for project in workspace.list_projects():
        for experiment in project.list_experiments():
            if experiment.has_run(run_id):
                return experiment.get_run(run_id)
    return None


def _find_experiment(workspace: Workspace, experiment_id: str) -> Experiment | None:
    """Find an ``Experiment`` by id across every project, or ``None``."""
    for project in workspace.list_projects():
        if project.has_experiment(experiment_id):
            return project.get_experiment(experiment_id)
    return None


def _resolve_note(bundle: Bundle, path: str) -> Note:
    """Resolve *path* to a :class:`Note`, mapping miss / non-note to a 404."""
    from molexp.workspace.concepts import Note
    from molexp.workspace.errors import ConceptNotFoundError

    try:
        concept = bundle.get(path)
    except ConceptNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"note {path!r} not found") from exc
    if not isinstance(concept, Note):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"concept {path!r} is not a note")
    return concept


class EntityBacklinkRow(BaseModel):
    """One knowledge document citing the queried entity."""

    path: str
    title: str
    type: str
    role: str


class EntityBacklinksResponse(BaseModel):
    """``GET /knowledge/entity-backlinks`` — who cites this entity?"""

    entity: str
    backlinks: list[EntityBacklinkRow]


@router.get("/entity-backlinks", response_model=EntityBacklinksResponse)
def entity_backlinks(
    kind: Annotated[Literal["run", "experiment"], Query(description="Entity kind.")],
    project_id: Annotated[str, Query(alias="projectId")],
    experiment_id: Annotated[str, Query(alias="experimentId")],
    run_id: Annotated[str | None, Query(alias="runId")] = None,
    workspace: Workspace = Depends(get_workspace),
) -> EntityBacklinksResponse:
    """Knowledge documents citing one entity — a thin ``Bundle.backlinks`` read.

    Pure derived read (no reverse index persisted): resolves the entity
    Folder, then asks the bundle which Concepts' ``index.md`` edges point at
    it. 404 on an unresolvable entity — never an empty-list fallback for a
    bad ref (no-fallback law).
    """
    from molexp.workspace.bundle_index import extract_title
    from molexp.workspace.errors import (
        ExperimentNotFoundError,
        ProjectNotFoundError,
        RunNotFoundError,
    )

    try:
        experiment = workspace.get_project(project_id).get_experiment(experiment_id)
        if kind == "run":
            if not run_id:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT, "kind=run requires runId"
                )
            entity = experiment.get_run(run_id)
        else:
            entity = experiment
    except (ProjectNotFoundError, ExperimentNotFoundError, RunNotFoundError) as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    bundle = _bundle(workspace)
    rows: list[EntityBacklinkRow] = []
    for link in bundle.backlinks(entity):
        meta = link.source.read_meta()
        rows.append(
            EntityBacklinkRow(
                path=bundle.rel_path(link.source),
                title=extract_title(link.source.read_index() or "") or link.source.name,
                type=str(meta.get("type", "")),
                role=str(link.role),
            )
        )
    return EntityBacklinksResponse(entity=f"{kind}:{run_id or experiment_id}", backlinks=rows)


class KnowledgeSearchRow(BaseModel):
    """One ranked search hit projected from the bundle index entry."""

    path: str
    title: str
    type: str
    tags: list[str] = []
    snippet: str | None = None
    score: float = 0.0
    source: str = ""
    ref: str = ""


class KnowledgeSearchResponse(BaseModel):
    """``GET /knowledge/search`` — ranked retrieval across the knowledge bases."""

    hits: list[KnowledgeSearchRow]
    truncated: bool


class KnowledgeBaseRow(BaseModel):
    """One registered OKF knowledge base (a group wiki).

    Named "knowledge base", not "knowledge source": ``agent_admin`` already owns
    ``KnowledgeSourcesResponse`` for the molmcp *package* allowlist, an unrelated
    concept. Two schemas with one name collide in the generated OpenAPI client,
    and the ambiguity was real before it was mechanical.
    """

    name: str
    root: str
    description: str = ""
    scope: str
    available: bool


class KnowledgeBasesResponse(BaseModel):
    """``GET /knowledge/sources`` — which knowledge bases this host can search."""

    sources: list[KnowledgeBaseRow]


@router.get("/sources", response_model=KnowledgeBasesResponse)
def list_knowledge_sources(
    workspace: Workspace = Depends(get_workspace),
) -> KnowledgeBasesResponse:
    """List the OKF knowledge bases registered on this host.

    ``available`` reports whether the directory is readable right now — a wiki
    on an unmounted share stays registered and simply cannot be searched until
    it is back, which is information the UI should show rather than hide.
    """
    from molexp.knowledge.sources import KnowledgeSourceStore

    return KnowledgeBasesResponse(
        sources=[
            KnowledgeBaseRow(
                name=source.name,
                root=str(source.path()),
                description=source.description,
                scope=str(scope),
                available=source.path().is_dir(),
            )
            for source, scope in KnowledgeSourceStore(workspace.resolve()).list()
        ]
    )


@router.get("/search", response_model=KnowledgeSearchResponse)
def search_knowledge(
    q: Annotated[str, Query(description="What you want to know, in words.")],
    type: Annotated[str | None, Query(description="Exact Concept type filter.")] = None,
    tag: Annotated[str | None, Query(description="Only concepts carrying this tag.")] = None,
    source: Annotated[
        list[str] | None, Query(description="Restrict to these registered sources.")
    ] = None,
    limit: Annotated[int, Query(description="Maximum hits to return.", ge=1, le=200)] = 50,
    workspace: Workspace = Depends(get_workspace),
    read_model: WorkspaceReadModel = Depends(get_read_model),
) -> KnowledgeSearchResponse:
    """Search this workspace and every registered knowledge base, BM25F-ranked.

    Pure exposure: all matching semantics (tokenization, ranking, body caps,
    cross-source fusion) live in
    :func:`molexp.knowledge.sources.search_sources`; this route only projects
    its hits onto the wire. Each row carries the ``<source>:<path>`` ``ref`` the
    other knowledge endpoints accept.
    """
    from molexp.knowledge.sources import search_sources

    root = workspace.resolve()
    bundle = _bundle(workspace)
    snapshot = read_model.knowledge()
    hits = search_sources(
        q,
        sources=source or None,
        workspace_root=root,
        limit=limit,
        concept_type=type,
        tag=tag,
        # The workspace is searched against the read model's cached index and
        # its already-tokenized BM25F corpus, so a keystroke re-ranks in memory
        # instead of re-walking the tree. A GET still never writes
        # ``index.json`` / ``INDEX.md``.
        workspace_searcher=lambda: bundle.search(
            q,
            concept_type=type,
            tag=tag,
            limit=limit,
            index=snapshot.index,
            bodies=snapshot.bodies,
            corpus=snapshot.corpus,
        ),
    )
    return KnowledgeSearchResponse(
        hits=[
            KnowledgeSearchRow(
                path=sourced.hit.entry.path,
                title=sourced.hit.entry.title or sourced.hit.entry.path,
                type=sourced.hit.entry.type,
                tags=list(sourced.hit.entry.tags),
                snippet=sourced.hit.snippet,
                score=sourced.hit.score,
                source=sourced.source,
                ref=sourced.ref,
            )
            for sourced in hits
        ],
        # Fusion returns at most ``limit`` rows; a full page means there may be
        # more behind it. Never a silent cap.
        truncated=len(hits) >= limit,
    )


@router.get("", response_model=KnowledgeListResponse)
def list_knowledge(
    tag: Annotated[str | None, Query(description="Only notes carrying this tag.")] = None,
    status: Annotated[
        str | None, Query(description="Only notes with this lifecycle status.")
    ] = None,
    request: Request = None,  # type: ignore[assignment]
    response: Response = None,  # type: ignore[assignment]
    workspace: Workspace = Depends(get_workspace),
    read_model: WorkspaceReadModel = Depends(get_read_model),
) -> KnowledgeListResponse:
    """List every Note + ReferenceConcept in the active workspace's bundle.

    Optional ``tag`` / ``status`` query params AND-narrow the note list (both
    read from the 05 :class:`~molexp.workspace.note_meta.NoteMeta` fields).
    """
    from molexp.workspace.reference_meta import ReferenceMeta

    bundle = _bundle(workspace)
    # The read model already walked the bundle once and kept every Concept's
    # parsed ``meta.yaml``; the list endpoint reads no file at all when warm.
    snapshot = read_model.knowledge()
    cached = not_modified(request, response, weak_etag("knowledge", snapshot.version, tag, status))
    if cached is not None:
        return cached  # type: ignore[return-value]
    part = _Partition(snapshot)

    notes: list[NoteSummary] = []
    for note in part.notes:
        raw_meta = part.metas.get(bundle.rel_path(note))
        note_meta = _note_meta_of(note, raw_meta)
        if tag is not None and tag not in note_meta.tags:
            continue
        if status is not None and note_meta.status != status:
            continue
        notes.append(_note_summary(bundle, note, meta=raw_meta))

    references: list[ReferenceSummary] = []
    for ref in part.references:
        raw_meta = part.metas.get(bundle.rel_path(ref))
        meta = ReferenceMeta.model_validate(raw_meta) if raw_meta else ref.read_ref_meta()
        references.append(
            ReferenceSummary(
                name=ref.name,
                relPath=bundle.rel_path(ref),
                title=meta.title,
                authors=list(meta.authors),
                year=meta.year,
                doi=meta.doi,
                venue=meta.venue,
                url=meta.url,
                source=meta.source,
            )
        )

    notes.sort(key=lambda n: n.name)
    references.sort(key=lambda r: (r.year or 0, r.name), reverse=True)
    return KnowledgeListResponse(
        notes=notes, references=references, total=len(notes) + len(references)
    )


@router.get("/note", response_model=NoteDetailResponse)
def get_note(
    path: str = Query(..., description="The note Concept's bundle-relative path (its identity)."),
    workspace: Workspace = Depends(get_workspace),
) -> NoteDetailResponse:
    """Return one note's full body (its ``index.md``) + its outgoing links + cards."""
    bundle = _bundle(workspace)
    concept = _resolve_note(bundle, path)
    return _note_detail(bundle, workspace, concept, path)


# ── Document authoring — thin delegators to workspace ``Bundle`` verbs ────────


@router.post(
    "/doc",
    response_model=NoteSummary,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_require_writable)],
)
def create_doc(
    body: DocCreateRequest,
    workspace: Workspace = Depends(get_workspace),
) -> NoteSummary:
    """Create a :class:`Note` document — delegates to ``Bundle.create_note``."""
    bundle = _bundle(workspace)
    parent = _resolve_note(bundle, body.parentPath) if body.parentPath else None
    note = bundle.create_note(body.name, parent=parent, body=body.body)
    after_mutation(workspace, "knowledge", ref=bundle.rel_path(note))
    return _note_summary(bundle, note)


@router.post(
    "/doc/embed",
    response_model=EmbedResponse,
    dependencies=[Depends(_require_writable)],
)
def embed_doc(
    body: EmbedRequest,
    path: str = Query(..., description="The source note Concept's bundle-relative path."),
    workspace: Workspace = Depends(get_workspace),
) -> EmbedResponse:
    """Embed a live entity into a document — delegates to ``knowledge_mount.embed``.

    Resolves the source ``Note`` (404 on miss / non-note) and the target entity
    (``run`` / ``experiment`` / ``asset`` / ``reference``; 404 on miss), then
    writes ONE typed provenance edge via ``knowledge_mount.embed`` — the same
    verb the CLI uses, so the edge-writing logic is never re-built at the HTTP
    boundary.
    """
    from molexp.workspace import knowledge_mount
    from molexp.workspace.doc_embed import default_role_for

    bundle = _bundle(workspace)
    note = _resolve_note(bundle, path)
    target = _resolve_embed_target(bundle, workspace, body.target_kind, body.target)
    # Resolve the effective role the same way ``knowledge_mount.embed`` will, so
    # the echoed response reports the edge that was actually written.
    role = body.role if body.role is not None else default_role_for(target)
    knowledge_mount.embed(note, target, root=bundle.root, role=role)
    after_mutation(workspace, "knowledge", ref=path)
    return EmbedResponse(srcPath=path, target=body.target, role=role)


@router.put(
    "/doc",
    response_model=NoteDetailResponse,
    dependencies=[Depends(_require_writable)],
)
def edit_doc(
    payload: DocBodyUpdate,
    path: str = Query(..., description="The note Concept's bundle-relative path (its identity)."),
    workspace: Workspace = Depends(get_workspace),
) -> NoteDetailResponse:
    """Rewrite a note's body (its ``index.md``) — delegates to ``Note.set_body``."""
    bundle = _bundle(workspace)
    note = _resolve_note(bundle, path)
    note.set_body(payload.body)
    after_mutation(workspace, "knowledge", ref=path)
    return _note_detail(bundle, workspace, note, path)


@router.patch(
    "/doc",
    response_model=NoteSummary,
    dependencies=[Depends(_require_writable)],
)
def move_doc(
    payload: DocMoveRequest,
    path: str = Query(..., description="The note Concept's bundle-relative path (its identity)."),
    workspace: Workspace = Depends(get_workspace),
) -> NoteSummary:
    """Rename and/or reparent a note — delegates to ``Bundle.rename_note`` / ``move_note``."""
    bundle = _bundle(workspace)
    note = _resolve_note(bundle, path)
    if payload.name is not None:
        bundle.rename_note(note, payload.name)
    if payload.parentPath is not None:
        bundle.move_note(note, _resolve_note(bundle, payload.parentPath))
    after_mutation(workspace, "knowledge", ref=bundle.rel_path(note))
    return _note_summary(bundle, note)


@router.patch(
    "/doc/meta",
    response_model=NoteSummary,
    dependencies=[Depends(_require_writable)],
)
def update_doc_meta(
    payload: DocMetaUpdate,
    path: str = Query(..., description="The note Concept's bundle-relative path (its identity)."),
    workspace: Workspace = Depends(get_workspace),
) -> NoteSummary:
    """Update a note's tags/status — delegates to ``Note.set_tags`` / ``Note.set_status``.

    Each field is applied only when present (``None`` = leave untouched), so a
    partial update preserves the sibling field. The write logic is never re-built
    here: the same ``Note`` verbs the CLI uses own it (the Python==UI invariant).
    """
    bundle = _bundle(workspace)
    note = _resolve_note(bundle, path)
    if payload.tags is not None:
        note.set_tags(payload.tags)
    if payload.status is not None:
        note.set_status(payload.status)
    after_mutation(workspace, "knowledge", ref=path)
    return _note_summary(bundle, note)


@router.delete(
    "/doc",
    response_model=MessageResponse,
    dependencies=[Depends(_require_writable)],
)
def delete_doc(
    path: str = Query(..., description="The note Concept's bundle-relative path (its identity)."),
    workspace: Workspace = Depends(get_workspace),
) -> MessageResponse:
    """Delete a note (its directory subtree) — delegates to ``Bundle.delete_note``."""
    bundle = _bundle(workspace)
    note = _resolve_note(bundle, path)
    bundle.delete_note(note)
    after_mutation(workspace, "knowledge", ref=path)
    return MessageResponse(message=f"note {path!r} deleted")


@router.get("/backlinks", response_model=BacklinksResponse)
def get_backlinks(
    path: str = Query(..., description="The target Concept's bundle-relative path (its identity)."),
    workspace: Workspace = Depends(get_workspace),
) -> BacklinksResponse:
    """Return every Concept linking at *path* — delegates to ``Bundle.backlinks``."""
    from molexp.workspace.errors import ConceptNotFoundError

    bundle = _bundle(workspace)
    try:
        concept = bundle.get(path)
    except ConceptNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"concept {path!r} not found") from exc

    backlinks: list[NoteSummary] = []
    for link in bundle.backlinks(concept):
        source = link.source
        body = source.read_index() or ""
        backlinks.append(
            NoteSummary(
                name=source.name,
                relPath=bundle.rel_path(source),
                excerpt=body[:_EXCERPT_CHARS],
            )
        )
    return BacklinksResponse(backlinks=backlinks)


@router.get("/doc/export")
def export_doc(
    path: str = Query(..., description="The note Concept's bundle-relative path (its identity)."),
    workspace: Workspace = Depends(get_workspace),
) -> PlainTextResponse:
    """Export a note as portable Markdown — delegates to ``Bundle.export_markdown``."""
    bundle = _bundle(workspace)
    note = _resolve_note(bundle, path)
    markdown = bundle.export_markdown(note)
    filename = f"{note.name}.md"
    return PlainTextResponse(
        content=markdown,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
