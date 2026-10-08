"""Knowledge routes — browse + author the workspace's OKF documents.

Documents are markdown files under a host's ``knowledges/`` directory. Create,
embed, rename, move, delete, backlinks and export call the knowledge verbs
(``write_knowledge`` / ``append_link`` / ``Concept.rename`` / ``move_to`` /
``delete`` / ``backlinks`` / ``export``). ``entity_backlinks`` calls
``backlinks_to``.

A host's ``manuscript/*.tex`` and ``knowledges/*.tex`` are listed and opened
read-only beside those documents. Knowledge verbs do not write them.

Each mutating handler is gated by :func:`_require_writable` (405 against a
remote/read-only served workspace). A missing document is a 404.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path as _StdPath
from typing import TYPE_CHECKING, Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from molab.knowledge.concepts import Note
from molab.knowledge.edges import EdgeRole
from molab.server.dependencies import get_workspace
from molab.workspace import Workspace

from ..deps.served import active_served_key, assert_workspace_writable
from ..schemas import MessageResponse

if TYPE_CHECKING:
    from molab.knowledge.concept import Concept
    from molab.workspace.domain import Asset
    from molab.workspace.folder import Folder

__all__ = ["router"]

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

_LOG = logging.getLogger(__name__)
_EXCERPT_CHARS = 320


class NoteSummary(BaseModel):
    name: str
    relPath: str
    hostPath: str = ""
    excerpt: str
    tags: list[str] = []
    status: str | None = None
    cls: str = "Note"


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
    """A clickable summary card for an entity a document embeds."""

    kind: str
    id: str
    title: str
    relPath: str | None = None
    status: str | None = None
    ref: str | None = None
    missing: bool = False


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
    # ``None`` defers to :func:`molab.knowledge.embed.default_role_for`
    # (run/experiment -> records, reference -> cites, asset/other -> references).
    # An explicit role overrides.
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
    hostPath: str | None = None


class DocBodyUpdate(BaseModel):
    body: str


class DocMoveRequest(BaseModel):
    name: str | None = None
    hostPath: str | None = None


class DocMetaUpdate(BaseModel):
    """Partial update of a document's tags/status.

    Each field is independently optional; ``None`` means "leave untouched", which
    maps onto ``Note.set_tags`` / ``Note.set_status`` each preserving the sibling
    field. A request with both ``None`` is a no-op that returns the current summary.
    """

    tags: list[str] | None = None
    status: str | None = None


class BacklinksResponse(BaseModel):
    backlinks: list[NoteSummary]


def _path_of(target: object) -> str:
    """Directory or file *target* names, without resolving a path."""
    from molab.knowledge.concept import Concept

    if isinstance(target, Concept):
        return str(target.path)
    if isinstance(target, (str, os.PathLike)):
        return os.fspath(target)
    resolve = getattr(target, "resolve", None)
    if callable(resolve):
        return str(resolve())
    return str(target)


def _rel(workspace: Workspace, path: object) -> str:
    """*path* relative to the workspace root, as a posix string."""
    return _StdPath(_path_of(path)).relative_to(_StdPath(str(workspace.root))).as_posix()


def _host_rel(workspace: Workspace, doc_path: object) -> str:
    """Host of *doc_path* relative to the workspace root. ``.`` is ``""``."""
    from molab.knowledge.location import host_of

    host = host_of(_path_of(doc_path))
    try:
        rel = _StdPath(str(host)).relative_to(_StdPath(str(workspace.root))).as_posix()
    except ValueError:
        return ""
    return "" if rel == "." else rel


def _resolve_host(workspace: Workspace, host_path: str | None) -> str:
    """Absolute path of *host_path*, or the workspace root when it is empty.

    Raises:
        HTTPException: 404 when *host_path* is not a host ``list_hosts`` yields.
    """
    if host_path is None or host_path == "":
        return str(workspace.root)
    root = _StdPath(str(workspace.root))
    for host in Workspace.list_hosts(workspace.root, fs=workspace.fs):
        try:
            rel = _StdPath(str(host)).relative_to(root).as_posix()
        except ValueError:
            continue
        if rel == ".":
            rel = ""
        if rel == host_path:
            return workspace.fs.join(str(workspace.root), host_path)
    raise HTTPException(status.HTTP_404_NOT_FOUND, f"host {host_path!r} not found")


def _require_writable(request: Request) -> None:
    """Reject a mutating request against a remote (read-only) served workspace.

    The flat ``/knowledge`` router is not under the ``/workspaces/{ws}`` scoped
    router, so it carries its own write-gate: it 405s a mutating verb against a
    remote served workspace (via :func:`assert_workspace_writable`); a local /
    unmanaged workspace stays writable. Safe methods pass through untouched.
    """
    assert_workspace_writable(active_served_key() or "", request.method)


def _note_summary(workspace: Workspace, note: Concept) -> NoteSummary:
    """Build a :class:`NoteSummary` for *note* (identity + host + excerpt)."""
    body = note.read() or ""
    status_val = note.status() if isinstance(note, Note) else None
    return NoteSummary(
        name=note.name,
        relPath=_rel(workspace, note.path),
        hostPath=_host_rel(workspace, note.path),
        excerpt=body[:_EXCERPT_CHARS],
        tags=note.tags(),
        status=status_val,
        cls=type(note).__name__,
    )


def _note_detail(workspace: Workspace, note: Concept, path: str) -> NoteDetailResponse:
    """Build a :class:`NoteDetailResponse` for *note* at its identity *path*."""
    return NoteDetailResponse(
        name=note.name,
        relPath=path,
        body=note.read(),
        links=list(note.out_edges()),
        cards=_resolve_cards(workspace, note),
    )


def _resolve_cards(workspace: Workspace, note: Concept) -> list[EntityCard]:
    """Resolve *note*'s typed out-edges to :class:`EntityCard` summary cards."""
    cards: list[EntityCard] = []
    for edge in note.links():
        card = _resolve_edge_entity(workspace, edge)
        if card is not None:
            cards.append(card)
    return cards


def _resolve_edge_entity(workspace: Workspace, edge: object) -> EntityCard | None:
    """One card for *edge*, or ``None`` when the edge is not a card."""
    from molab.knowledge.edges import Edge
    from molab.workspace.refs import is_ref

    if not isinstance(edge, Edge):
        return None
    if is_ref(edge.target):
        return _ref_card(workspace, edge.target)
    if edge.target.startswith(("http://", "https://")):
        return None
    return _path_card(workspace, edge.target)


def _ref_tail(target: str) -> str:
    """The last segment of a reference, ignoring a fragment."""
    return target.split("#", 1)[0].rstrip("/").rsplit("/", 1)[-1]


def _ref_card(workspace: Workspace, target: str) -> EntityCard:
    """A card for a reference edge. A bad edge is ``missing``, never a failed GET."""
    from molab.knowledge.concept import Concept
    from molab.knowledge.embed import summarize_entity
    from molab.server.schemas.responses import workspace_relative
    from molab.workspace.domain import Artifact, Asset, Execution
    from molab.workspace.errors import AmbiguousRefError, RefNotFoundError
    from molab.workspace.folder import Folder
    from molab.workspace.refs import InvalidRefError, parse_ref

    body = target.split("#", 1)[0]
    try:
        parsed = parse_ref(body)
    except InvalidRefError:
        return EntityCard(kind="ref", id=_ref_tail(target), title=target, ref=target, missing=True)
    try:
        entity = workspace.find(body)
    except RefNotFoundError:
        return EntityCard(
            kind=parsed.kind, id=_ref_tail(target), title=target, ref=target, missing=True
        )
    except AmbiguousRefError as exc:
        _LOG.warning("ambiguous reference %s (%d candidates)", target, len(exc.candidates))
        return EntityCard(
            kind=parsed.kind,
            id=_ref_tail(target),
            title=f"{target} (ambiguous: {len(exc.candidates)} candidates)",
            ref=target,
            missing=True,
        )
    if isinstance(entity, (Concept, Folder, Asset)):
        title = summarize_entity(entity).title
    elif isinstance(entity, Artifact):
        title = entity.name
    elif isinstance(entity, Execution):
        title = entity.id
    else:
        title = _ref_tail(target)
    rel = (
        workspace_relative(workspace.root, entity.resolve()) if isinstance(entity, Folder) else None
    )
    return EntityCard(
        kind=parsed.kind,
        id=_ref_tail(target),
        title=title,
        relPath=rel,
        ref=target,
        missing=False,
    )


def _document_card(workspace: Workspace, document: Concept) -> EntityCard:
    """A card for a knowledge document, as a path edge resolves one."""
    from molab.knowledge.embed import summarize_entity

    summary = summarize_entity(document)
    return EntityCard(
        kind=summary.kind,
        id=summary.id,
        title=summary.title,
        relPath=_rel(workspace, document),
        status=_entity_status(document),
    )


def _path_card(workspace: Workspace, target: str) -> EntityCard | None:
    """A path edge: a document, a missing document, a legacy directory, or nothing."""
    from molab.knowledge import Knowledge
    from molab.knowledge.errors import KnowledgeNotFoundError

    path = target.split("#", 1)[0]
    try:
        document = Knowledge.open(path, fs=workspace.fs)
    except (KnowledgeNotFoundError, FileNotFoundError, OSError, ValueError):
        document = None
    else:
        return _document_card(workspace, document)
    if workspace.fs.is_dir(path) or workspace.fs.is_file(path):
        return None
    name = _StdPath(path).name or path
    return EntityCard(kind="document", id=name, title=target, missing=True)


def _entity_status(entity: Concept | Folder | Asset) -> str | None:
    """A ``Note`` entity's lifecycle status; ``None`` for anything else."""
    return entity.status() if isinstance(entity, Note) else None


def _resolve_embed_entity(
    workspace: Workspace, target_kind: str, target: str
) -> Concept | Folder | Asset:
    """Resolve an embed ``(target_kind, target)`` to a live entity.

    A run target must be a reference. An experiment or asset target is a
    reference, or a bare id resolved by :meth:`Workspace.find`. A miss, an
    ambiguity, or a malformed reference propagates to the process-wide handlers.
    """
    from molab.workspace.refs import REF_SCHEME, MolabRef, is_ref, parse_ref

    if target_kind == "reference":
        try:
            return _open_doc(workspace, target)
        except HTTPException as exc:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, f"reference {target!r} not found"
            ) from exc

    if target_kind == "run":
        if not is_ref(target):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"a run target must be a {REF_SCHEME} reference",
            )
        return workspace.find(parse_ref(target, kind="run"))  # ty: ignore[invalid-return-type]
    if target_kind == "experiment":
        ref = (
            parse_ref(target, kind="experiment")
            if is_ref(target)
            else MolabRef(experiment_id=target)
        )
        return workspace.find(ref)  # ty: ignore[invalid-return-type]
    ref = parse_ref(target, kind="asset") if is_ref(target) else MolabRef(asset_id=target)
    return workspace.find(ref)  # ty: ignore[invalid-return-type]


def _open_doc(workspace: Workspace, path: str) -> Concept:
    """Open any of the six Knowledge classes at *path* (404 on miss)."""
    from molab.knowledge import Knowledge, KnowledgeNotFoundError

    try:
        return Knowledge.open(workspace.fs.join(str(workspace.root), path), fs=workspace.fs)
    except (KnowledgeNotFoundError, FileNotFoundError, OSError) as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"note {path!r} not found") from exc


def _reject_tex(path: str) -> None:
    """Refuse a knowledge write verb on a TeX file.

    Raises:
        HTTPException: 405 when *path* is ``.tex`` or ``.ltx``.
    """
    from molab.knowledge.tex_docs import is_tex_file

    if is_tex_file(path):
        raise HTTPException(
            status.HTTP_405_METHOD_NOT_ALLOWED,
            "a TeX file is shown in knowledge and is not edited there",
        )


def _tex_text(workspace: Workspace, path: str) -> str:
    """Read a workspace-relative TeX file (404 when it is missing or escapes)."""
    from molab.knowledge.concept import read_text_or_none
    from molab.knowledge.tex_docs import is_tex_file

    pure = _StdPath(path)
    if not is_tex_file(path) or pure.is_absolute() or ".." in pure.parts:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"note {path!r} not found")
    absolute = workspace.fs.join(str(workspace.root), path)
    try:
        _StdPath(absolute).relative_to(_StdPath(str(workspace.root)))
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"note {path!r} not found") from exc
    text = read_text_or_none(absolute, fs=workspace.fs)
    if text is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"note {path!r} not found")
    return text


def _tex_detail(workspace: Workspace, path: str) -> NoteDetailResponse:
    """A TeX file as a read-only note detail. The body is the file itself."""
    return NoteDetailResponse(
        name=_StdPath(path).stem,
        relPath=path,
        body=_tex_text(workspace, path),
        links=[],
        cards=[],
    )


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
    """Knowledge documents citing one entity.

    Pure derived read (no reverse index persisted): resolves the entity
    folder, then walks documents whose edges point at its reference.
    404 on an unresolvable entity — never an empty-list fallback
    for a bad ref.
    """
    from molab.knowledge.concept import backlinks_to
    from molab.knowledge.search import extract_title
    from molab.workspace.errors import (
        ExperimentNotFoundError,
        ProjectNotFoundError,
        RunNotFoundError,
    )
    from molab.workspace.refs import ref_of

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

    rows: list[EntityBacklinkRow] = []
    for link in backlinks_to(
        [str(ref_of(entity))],
        within=workspace.root,
        fs=workspace.fs,
    ):
        narrative = link.source.read() or ""
        front = link.source.frontmatter()
        kind_name = front.get("class") or front.get("type") or type(link.source).__name__
        rows.append(
            EntityBacklinkRow(
                path=_rel(workspace, link.source),
                title=extract_title(narrative) or link.source.name,
                type=str(kind_name),
                role=str(link.role),
            )
        )
    return EntityBacklinksResponse(entity=f"{kind}:{run_id or experiment_id}", backlinks=rows)


class KnowledgeSearchRow(BaseModel):
    """One search hit projected from a search-index row."""

    path: str
    title: str
    type: str
    tags: list[str] = []
    snippet: str | None = None


class KnowledgeSearchResponse(BaseModel):
    """``GET /knowledge/search`` — body-aware retrieval over the documents."""

    hits: list[KnowledgeSearchRow]
    truncated: bool


@router.get("/search", response_model=KnowledgeSearchResponse)
def search_knowledge(
    q: Annotated[str, Query(description="Case-insensitive needle (path/title/tags/body).")],
    type: Annotated[str | None, Query(description="Exact Knowledge class name.")] = None,
    tag: Annotated[str | None, Query(description="Only documents carrying this tag.")] = None,
    workspace: Workspace = Depends(get_workspace),
) -> KnowledgeSearchResponse:
    """Search the workspace knowledge tree — wraps ``Knowledge.search``."""
    from molab.knowledge import Knowledge
    from molab.knowledge.concepts import parse_class

    cls = parse_class(type) if type else None
    result = Knowledge(workspace.root, fs=workspace.fs).search(q, of=cls, tag=tag)
    return KnowledgeSearchResponse(
        hits=[
            KnowledgeSearchRow(
                path=hit.entry.path,
                title=hit.entry.title or hit.entry.path,
                type=hit.entry.type,
                tags=list(hit.entry.tags),
                snippet=hit.snippet,
            )
            for hit in result.hits
        ],
        truncated=result.truncated,
    )


@router.get("", response_model=KnowledgeListResponse)
def list_knowledge(
    tag: Annotated[str | None, Query(description="Only notes carrying this tag.")] = None,
    status: Annotated[
        str | None, Query(description="Only notes with this lifecycle status.")
    ] = None,
    workspace: Workspace = Depends(get_workspace),
) -> KnowledgeListResponse:
    """List every Knowledge document, plus each host's TeX manuscripts."""
    from molab.knowledge import Knowledge, Literature
    from molab.knowledge.concept import read_text_or_none
    from molab.knowledge.tex_docs import TEX_CLASS, iter_tex_documents, tex_host_path

    root = Knowledge(workspace.root, fs=workspace.fs)
    notes: list[NoteSummary] = []
    references: list[ReferenceSummary] = []
    for item in root.walk():
        rel = _rel(workspace, item.path)
        tags = item.tags()
        if tag is not None and tag not in tags:
            continue
        status_val = item.status() if isinstance(item, Note) else None
        if status is not None and status_val != status:
            continue
        body = item.read() or ""
        notes.append(
            NoteSummary(
                name=item.name,
                relPath=rel,
                hostPath=_host_rel(workspace, item.path),
                excerpt=body[:_EXCERPT_CHARS],
                tags=tags,
                status=status_val,
                cls=type(item).__name__,
            )
        )
        if isinstance(item, Literature):
            meta = item.record
            references.append(
                ReferenceSummary(
                    name=item.name,
                    relPath=rel,
                    title=meta.title,
                    authors=list(meta.authors),
                    year=meta.year,
                    doi=meta.doi,
                    venue=meta.venue,
                    url=meta.url,
                    source=meta.source,
                )
            )

    if tag is None and status is None:
        for absolute in iter_tex_documents(workspace.root, workspace.fs):
            rel = _rel(workspace, absolute)
            text = read_text_or_none(absolute, fs=workspace.fs) or ""
            notes.append(
                NoteSummary(
                    name=_StdPath(rel).stem,
                    relPath=rel,
                    hostPath=tex_host_path(rel),
                    excerpt=text[:_EXCERPT_CHARS],
                    cls=TEX_CLASS,
                )
            )

    notes.sort(key=lambda n: n.name)
    references.sort(key=lambda r: (r.year or 0, r.name), reverse=True)
    return KnowledgeListResponse(notes=notes, references=references, total=len(notes))


@router.get("/note", response_model=NoteDetailResponse)
def get_note(
    path: str = Query(..., description="The document's workspace-relative path (its identity)."),
    workspace: Workspace = Depends(get_workspace),
) -> NoteDetailResponse:
    """Return one document's full body via ``Knowledge.open``.

    A ``.tex`` / ``.ltx`` path is the file bytes, not a Knowledge document.
    """
    from molab.knowledge.tex_docs import is_tex_file

    if is_tex_file(path):
        return _tex_detail(workspace, path)
    concept = _open_doc(workspace, path)
    return _note_detail(workspace, concept, path)


# ── Document authoring — knowledge verbs, one host per document ───────────────


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
    """Create a :class:`Note` under *hostPath* (the workspace root when omitted)."""
    from molab.knowledge.write import write_knowledge

    host = _resolve_host(workspace, body.hostPath)
    note = write_knowledge(
        host,
        name=body.name,
        of=Note,
        created_by="ui",
        text=body.body,
        fs=workspace.fs,
    )
    return _note_summary(workspace, note)


@router.post(
    "/doc/embed",
    response_model=EmbedResponse,
    dependencies=[Depends(_require_writable)],
)
def embed_doc(
    body: EmbedRequest,
    path: str = Query(
        ..., description="The source note Concept's workspace-relative document path."
    ),
    workspace: Workspace = Depends(get_workspace),
) -> EmbedResponse:
    """Embed a live entity into a document — one typed edge via ``append_link``.

    Resolves the source document (404 on miss) and the target entity
    (``run`` / ``experiment`` / ``asset`` / ``reference``; 404 on miss), then
    writes ONE typed provenance edge at the target resolved by
    :func:`~molab.knowledge.embed.resolve_embed_target`.
    """
    _reject_tex(path)
    from molab.knowledge.concept import append_link
    from molab.knowledge.embed import default_role_for, resolve_embed_target

    doc = _open_doc(workspace, path)
    target = _resolve_embed_entity(workspace, body.target_kind, body.target)
    role = body.role if body.role is not None else default_role_for(target)
    append_link(doc, resolve_embed_target(target), role=role)
    return EmbedResponse(srcPath=path, target=body.target, role=role)


@router.put(
    "/doc",
    response_model=NoteDetailResponse,
    dependencies=[Depends(_require_writable)],
)
def edit_doc(
    payload: DocBodyUpdate,
    path: str = Query(
        ..., description="The note Concept's workspace-relative document path (its identity)."
    ),
    workspace: Workspace = Depends(get_workspace),
) -> NoteDetailResponse:
    """Rewrite a document's narrative — ``Knowledge.write`` for all six classes."""
    _reject_tex(path)
    doc = _open_doc(workspace, path)
    doc.write(payload.body)
    return _note_detail(workspace, doc, path)


@router.patch(
    "/doc",
    response_model=NoteSummary,
    dependencies=[Depends(_require_writable)],
)
def move_doc(
    payload: DocMoveRequest,
    path: str = Query(
        ..., description="The note Concept's workspace-relative document path (its identity)."
    ),
    workspace: Workspace = Depends(get_workspace),
) -> NoteSummary:
    """Rename and/or move a document onto another host."""
    _reject_tex(path)
    doc = _open_doc(workspace, path)
    try:
        if payload.name is not None:
            doc.rename(payload.name, within=workspace.root)
        if payload.hostPath is not None:
            doc.move_to(_resolve_host(workspace, payload.hostPath), within=workspace.root)
    except FileExistsError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _note_summary(workspace, doc)


@router.patch(
    "/doc/meta",
    response_model=NoteSummary,
    dependencies=[Depends(_require_writable)],
)
def update_doc_meta(
    payload: DocMetaUpdate,
    path: str = Query(
        ..., description="The note Concept's workspace-relative document path (its identity)."
    ),
    workspace: Workspace = Depends(get_workspace),
) -> NoteSummary:
    """Update a document's tags/status — ``Knowledge.write`` for all six classes."""
    _reject_tex(path)
    doc = _open_doc(workspace, path)
    if payload.tags is not None or payload.status is not None:
        doc.write(tags=payload.tags, status=payload.status)
    return _note_summary(workspace, doc)


@router.delete(
    "/doc",
    response_model=MessageResponse,
    dependencies=[Depends(_require_writable)],
)
def delete_doc(
    path: str = Query(
        ..., description="The note Concept's workspace-relative document path (its identity)."
    ),
    workspace: Workspace = Depends(get_workspace),
) -> MessageResponse:
    """Delete a document. Inbound links are left dangling."""
    _reject_tex(path)
    doc = _open_doc(workspace, path)
    doc.delete()
    return MessageResponse(message=f"note {path!r} deleted")


@router.get("/backlinks", response_model=BacklinksResponse)
def get_backlinks(
    path: str = Query(
        ..., description="The target Concept's workspace-relative document path (its identity)."
    ),
    workspace: Workspace = Depends(get_workspace),
) -> BacklinksResponse:
    """Return every document linking at *path*."""
    from molab.knowledge.tex_docs import is_tex_file

    if is_tex_file(path):
        _tex_text(workspace, path)
        return BacklinksResponse(backlinks=[])
    doc = _open_doc(workspace, path)
    backlinks = [
        _note_summary(workspace, link.source) for link in doc.backlinks(within=workspace.root)
    ]
    return BacklinksResponse(backlinks=backlinks)


@router.get("/doc/export")
def export_doc(
    path: str = Query(
        ..., description="The note Concept's workspace-relative document path (its identity)."
    ),
    workspace: Workspace = Depends(get_workspace),
) -> PlainTextResponse:
    """Export a document as its narrative markdown, or the TeX file itself."""
    from molab.knowledge.tex_docs import is_tex_file

    if is_tex_file(path):
        filename = _StdPath(path).name
        return PlainTextResponse(
            content=_tex_text(workspace, path),
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    doc = _open_doc(workspace, path)
    markdown = doc.export()
    filename = f"{doc.name}.md"
    return PlainTextResponse(
        content=markdown,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
