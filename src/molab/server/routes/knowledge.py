"""Knowledge routes — browse + author the workspace's OKF documents.

Documents are ``.md`` (YAML frontmatter + markdown) or ``.html`` files under a
host's ``knowledges/`` directory. Create,
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

import io
import json
import logging
import os
import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path as _StdPath
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Annotated, Any, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from molab.knowledge.concepts import LiteratureFields, Note
from molab.knowledge.edges import EdgeRole
from molab.server.dependencies import get_workspace
from molab.workspace import Workspace

from ..deps.served import active_served_key, assert_workspace_writable
from ..schemas import MessageResponse
from ..schemas._wire import KnowledgeClassName

if TYPE_CHECKING:
    from molab.knowledge.concept import Concept
    from molab.workspace.domain import Asset
    from molab.workspace.folder import Folder
    from molab.workspace.refs import MolabRef

__all__ = ["router"]

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

_LOG = logging.getLogger(__name__)
_EXCERPT_CHARS = 320

#: How a listed file is stored: a markdown or HTML document, or a TeX manuscript.
DocFormat = Literal["md", "html", "tex"]


class NoteSummary(BaseModel):
    name: str
    title: str = Field(
        default="",
        description="Display title: frontmatter `title`, else the first H1, else `name`.",
    )
    relPath: str
    hostPath: str = ""
    excerpt: str
    tags: list[str] = []
    status: str | None = None
    cls: str = Field(description="The knowledge class, or `Tex` for a TeX file.")
    format: DocFormat = "md"
    updatedAt: str | None = Field(
        default=None, description="ISO-8601 UTC time the file was last modified."
    )
    createdAt: str | None = Field(
        default=None,
        description="ISO-8601 UTC creation stamp (`created_at`); absent on older documents.",
    )


class ReferenceSummary(LiteratureFields):
    """A Literature row: its identity and its bibliographic fields."""

    name: str
    relPath: str


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
    detail: str | None = None
    ref: str | None = None
    missing: bool = False


class NoteDetailResponse(BaseModel):
    name: str
    relPath: str
    cls: str = Field(description="The knowledge class, or `Tex` for a TeX file.")
    body: str
    links: list[str]
    cards: list[EntityCard] = []
    fields: dict[str, Any] = Field(
        default_factory=dict,
        description="The fields the class declares, as stored (no common key).",
    )
    format: DocFormat = "md"
    updatedAt: str | None = Field(
        default=None, description="ISO-8601 UTC time the file was last modified."
    )
    createdAt: str | None = Field(
        default=None,
        description="ISO-8601 UTC creation stamp (`created_at`); absent on older documents.",
    )


class EmbedRequest(BaseModel):
    """Embed a live workspace entity into a document as one typed provenance edge."""

    target_kind: Literal["run", "asset", "experiment", "reference"]
    target: str
    # ``None`` defers to :func:`molab.knowledge.embed.default_role_for`
    # (run/experiment -> derived_from, reference -> cites, asset/other -> references).
    # An explicit role overrides.
    role: EdgeRole | None = None
    text: str | None = None


class EmbedResponse(BaseModel):
    """Echo of the written embed edge."""

    srcPath: str
    target: str
    role: EdgeRole


class DocCite(BaseModel):
    """One edge a new document carries from the moment it lands."""

    target: str = Field(
        description="A workspace-relative knowledge document path or an entity ref."
    )
    role: EdgeRole = "cites"


class DocCreateRequest(BaseModel):
    name: str
    body: str = ""
    hostPath: str | None = None
    format: Literal["md", "html"] = Field(
        default="md",
        description="`md` lands `<slug>.md`; `html` lands `<slug>.html` (body stored verbatim).",
    )
    cls: KnowledgeClassName = "Note"
    sources: list[str] = Field(
        default_factory=list,
        description="What the document rests on: entity refs, http(s) URLs or DOIs, and "
        "workspace-relative files. A sourced class given none names its host.",
    )
    fields: dict[str, Any] = Field(
        default_factory=dict,
        description="The fields the class declares (a Hypothesis `verdict`, a Literature's "
        "bibliography, a Note `status`); any other key is refused with 422.",
    )
    cites: list[DocCite] = Field(
        default_factory=list,
        description="Typed edges to write with the document. A target that names nothing "
        "here is refused with 422 and nothing lands.",
    )
    createdBy: str = "ui"


class DocMediaResponse(BaseModel):
    """Path of an uploaded figure, relative to the document."""

    path: str


class DocBodyUpdate(BaseModel):
    body: str


class DocFieldsResponse(BaseModel):
    """A document's own fields and the digest of the file they came from."""

    relPath: str
    cls: str
    fields: dict[str, Any]
    digest: str


class DocFieldsUpdate(BaseModel):
    """Replace a document's own fields whole; an omitted key is removed.

    ``ifMatch`` is the digest the caller read; a changed file answers 409.
    ``body`` optionally rewrites the narrative in the same write.
    """

    fields: dict[str, Any]
    ifMatch: str | None = None
    body: str | None = None


#: What a link points at. ``missing`` is a relative path with no file behind it.
LinkKind = Literal["document", "ref", "external", "missing"]


class DocRelation(BaseModel):
    """One narrative occurrence; its id is valid only with this file digest."""

    id: int
    target: str
    role: EdgeRole
    label: str
    kind: LinkKind


class DocRelationsResponse(BaseModel):
    relPath: str
    digest: str
    relations: list[DocRelation]


class DocRelationUpdate(BaseModel):
    action: Literal["add", "replace", "remove"]
    ifMatch: str = Field(min_length=1)
    id: int | None = Field(default=None, ge=0)
    target: str | None = None
    role: EdgeRole = "references"
    text: str | None = None


class DocMoveRequest(BaseModel):
    name: str | None = None
    hostPath: str | None = None


class DocMetaUpdate(BaseModel):
    """Set a document's tags; ``None`` leaves them untouched and returns the summary.

    A class's own fields (a Note ``status``) are ``PATCH /knowledge/doc/fields``.
    """

    model_config = ConfigDict(extra="forbid")

    tags: list[str] | None = None


class BacklinksResponse(BaseModel):
    backlinks: list[NoteSummary]


class KnowledgeGraphEdge(BaseModel):
    """One typed link from a document's narrative."""

    source: str = Field(description="`relPath` of the document holding the link.")
    target: str = Field(
        description=(
            "`relPath` of the linked document (`document`), the path the link names "
            "relative to the served root (`missing`), the reference verbatim (`ref`), "
            "or the URL verbatim (`external`)."
        )
    )
    role: EdgeRole
    kind: LinkKind


class KnowledgeGraphResponse(BaseModel):
    """``GET /knowledge/graph`` — every listed document and every typed link between them."""

    nodes: list[NoteSummary]
    edges: list[KnowledgeGraphEdge]


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


def _host_folder(workspace: Workspace, host_path: str | None) -> Folder:
    """The workspace, project, experiment, or run *host_path* names.

    Raises:
        HTTPException: 404 when *host_path* is not one of those folders.
    """
    wanted = host_path or ""
    if wanted == "":
        return workspace
    root = _StdPath(str(workspace.root))
    folders: list[Folder] = []
    for project in workspace.list_projects():
        folders.append(project)
        for experiment in project.list_experiments():
            folders.append(experiment)
            folders.extend(experiment.list_runs())
    for folder in folders:
        try:
            rel = _StdPath(str(folder.resolve())).relative_to(root).as_posix()
        except ValueError:
            continue
        if rel == wanted:
            return folder
    raise HTTPException(status.HTTP_404_NOT_FOUND, f"host {wanted!r} not found")


def _resolve_host(workspace: Workspace, host_path: str | None) -> str:
    """Absolute path of *host_path*, or the workspace root when it is empty.

    Raises:
        HTTPException: 404 when *host_path* is not a host folder.
    """
    return str(_host_folder(workspace, host_path).resolve())


def _file_source(workspace: Workspace, ref: str) -> object:
    """A workspace-relative file as a ``file`` source.

    The stored pointer is absolute so the writer can relativize the link from
    the new document. A path that leaves the workspace is rejected.
    """
    from molab.knowledge.knowledge_item import SourceRef

    text = ref.strip()
    pure = PurePosixPath(text)
    if not text or pure.is_absolute() or ".." in pure.parts:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"file source {ref!r} must be a path inside this workspace",
        )
    joined = workspace.fs.join(str(workspace.root), text)
    if not workspace.fs.is_file(joined):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"file source {ref!r} is not a file in this workspace",
        )
    root = _StdPath(workspace.fs.resolve(str(workspace.root)))
    absolute = _StdPath(workspace.fs.resolve(joined))
    try:
        absolute.relative_to(root)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"file source {ref!r} must be a path inside this workspace",
        ) from exc
    return SourceRef(kind="file", ref=str(absolute))


def _source_from_request(workspace: Workspace, text: str) -> object:
    """One create-request source as a :class:`SourceRef` that names something here.

    :meth:`SourceRef.parse` classifies it; a file must lie inside the
    workspace and an entity ref must resolve in it (422 otherwise).
    """
    from molab.knowledge.knowledge_item import SourceRef
    from molab.workspace.refs import parse_ref

    try:
        source = SourceRef.parse(text.strip())
        if source.kind == "file":
            return _file_source(workspace, source.ref)
        if source.kind != "reference":
            workspace.find(parse_ref(source.ref))
    except (LookupError, ValueError) as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"source {text!r} names nothing here: {exc}"
        ) from exc
    return source


def _cite_from_request(workspace: Workspace, cite: DocCite) -> tuple[Concept | MolabRef, EdgeRole]:
    """One create-request cite as the document or entity ref it names (422 otherwise)."""
    from molab.knowledge.concepts import _open_document
    from molab.workspace.refs import is_ref, parse_ref

    text = cite.target.strip()
    pure = PurePosixPath(text)
    if not is_ref(text) and (not text or pure.is_absolute() or ".." in pure.parts):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"cite {cite.target!r} must be an entity ref or a document path inside this workspace",
        )
    try:
        if is_ref(text):
            ref = parse_ref(text)
            workspace.find(ref)
            return ref, cite.role
        path = workspace.fs.join(str(workspace.root), text)
        return _open_document(path, fs=workspace.fs), cite.role
    except (LookupError, ValueError) as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"cite {cite.target!r} names nothing here: {exc}"
        ) from exc


_IMAGE_LINK = re.compile(r"!\[[^\]]*\]\((<)?([^)\s>]+)(>)?\)")
_IMAGE_TAG = re.compile(r"<img\b[^>]*?\bsrc\s*=\s*([\"'])([^\"']+)\1", re.IGNORECASE)
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
_MEDIA_LIMIT = 8 * 1024 * 1024


def _image_workspace_rel(doc_rel: str, src: str) -> str | None:
    """Workspace-relative path of a markdown image, or ``None`` when it is external."""
    text = src.strip()
    if not text or text.startswith(("#", "/")):
        return None
    if text.startswith(("http://", "https://", "data:", "/api/")):
        return None
    parts: list[str] = []
    for part in (PurePosixPath(doc_rel).parent / text).parts:
        if part == "..":
            if not parts:
                return None
            parts.pop()
        elif part not in {"", "."}:
            parts.append(part)
    return "/".join(parts) or None


def _card_facts(entity: object) -> tuple[str | None, str | None]:
    """``(status, detail)`` for a resolved card target."""
    from molab.workspace.domain import Asset
    from molab.workspace.run import Run

    if isinstance(entity, Note):
        return entity.status(), None
    if isinstance(entity, Run):
        params = entity.parameters
        detail: str | None = None
        if params:
            parts = [f"{key}={params[key]}" for key in sorted(params)]
            text = ", ".join(parts)
            detail = text if len(text) <= 160 else text[:157] + "…"
        return entity.status_label, detail
    if isinstance(entity, Asset):
        return None, entity.scope.kind
    return None, None


def _require_writable(request: Request) -> None:
    """Reject a mutating request against a remote (read-only) served workspace.

    The flat ``/knowledge`` router is not under the ``/workspaces/{ws}`` scoped
    router, so it carries its own write-gate: it 405s a mutating verb against a
    remote served workspace (via :func:`assert_workspace_writable`); a local /
    unmanaged workspace stays writable. Safe methods pass through untouched.
    """
    assert_workspace_writable(active_served_key() or "", request.method)


def _updated_at(workspace: Workspace, path: object) -> str | None:
    """The file's mtime as ISO-8601 UTC (seconds), or ``None`` when it cannot be read."""
    try:
        mtime = workspace.fs.stat(_path_of(path)).mtime
    except OSError:
        return None
    return datetime.fromtimestamp(mtime, tz=UTC).replace(microsecond=0).isoformat()


def _created_at(note: Concept) -> str | None:
    """The document's ``created_at`` stamp, or ``None`` when it has none."""
    value = note.frontmatter().get("created_at")
    return value if isinstance(value, str) and value else None


def _note_summary(workspace: Workspace, note: Concept) -> NoteSummary:
    """Build a :class:`NoteSummary` for *note* (identity + host + excerpt + times)."""
    from molab.knowledge.frontmatter import document_text
    from molab.knowledge.naming import document_format

    body = document_text(note.read() or "", path=note.path)
    status_val = note.status() if isinstance(note, Note) else None
    return NoteSummary(
        name=note.name,
        title=note.title(),
        relPath=_rel(workspace, note.path),
        hostPath=_host_rel(workspace, note.path),
        excerpt=body[:_EXCERPT_CHARS],
        tags=note.tags(),
        status=status_val,
        cls=type(note).__name__,
        format=document_format(note.path),
        updatedAt=_updated_at(workspace, note.path),
        createdAt=_created_at(note),
    )


def _note_detail(workspace: Workspace, note: Concept, path: str) -> NoteDetailResponse:
    """Build a :class:`NoteDetailResponse` for *note* at its identity *path*."""
    from molab.knowledge.fields import own_fields
    from molab.knowledge.naming import document_format

    return NoteDetailResponse(
        name=note.name,
        relPath=path,
        cls=type(note).__name__,
        body=note.read(),
        links=list(note.out_edges()),
        cards=_resolve_cards(workspace, note),
        fields=own_fields(note.frontmatter()),
        format=document_format(note.path),
        updatedAt=_updated_at(workspace, note.path),
        createdAt=_created_at(note),
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
    from molab.workspace.domain import Asset, Execution
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
    elif isinstance(entity, Execution):
        title = entity.id
    else:
        title = _ref_tail(target)
    rel = (
        workspace_relative(workspace.root, entity.resolve()) if isinstance(entity, Folder) else None
    )
    card_status, detail = _card_facts(entity)
    return EntityCard(
        kind=parsed.kind,
        id=_ref_tail(target),
        title=title,
        relPath=rel,
        status=card_status,
        detail=detail,
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
        status=_card_facts(document)[0],
    )


def _path_card(workspace: Workspace, target: str) -> EntityCard | None:
    """A path edge: a document, a missing document, a legacy directory, or nothing."""
    from molab.knowledge.concepts import _open_document
    from molab.knowledge.errors import KnowledgeNotFoundError

    path = target.split("#", 1)[0]
    try:
        document = _open_document(path, fs=workspace.fs)
    except (KnowledgeNotFoundError, FileNotFoundError, OSError, ValueError):
        document = None
    else:
        return _document_card(workspace, document)
    if workspace.fs.is_dir(path) or workspace.fs.is_file(path):
        return None
    name = _StdPath(path).name or path
    return EntityCard(kind="document", id=name, title=target, missing=True)


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
    """Open the Knowledge document at *path*: 404 on a miss, 422 when it names no class."""
    from molab.knowledge import KnowledgeNotFoundError
    from molab.knowledge.concepts import _open_document

    try:
        return _open_document(workspace.fs.join(str(workspace.root), path), fs=workspace.fs)
    except (KnowledgeNotFoundError, FileNotFoundError, OSError) as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"note {path!r} not found") from exc
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"{path!r} is not a knowledge document: {exc}"
        ) from exc


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
    body = _tex_text(workspace, path)
    from molab.knowledge.tex_docs import TEX_CLASS

    return NoteDetailResponse(
        name=_StdPath(path).stem,
        relPath=path,
        cls=TEX_CLASS,
        body=body,
        links=[],
        cards=[],
        format="tex",
        updatedAt=_updated_at(workspace, workspace.fs.join(str(workspace.root), path)),
    )


class EntityBacklinkRow(BaseModel):
    """One knowledge document citing the queried entity."""

    path: str
    title: str
    cls: str
    role: str


class EntityBacklinksResponse(BaseModel):
    """``GET /knowledge/entity-backlinks`` — who cites this entity?"""

    entity: str
    backlinks: list[EntityBacklinkRow]


@router.get("/entity-backlinks", response_model=EntityBacklinksResponse)
def entity_backlinks(
    kind: Annotated[Literal["run", "experiment", "asset"], Query(description="Entity kind.")],
    project_id: Annotated[str | None, Query(alias="projectId")] = None,
    experiment_id: Annotated[str | None, Query(alias="experimentId")] = None,
    run_id: Annotated[str | None, Query(alias="runId")] = None,
    asset_id: Annotated[str | None, Query(alias="assetId")] = None,
    workspace: Workspace = Depends(get_workspace),
) -> EntityBacklinksResponse:
    """Knowledge documents citing one entity.

    Pure derived read (no reverse index persisted): resolves the entity,
    then walks documents whose edges point at its reference. A run or an
    experiment needs ``projectId`` + ``experimentId`` (and ``runId``); an
    asset needs ``assetId`` alone, since its id is unique in the workspace.
    404 on an unresolvable entity — never an empty-list fallback
    for a bad ref.
    """
    from molab.workspace.errors import (
        AmbiguousRefError,
        ExperimentNotFoundError,
        ProjectNotFoundError,
        RefNotFoundError,
        RunNotFoundError,
    )
    from molab.workspace.refs import MolabRef, ref_of

    if kind == "asset":
        if not asset_id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "kind=asset requires assetId"
            )
        target = MolabRef(asset_id=asset_id)
        try:
            workspace.find(target)
        except RefNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
        except AmbiguousRefError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
        return EntityBacklinksResponse(
            entity=f"asset:{asset_id}", backlinks=_citing_rows(workspace, str(target))
        )
    if not project_id or not experiment_id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"kind={kind} requires projectId and experimentId",
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

    return EntityBacklinksResponse(
        entity=f"{kind}:{run_id or experiment_id}",
        backlinks=_citing_rows(workspace, str(ref_of(entity))),
    )


def _citing_rows(workspace: Workspace, ref: str) -> list[EntityBacklinkRow]:
    """Knowledge documents whose links cite *ref*, one row each."""
    from molab.knowledge.concept import backlinks_to

    return [
        EntityBacklinkRow(
            path=_rel(workspace, link.source),
            title=link.source.title(),
            cls=type(link.source).__name__,
            role=str(link.role),
        )
        for link in backlinks_to([ref], within=workspace.root, fs=workspace.fs)
    ]


class KnowledgeSearchRow(BaseModel):
    """One search hit projected from a search-index row."""

    path: str
    title: str
    cls: str
    tags: list[str] = []
    snippet: str | None = None
    source: str = ""


class KnowledgeSearchResponse(BaseModel):
    """``GET /knowledge/search`` — body-aware retrieval over the documents."""

    hits: list[KnowledgeSearchRow]
    truncated: bool


@router.get("/search", response_model=KnowledgeSearchResponse)
def search_knowledge(
    q: Annotated[str, Query(description="Case-insensitive needle (path/title/tags/body).")],
    cls: Annotated[
        KnowledgeClassName | None, Query(description="Only documents of this class or a subclass.")
    ] = None,
    tag: Annotated[str | None, Query(description="Only documents carrying this tag.")] = None,
    workspace: Workspace = Depends(get_workspace),
) -> KnowledgeSearchResponse:
    """Search registered wikis and this workspace — the CLI's ``knowledge search``.

    The workspace corpus goes through ``Knowledge.search`` on the workspace
    disk. Registered sources are fused by :meth:`KnowledgeSourceStore.search`,
    which is the same function the CLI calls.
    """
    from molab.knowledge.concepts import _product
    from molab.knowledge.sources import KnowledgeSourceStore

    limit = 50
    hits = KnowledgeSourceStore(workspace.root).search(
        q,
        workspace_root=workspace.root,
        include_workspace=True,
        tag=tag,
        of=_product(cls) if cls else None,
        limit=limit,
        fs=workspace.fs,
    )
    return KnowledgeSearchResponse(
        hits=[
            KnowledgeSearchRow(
                path=hit.hit.entry.path,
                title=hit.hit.entry.title or hit.hit.entry.path,
                cls=hit.hit.entry.cls,
                tags=list(hit.hit.entry.tags),
                snippet=hit.hit.snippet,
                source=hit.source,
            )
            for hit in hits
        ],
        truncated=len(hits) >= limit,
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
        summary = _note_summary(workspace, item)
        if tag is not None and tag not in summary.tags:
            continue
        if status is not None and summary.status != status:
            continue
        rel = summary.relPath
        notes.append(summary)
        if isinstance(item, Literature):
            references.append(ReferenceSummary(name=item.name, relPath=rel, **dict(item.fields())))

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
                    format="tex",
                    updatedAt=_updated_at(workspace, absolute),
                )
            )

    notes.sort(key=lambda n: n.name)
    references.sort(key=lambda r: (r.year or 0, r.name), reverse=True)
    return KnowledgeListResponse(notes=notes, references=references, total=len(notes))


def _graph_edges(workspace: Workspace, doc: Concept, listed: set[str]) -> list[KnowledgeGraphEdge]:
    """The typed out-links of *doc* as graph edges, in narrative order.

    Classification is :meth:`Concept.scan_links`; nothing here reads markdown.
    A path link is an edge when it names a listed document or no file at all.
    A path to an existing file that is not listed (a data file, a directory, a
    document outside the served root) is not an edge. A fragment is dropped,
    and a link repeated with one role is one edge. The scan types an http(s)
    link only for ``cites`` / ``derived_from``; every other http(s) link is
    reported with the default role.

    Args:
        workspace: The served root; targets are spelled relative to it.
        doc: The document whose narrative is scanned.
        listed: ``relPath`` of every node of the graph.
    """
    from collections import Counter

    from molab.knowledge.edges import DEFAULT_EDGE_ROLE, Edge

    web = ("http://", "https://")
    scan = doc.scan_links(doc.read())
    links = list(scan.typed_concepts)
    typed_urls = Counter(edge.target for edge in links if edge.target.startswith(web))
    for url in scan.external:
        if typed_urls[url] > 0:
            typed_urls[url] -= 1
        else:
            links.append(Edge(target=url, role=DEFAULT_EDGE_ROLE))

    source = _rel(workspace, doc.path)
    root = str(workspace.root)
    missing = set(scan.missing)
    found: dict[tuple[str, EdgeRole, LinkKind], None] = {}
    for edge in links:
        kind: LinkKind
        if edge.is_ref:
            target, kind = edge.target, "ref"
        elif edge.target.startswith(web):
            target, kind = edge.target, "external"
        else:
            absolute = edge.target.split("#", 1)[0]
            target = PurePosixPath(os.path.relpath(absolute, root)).as_posix()
            if absolute in missing:
                kind = "missing"
            elif target in listed:
                kind = "document"
            else:
                continue
        found[(target, edge.role, kind)] = None
    return [
        KnowledgeGraphEdge(source=source, target=target, role=role, kind=kind)
        for target, role, kind in found
    ]


@router.get("/graph", response_model=KnowledgeGraphResponse)
def get_knowledge_graph(
    workspace: Workspace = Depends(get_workspace),
) -> KnowledgeGraphResponse:
    """The whole knowledge graph: the unfiltered listing as nodes, typed links as edges.

    Pure derived read. Nothing is indexed, and a TeX manuscript is a node with
    no out-links.
    """
    from molab.knowledge import Knowledge

    nodes = list_knowledge(tag=None, status=None, workspace=workspace).notes
    listed = {node.relPath for node in nodes}
    edges: list[KnowledgeGraphEdge] = []
    for doc in Knowledge(workspace.root, fs=workspace.fs).walk():
        edges.extend(_graph_edges(workspace, doc, listed))
    edges.sort(key=lambda edge: edge.source)
    return KnowledgeGraphResponse(nodes=nodes, edges=edges)


@router.get("/note", response_model=NoteDetailResponse)
def get_note(
    path: str = Query(..., description="The document's workspace-relative path (its identity)."),
    workspace: Workspace = Depends(get_workspace),
) -> NoteDetailResponse:
    """Return one document's full body.

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
    """Create one knowledge class under *hostPath* (the workspace root when omitted)."""
    from molab.knowledge.concepts import _product
    from molab.knowledge.write import normalize_sources, write_knowledge

    klass = _product(body.cls)
    host = _host_folder(workspace, body.hostPath)
    sources = normalize_sources(
        [_source_from_request(workspace, item) for item in body.sources],
        default_host=host,
        of=klass,
    )
    cites = [_cite_from_request(workspace, cite) for cite in body.cites]
    try:
        note = write_knowledge(
            str(host.resolve()),
            name=body.name,
            of=klass,
            sources=sources,
            created_by=body.createdBy or "ui",
            text=body.body,
            cite=cites,
            fields=body.fields,
            fs=workspace.fs,
            format=body.format,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
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
    writes ONE typed provenance edge to it.
    """
    _reject_tex(path)
    from molab.knowledge.concept import append_link
    from molab.knowledge.embed import default_role_for

    doc = _open_doc(workspace, path)
    target = _resolve_embed_entity(workspace, body.target_kind, body.target)
    role = body.role if body.role is not None else default_role_for(target)
    append_link(doc, target, role=role)
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
    """Rewrite a document's narrative — ``Knowledge.write`` for every knowledge class."""
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
    """Set a document's tags — ``Knowledge.write`` for every knowledge class."""
    _reject_tex(path)
    doc = _open_doc(workspace, path)
    if payload.tags is not None:
        doc.write(tags=payload.tags)
    return _note_summary(workspace, doc)


def _relation_path(workspace: Workspace, path: str) -> str:
    """Constrain authoring handles to workspace-relative paths."""
    candidate = PurePosixPath(path)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "path must be workspace-relative"
        )
    absolute = workspace.fs.join(str(workspace.root), path)
    root = PurePosixPath(workspace.fs.resolve(workspace.root))
    if not PurePosixPath(workspace.fs.resolve(absolute)).is_relative_to(root):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "path resolves outside the workspace"
        )
    return absolute


def _doc_relations(workspace: Workspace, path: str, doc: Concept) -> DocRelationsResponse:
    from molab.knowledge.fields import digest_of
    from molab.knowledge.relations import relation_links
    from molab.workspace.refs import is_ref

    digest = digest_of(doc)
    relations = []
    for link in relation_links(doc):
        kind: LinkKind
        if is_ref(link.target):
            target, kind = link.target, "ref"
        elif link.target.startswith(("http://", "https://")):
            target, kind = link.target, "external"
        else:
            absolute, separator, fragment = link.target.partition("#")
            target = PurePosixPath(os.path.relpath(absolute, str(workspace.root))).as_posix()
            if separator:
                target += f"#{fragment}"
            kind = "document" if workspace.fs.exists(absolute) else "missing"
        relations.append(
            DocRelation(
                id=link.id,
                target=target,
                role=link.role,
                label=link.label,
                kind=kind,
            )
        )
    if digest_of(doc) != digest:
        raise HTTPException(status.HTTP_409_CONFLICT, "Document changed while reading relations")
    return DocRelationsResponse(relPath=path, digest=digest, relations=relations)


@router.get("/doc/relations", response_model=DocRelationsResponse)
def get_doc_relations(
    path: str = Query(...),
    workspace: Workspace = Depends(get_workspace),
) -> DocRelationsResponse:
    """Editable typed narrative links and the digest they were read from."""
    _relation_path(workspace, path)
    _reject_tex(path)
    return _doc_relations(workspace, path, _open_doc(workspace, path))


@router.patch(
    "/doc/relations",
    response_model=DocRelationsResponse,
    dependencies=[Depends(_require_writable)],
)
def update_doc_relation(
    payload: DocRelationUpdate,
    path: str = Query(...),
    workspace: Workspace = Depends(get_workspace),
) -> DocRelationsResponse:
    """Edit the original markdown link; reject stale authoring with 409."""
    from molab.knowledge.fields import DigestConflictError
    from molab.knowledge.relations import mutate_relation
    from molab.workspace.refs import is_ref, parse_ref

    _relation_path(workspace, path)
    _reject_tex(path)
    doc = _open_doc(workspace, path)
    try:
        target = payload.target
        if payload.action == "add" and target:
            if is_ref(target):
                target = str(parse_ref(target))
            elif not target.startswith(("http://", "https://")):
                target = _relation_path(workspace, target)
                if not workspace.fs.exists(target):
                    raise ValueError("relation target does not exist")
        mutate_relation(
            doc,
            action=payload.action,
            if_match=payload.ifMatch,
            occurrence=payload.id,
            target=target,
            role=payload.role,
            text=payload.text,
        )
    except DigestConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return _doc_relations(workspace, path, doc)


@router.get("/doc/fields", response_model=DocFieldsResponse)
def get_doc_fields(
    path: str = Query(..., description="The document's workspace-relative path (its identity)."),
    workspace: Workspace = Depends(get_workspace),
) -> DocFieldsResponse:
    """A document's own fields and its file digest (for ``ifMatch``)."""
    from molab.knowledge.fields import digest_of, own_fields

    _reject_tex(path)
    doc = _open_doc(workspace, path)
    return DocFieldsResponse(
        relPath=path,
        cls=type(doc).__name__,
        fields=own_fields(doc.frontmatter()),
        digest=digest_of(doc),
    )


@router.patch(
    "/doc/fields",
    response_model=DocFieldsResponse,
    dependencies=[Depends(_require_writable)],
)
def replace_doc_fields(
    payload: DocFieldsUpdate,
    path: str = Query(..., description="The document's workspace-relative path (its identity)."),
    workspace: Workspace = Depends(get_workspace),
) -> DocFieldsResponse:
    """Replace a document's own fields whole — 409 when ``ifMatch`` is stale.

    The class's fields check them: a key it does not declare, or a value it
    refuses, answers 422. The change is recorded in the workspace history as
    ``knowledge.fields_replaced``.
    """
    from molab.knowledge.fields import DigestConflictError, own_fields, replace_fields

    _reject_tex(path)
    doc = _open_doc(workspace, path)
    try:
        digest = replace_fields(doc, payload.fields, if_match=payload.ifMatch, body=payload.body)
    except DigestConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return DocFieldsResponse(
        relPath=path, cls=type(doc).__name__, fields=own_fields(doc.frontmatter()), digest=digest
    )


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
    """Export a document: a markdown narrative, the HTML document, or the TeX file itself."""
    from molab.knowledge.tex_docs import is_tex_file

    if is_tex_file(path):
        filename = _StdPath(path).name
        return PlainTextResponse(
            content=_tex_text(workspace, path),
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    from molab.knowledge.naming import is_html_document

    doc = _open_doc(workspace, path)
    html = is_html_document(doc.path)
    filename = f"{doc.name}{PurePosixPath(str(doc.path)).suffix}"
    return PlainTextResponse(
        content=doc.export(),
        media_type="text/html; charset=utf-8" if html else "text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class DocPageResponse(BaseModel):
    """``GET /knowledge/doc/page``: one document as a self-contained HTML page."""

    title: str
    html: str = Field(description="The whole page; every asset it shows is inlined.")


@router.get("/doc/page", response_model=DocPageResponse)
def doc_page(
    path: str = Query(..., description="The document's workspace-relative path (its identity)."),
    workspace: Workspace = Depends(get_workspace),
) -> DocPageResponse:
    """Render a document the way a reader sees it, as one self-contained page.

    The same page ``molab knowledge serve --export`` writes: markdown rendered,
    sources listed, assets inlined. 404 when the document or an asset it shows
    is missing.
    """
    from molab.knowledge.preview import standalone_page

    doc = _open_doc(workspace, path)
    try:
        page = standalone_page(_StdPath(str(doc.path)), workspace)
    except (FileNotFoundError, LookupError) as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"{path!r} shows an asset that is missing: {exc}"
        ) from exc
    return DocPageResponse(title=page.title, html=page.html)


def _figure_name(raw: str | None) -> str:
    """A safe ``figs/`` filename, or 415 when the suffix is not an image."""
    name = _StdPath(raw or "image").name
    suffix = _StdPath(name).suffix.lower()
    if suffix not in _IMAGE_SUFFIXES:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"{suffix or 'file'} is not a figure",
        )
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", _StdPath(name).stem).strip(".-")[:80] or "image"
    return f"{stem}{suffix}"


@router.post(
    "/doc/media",
    response_model=DocMediaResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_require_writable)],
)
async def upload_doc_media(
    path: str = Query(..., description="The document the figure belongs to."),
    file: UploadFile = File(...),
    workspace: Workspace = Depends(get_workspace),
) -> DocMediaResponse:
    """Write one image beside the document, under ``knowledges/figs/``."""
    _reject_tex(path)
    doc = _open_doc(workspace, path)
    filename = _figure_name(file.filename)
    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "empty figure")
    if len(data) > _MEDIA_LIMIT:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "figure exceeds 8 MiB")
    host = _host_folder(workspace, _host_rel(workspace, doc.path))
    store = host.files
    rel = PurePosixPath("knowledges") / "figs" / filename
    stem, suffix = rel.stem, rel.suffix
    candidate = rel
    index = 2
    while workspace.fs.is_file(str(store.resolve(candidate.as_posix()))):
        candidate = rel.with_name(f"{stem}-{index}{suffix}")
        index += 1
    store.put(candidate.as_posix(), data)
    return DocMediaResponse(path=f"figs/{candidate.name}")


@router.get("/export")
def export_notebook(
    hostPath: str = Query(
        "",
        description="Workspace-relative host. Empty exports the workspace root's documents.",
    ),
    workspace: Workspace = Depends(get_workspace),
) -> StreamingResponse:
    """Zip one host's documents, the figures they cite, and an embed list."""
    from molab.knowledge import Knowledge
    from molab.knowledge.tex_docs import is_tex_file

    _host_folder(workspace, hostPath or None)
    wanted = hostPath or ""
    buffer = io.BytesIO()
    embeds: list[dict[str, object]] = []
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        seen: set[str] = set()
        for item in Knowledge(workspace.root, fs=workspace.fs).walk():
            rel = _rel(workspace, item.path)
            if is_tex_file(rel) or _host_rel(workspace, item.path) != wanted:
                continue
            text = workspace.fs.read_text(str(item.path))
            archive.writestr(rel, text)
            embeds.append(
                {
                    "path": rel,
                    "cards": [card.model_dump() for card in _resolve_cards(workspace, item)],
                }
            )
            sources = [match.group(2) for match in _IMAGE_LINK.finditer(text)]
            sources += [match.group(2) for match in _IMAGE_TAG.finditer(text)]
            for source in sources:
                image_rel = _image_workspace_rel(rel, source)
                if image_rel is None or image_rel in seen:
                    continue
                if PurePosixPath(image_rel).suffix.lower() not in _IMAGE_SUFFIXES:
                    continue
                absolute = workspace.fs.join(str(workspace.root), image_rel)
                if not workspace.fs.is_file(absolute):
                    continue
                seen.add(image_rel)
                archive.writestr(image_rel, workspace.fs.read_bytes(absolute))
        archive.writestr("embeds.json", json.dumps(embeds, indent=2) + "\n")
    payload = buffer.getvalue()
    label = PurePosixPath(wanted).name if wanted else "workspace"
    return StreamingResponse(
        io.BytesIO(payload),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{label}-notebook.zip"'},
    )
