"""Workspace routes for Molab API."""

from __future__ import annotations

import contextlib
import mimetypes
import shutil
import tempfile
import uuid
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Annotated, Any, cast
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from molab.fs.window import iter_file_chunks
from molab.server.deps.scope_root import ScopeRoot
from molab.services.auth import AuthError, AuthUser, get_auth_service, is_auth_enabled
from molab.workspace import ContextFocus, Run
from molab.workspace.folder import WORKSPACE_EXPERIMENT_KIND, WORKSPACE_PROJECT_KIND
from molab.workspace.fs_cached import CachedRemoteFileSystem, prefetch_workspace_indices
from molab.workspace.fs_local import LocalFileSystem
from molab.workspace.scope import as_folder, descendants, display_name, open_serve_root

from ..dependencies import (
    get_remote_fs_factory,
    get_served_workspaces,
    get_workspace,
    get_workspace_target_registry,
    set_active_workspace_descriptor,
    set_workspace_path_override,
)
from ..deps.auth import get_optional_user
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
    pass


class DirectoryCreateRequest(BaseModel):
    folder_id: str = Field(..., description="Workspace folder ID or 'workspace'")
    path: str = Field(..., description="Relative path for new directory")


class FileContentUpdateRequest(BaseModel):
    folder_id: str = Field(..., description="Workspace folder ID or 'workspace'")
    path: str = Field(..., description="Relative path within the folder")
    content: str = Field(..., description="New file content")


router = APIRouter(prefix="/workspace", tags=["workspace"])


MAX_TEXT_BYTES = 2_000_000
# What /file/blob streams: formats a browser renders by itself. SVG stays out —
# served from this origin it can run script.
BINARY_PREVIEW_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf"}


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
    ``workspace.fs`` rather than ``pathlib.Path``.  For pure local
    workspaces (``fs is LocalFileSystem``) it preserves the existing
    ``Path.resolve()`` containment check so symlink escapes are still
    caught.  For any non-local backend (e.g. a remote workspace wrapped
    in :class:`CachedRemoteFileSystem`) it does string-level
    containment against the remote root.
    """
    fs = workspace.fs
    root = str(workspace.root)
    if isinstance(fs, LocalFileSystem):
        resolved = resolve_workspace_path(Path(root).resolve(), path_str)
        return str(resolved)

    if ".." in PurePosixPath(path_str).parts:
        raise HTTPException(status_code=400, detail="Path is outside workspace root")

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


class ServeScopeResponse(BaseModel):
    """The directory ``molab serve`` opened. Navigation stops here."""

    kind: str
    id: str
    name: str


def _scope_payload(workspace: object) -> ServeScopeResponse:
    folder = as_folder(workspace)
    return ServeScopeResponse(
        kind=folder.kind,
        id=str(getattr(folder, "id", folder.metadata.id)),
        name=display_name(folder),
    )


@router.get("/scope", response_model=ServeScopeResponse)
def get_serve_scope(workspace=Depends(get_workspace)) -> ServeScopeResponse:  # noqa: ANN001
    """Kind of the served directory. The UI uses this instead of guessing."""
    return _scope_payload(workspace)


@router.get("/info", response_model=WorkspaceInfoResponse)
def get_workspace_info(workspace=Depends(get_workspace)) -> WorkspaceInfoResponse:  # noqa: ANN001
    """Get workspace information."""
    fs = getattr(workspace, "fs", None)
    is_cached = isinstance(fs, CachedRemoteFileSystem)
    return WorkspaceInfoResponse(
        root=str(workspace.root),
        projectCount=len(workspace.list_projects()),
        assetCount=len(workspace.assets.list()),
        connected=fs.connected if is_cached else None,
        indexed=fs.indexed if is_cached else None,
        ready=fs.ready if is_cached else None,
    )


@router.get("/context", response_model=WorkspaceContextResponse)
def get_workspace_context(
    project_id: str | None = Query(default=None, alias="projectId"),
    experiment_id: str | None = Query(default=None, alias="experimentId"),
    run_id: str | None = Query(default=None, alias="runId"),
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> WorkspaceContextResponse:
    """The canonical structural workspace read-model (integration.md §1).

    A read-only projection assembled from authoritative workspace state — the one
    shape agents/planners/CLI/UI observe. ``ContextFocus`` is supplied by the
    caller via optional query params and is never persisted. ``/runs`` remains the
    specialized detailed run view (richer per-execution rows); this endpoint is the
    canonical *structure* and stays consistent with it.

    The ``knowledge`` field comes from the single projection producer
    (:mod:`molab.services.knowledge_context`) — the server assembles no producer
    of its own, so this route and the CLI report the same rows.
    """
    from molab.services.knowledge_context import context_with_knowledge

    focus = ContextFocus(project_id=project_id, experiment_id=experiment_id, run_id=run_id)
    context = context_with_knowledge(workspace, focus=focus)
    return WorkspaceContextResponse.from_context(context)


@router.get("/copilot", response_model=WorkspaceSummaryResponse)
def get_workspace_copilot(workspace=Depends(get_workspace)) -> WorkspaceSummaryResponse:  # noqa: ANN001
    """The read-only Workspace Copilot summary — structured state + ranked next-actions.

    A pure projection over the canonical ``WorkspaceContext``; it mutates nothing.
    Next-actions are **advisory** and separated from execution — a mutating one
    names the operation it would perform in ``op``, and whoever executes it owns
    the policy for what that operation requires.
    """
    from molab.services.copilot import summarize_workspace
    from molab.services.knowledge_context import context_with_knowledge

    summary = summarize_workspace(context_with_knowledge(workspace))
    return WorkspaceSummaryResponse.from_summary(summary)


@router.get("/runs", response_model=WorkspaceRunsResponse)
def list_workspace_runs(
    project_id: str | None = Query(default=None, alias="projectId"),
    experiment_id: str | None = Query(default=None, alias="experimentId"),
    backend: str | None = Query(default=None, description="Filter by executor backend"),
    status: str | None = Query(default=None, description="Filter by contained Execution status"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=500, ge=1, le=2000),
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> WorkspaceRunsResponse:
    """Cross-experiment list of runs, each with embedded execution attempts.

    Returns rows ordered by ``created_at`` desc.  Plugins surface
    backend-specific columns (cluster, scheduler job id, etc.) via the
    ``backend`` / ``backendMetadata`` fields on each execution row.
    """

    rows: list[WorkspaceRunRow] = []
    for node in descendants(as_folder(workspace), Run):
        if not isinstance(node, Run):
            continue
        run = node
        project = run.ancestor(WORKSPACE_PROJECT_KIND)
        experiment = run.ancestor(WORKSPACE_EXPERIMENT_KIND)
        if project_id and run.ancestor_id(WORKSPACE_PROJECT_KIND) != project_id:
            continue
        if experiment_id and run.ancestor_id(WORKSPACE_EXPERIMENT_KIND) != experiment_id:
            continue
        row = WorkspaceRunRow.from_run(
            run,
            project_name=display_name(project),
            experiment_name=display_name(experiment),
        )
        if backend and not any(
            (execution.backend or "").lower() == backend.lower() for execution in row.executions
        ):
            continue
        if status and (
            (status.lower() == "not_started" and not row.statusSummary.notStarted)
            or (
                status.lower() != "not_started"
                and row.statusSummary.byStatus.get(status.lower(), 0) == 0
            )
        ):
            continue
        rows.append(row)

    rows.sort(key=lambda r: r.createdAt, reverse=True)
    total = len(rows)
    stats = compute_workspace_runs_stats(rows)
    page = rows[offset : offset + limit]
    truncated = offset + len(page) < total

    return WorkspaceRunsResponse(
        runs=page,
        stats=stats,
        total=total,
        truncated=truncated,
    )


@router.get("/files")
def list_workspace_files(
    path: str = Query("", description="Workspace-relative path to list"),
    max_depth: int = Query(4, ge=0, le=8, description="Maximum recursion depth"),
    include: str | None = Query(
        None,
        description="Comma-separated optional enrichments (e.g. 'catalog')",
    ),
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> dict:
    """Return a nested file tree rooted at the requested path.

    Routes through ``workspace.fs`` so remote workspaces (and the
    :class:`CachedRemoteFileSystem` mirror) work the same as local ones.

    With ``include=catalog``, file nodes that match a registered asset
    are enriched with ``assetId``, ``assetKind``, ``producerRunId`` and
    ``producerTaskId`` so the UI can render lineage chips inline.

    Children matching the workspace ``.gitignore`` cascade (plus a safety
    floor for ``node_modules`` / ``.git`` / venvs) are omitted so git-managed
    workspaces do not dump dependency trees into the UI.
    """
    from molab.workspace.fs_tree import list_tree_children, tree_to_workspace_file_dicts
    from molab.workspace.gitignore import load_gitignore_matcher

    fs = workspace.fs
    root = resolve_workspace_path_via_fs(workspace, "")
    requested = resolve_workspace_path_via_fs(workspace, path.lstrip("/"))
    if not fs.exists(requested):
        raise HTTPException(status_code=404, detail="Path not found")

    # Remote pin-until-refresh can freeze a directory listing as empty after a
    # race / early list. Explicit files API calls are expand/refresh — drop the
    # pin for *this* path so the walk re-listdir from SSH (children still pin).
    if isinstance(fs, CachedRemoteFileSystem):
        fs.invalidate_dir_listing(requested)

    # Remote trees pay one SSH RTT per node. A deep walk over hundreds of run
    # dirs (trajectory.pt etc.) freezes the UI bootstrap. Cap remote depth
    # server-side; clients expand path-by-path for deeper levels.
    effective_depth = max_depth
    if isinstance(fs, CachedRemoteFileSystem) and max_depth > 4:
        effective_depth = 4

    # gitignore matcher is path-string based against the workspace root.
    gitignore = load_gitignore_matcher(Path(str(workspace.root)), fs=fs)
    root_norm = root.rstrip("/") or "/"
    req_norm = requested.rstrip("/") or "/"

    def _ws_rel(abs_path: str) -> str | None:
        node = abs_path.rstrip("/") or "/"
        if node == root_norm:
            return ""
        prefix = root_norm + "/"
        if not node.startswith(prefix):
            return None
        return node[len(prefix) :]

    # list_tree_children rel paths are relative to *requested*; map to
    # workspace-relative paths for the gitignore cascade.
    req_ws_rel = _ws_rel(req_norm) or ""

    def ignore_fn(rel: str, is_dir: bool) -> bool:
        if req_ws_rel and rel:
            full = f"{req_ws_rel}/{rel}"
        else:
            full = req_ws_rel or rel
        return gitignore.is_ignored(full, is_dir=is_dir)

    include_set = {part.strip() for part in (include or "").split(",") if part.strip()}
    # Catalog enrichment is local-path keyed; skip on non-local FS for now
    # (remote asset scans still work via the catalog API, not inline chips).
    asset_index_by_abs: dict[str, dict] = {}
    if "catalog" in include_set and isinstance(fs, LocalFileSystem):
        from molab.workspace.artifact_repository import scan_asset_repositories, walk_artifacts
        from molab.workspace.errors import AmbiguousRefError, RefNotFoundError

        for loc in walk_artifacts(workspace):
            if loc.location is None:
                continue
            try:
                abs_path = Path(loc.location).resolve()
            except OSError:
                continue
            task_id = loc.artifact.metadata.get("task_id")
            asset_index_by_abs[str(abs_path)] = {
                "assetId": loc.artifact.id,
                "assetKind": loc.artifact.semantic_type or "artifact",
                "producerRunId": loc.run_id,
                "producerTaskId": task_id if isinstance(task_id, str) else None,
                "hasPreviewSidecar": resolve_sidecar(abs_path) is not None,
            }

        for repository in scan_asset_repositories(workspace):
            for asset in repository.list():
                try:
                    abs_path = Path(repository.payload_path(asset.id)).resolve()
                except (OSError, KeyError, ValueError, RefNotFoundError, AmbiguousRefError):
                    continue
                key = str(abs_path)
                sidecar = resolve_sidecar(abs_path) is not None
                existing = asset_index_by_abs.get(key)
                if existing is not None:
                    existing["assetId"] = asset.id
                    existing["assetKind"] = asset.kind
                    existing["hasPreviewSidecar"] = sidecar
                    continue
                asset_index_by_abs[key] = {
                    "assetId": asset.id,
                    "assetKind": asset.kind,
                    "producerRunId": None,
                    "producerTaskId": None,
                    "hasPreviewSidecar": sidecar,
                }

    # Single tree walk — same implementation as GET …/runs/{id}/files.
    nodes = list_tree_children(fs, requested, max_depth=effective_depth, ignore=ignore_fn)
    children = tree_to_workspace_file_dicts(nodes)
    if asset_index_by_abs:

        def _enrich(node: dict[str, Any]) -> None:
            enrich = asset_index_by_abs.get(node.get("path") or "")
            if enrich is not None:
                node.update(enrich)
            for child in node.get("children") or []:
                _enrich(child)

        for child in children:
            _enrich(child)
    return {"path": requested, "children": children}


@router.get("/file", response_model=FileContentResponse)
def read_workspace_file(
    path: str = Query("", description="Workspace-relative path to read"),
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> FileContentResponse:
    """Read a text file from the workspace.

    Routes through ``workspace.fs`` so remote workspaces (and the
    :class:`CachedRemoteFileSystem` mirror) take effect.
    """
    target = resolve_workspace_path_via_fs(workspace, path)
    fs = workspace.fs
    if not fs.exists(target) or not fs.is_file(target):
        raise HTTPException(status_code=404, detail="File not found")

    size = fs.getsize(target)
    if size > MAX_TEXT_BYTES:
        raise HTTPException(status_code=413, detail="File too large for text preview")

    try:
        content = fs.read_text(target, encoding="utf-8")
    except UnicodeDecodeError:
        content = fs.read_bytes(target).decode("utf-8", errors="replace")
    return FileContentResponse(content=content)


@router.get("/file/blob")
def read_workspace_file_blob(
    download: bool = Query(False, description="Download as an attachment instead of previewing"),
    path: str = Query("", description="Workspace-relative path to read"),
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> StreamingResponse:
    """Read a binary file from the workspace.

    Routes through ``workspace.fs`` so remote workspaces (and the
    :class:`CachedRemoteFileSystem` mirror) take effect.
    """
    target = resolve_workspace_path_via_fs(workspace, path)
    fs = workspace.fs
    if not fs.exists(target) or not fs.is_file(target):
        raise HTTPException(status_code=404, detail="File not found")

    name = fs.basename(target)
    suffix = ("." + name.rsplit(".", 1)[-1]).lower() if "." in name else ""
    if not download and suffix not in BINARY_PREVIEW_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported binary preview type")

    media_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
    size = fs.getsize(target)

    headers = {"Content-Length": str(size)}
    if download:
        headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(name, safe='')}"
    return StreamingResponse(
        iter_file_chunks(fs, target, size=size), media_type=media_type, headers=headers
    )


@router.post("/file/upload", status_code=204)
async def upload_workspace_file(
    request: Request,
    path: str = Query(
        ..., description="Workspace-relative destination; request body is raw file bytes"
    ),
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> None:
    """Stage a bounded HTTP stream on disk, then publish through the workspace filesystem."""
    from molq import MolqError
    from starlette.concurrency import run_in_threadpool

    target = resolve_workspace_path_via_fs(workspace, path)
    fs = workspace.fs
    staged = fs.join(fs.dirname(target), f".molab-upload-{uuid.uuid4().hex}")
    with tempfile.TemporaryDirectory(prefix="molab-upload-") as directory:
        local = Path(directory) / "payload"
        received = 0
        with local.open("wb") as output:
            async for chunk in request.stream():
                received += len(chunk)
                if received > 8 * 1024**3:
                    raise HTTPException(status_code=413, detail="Upload exceeds 8 GiB")
                await run_in_threadpool(output.write, chunk)
        try:
            upload = getattr(fs, "upload", None)
            if callable(upload):
                await run_in_threadpool(upload, str(local), staged)
            else:
                await run_in_threadpool(shutil.copyfile, local, staged)
            await run_in_threadpool(fs.rename, staged, target)
        finally:
            with contextlib.suppress(OSError, MolqError):
                await run_in_threadpool(fs.remove, staged)


def _asset_count(root: object) -> int:
    """How many assets ``root`` lists. A serve root forwards ``assets``."""
    assets = getattr(root, "assets", None)
    list_assets = getattr(assets, "list", None)
    if not callable(list_assets):
        return 0
    found = list_assets()
    return len(found) if isinstance(found, list) else 0


def _reject_outside_served(path: Path | None, remote_name: str | None) -> None:
    """Refuse to leave the directories ``molab serve`` was started with.

    An empty served set (tests and a bare API) stays open. Switching among
    the served keys stays allowed. A non-empty set is a hard boundary, including
    for an admin session.
    """
    served = get_served_workspaces()
    if not served:
        return
    if path is not None:
        resolved = path.resolve()
        allowed = {Path(item.path).resolve() for item in served if item.path}
        if resolved not in allowed:
            raise HTTPException(status_code=403, detail="path is outside the served root")
        return
    if remote_name is None:
        return
    names: set[str] = set()
    for item in served:
        names.add(item.key)
        if item.target_name:
            names.add(item.target_name)
    if remote_name not in names:
        raise HTTPException(status_code=403, detail="path is outside the served root")


def _assert_open_workspace_allowed(
    request: WorkspaceOpenRequest,
    user: AuthUser | None,
) -> None:
    """When auth is on, require a session and allowlist for served keys."""
    if not is_auth_enabled():
        return
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    # Map open target → served key when possible.
    key: str | None = None
    if isinstance(request, WorkspaceOpenLocalRequest):
        path = str(Path(request.path).expanduser().resolve())
        for sw in get_served_workspaces():
            if not sw.is_remote and sw.path is not None and Path(sw.path).resolve() == Path(path):
                key = sw.key
                break
        # Opening an arbitrary local path outside the served set is admin-only
        # when auth is on (otherwise any operator could escape allowlist).
        if key is None and user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can open paths outside the served workspace set",
            )
    else:
        name = getattr(request, "name", None)
        if isinstance(name, str):
            for sw in get_served_workspaces():
                aliases = {sw.key, sw.target_name}
                if sw.remote_target is not None:
                    aliases.add(sw.remote_target.name)
                aliases.discard(None)
                if name in aliases:
                    key = sw.key
                    break
    if key is not None:
        try:
            get_auth_service().assert_workspace_access(user, key)
        except AuthError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=exc.message) from exc


@router.post("/open", response_model=WorkspaceInfoResponse)
def open_workspace(
    request: WorkspaceOpenRequest,
    registry=Depends(get_workspace_target_registry),  # noqa: ANN001
    user: Annotated[AuthUser | None, Depends(get_optional_user)] = None,
) -> WorkspaceInfoResponse:
    """Set the active workspace — local path or registered remote descriptor.

    Switching the active workspace drains any registered workspace
    subscribers (SSE streams, file watchers — registered via
    :func:`~molab.server.dependencies.register_workspace_subscriber`)
    *before* the cache is reset, so the new workspace starts from a
    clean subscriber slate.
    """
    _assert_open_workspace_allowed(request, user)
    if isinstance(request, WorkspaceOpenLocalRequest):
        path = Path(request.path).expanduser().resolve()
        _reject_outside_served(path, None)
        if not path.exists():
            if not request.create_if_missing:
                raise HTTPException(status_code=404, detail="Workspace path not found")
            path.mkdir(parents=True, exist_ok=True)

        set_workspace_path_override(path)
        root = ScopeRoot(open_serve_root(path))
        return WorkspaceInfoResponse(
            root=str(root.root),
            projectCount=len(root.list_projects()),
            assetCount=_asset_count(root),
        )

    # Remote branch — CLI ``-ws cluster:path`` injects an inline ServedWorkspace
    # target (not the on-disk registry). Prefer that resolver so open accepts
    # the served key *or* target_name the UI may send.
    from molab.server.deps.served import resolve_served_remote_target

    from ..workspace_targets import target_to_filesystem_for_workspace_target

    try:
        target = resolve_served_remote_target(request.name)
    except KeyError:
        try:
            target = registry.get(request.name)
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail=f"workspace target {request.name!r} not found",
            ) from exc

    _reject_outside_served(None, request.name)
    fs = target_to_filesystem_for_workspace_target(target)
    set_active_workspace_descriptor(target.name)
    workspace = ScopeRoot(open_serve_root(target.root_path, fs=fs))
    # ScopeRoot forwards the folder surface those helpers read (.root, .fs, listings).
    from molab.workspace import Workspace as WorkspaceEntity

    host = cast(WorkspaceEntity, workspace)
    # Linking a remote always force-refreshes (async). UI polls
    # GET /api/workspace/cache/status for the file-count progress bar.
    if isinstance(fs, CachedRemoteFileSystem):
        warnings = fs.prepare(host, block_index=False, refresh_on_open=True)
        project_count = len(workspace.list_projects()) if fs.indexed else 0
        asset_count = _asset_count(workspace) if fs.indexed else 0
        return WorkspaceInfoResponse(
            root=str(workspace.root),
            projectCount=project_count,
            assetCount=asset_count,
            warnings=[f"{w.path}: {w.reason}" for w in warnings],
            connected=fs.connected,
            indexed=fs.indexed,
            ready=fs.ready,
        )

    warnings = prefetch_workspace_indices(host)
    return WorkspaceInfoResponse(
        root=str(workspace.root),
        projectCount=len(workspace.list_projects()),
        assetCount=_asset_count(workspace),
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

    target = resolve_workspace_path_via_fs(workspace, request.path)
    workspace.fs.mkdir(target, parents=True, exist_ok=True)
    return {"path": target}


@router.put("/files")
def write_file(
    request: FileContentUpdateRequest,
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> dict:
    """Create or update a file in the workspace."""
    if request.folder_id != "workspace":
        raise HTTPException(status_code=400, detail="Only workspace folder is supported")

    target = resolve_workspace_path_via_fs(workspace, request.path)
    fs = workspace.fs
    fs.mkdir(fs.dirname(target), parents=True, exist_ok=True)
    if fs.exists(target) and fs.is_dir(target):
        raise HTTPException(status_code=400, detail="Path is a directory")
    fs.atomic_write_text(target, request.content)
    return {"path": target}


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
        target = WorkspaceTarget(**payload.model_dump())
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
    probe_path = f"{target.root_path.rstrip('/')}/.molab-workspace-test"
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


class CacheStatusResponse(BaseModel):
    """Live remote-index progress for the MolVis-style status bar."""

    cached: bool = Field(..., description="False when the active workspace is local")
    connected: bool | None = None
    indexed: bool | None = None
    ready: bool | None = None
    indexing: bool | None = None
    phase: str = "idle"
    total: int = 0
    done: int = 0
    percent: float | None = None
    message: str = ""


def _require_cached_fs(workspace) -> CachedRemoteFileSystem:  # noqa: ANN001
    fs = getattr(workspace, "fs", None)
    if not isinstance(fs, CachedRemoteFileSystem):
        raise HTTPException(
            status_code=409,
            detail="Active workspace has no cache (local workspaces are not cached).",
        )
    return fs


@router.get("/cache/status", response_model=CacheStatusResponse)
def workspace_cache_status(workspace=Depends(get_workspace)) -> CacheStatusResponse:  # noqa: ANN001
    """Poll remote-index progress (file-count total → fetch done).

    Local workspaces return ``cached=false`` with idle progress. The UI
    status strip polls this while ``phase`` is ``counting`` / ``fetching``.
    """
    fs = getattr(workspace, "fs", None)
    if not isinstance(fs, CachedRemoteFileSystem):
        return CacheStatusResponse(cached=False, phase="idle", message="")
    progress = fs.progress
    return CacheStatusResponse(
        cached=True,
        connected=fs.connected,
        indexed=fs.indexed,
        ready=fs.ready,
        indexing=fs.indexing,
        phase=progress.phase,
        total=progress.total,
        done=progress.done,
        percent=progress.percent,
        message=progress.message,
    )


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
    return CacheControlResponse(
        dropped=dropped,
        warnings=[f"{w.path}: {w.reason}" for w in warnings],
    )
