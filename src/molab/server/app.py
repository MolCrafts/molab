"""Molab API Server.

This module provides the FastAPI application factory.
It strictly adheres to the standard pattern:
- /api/* -> Backend API
- /* -> Static Files (Production only, SPA support)
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mollog import get_logger

from molab.plugins import discover_ui_plugin_dirs

from .handlers import register_exception_handlers
from .routes import create_api_router
from .schemas import HealthResponse

logger = get_logger(__name__)

# Shown when ``src/molab/dist/index.html`` is missing (typical editable
# install before ``npm run build:web``). Keep this HTML, not JSON: a
# colleague opening the ``--tunnel`` URL in a browser should see next steps.
_API_ONLY_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>molab</title></head>
<body style="font:16px/1.5 system-ui,sans-serif;max-width:40rem;margin:3rem auto;padding:0 1rem">
<h1>molab API only</h1>
<p>This process has no bundled UI (<code>src/molab/dist/index.html</code> is missing).</p>
<ul>
  <li><a href="/api/docs">OpenAPI docs</a></li>
  <li><a href="/api/health">Health</a></li>
</ul>
<p>From a source checkout:</p>
<pre>npm install
npm run build:web
molab serve -ws … --tunnel</pre>
<p>Or live-reload: <code>molab serve --dev -ws …</code>. With <code>--tunnel</code> the public URL punches the Dev UI (Rsbuild), not this API-only page.</p>
</body></html>"""


async def _run_plugin_hook(plugin: object, attr: str) -> None:
    """Run one server plugin lifespan hook, awaiting it when it is async.

    A plugin that raises must not abort startup or strand the remaining
    plugins' teardown, so failures are logged and swallowed.
    """
    import inspect

    hook = getattr(plugin, attr, None)
    if hook is None:
        return
    try:
        result = hook()
        if inspect.isawaitable(result):
            await result
    except Exception as exc:
        pid = getattr(plugin, "id", "<unknown>")
        logger.warning(f"server plugin '{pid}' {attr} raised; ignoring: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:  # noqa: ARG001
    """Application lifespan: run each server plugin's startup and shutdown hook.

    Shutdown order matters: each plugin's SSE / long-poll generators are woken
    first (via :func:`~molab.plugins.server.signal_shutdown_server_plugins`) so
    uvicorn's connection drain can finish, and only then is each plugin's
    in-flight background work cancelled and awaited, so no orphan task
    survives teardown. With no plugin installed both steps are no-ops.
    """
    from molab.plugins import discover_server_plugins, signal_shutdown_server_plugins

    plugins = discover_server_plugins()

    for plugin in plugins:
        await _run_plugin_hook(plugin, "startup")
    logger.info("Molab server starting up")
    try:
        yield
    finally:
        # 1) Cooperative stop for plugin SSE / long-poll generators still open
        # in the browser. Without this, uvicorn hangs on "Waiting for
        # connections to close" until every tab disconnects.
        signal_shutdown_server_plugins()
        # 2) Cancel in-flight background work owned by this process.
        for plugin in plugins:
            await _run_plugin_hook(plugin, "shutdown")
        logger.info("Molab server shutting down")


# ---------------------------------------------------------------------------
# Bundled frontend discovery
# ---------------------------------------------------------------------------


def _find_bundled_webapp() -> Path | None:
    """Locate the ``dist`` directory shipped inside the installed package.

    Uses ``importlib.resources`` so this works regardless of whether the
    package was installed from a wheel, an editable install, or a checkout.
    Returns *None* when the frontend has not been compiled (normal in dev).
    """
    from importlib import resources

    try:
        pkg_path = Path(str(resources.files("molab")))
        webapp = pkg_path / "dist"
        if webapp.is_dir() and (webapp / "index.html").exists():
            return webapp
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# SPA mount helper
# ---------------------------------------------------------------------------


def _mount_webapp(app: FastAPI, webapp_dir: Path) -> None:
    """Mount the React SPA and its static assets onto *app*.

    Must be called **after** all ``/api`` routes have been registered so that
    API routes take priority over the catch-all SPA fallback.
    """
    from fastapi.responses import FileResponse
    from starlette.staticfiles import StaticFiles

    index_html = str(webapp_dir / "index.html")

    # Serve hashed JS / CSS / images produced by rsbuild. These have
    # content-hashed filenames so browsers can cache them aggressively
    # — a new build produces new filenames automatically.
    static_subdir = webapp_dir / "static"
    if static_subdir.is_dir():
        app.mount(
            "/static",
            StaticFiles(directory=str(static_subdir)),
            name="webapp_static",
        )

    # SPA fallback — serves index.html for every non-API, non-static path.
    # ``index.html`` is the only un-hashed asset, so it MUST never be cached
    # by the browser; otherwise a fresh build's new JS hashes won't be loaded.
    # Unmatched ``/api/*`` must NOT fall through to index.html (200 HTML) —
    # the SPA client then tries ``response.json()`` and floods the console
    # with "Unexpected token '<'" parse errors.
    from fastapi import HTTPException

    no_cache_headers = {"Cache-Control": "no-store, must-revalidate"}

    @app.get("/{full_path:path}", include_in_schema=False)
    async def _spa_fallback(full_path: str) -> FileResponse:
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = webapp_dir / full_path
        if full_path and candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(index_html, headers=no_cache_headers)


# ---------------------------------------------------------------------------
# Plugin static-asset mounting
# ---------------------------------------------------------------------------


def _mount_plugin_static_dirs(app: FastAPI) -> None:
    """Mount one ``StaticFiles`` route per third-party UI bundle.

    Each discovered bundle is mounted at ``/api/plugins/{id}/`` so the
    browser can fetch ``manifest.json`` and the ESM entry from there.
    Built-in plugins (``core``, ``metrics``, ``molq``, ``molvis``) ship
    their UI inside the main bundle; only third-party plugins need this
    out-of-band mount.
    """
    from starlette.staticfiles import StaticFiles

    for plugin_id, path in discover_ui_plugin_dirs().items():
        app.mount(
            f"/api/plugins/{plugin_id}",
            StaticFiles(directory=str(path)),
            name=f"plugin_static_{plugin_id}",
        )


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def create_app(
    static_dir: str | Path | None = None,
    *,
    serve_static: bool = True,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        static_dir: Explicit path to built UI files.  When *None* and
            *serve_static* is ``True`` the bundled ``dist`` directory
            is auto-detected via ``importlib.resources``.
        serve_static: Set to ``False`` to run in API-only mode.
    """
    from .openapi_ids import molab_operation_id

    app = FastAPI(
        title="Molab API",
        version="0.1.0",
        description="Research workflow management API",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
        generate_unique_id_function=molab_operation_id,
    )

    # 1. CORS Configuration (Dev Mode Support)
    origins = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 2. Exception Handlers
    register_exception_handlers(app)

    # 3. API Routes (all under /api prefix)
    api_router = create_api_router()
    app.include_router(api_router, prefix="/api")

    # 3.5 Per-plugin static-asset mounts (third-party only)
    _mount_plugin_static_dirs(app)

    # 4. System Routes (Health Check) — always public (auth gate does not wrap app-level routes)
    @app.get("/api/health", response_model=HealthResponse, tags=["system"])
    def health_check() -> HealthResponse:
        from molab.plugins import Capability, registry
        from molab.services.auth import is_auth_enabled

        return HealthResponse(
            status="healthy",
            workspace_available=True,
            capabilities={cap.value: registry.is_available(cap) for cap in Capability},
            auth_required=is_auth_enabled(),
        )

    # 5. Static file serving (production) or root fallback (dev / no build)
    webapp_path: Path | None = None
    if serve_static:
        if static_dir is not None:
            webapp_path = Path(static_dir)
        else:
            webapp_path = _find_bundled_webapp()

    if webapp_path is not None and webapp_path.is_dir() and (webapp_path / "index.html").exists():
        _mount_webapp(app, webapp_path)
    else:

        @app.get("/", tags=["system"])
        def root():  # noqa: ANN202
            from fastapi.responses import HTMLResponse

            # No compiled SPA (src/molab/dist/index.html missing). Browsers
            # hitting the tunnel URL used to see a raw JSON stub — show a
            # short page instead. API clients still have /api/docs.
            return HTMLResponse(_API_ONLY_PAGE)

    return app
