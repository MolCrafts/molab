"""Request-aware workspace resolution (FastAPI dependencies).

Resolves the workspace a request addresses — explicit ``{ws}`` key, query
param, header, or the active/default workspace — caching instances in the
``(kind, identifier)``-keyed cache owned by :mod:`.workspace_state`.
"""

from __future__ import annotations

from pathlib import Path
from time import monotonic
from typing import Annotated, cast

from fastapi import Depends, HTTPException, Request

from molab.server.deps.scope_root import ScopeRoot
from molab.server.deps.served import _served_by_key
from molab.server.deps.workspace_state import (
    _active_workspace_key,
    _RemoteOpenFailure,
    _workspace_cache,
    _workspace_cache_lock,
)
from molab.services.auth import AuthError, AuthUser, get_auth_service, is_auth_enabled
from molab.workspace.scope import open_serve_root

from .auth import get_optional_user
from .served import active_served_key, assert_workspace_writable


def _ensure_remote_ready(workspace: ScopeRoot) -> None:
    """Prepare a remote workspace for serve / API open.

    On **every link** (this process's first open of the root): connect
    and **force-refresh** the local pin. The refresh is **async** so the
    UI can poll ``GET /api/workspace/cache/status`` for a file-count
    progress bar (count total → fetch). Further requests reuse the
    in-memory Workspace; ``POST /api/workspace/cache/refresh`` re-pulls.

    Local workspaces are a no-op. Connection failures raise
    :class:`ConnectionError` / transport errors — callers convert to
    :class:`RemoteWorkspaceUnreachableError` (soft JSON, no stack spam).
    """
    from molab.workspace.fs_cached import CachedRemoteFileSystem

    fs = getattr(workspace, "fs", None)
    if not isinstance(fs, CachedRemoteFileSystem):
        return
    # Async force-refresh on link — progress is polled by the status strip.
    from molab.workspace import Workspace as WorkspaceEntity

    fs.prepare(cast(WorkspaceEntity, workspace), block_index=False, refresh_on_open=False)


def _open_remote_workspace(identifier: str, *, served_key: str | None = None) -> ScopeRoot:
    """Build + prepare a remote Workspace, or soft-raise unreachable.

    *identifier* is the workspace-target name (serve registry key).
    """
    from molab.server.deps.served import resolve_served_remote_target
    from molab.server.exceptions import RemoteWorkspaceUnreachableError
    from molab.server.workspace_targets import target_to_filesystem_for_workspace_target

    key = served_key or identifier
    cache_key = ("remote", identifier)
    cached = _workspace_cache.get(cache_key)
    if cached is not None and not isinstance(cached, _RemoteOpenFailure):
        return _as_scope_root(cached)
    # Share the initial probe across concurrent browser requests. Polling an
    # authentication failure must not repeatedly open rejected SSH connections.
    with _workspace_cache_lock:
        cached = _workspace_cache.get(cache_key)
        if isinstance(cached, _RemoteOpenFailure):
            if monotonic() < cached.retry_at:
                raise RemoteWorkspaceUnreachableError(key, cached.reason)
        elif cached is not None:
            return _as_scope_root(cached)
        try:
            target = resolve_served_remote_target(identifier)
        except KeyError as exc:
            raise KeyError(f"workspace target {identifier!r} no longer registered") from exc

        try:
            fs = target_to_filesystem_for_workspace_target(target)
            folder = open_serve_root(target.root_path, fs=fs)
            root = ScopeRoot(folder)
            _ensure_remote_ready(root)
        except Exception as exc:
            from molq import MolqError

            reason = (
                "needs_auth"
                if isinstance(exc, MolqError) and exc.kind == "AUTH_REQUIRED"
                else "unreachable"
            )
            # Explicit authentication clears this cache. Network failures may
            # be probed again after a quiet interval, never on every UI poll.
            retry_at = float("inf") if reason == "needs_auth" else monotonic() + 60
            _workspace_cache[cache_key] = _RemoteOpenFailure(reason, retry_at)
            raise RemoteWorkspaceUnreachableError(key, reason) from exc
        _workspace_cache[cache_key] = root
        return root


def _workspace_key_from_request(request: Request | None) -> str | None:
    """Extract an explicit workspace key from a request, if any.

    Resolution order: ``{ws}`` path segment (the aggregate routes) →
    ``?ws=`` query param → ``X-Molab-Workspace`` header. Returns ``None``
    when the request addresses the active/default workspace (flat routes).
    """
    if request is None:
        return None
    return (
        request.path_params.get("ws")
        or request.query_params.get("ws")
        or request.headers.get("x-molab-workspace")
        or None
    )


def get_workspace(
    request: Request, user: Annotated[AuthUser | None, Depends(get_optional_user)] = None
) -> ScopeRoot:
    """FastAPI dependency to get a cached Workspace instance.

    When the request carries an explicit workspace key (``{ws}`` path segment,
    ``?ws=``, or ``X-Molab-Workspace`` header) the named served workspace is
    resolved via :func:`get_workspace_by_key`. Otherwise the **active/default**
    workspace is used — the unchanged single-workspace path.

    Workspace access and write permissions are enforced by the HTTP authorization layer.
    """
    explicit_key = _workspace_key_from_request(request)
    key = explicit_key or active_served_key()
    if is_auth_enabled():
        if user is None:
            raise HTTPException(status_code=401, detail="Authentication required")
        try:
            get_auth_service().assert_workspace_access(user, key or _active_workspace_key()[1])
        except AuthError as exc:
            raise HTTPException(status_code=403, detail=exc.message) from exc
    if key and not request.url.path.startswith("/api/workspace/"):
        assert_workspace_writable(key, request.method)
    if explicit_key is not None:
        return get_workspace_by_key(explicit_key)

    return get_active_workspace()


def get_active_workspace():  # noqa: ANN201
    """Resolve (and cache) the active/default workspace, ignoring any request.

    The cache key is ``(kind, identifier)`` — local-vs-remote workspaces
    coexist without collision. This is the request-free core used by
    :func:`get_workspace` and by direct callers that have no request.

    Local roots open without requiring ``workspace.json`` (plain folders are
    valid; index views stay empty until the layout is present).
    """
    kind, identifier = _active_workspace_key()
    cache_key = (kind, identifier)
    if kind == "remote":
        return _open_remote_workspace(identifier, served_key=active_served_key())
    if cache_key not in _workspace_cache:
        _workspace_cache[cache_key] = ScopeRoot(open_serve_root(Path(identifier)))
    return _as_scope_root(_workspace_cache[cache_key])


def get_workspace_by_key(key: str):  # noqa: ANN201
    """Resolve a served workspace by its stable ``key`` (the ``{ws}`` segment).

    Raises:
        UnknownWorkspaceError: ``key`` names no served workspace (404).
        RemoteWorkspaceUnreachableError: the remote transport failed (soft 503).
    """
    sw = _served_by_key(key)
    if sw is None:
        from molab.server.exceptions import UnknownWorkspaceError

        raise UnknownWorkspaceError(key)

    if sw.is_remote:
        target_name = sw.target_name or sw.key
        return _open_remote_workspace(target_name, served_key=sw.key)

    assert sw.path is not None  # local always carries a path
    cache_key = ("local", str(Path(sw.path).resolve()))
    if cache_key not in _workspace_cache:
        _workspace_cache[cache_key] = ScopeRoot(open_serve_root(Path(sw.path)))
    return _as_scope_root(_workspace_cache[cache_key])


def _as_scope_root(cached: object) -> ScopeRoot:
    """Return *cached* when it is already a serve root, else wrap a folder."""
    if isinstance(cached, ScopeRoot):
        return cached
    from molab.workspace.folder import Folder

    if isinstance(cached, Folder):
        return ScopeRoot(cached)
    raise TypeError(f"workspace cache holds {type(cached).__name__}, not a folder")
