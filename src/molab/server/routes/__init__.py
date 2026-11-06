"""API Routes package.

This package contains all the modularized API routes organized by domain.
"""

from fastapi import APIRouter, Depends, Request
from mollog import get_logger

from ..dependencies import assert_served_workspace, assert_workspace_writable
from ..deps.auth import require_user_if_enabled
from . import (
    auth,
    catalog,
    experiment,
    history,
    knowledge,
    molq,
    preview,
    project,
    registry,
    run,
    runs_flat,
    targets,
    tensorboard,
    workflow,
    workspace,
    workspaces,
)

_logger = get_logger(__name__)


# Domain routers that address entities *inside* one workspace. They are
# mounted twice: flat (active/default workspace, back-compat) and again under
# the ``/workspaces/{ws}`` prefix (the aggregate surface). Process-global or
# active-workspace-management routers (molq, registry, targets, workspace,
# workspaces) are NOT namespaced, and neither is anything a server plugin
# contributes.
def _workspace_scoped_modules() -> tuple:
    return (
        project,
        experiment,
        run,
        runs_flat,
        preview,
        catalog,
        workflow,
        tensorboard,
        history,
    )


def _bind_ws(ws: str, request: Request) -> str:
    """Router-level dependency for the ``/workspaces/{ws}`` mount.

    Declares the ``{ws}`` path param, 404s early when it names no served
    workspace, and 405s a mutating request against a remote workspace (before
    body validation). Resolved ahead of the endpoint body. When auth is on,
    also enforces the caller's workspace allowlist.
    """
    from fastapi import HTTPException, status

    from molab.services.auth import AuthError, get_auth_service, is_auth_enabled

    from ..deps.auth import get_session_id

    assert_served_workspace(ws)
    assert_workspace_writable(ws, request.method)
    if is_auth_enabled():
        session_id = get_session_id(request, request.cookies.get("molab_session"))
        user = get_auth_service().resolve_session(session_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )
        try:
            get_auth_service().assert_workspace_access(user, ws)
        except AuthError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=exc.message) from exc
    return ws


def _create_workspace_scoped_router() -> APIRouter:
    """A mirror of the per-workspace domain routers, gated on a valid ``{ws}``."""
    scoped = APIRouter(dependencies=[Depends(_bind_ws)])
    for module in _workspace_scoped_modules():
        scoped.include_router(module.router)
    return scoped


def _register_server_plugins(router: APIRouter) -> None:
    """Attach every discovered ``molab.server_plugins`` surface to *router*.

    A plugin that raises during ``register`` is skipped with a warning: a
    broken extension must not take the whole API down.
    """
    from molab.plugins import discover_server_plugins

    for plugin in discover_server_plugins():
        try:
            plugin.register(router)
        except Exception as exc:
            _logger.warning(f"server plugin '{plugin.id}' register raised; skipping: {exc}")


def create_api_router() -> APIRouter:
    """Create and configure the main API router with all sub-routes.

    Returns:
        Configured APIRouter with all domain routes included
    """
    api_router = APIRouter()

    # Auth routes are outside the session gate (login/status are public;
    # me/users carry their own Depends).
    api_router.include_router(auth.router)

    # Everything else is gated when ``services.auth`` is enabled.
    gated = APIRouter(dependencies=[Depends(require_user_if_enabled)])

    # Third-party HTTP surfaces first: a plugin's prefixes are its own, and
    # going first lets one own a catch-all under its prefix without a core
    # router shadowing it. Ordering *within* a plugin is the plugin's business.
    _register_server_plugins(gated)

    gated.include_router(knowledge.router)
    gated.include_router(project.router)
    gated.include_router(experiment.router)
    gated.include_router(run.router)
    gated.include_router(runs_flat.flat_router)
    gated.include_router(preview.router)
    gated.include_router(catalog.router)
    gated.include_router(workspace.router)
    gated.include_router(workspaces.router)
    gated.include_router(registry.router)
    gated.include_router(molq.router)
    gated.include_router(targets.router)
    gated.include_router(tensorboard.router)
    gated.include_router(workflow.router)
    gated.include_router(history.router)

    # Aggregate surface: the same domain routers, namespaced by workspace.
    gated.include_router(_create_workspace_scoped_router(), prefix="/workspaces/{ws}")

    api_router.include_router(gated)
    return api_router


__all__ = [
    "auth",
    "catalog",
    "create_api_router",
    "experiment",
    "history",
    "knowledge",
    "molq",
    "preview",
    "project",
    "registry",
    "run",
    "runs_flat",
    "targets",
    "tensorboard",
    "workflow",
    "workspace",
    "workspaces",
]
