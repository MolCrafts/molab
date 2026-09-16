"""Workspace routes for MolExp API."""

from __future__ import annotations

import mimetypes
from collections.abc import AsyncIterator, Iterator
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from molexp._typing import JSONValue
from molexp.fs.window import read_text_window
from molexp.services.workspace_read_model import WorkspaceReadModel
from molexp.workspace import ContextFocus, Workspace, assemble_workspace_context
from molexp.workspace.events import WorkspaceEvent, WorkspaceEventType, read_workspace_events
from molexp.workspace.fs_cached import CachedRemoteFileSystem, prefetch_workspace_indices
from molexp.workspace.fs_local import LocalFileSystem

from ..dependencies import (
    get_remote_fs_factory,
    get_workspace,
    get_workspace_target_registry,
    set_active_workspace_descriptor,
    set_workspace_path_override,
)
from ..deps.read_model import get_read_model
from ..executors import run_heavy
from ..http_cache import not_modified, weak_etag
from ..mutations import after_mutation
from ..preview import resolve_sidecar
from ..schemas import (
    FileContentResponse,
    TargetTestCheck,
    TargetTestResponse,
    WorkspaceContextResponse,
    WorkspaceInfoResponse,
    WorkspaceOpenLocalRequest,
    WorkspaceOpenRequest,
    WorkspaceRunRow,
    WorkspaceRunsResponse,
    WorkspaceSummaryResponse,
    WorkspaceTargetCreateRequest,
    WorkspaceTargetListResponse,
    WorkspaceTargetResponse,
    compute_workspace_runs_stats,
)
from ..workspace_targets import WorkspaceTarget

if TYPE_CHECKING:
    from molexp.harness.schemas import ApprovalDecision, ApprovalRequest


class DirectoryCreateRequest(BaseModel):
    folder_id: str = Field(..., description="Workspace folder ID or 'workspace'")
    path: str = Field(..., description="Relative path for new directory")


class FileContentUpdateRequest(BaseModel):
    folder_id: str = Field(..., description="Workspace folder ID or 'workspace'")
    path: str = Field(..., description="Relative path within the folder")
    content: str = Field(..., description="New file content")


router = APIRouter(prefix="/workspace", tags=["workspace"])

# The activity stream mounts at the literal ``/api/events`` (no ``/workspace``
# prefix) — same flat-router precedent as ``plans.flat_router``.
events_router = APIRouter(tags=["workspace"])


class WorkspaceEventResponse(BaseModel):
    """One workspace-timeline event (read side of the event spine).

    The ONE wire shape for spine reads — the per-run route
    (``GET /runs/{run_id}/events``) aliases this model, so the two surfaces
    can never drift (vision-loop-12).
    """

    model_config = ConfigDict(frozen=True)

    id: str
    seq: int
    type: str
    actor: str
    created_at: datetime
    payload: dict[str, JSONValue]
    refs: list[str]

    @classmethod
    def from_event(cls, event: WorkspaceEvent) -> WorkspaceEventResponse:
        """The one event→wire mapping (both routes call this — no drift)."""
        return cls(
            id=event.id,
            seq=event.seq,
            type=event.type,
            actor=event.actor,
            created_at=event.created_at,
            payload=event.payload,
            refs=event.refs,
        )


@events_router.get("/events", response_model=list[WorkspaceEventResponse])
def get_workspace_events(
    request: Request,
    response: Response,
    type: WorkspaceEventType | None = Query(default=None, description="Keep only this event type"),
    ref: str | None = Query(default=None, description="Keep only events referencing this id"),
    limit: int = Query(default=50, ge=1, le=500),
    workspace: Workspace = Depends(get_workspace),
) -> list[WorkspaceEventResponse]:
    """The workspace-wide activity stream, newest first.

    The global read over the event spine — the same shared
    :func:`molexp.workspace.events.read_workspace_events` code path the
    per-run route and ``molexp runs info`` use. A workspace with no timeline
    yet answers ``[]`` without creating the DB (reading is side-effect free).

    The timeline is append-only, so its ``max_seq`` is an exact validator: a
    poll that sees no new events answers 304 without materializing a row.
    """
    cached = not_modified(
        request, response, weak_etag("events", _events_seq(workspace), type, ref, limit)
    )
    if cached is not None:
        return cached  # type: ignore[return-value]
    events = read_workspace_events(workspace.root, type=type, ref=ref, limit=limit)
    return [WorkspaceEventResponse.from_event(e) for e in events]


def _events_seq(workspace: Workspace) -> int:
    """The spine's highest ``seq`` (``0`` when the workspace has no timeline)."""
    from molexp.workspace.events import (
        WORKSPACE_EVENTS_DB,
        WorkspaceEventLog,
        is_remote_root,
    )

    root = workspace.root
    if is_remote_root(root) or not (Path(root) / WORKSPACE_EVENTS_DB).exists():
        return 0
    try:
        return WorkspaceEventLog.open(root).max_seq()
    except Exception:
        return 0


@events_router.get("/workspace/events/stream")
async def stream_workspace_changes(
    since: int | None = Query(default=None, description="Resume after this spine ``seq``"),
    workspace: Workspace = Depends(get_workspace),
    read_model: WorkspaceReadModel = Depends(get_read_model),
) -> StreamingResponse:
    """SSE: one ``change`` frame per workspace change — the UI's invalidation signal.

    Replaces polling. The first frame is ``hello`` carrying the current view
    versions and spine ``seq``.

    ``replayed`` is the client's caught-up flag and means exactly one thing:
    **every** change after ``since`` is accounted for — either nothing happened
    (``since >= seq``) or the whole backlog follows as ``change`` frames. It is
    ``false`` whenever the client must invalidate its list queries once instead
    of trusting deltas: no ``since`` was given, or the backlog exceeded
    :data:`_REPLAY_LIMIT` and is therefore *not* sent at all. A partial replay
    is never paired with ``replayed: true``, so the client needs no cap of its
    own to second-guess this.

    A comment line every 15 s keeps proxies from idling the connection out.

    Subscribing marks the read model hot, so its background sweep keeps
    running while any tab is watching and goes quiet when none is.
    """
    import asyncio
    import json as _json

    from molexp.services.workspace_notify import subscribe_workspace_changes

    from ..shutdown import is_shutting_down

    root = str(workspace.resolve())
    read_model.touch()
    current_seq = _events_seq(workspace)
    replayed: list[WorkspaceEventResponse] = []
    caught_up = since is not None and since >= current_seq
    if since is not None and since < current_seq:
        # Ask for one more than we will send: getting it back is how we learn
        # the backlog outran the cap. The spine reads newest-first, so a
        # truncated read drops the *oldest* events after ``since`` — a hole in
        # the middle of the delta, not a short tail. Sending it anyway is the
        # bug this guards: the client would apply the surviving deltas, believe
        # itself current, and serve stale data until the next reconnect.
        backlog = read_workspace_events(workspace.root, after_seq=since, limit=_REPLAY_LIMIT + 1)
        if len(backlog) <= _REPLAY_LIMIT:
            replayed = [WorkspaceEventResponse.from_event(e) for e in backlog]
            caught_up = True
        # else: leave ``replayed`` empty and ``caught_up`` False — the client
        # invalidates its list queries once instead of trusting partial deltas.

    async def _generate() -> AsyncIterator[str]:
        hello = {
            "versions": read_model.versions(),
            "seq": current_seq,
            "replayed": caught_up,
        }
        yield f"event: hello\ndata: {_json.dumps(hello)}\n\n"
        for event in reversed(replayed):  # spine reads newest-first; replay in order
            frame = {
                "kind": _KIND_BY_EVENT.get(event.type, "all"),
                "ref": event.refs[0] if event.refs else None,
                "seq": event.seq,
            }
            yield f"event: change\ndata: {_json.dumps(frame)}\n\n"

        stream = subscribe_workspace_changes(root)
        idle = 0.0
        while True:
            try:
                # Poll finely but comment rarely: the wait is what notices a
                # shutdown or a disconnect, so a 15 s one would keep the
                # worker (and uvicorn's connection drain) hanging that long.
                change = await asyncio.wait_for(anext(stream), timeout=_STREAM_POLL_SECONDS)
            except TimeoutError:
                if is_shutting_down():
                    return
                idle += _STREAM_POLL_SECONDS
                if idle >= _KEEP_ALIVE_SECONDS:
                    idle = 0.0
                    read_model.touch()
                    yield ": keep-alive\n\n"
                continue
            except StopAsyncIteration:
                return
            idle = 0.0
            payload = {
                "kind": change.kind,
                "ref": change.ref,
                "seq": change.seq,
                "projectId": change.project_id,
                "experimentId": change.experiment_id,
                "runId": change.run_id,
                "versions": change.versions or read_model.versions(),
            }
            yield f"event: change\ndata: {_json.dumps(payload)}\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


#: How often the change stream wakes to check for shutdown / disconnect.
_STREAM_POLL_SECONDS = 1.0
#: How often an idle stream emits a comment so proxies keep it open.
_KEEP_ALIVE_SECONDS = 15.0
#: Most backlog events one reconnect will replay. A gap longer than this is
#: reported as *not* replayed rather than delivered in part — see
#: :func:`stream_workspace_changes`.
_REPLAY_LIMIT = 200

_KIND_BY_EVENT: dict[str, str] = {
    "run.created": "run",
    "run.started": "run",
    "run.failed": "run",
    "run.completed": "run",
    "run.cancelled": "run",
    "asset.added": "asset",
    "knowledge.created": "knowledge",
    "workflow.created": "experiment",
    "experiment.created": "experiment",
}


MAX_TEXT_BYTES = 2_000_000

MAX_BLOB_BYTES = 64 * 1024 * 1024
"""Image preview ceiling — above this the client should download, not preview."""

BLOB_CHUNK_BYTES = 1 << 20
"""Chunk size when streaming a blob off a remote filesystem."""

DEFAULT_DIR_ENTRIES = 2000
"""Children returned per directory before the node reports ``truncated``."""

MAX_DIR_ENTRIES = 10000
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}


def resolve_workspace_path(root: Path, path_str: str) -> Path:
    """Resolve a workspace-relative or absolute path within the workspace root."""
    raw_path = Path(path_str).expanduser()
    target = raw_path.resolve() if raw_path.is_absolute() else (root / path_str).resolve()
    if root not in target.parents and target != root:
        raise HTTPException(status_code=400, detail="Path is outside workspace root")
    return target


def resolve_workspace_path_via_fs(workspace, path_str: str) -> str:  # noqa: ANN001
    """Filesystem-aware variant of :func:`resolve_workspace_path`.

    Works for both local and remote workspaces by going through
    ``workspace._fs`` rather than ``pathlib.Path``.  For pure local
    workspaces (``_fs is LocalFileSystem``) it preserves the existing
    ``Path.resolve()`` containment check so symlink escapes are still
    caught.  For any non-local backend (e.g. a remote workspace wrapped
    in :class:`CachedRemoteFileSystem`) it does string-level
    containment against the remote root.
    """
    fs = workspace._fs
    root = str(workspace.root)
    if isinstance(fs, LocalFileSystem):
        resolved = resolve_workspace_path(Path(root).resolve(), path_str)
        return str(resolved)

    normalized_root = root.rstrip("/") or "/"
    if not path_str or path_str in {"/", "."}:
        return normalized_root

    if path_str.startswith("/"):
        candidate = path_str
    else:
        candidate = fs.join(normalized_root, path_str)
    candidate = candidate.rstrip("/")
    if candidate != normalized_root and not candidate.startswith(normalized_root + "/"):
        raise HTTPException(status_code=400, detail="Path is outside workspace root")
    return candidate


@router.get("/info", response_model=WorkspaceInfoResponse)
def get_workspace_info(
    request: Request,
    response: Response,
    workspace=Depends(get_workspace),  # noqa: ANN001
    read_model: WorkspaceReadModel = Depends(get_read_model),
) -> WorkspaceInfoResponse:
    """Get workspace information.

    Counts come from the read-model snapshots. ``assetCount`` used to trigger
    a full manifest scan of the workspace — on the bootstrap critical path, for
    one integer.
    """
    fs = getattr(workspace, "_fs", None)
    is_cached = isinstance(fs, CachedRemoteFileSystem)
    runs = read_model.runs()
    assets = read_model.assets()
    versions = read_model.versions()
    cached = not_modified(
        request, response, weak_etag("info", runs.version, assets.version, versions["knowledge"])
    )
    if cached is not None:
        return cached  # type: ignore[return-value]
    return WorkspaceInfoResponse(
        root=str(workspace.root),
        projectCount=len(runs.projects),
        assetCount=len(assets),
        versions=versions,
        connected=fs.connected if is_cached else None,
        indexed=fs.indexed if is_cached else None,
        ready=fs.ready if is_cached else None,
    )


@router.get("/context", response_model=WorkspaceContextResponse)
async def get_workspace_context(
    request: Request,
    response: Response,
    project_id: str | None = Query(default=None, alias="projectId"),
    experiment_id: str | None = Query(default=None, alias="experimentId"),
    run_id: str | None = Query(default=None, alias="runId"),
    workspace=Depends(get_workspace),  # noqa: ANN001
    read_model: WorkspaceReadModel = Depends(get_read_model),
) -> WorkspaceContextResponse:
    """The canonical structural workspace read-model (integration.md §1).

    A read-only projection assembled from authoritative workspace state — the one
    shape agents/planners/CLI/UI observe. ``ContextFocus`` is supplied by the
    caller via optional query params and is never persisted. ``/runs`` remains the
    specialized detailed run view (richer per-execution rows); this endpoint is the
    canonical *structure* and stays consistent with it.
    """
    focus = ContextFocus(project_id=project_id, experiment_id=experiment_id, run_id=run_id)
    runs, assets, knowledge = _context_snapshots(read_model)
    cached = not_modified(
        request,
        response,
        weak_etag(
            "context",
            runs.version,
            assets.version,
            knowledge.version,
            project_id,
            experiment_id,
            run_id,
        ),
    )
    if cached is not None:
        return cached  # type: ignore[return-value]
    context = await run_heavy(
        assemble_workspace_context,
        workspace,
        focus=focus,
        runs=runs,
        assets=assets,
        knowledge=knowledge,
    )
    return WorkspaceContextResponse.from_context(context)


def _context_snapshots(read_model: WorkspaceReadModel):  # noqa: ANN202
    """The three snapshots a context assembly reads from (built on first use)."""
    return read_model.runs(), read_model.assets(), read_model.knowledge()


@router.get("/copilot", response_model=WorkspaceSummaryResponse)
async def get_workspace_copilot(
    request: Request,
    response: Response,
    workspace=Depends(get_workspace),  # noqa: ANN001
    read_model: WorkspaceReadModel = Depends(get_read_model),
) -> WorkspaceSummaryResponse:
    """The read-only Workspace Copilot summary — structured state + ranked next-actions.

    A pure projection over the canonical ``WorkspaceContext``; it mutates nothing.
    Next-actions are **advisory** and separated from execution — high-risk ones are
    flagged ``requiresProposal`` (they must go through a ``ChangeProposal`` first).
    """
    from molexp.harness.copilot import summarize_workspace

    runs, assets, knowledge = _context_snapshots(read_model)
    cached = not_modified(
        request,
        response,
        weak_etag("copilot", runs.version, assets.version, knowledge.version),
    )
    if cached is not None:
        return cached  # type: ignore[return-value]

    def _summarize():  # noqa: ANN202
        return summarize_workspace(
            assemble_workspace_context(workspace, runs=runs, assets=assets, knowledge=knowledge)
        )

    return WorkspaceSummaryResponse.from_summary(await run_heavy(_summarize))


@router.get("/runs", response_model=WorkspaceRunsResponse)
def list_workspace_runs(
    request: Request,
    response: Response,
    project_id: str | None = Query(default=None, alias="projectId"),
    experiment_id: str | None = Query(default=None, alias="experimentId"),
    backend: str | None = Query(default=None, description="Filter by executor backend"),
    status: str | None = Query(default=None, description="Filter by run status"),
    limit: int = Query(default=500, ge=1, le=2000),
    offset: int = Query(default=0, ge=0, description="Rows to skip (pagination)"),
    read_model: WorkspaceReadModel = Depends(get_read_model),
) -> WorkspaceRunsResponse:
    """Cross-experiment list of runs, each with embedded execution attempts.

    Served from the read-model snapshot: rows are already ordered
    ``created_at`` desc and already parsed, so a warm request reads no files
    at all and an unchanged one answers 304. Plugins surface backend-specific
    columns via the ``backend`` / ``backendMetadata`` fields on each execution
    row.

    ``total`` is the number of rows **matching the filters**, not the size of
    the returned page — which is what makes ``offset`` usable for paging.
    """
    snapshot = read_model.runs()
    version = (
        snapshot.version_for_experiment(project_id, experiment_id)
        if project_id and experiment_id
        else snapshot.version
    )
    cached = not_modified(
        request,
        response,
        weak_etag("runs", version, project_id, experiment_id, backend, status, limit, offset),
    )
    if cached is not None:
        return cached  # type: ignore[return-value]

    if project_id and experiment_id:
        source = snapshot.experiment_rows(project_id, experiment_id)
    else:
        source = snapshot.rows

    matched = [
        row
        for row in source
        if (not project_id or row.project_id == project_id)
        and (not experiment_id or row.experiment_id == experiment_id)
        and (not status or row.status.lower() == status.lower())
    ]
    rows = [WorkspaceRunRow.from_row(row) for row in matched]
    if backend:
        rows = [r for r in rows if (r.backend or "").lower() == backend.lower()]

    total = len(rows)
    page = rows[offset : offset + limit]
    return WorkspaceRunsResponse(
        runs=page,
        stats=compute_workspace_runs_stats(rows),
        total=total,
        truncated=(offset + len(page)) < total,
    )


@router.get("/files")
def list_workspace_files(
    path: str = Query("", description="Workspace-relative path to list"),
    max_depth: int = Query(4, ge=0, le=8, description="Maximum recursion depth"),
    max_entries: int = Query(
        DEFAULT_DIR_ENTRIES,
        ge=1,
        le=MAX_DIR_ENTRIES,
        description="Maximum children returned per directory",
    ),
    include: str | None = Query(
        None,
        description="Comma-separated optional enrichments (e.g. 'catalog')",
    ),
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> dict:
    """Return a nested file tree rooted at the requested path.

    Routes through ``workspace._fs`` so remote workspaces (and the
    :class:`CachedRemoteFileSystem` mirror) work the same as local ones.

    With ``include=catalog``, file nodes that match a registered asset
    are enriched with ``assetId``, ``assetKind``, ``producerRunId`` and
    ``producerTaskId`` so the UI can render lineage chips inline.

    Children matching the workspace ``.gitignore`` cascade (plus a safety
    floor for ``node_modules`` / ``.git`` / venvs) are omitted so git-managed
    workspaces do not dump dependency trees into the UI.
    """
    from molexp.workspace.gitignore import load_gitignore_matcher

    fs = workspace._fs
    root = resolve_workspace_path_via_fs(workspace, "")
    requested = resolve_workspace_path_via_fs(workspace, path.lstrip("/"))
    if not fs.exists(requested):
        raise HTTPException(status_code=404, detail="Path not found")

    # Remote trees pay one SSH RTT per node. A deep walk over hundreds of run
    # dirs (trajectory.pt etc.) freezes the UI bootstrap. Cap remote depth
    # server-side; clients expand path-by-path for deeper levels.
    effective_depth = max_depth
    if isinstance(fs, CachedRemoteFileSystem) and max_depth > 4:
        effective_depth = 4

    # gitignore matcher is path-string based; pass the logical root.
    ignore = load_gitignore_matcher(Path(str(workspace.root)), fs=fs)

    include_set = {part.strip() for part in (include or "").split(",") if part.strip()}
    # Catalog enrichment is local-path keyed; skip on non-local FS for now
    # (remote asset scans still work via the catalog API, not inline chips).
    asset_index_by_abs: dict[str, dict] = {}
    if "catalog" in include_set and isinstance(fs, LocalFileSystem):
        from molexp.workspace.assets import scan

        from ._scope import resolve_scope_dir

        for asset in scan.scan_assets(workspace.root):
            scope_dir = resolve_scope_dir(workspace, asset.scope)
            if scope_dir is None:
                continue
            try:
                abs_path = (scope_dir / asset.path).resolve()
            except OSError:
                continue
            asset_index_by_abs[str(abs_path)] = {
                "assetId": asset.asset_id,
                "assetKind": asset.kind,  # type: ignore[attr-defined]
                "producerRunId": asset.producer.run_id if asset.producer else None,
                "producerTaskId": asset.producer.task_id if asset.producer else None,
                "hasPreviewSidecar": resolve_sidecar(abs_path) is not None,
            }

    root_norm = root.rstrip("/") or "/"

    def _rel_for(node_path: str) -> str | None:
        node = node_path.rstrip("/") or "/"
        if node == root_norm:
            return ""
        prefix = root_norm + "/"
        if not node.startswith(prefix):
            return None
        return node[len(prefix) :]

    def build_node(
        node_path: str, depth: int, *, _visited: set[str] | None = None
    ) -> dict[str, Any]:
        visited = _visited if _visited is not None else set()
        try:
            real = fs.resolve(node_path)
        except OSError:
            real = node_path
        if real in visited:
            return {
                "id": node_path,
                "name": fs.basename(node_path) or node_path,
                "path": node_path,
                "type": "folder",
                "size": None,
                "modified": None,
                "children": [],
            }
        visited.add(real)

        try:
            st = fs.stat(node_path)
            is_file = st.is_file
        except OSError:
            return {
                "id": node_path,
                "name": fs.basename(node_path) or node_path,
                "path": node_path,
                "type": "folder",
                "size": None,
                "modified": None,
                "children": [],
            }

        node: dict[str, Any] = {
            "id": node_path,
            "name": fs.basename(node_path) or node_path,
            "path": node_path,
            "type": "file" if is_file else "folder",
            "size": st.size if is_file else None,
            "modified": st.mtime,
        }
        if asset_index_by_abs:
            enrich = asset_index_by_abs.get(real)
            if enrich is not None:
                node.update(enrich)
        if not is_file and depth < effective_depth:
            children: list[dict[str, Any]] = []
            try:
                names = fs.listdir(node_path)
            except OSError:
                names = []
            # One remote RTT per child via build_node→stat only — do NOT
            # pre-probe is_file (that doubled SSH traffic and hung depth-8
            # walks over run trees). Sort by name; type comes from stat.
            kept: list[str] = []
            for name in sorted(names):
                child = fs.join(node_path, name)
                rel = _rel_for(child)
                if rel is None:
                    continue
                # Cheap is_dir guess for ignore (avoid extra SSH): dotted names
                # that are not hidden dirs are treated as files.
                looks_like_file = "." in name and not name.startswith(".")
                if ignore.is_ignored(rel, is_dir=not looks_like_file):
                    continue
                kept.append(child)
            # A directory holding 100k trajectory frames must not become a
            # 100k-node response; report the real count and cap what is built.
            node["entryCount"] = len(kept)
            node["truncated"] = len(kept) > max_entries
            for child in kept[:max_entries]:
                children.append(build_node(child, depth + 1, _visited=visited))
            # Dirs first, then files (stable by name within each group).
            children.sort(key=lambda c: (c.get("type") == "file", c.get("name") or ""))
            node["children"] = children
        else:
            node["children"] = []
            if not is_file:
                # Depth-capped. Mark it truncated *without* listing: we know we
                # stopped early by construction, and probing here would cost one
                # SSH round-trip per boundary directory — the exact traffic this
                # walk is shaped to avoid. ``entryCount`` stays unset because we
                # genuinely do not know it.
                node["truncated"] = True
        return node

    root_node = build_node(requested, 0)
    return {"path": requested, "children": root_node.get("children", [])}


@router.get("/file", response_model=FileContentResponse)
def read_workspace_file(
    path: str = Query("", description="Workspace-relative path to read"),
    mode: Literal["head", "tail"] = Query(default="head"),
    max_bytes: int = Query(default=MAX_TEXT_BYTES, ge=1, le=MAX_TEXT_BYTES),
    since_offset: int | None = Query(default=None, ge=0),
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> FileContentResponse:
    """Read a bounded text window from a workspace file.

    Routes through ``workspace._fs`` so remote workspaces (and the
    :class:`CachedRemoteFileSystem` mirror) take effect.

    A file larger than the window used to be refused with 413. It is now
    served windowed instead: opening a 500 MB log should show its head (or,
    with ``mode=tail``, its end) rather than nothing at all. Page with
    ``since_offset=end``.
    """
    target = resolve_workspace_path_via_fs(workspace, path)
    fs = workspace._fs
    if not fs.exists(target) or not fs.is_file(target):
        raise HTTPException(status_code=404, detail="File not found")

    window = read_text_window(fs, target, max_bytes=max_bytes, mode=mode, since_offset=since_offset)
    return FileContentResponse(
        content=window.text,
        offset=window.start,
        end=window.end,
        totalBytes=window.total_bytes,
        truncated=window.truncated,
    )


@router.get("/file/blob")
def read_workspace_file_blob(
    path: str = Query("", description="Workspace-relative path to read"),
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> Response:
    """Stream a binary file from the workspace.

    Routes through ``workspace._fs`` so remote workspaces (and the
    :class:`CachedRemoteFileSystem` mirror) take effect. Local files are
    handed to :class:`FileResponse` (the OS streams them); remote files are
    streamed in bounded chunks. Either way the server never holds the whole
    image in memory, which it previously did.
    """
    target = resolve_workspace_path_via_fs(workspace, path)
    fs = workspace._fs
    if not fs.exists(target) or not fs.is_file(target):
        raise HTTPException(status_code=404, detail="File not found")

    name = fs.basename(target)
    suffix = ("." + name.rsplit(".", 1)[-1]).lower() if "." in name else ""
    if suffix not in IMAGE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported binary preview type")

    size = fs.getsize(target)
    if size > MAX_BLOB_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"file is {size} bytes, above the {MAX_BLOB_BYTES}-byte preview limit",
        )

    media_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
    if isinstance(fs, LocalFileSystem):
        return FileResponse(target, media_type=media_type)

    def _chunks() -> Iterator[bytes]:
        offset = 0
        while True:
            block = fs.read_range(target, offset, BLOB_CHUNK_BYTES)
            if not block:
                break
            offset += len(block)
            yield block

    return StreamingResponse(
        _chunks(),
        media_type=media_type,
        headers={"Content-Length": str(size)},
    )


@router.post("/open", response_model=WorkspaceInfoResponse)
def open_workspace(
    request: WorkspaceOpenRequest,
    registry=Depends(get_workspace_target_registry),  # noqa: ANN001
) -> WorkspaceInfoResponse:
    """Set the active workspace — local path or registered remote descriptor.

    Switching the active workspace drains any registered workspace
    subscribers (SSE streams, file watchers — registered via
    :func:`~molexp.server.dependencies.register_workspace_subscriber`)
    *before* the cache is reset, so the new workspace starts from a
    clean subscriber slate.
    """
    if isinstance(request, WorkspaceOpenLocalRequest):
        path = Path(request.path).expanduser().resolve()
        created = False
        if not path.exists():
            if not request.create_if_missing:
                raise HTTPException(status_code=404, detail="Workspace path not found")
            path.mkdir(parents=True, exist_ok=True)
            created = True

        set_workspace_path_override(path)
        workspace = Workspace(path)
        if created:
            # Only a just-created directory is materialized — opening an
            # existing path must never write workspace.json on its own.
            workspace.materialize()
        return WorkspaceInfoResponse(
            root=str(workspace.root),
            projectCount=len(workspace.list_projects()),
            assetCount=len(workspace.assets.list()),
        )

    # Remote branch
    try:
        target = registry.get(request.name)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"workspace target {request.name!r} not found",
        ) from exc

    from ..workspace_targets import target_to_filesystem_for_workspace_target

    fs = target_to_filesystem_for_workspace_target(target)
    set_active_workspace_descriptor(target.name)
    workspace = Workspace(target.root_path, fs=fs)
    # Pin-until-refresh: warm → local only; cold → SSH + async index walk.
    # Explicit refresh is POST /api/workspace/cache/refresh (blocking index).
    if isinstance(fs, CachedRemoteFileSystem):
        warnings = fs.prepare(workspace, block_index=False)
        # Cold open may still be indexing in the background — don't block the
        # response on a full tree walk (that was the slow path).
        if fs.indexed:
            project_count = len(workspace.list_projects())
            asset_count = len(workspace.assets.list())
        else:
            project_count = 0
            asset_count = 0
        return WorkspaceInfoResponse(
            root=str(workspace.root),
            projectCount=project_count,
            assetCount=asset_count,
            warnings=[f"{w.path}: {w.reason}" for w in warnings],
            connected=fs.connected,
            indexed=fs.indexed,
            ready=fs.ready,
        )

    warnings = prefetch_workspace_indices(workspace)
    return WorkspaceInfoResponse(
        root=str(workspace.root),
        projectCount=len(workspace.list_projects()),
        assetCount=len(workspace.assets.list()),
        warnings=[f"{w.path}: {w.reason}" for w in warnings],
    )


@router.post("/directories")
def create_directory(
    request: DirectoryCreateRequest,
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> dict:
    """Create a directory in the workspace."""
    if request.folder_id != "workspace":
        raise HTTPException(status_code=400, detail="Only workspace folder is supported")

    root = Path(workspace.root).resolve()
    target = resolve_workspace_path(root, request.path)

    target.mkdir(parents=True, exist_ok=True)
    return {"path": str(target)}


@router.put("/files")
def write_file(
    request: FileContentUpdateRequest,
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> dict:
    """Create or update a file in the workspace."""
    if request.folder_id != "workspace":
        raise HTTPException(status_code=400, detail="Only workspace folder is supported")

    root = Path(workspace.root).resolve()
    target = resolve_workspace_path(root, request.path)

    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.is_dir():
        raise HTTPException(status_code=400, detail="Path is a directory")
    target.write_text(request.content, encoding="utf-8")
    return {"path": str(target)}


# ============================================================================
# Workspace-target registry endpoints
# ============================================================================
#
# A *workspace target* is a server-process-scoped descriptor that names
# a remote workspace root.  These endpoints CRUD the registry and probe
# connectivity; the active-workspace switch (which actually mounts the
# remote root) lives in sub-spec 02.


@router.get("/targets", response_model=WorkspaceTargetListResponse)
def list_workspace_targets(
    registry=Depends(get_workspace_target_registry),  # noqa: ANN001
) -> WorkspaceTargetListResponse:
    rows = [WorkspaceTargetResponse.from_model(t) for t in registry.list()]
    return WorkspaceTargetListResponse(targets=rows, total=len(rows))


@router.post("/targets", response_model=WorkspaceTargetResponse, status_code=201)
def create_workspace_target(
    payload: WorkspaceTargetCreateRequest,
    registry=Depends(get_workspace_target_registry),  # noqa: ANN001
) -> WorkspaceTargetResponse:
    try:
        target = WorkspaceTarget(
            name=payload.name,
            host=payload.host,
            root_path=payload.root_path,
            port=payload.port,
            identity_file=payload.identity_file,
            ssh_opts=tuple(payload.ssh_opts),
            cache_dir=payload.cache_dir,
            cache_ttl_seconds=payload.cache_ttl_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        registry.add(target)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return WorkspaceTargetResponse.from_model(target)


@router.delete("/targets/{name}", status_code=204)
def delete_workspace_target(
    name: str,
    registry=Depends(get_workspace_target_registry),  # noqa: ANN001
) -> None:
    try:
        registry.remove(name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"workspace target {name!r} not found") from exc


@router.post("/targets/{name}/test", response_model=TargetTestResponse)
def test_workspace_target(
    name: str,
    registry=Depends(get_workspace_target_registry),  # noqa: ANN001
    fs_factory=Depends(get_remote_fs_factory),  # noqa: ANN001
) -> TargetTestResponse:
    """Connectivity probe for a workspace-target descriptor.

    Returns HTTP 200 with ``ok=False`` on probe failure (matches the
    ``/api/targets/{name}/test`` pattern) so the UI can render failures
    inline rather than parsing HTTP error envelopes.
    """
    try:
        target = registry.get(name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"workspace target {name!r} not found") from exc

    fs = fs_factory(target)
    checks: list[TargetTestCheck] = []

    # 1. mkdir root_path
    try:
        fs.mkdir(target.root_path, parents=True, exist_ok=True)
        checks.append(TargetTestCheck(label=f"mkdir {target.root_path}", ok=True))
    except Exception as exc:
        checks.append(
            TargetTestCheck(
                label=f"mkdir {target.root_path}",
                ok=False,
                detail=str(exc),
            )
        )
        return TargetTestResponse(
            name=name,
            ok=False,
            checks=checks,
            error=f"mkdir failed: {exc}",
        )

    # 2. file round-trip (write → read → remove)
    probe_path = f"{target.root_path.rstrip('/')}/.molexp-workspace-test"
    try:
        fs.write_text(probe_path, "ok")
        if fs.read_text(probe_path) != "ok":
            checks.append(
                TargetTestCheck(
                    label="file round-trip",
                    ok=False,
                    detail="content mismatch",
                )
            )
            return TargetTestResponse(
                name=name,
                ok=False,
                checks=checks,
                error="file round-trip mismatch",
            )
        fs.remove(probe_path)
        checks.append(TargetTestCheck(label="file round-trip", ok=True))
    except Exception as exc:
        checks.append(
            TargetTestCheck(
                label="file round-trip",
                ok=False,
                detail=str(exc),
            )
        )
        return TargetTestResponse(
            name=name,
            ok=False,
            checks=checks,
            error=f"round-trip failed: {exc}",
        )

    return TargetTestResponse(name=name, ok=True, checks=checks, error=None)


# ============================================================================
# Remote-workspace cache control
# ============================================================================
#
# The active workspace's :class:`CachedRemoteFileSystem` mirrors remote
# bytes locally.  These endpoints let the UI invalidate or refresh the
# mirror without having to re-open the workspace.  Local workspaces have
# no cache; the endpoints respond ``409 Conflict`` rather than 404 so the
# UI can distinguish "no such cache" from "workspace not found".


class CacheControlRequest(BaseModel):
    """Body for ``POST /api/workspace/cache/{invalidate,refresh}``."""

    path: str | None = Field(
        default=None,
        description="Drop this entry only (and its descendants if a directory).",
    )
    scope: str = Field(
        default="all",
        description="When ``path`` is null: 'all' drops everything; 'indices' drops navigation-index entries only.",
    )


class CacheControlResponse(BaseModel):
    dropped: int = Field(..., description="Number of cache entries removed")
    warnings: list[str] = Field(
        default_factory=list,
        description="Per-node warnings raised by the post-invalidate refresh (refresh endpoint only).",
    )


def _require_cached_fs(workspace) -> CachedRemoteFileSystem:  # noqa: ANN001
    fs = getattr(workspace, "_fs", None)
    if not isinstance(fs, CachedRemoteFileSystem):
        raise HTTPException(
            status_code=409,
            detail="Active workspace has no cache (local workspaces are not cached).",
        )
    return fs


@router.post("/cache/invalidate", response_model=CacheControlResponse)
def invalidate_workspace_cache(
    request: CacheControlRequest,
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> CacheControlResponse:
    """Drop cached entries from the active workspace's mirror.

    ``scope="indices"`` is the "I added a run on the remote, refresh
    navigation" knob — it drops only entries whose basename identifies
    a navigation-index file, leaving log/blob bytes intact.
    """
    fs = _require_cached_fs(workspace)
    dropped = fs.invalidate(request.path, scope=request.scope)
    # The mirror moved under the read model: its pinned snapshots describe the
    # pre-invalidation tree, so drop them and tell the UI.
    after_mutation(workspace, "workspace")
    return CacheControlResponse(dropped=dropped, warnings=[])


@router.post("/cache/refresh", response_model=CacheControlResponse)
def refresh_workspace_cache(
    request: CacheControlRequest,
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> CacheControlResponse:
    """Invalidate, then walk the navigation indices again.

    Saves the UI from issuing a follow-up call after a refresh button
    click.  Per-node failures during the walk surface as ``warnings`` —
    the response is still 200 so a single bad project does not blank
    the whole tree.
    """
    fs = _require_cached_fs(workspace)
    dropped = fs.invalidate(request.path, scope=request.scope)
    # User-initiated: blocking rebuild so the response reflects the new tree.
    warnings = (
        fs.index(workspace) if request.path is None else prefetch_workspace_indices(workspace)
    )
    after_mutation(workspace, "workspace")
    return CacheControlResponse(
        dropped=dropped,
        warnings=[f"{w.path}: {w.reason}" for w in warnings],
    )


# ── Guarded curation (deterministic, LLM-free) — curate-unify-03 ──────────────


class CurateRequest(BaseModel):
    """A structured, LLM-free destructive-curation request.

    Builds a §8 ``ChangeProposal`` directly from typed args and drives it through
    the shared ``run_curation_proposal`` backend (the same one the CLI + NL flow
    use). ``approve`` defaults to ``False`` so a destructive mutation over HTTP
    never auto-executes — the proposal is recorded and refused unless the caller
    opts in.
    """

    op: Literal["move_run", "delete_folder", "rehome_asset"]
    run: str | None = None
    target_experiment: str | None = None
    folder: str | None = None
    asset: str | None = None
    source: dict[str, str] | None = None
    target: dict[str, str] | None = None
    action: str = "copy"
    approve: bool = False
    project: str = "curations"
    experiment: str = "curate"


class CurateResponse(BaseModel):
    """The gated-execution outcome for a deterministic curation request."""

    proposalId: str
    status: str
    reason: str | None = None
    resultArtifactIds: list[str] = Field(default_factory=list)


async def _curate_reject_approver(request: ApprovalRequest) -> ApprovalDecision:
    from datetime import UTC, datetime

    from molexp.harness.schemas import ApprovalDecision

    return ApprovalDecision(
        request_id=request.id,
        granted=False,
        decided_by="http-operator",
        decided_at=datetime.now(tz=UTC),
        reason="approve=false",
    )


async def _curate_grant_approver(request: ApprovalRequest) -> ApprovalDecision:
    """Grant carried by the HTTP request body's explicit ``approve: true``.

    An explicit per-request decision by the HTTP caller — NOT a silent
    default — so ``decided_by`` names the caller, never "auto-approver".
    """
    from datetime import UTC, datetime

    from molexp.harness.schemas import ApprovalDecision

    return ApprovalDecision(
        request_id=request.id,
        granted=True,
        decided_by="http-operator",
        decided_at=datetime.now(tz=UTC),
        reason="approve=true (explicit in the request body)",
    )


@router.post("/curate", response_model=CurateResponse)
async def curate_workspace(
    request: CurateRequest,
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> CurateResponse:
    """Gate + execute one deterministic destructive-curation op (single stack).

    Shares the ``run_curation_proposal`` backend with ``molexp curate`` (Python ≡
    UI). ``approve=false`` (default) records the proposal and refuses; ``true``
    executes the mutation. Either way the §8 ``change_proposal`` artifact is the audit.
    """
    from molexp.services.curate_runtime import build_curation_proposal, run_curation_proposal
    from molexp.workspace.utils import derive_run_id

    try:
        proposal = build_curation_proposal(
            request.op,
            run=request.run,
            target_experiment=request.target_experiment,
            folder=request.folder,
            asset=request.asset,
            source=request.source,
            target=request.target,
            action=request.action,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    params: dict[str, Any] = {"mode": "curate-propose", "op": request.op, "proposal": proposal.id}
    audit_run = (
        workspace.add_project(request.project)
        .add_experiment(request.experiment)
        .add_run(params, id=derive_run_id(params))
    )
    approver = _curate_grant_approver if request.approve else _curate_reject_approver
    result = await run_curation_proposal(
        proposal, workspace=workspace, run=audit_run, approve=approver
    )
    outcome = result.execution_result
    if outcome is not None and outcome.status == "succeeded":
        # Curation moves runs and rehomes assets across the tree: every view
        # can be affected, so invalidate broadly rather than guess.
        after_mutation(workspace, "all")
    return CurateResponse(
        proposalId=proposal.id,
        status=outcome.status if outcome is not None else "failed",
        reason=outcome.reason if outcome is not None else None,
        resultArtifactIds=list(outcome.result_artifact_ids) if outcome is not None else [],
    )
