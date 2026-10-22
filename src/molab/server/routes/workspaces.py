"""``GET /api/workspaces`` — the set of workspaces this server is hosting.

``molab serve`` can be pointed at one or more workspaces (local or remote).
This route exposes that set so the UI can list them and switch between them via
``POST /api/workspace/open`` (singular — active-workspace operations live in
``routes/workspace.py``). With a single served workspace this returns one row,
matching the unchanged single-workspace behaviour.

``POST /api/workspaces/{key}/connect`` accepts a verification code for
2FA/OTP hosts and establishes an OpenSSH ControlMaster so subsequent
BatchMode ops succeed without a TTY.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from molq import Cluster
from pydantic import BaseModel, Field

from molab.server.dependencies import (
    active_served_key,
    get_served_workspaces,
    get_workspace_by_key,
    reset_workspace_cache,
    set_active_workspace_descriptor,
    set_workspace_path_override,
)
from molab.server.deps.auth import get_optional_user
from molab.server.deps.served import (
    ServedWorkspace,
    _served_by_key,
    add_served_workspace,
    remove_served_workspace,
)
from molab.server.exceptions import RemoteWorkspaceUnreachableError, UnknownWorkspaceError
from molab.services.auth import AuthUser, get_auth_service, is_auth_enabled

router = APIRouter(prefix="/workspaces", tags=["workspaces"])

_SLUG_RE = re.compile(r"[^A-Za-z0-9._-]+")


class ServedWorkspaceResponse(BaseModel):
    """One workspace the server is hosting."""

    key: str = Field(..., description="Stable switch handle, unique per server process")
    label: str = Field(..., description="Human-facing label (path or cluster:/path)")
    isRemote: bool = Field(..., description="True for an SSH-backed remote workspace")
    path: str | None = Field(default=None, description="Absolute local root, null when remote")
    active: bool = Field(
        default=False,
        description="True for the workspace the flat routes / active tree address",
    )
    unreachable: bool = Field(
        default=False,
        description="True when a remote workspace's transport could not be reached",
    )
    needsAuth: bool = Field(
        default=False,
        description="True when the destination reports that SSH authentication is required.",
    )


class WorkspaceConnectRequest(BaseModel):
    """Body for ``POST /api/workspaces/{key}/connect``."""

    code: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="One-time verification code / OTP from the authenticator app or SMS",
    )


class WorkspaceConnectResponse(BaseModel):
    """Result of a bounded authentication attempt."""

    ok: bool
    key: str
    destination: str
    authenticated: bool
    message: str = ""


class WorkspaceAddRequest(BaseModel):
    """VS Code ``Add Folder to Workspace`` — append a root to the served set."""

    kind: Literal["local", "remote"] = Field(
        default="local",
        description="``local`` path or ``remote`` (registered target or cluster:/path)",
    )
    path: str | None = Field(
        default=None,
        description="Local absolute path (kind=local) or SCP cluster:/abs (kind=remote)",
    )
    name: str | None = Field(
        default=None,
        description="Registered workspace-target name (kind=remote alternative to path)",
    )
    create_if_missing: bool = Field(
        default=False,
        description="When kind=local, create the directory if it does not exist",
    )
    activate: bool = Field(
        default=True,
        description="Switch active workspace to the newly added root",
    )


def _slug(text: str) -> str:
    cleaned = _SLUG_RE.sub("-", text).strip("-").lower()
    return cleaned or "ws"


def _unique_key(base: str) -> str:
    used = {sw.key for sw in get_served_workspaces()}
    key, n = base, 2
    while key in used:
        key, n = f"{base}-{n}", n + 1
    return key


def _build_local_served(path: str, *, create_if_missing: bool) -> ServedWorkspace:
    resolved = Path(path).expanduser().resolve()
    if resolved.exists() and not resolved.is_dir():
        raise HTTPException(status_code=400, detail=f"not a directory: {resolved}")
    if not resolved.exists():
        if not create_if_missing:
            raise HTTPException(status_code=404, detail=f"path not found: {resolved}")
        resolved.mkdir(parents=True, exist_ok=True)
    key = _unique_key(_slug(f"local-{resolved.name or 'ws'}"))
    return ServedWorkspace(
        key=key,
        label=str(resolved),
        is_remote=False,
        path=str(resolved),
    )


def _build_remote_served(*, name: str | None, path: str | None) -> ServedWorkspace:
    from molab.server.deps.targets import get_workspace_target_registry
    from molab.server.workspace_targets import WorkspaceTarget
    from molab.workspace.connection import get_client
    from molab.workspace.target import LocalTarget, RemoteTarget, parse_target

    if name:
        try:
            target = get_workspace_target_registry().get(name)
        except KeyError as exc:
            raise HTTPException(
                status_code=404, detail=f"workspace target {name!r} not found"
            ) from exc
        key = _unique_key(_slug(f"remote-{target.name}"))
        cluster = get_client(target.registry_id).cluster(target.cluster_id).definition()
        label = f"{cluster['name']}:{target.root_path}"
        return ServedWorkspace(
            key=key,
            label=label,
            is_remote=True,
            target_name=target.name,
            remote_target=target,
        )

    if not path:
        raise HTTPException(
            status_code=400,
            detail="remote add requires name= (registry) or path= (cluster:/abs)",
        )
    raw = path.strip()
    if raw.startswith("@"):
        return _build_remote_served(name=raw[1:], path=None)

    parsed = parse_target(raw)
    if isinstance(parsed, LocalTarget):
        raise HTTPException(
            status_code=400,
            detail="path looks local; use kind=local",
        )
    assert isinstance(parsed, RemoteTarget)
    assert parsed.registry_id is not None and parsed.cluster_id is not None
    host_part = parsed.cluster_id
    root = parsed.path
    target_name = _slug(f"{host_part}-{Path(root).name or 'ws'}")
    wt = WorkspaceTarget(
        name=_unique_key(target_name),
        registry_id=parsed.registry_id,
        cluster_id=parsed.cluster_id,
        root_path=root,
    )
    key = _unique_key(_slug(f"remote-{wt.name}"))
    return ServedWorkspace(
        key=key,
        label=f"{parsed.name}:{root}",
        is_remote=True,
        target_name=wt.name,
        remote_target=wt,
    )


def _to_response(sw: ServedWorkspace, *, active_key: str | None) -> ServedWorkspaceResponse:
    unreachable = False
    needs_auth = False
    if sw.is_remote:
        try:
            get_workspace_by_key(sw.key)
        except RemoteWorkspaceUnreachableError as exc:
            unreachable = True
            needs_auth = exc.details.get("reason") == "needs_auth"
    return ServedWorkspaceResponse(
        key=sw.key,
        label=sw.label,
        isRemote=sw.is_remote,
        path=sw.path,
        active=sw.key == active_key,
        unreachable=unreachable,
        needsAuth=needs_auth,
    )


def _cluster_for_served_key(key: str) -> tuple[Cluster, str]:
    from molab.server.deps.served import resolve_served_remote_target
    from molab.workspace.connection import get_client

    sw = _served_by_key(key)
    if sw is None:
        raise UnknownWorkspaceError(key)
    if not sw.is_remote:
        raise HTTPException(status_code=400, detail="Workspace uses the local filesystem")
    target = resolve_served_remote_target(sw.target_name or sw.key)
    return get_client(target.registry_id).cluster(target.cluster_id), target.cluster_id


def _list_visible(
    user: AuthUser | None,
) -> list[ServedWorkspaceResponse]:
    """Shared list builder for GET / and post-mutation responses."""
    active_key = active_served_key()
    served = get_served_workspaces()
    if is_auth_enabled() and user is not None:
        allowed = set(get_auth_service().filter_workspaces(user, [w.key for w in served]))
        served = [w for w in served if w.key in allowed]
    return [_to_response(w, active_key=active_key) for w in served]


def _activate_served(sw: ServedWorkspace) -> None:
    """Point the active-workspace overrides at *sw* (local path or remote name)."""
    if sw.is_remote:
        name = sw.target_name or (sw.remote_target.name if sw.remote_target else sw.key)
        set_active_workspace_descriptor(name)
    else:
        if not sw.path:
            raise HTTPException(status_code=500, detail="local workspace missing path")
        set_workspace_path_override(Path(sw.path).expanduser().resolve())


@router.get("", response_model=list[ServedWorkspaceResponse])
def list_workspaces(
    user: Annotated[AuthUser | None, Depends(get_optional_user)] = None,
) -> list[ServedWorkspaceResponse]:
    """List the workspaces ``molab serve`` was started with.

    A remote workspace whose transport is currently unreachable is still
    listed, flagged ``unreachable`` so the UI can degrade gracefully rather
    than failing the whole list. ``needsAuth`` identifies authentication failures;
    network failures do not trigger a verification-code dialog.

    When auth is enabled, the list is filtered by the user's workspace allowlist.
    """
    return _list_visible(user)


@router.post("/add", response_model=ServedWorkspaceResponse)
def add_workspace(
    body: WorkspaceAddRequest,
    user: Annotated[AuthUser | None, Depends(get_optional_user)] = None,
) -> ServedWorkspaceResponse:
    """VS Code ``Add Folder to Workspace`` — append a root to the live served set.

    Accepts a local absolute path (``kind=local``) or a remote descriptor
    (``kind=remote`` with registry ``name`` / ``@name`` / ``cluster:/abs`` path).
    Optional ``activate`` switches the active workspace to the new root.
    """
    del user  # auth allowlist for dynamic roots is process-scoped in v1
    if body.kind == "local":
        if not body.path or not body.path.strip():
            raise HTTPException(status_code=400, detail="local add requires path=")
        sw = _build_local_served(body.path.strip(), create_if_missing=body.create_if_missing)
        if body.create_if_missing and sw.path:
            from molab.workspace import Workspace

            Workspace(Path(sw.path))
    else:
        sw = _build_remote_served(name=body.name, path=body.path)

    added = add_served_workspace(sw)
    if body.activate:
        _activate_served(added)
        reset_workspace_cache()

    return _to_response(added, active_key=active_served_key())


@router.delete("/{key}", response_model=list[ServedWorkspaceResponse])
def remove_workspace(
    key: str,
    user: Annotated[AuthUser | None, Depends(get_optional_user)] = None,
) -> list[ServedWorkspaceResponse]:
    """VS Code ``Remove Folder from Workspace`` — drop a root from the served set.

    Does not delete files on disk. When the removed root was active, the first
    remaining served workspace becomes active (if any).
    """
    if is_auth_enabled() and user is not None:
        allowed = get_auth_service().filter_workspaces(user, [key])
        if key not in allowed:
            raise HTTPException(status_code=403, detail=f"workspace {key!r} not allowed")

    was_active = active_served_key() == key
    if not remove_served_workspace(key):
        raise HTTPException(status_code=404, detail=f"workspace {key!r} not found")

    if was_active:
        remaining = get_served_workspaces()
        if remaining:
            _activate_served(remaining[0])
        else:
            set_workspace_path_override(None)
            set_active_workspace_descriptor(None)
        reset_workspace_cache()

    return _list_visible(user)


@router.post("/{key}/connect", response_model=WorkspaceConnectResponse)
def connect_workspace(
    key: str,
    body: WorkspaceConnectRequest,
    user: Annotated[AuthUser | None, Depends(get_optional_user)] = None,
) -> WorkspaceConnectResponse:
    """Authenticate through molq, then reopen the workspace with the same connection settings."""
    if is_auth_enabled() and user is not None:
        allowed = get_auth_service().filter_workspaces(user, [key])
        if key not in allowed:
            raise HTTPException(status_code=403, detail=f"workspace {key!r} not allowed")

    try:
        cluster, destination = _cluster_for_served_key(key)
    except UnknownWorkspaceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    from molq import MolqError

    try:
        cluster.authenticate(body.code)
    except MolqError as exc:
        status = {"AUTH_REQUIRED": 401, "CONNECTION_TIMEOUT": 504}.get(exc.kind, 502)
        detail = {401: "auth", 504: "timeout"}.get(
            status, f"Authentication connection failed: {exc.context.get('diagnostic') or exc}"
        )
        raise HTTPException(status_code=status, detail=detail) from None

    # Drop any prior failed Workspace so the next probe re-opens cleanly.
    reset_workspace_cache()

    # Probe actual access; authentication success alone does not prove the root is readable.
    try:
        get_workspace_by_key(key)
    except RemoteWorkspaceUnreachableError as exc:
        raise HTTPException(
            status_code=502, detail=f"Connected, but cannot read this root: {exc.__cause__ or exc}"
        ) from exc

    return WorkspaceConnectResponse(
        ok=True,
        key=key,
        destination=destination,
        authenticated=True,
        message="ok",
    )
