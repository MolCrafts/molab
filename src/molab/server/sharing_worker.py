"""A fixed-UID private workspace service with owner-approved publication."""

from collections.abc import AsyncGenerator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

import anyio
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from mollog import get_logger
from starlette.background import BackgroundTask

from molab.ids import compute_definition_hash
from molab.services.auth import set_auth_enabled
from molab.sharing.assets import AssetPublisher
from molab.sharing.models import (
    AssetInventoryItem,
    AssetShare,
    AssetShareRequest,
    AssetSharingCapabilities,
    InventoryProject,
    PreviewResponse,
    PublicationReceipt,
    PublicationSelection,
    PublishRequest,
)
from molab.sharing.publisher import Publisher, build_preview
from molab.sharing.settings import WorkerSettings
from molab.sharing.store import SharingError
from molab.workspace import Workspace
from molab.workspace.refs import ref_of

from .app import _mount_webapp, create_app
from .dependencies import ServedWorkspace, set_served_workspaces, set_workspace_path_override
from .sharing_boundary import SharingBoundary

logger = get_logger(__name__)


def create_managed_app(
    root: Path, settings: WorkerSettings, *, static_dir: Path | None = None
) -> FastAPI:
    settings.assert_uid()
    root = root.resolve(strict=True)
    workspace = Workspace(root)
    publisher = Publisher(workspace, settings)
    assets = AssetPublisher(publisher)
    # This factory owns its process. Local password sessions are not accepted
    # as proxy identities, nor shared between per-user services.
    set_auth_enabled(False)
    set_workspace_path_override(root)
    set_served_workspaces(
        [ServedWorkspace(key="managed", label="Workspace", is_remote=False, path=str(root))]
    )
    app = create_app(serve_static=False, allow_dev_origins=False)
    app.add_middleware(SharingBoundary, settings=settings, worker_subject=settings.subject)
    original_lifespan = app.router.lifespan_context

    async def refresh() -> None:
        while True:
            await anyio.sleep(15)
            try:
                await anyio.to_thread.run_sync(assets.reconcile)
            except (OSError, ValueError, SharingError):
                logger.warning("Asset filesystem revocation is pending; cleanup will retry")
            try:
                await anyio.to_thread.run_sync(publisher.refresh_all)
            except (OSError, ValueError, SharingError):
                logger.warning("Sharing gateway unavailable; keeping the last published version")

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncGenerator[None]:
        # Cleanup-only source authentication also works after a source or owner
        # is disabled. Do this before normal source verification at startup.
        await anyio.to_thread.run_sync(assets.reconcile)
        await anyio.to_thread.run_sync(publisher.verify_source)
        async with original_lifespan(application), anyio.create_task_group() as tasks:
            tasks.start_soon(refresh)
            try:
                yield
            finally:
                tasks.cancel_scope.cancel()

    app.router.lifespan_context = lifespan

    @app.exception_handler(SharingError)
    async def sharing_error(_request: Request, exc: SharingError) -> JSONResponse:
        return JSONResponse({"detail": exc.message}, status_code=exc.status)

    @app.get("/api/sharing/worker")
    def worker_identity() -> dict[str, object]:
        return {
            "principal_id": settings.principal_id,
            "gateway_url": str(settings.gateway_url),
            "uid": settings.uid,
        }

    @app.get("/api/sharing/worker/inventory", response_model=list[InventoryProject])
    def publication_inventory() -> list[dict[str, object]]:
        return [
            {
                "id": p.id,
                "name": p.name,
                "experiments": [
                    {
                        "id": e.id,
                        "name": e.name,
                        "runs": [
                            {
                                "ref": str(ref_of(r)),
                                "name": r.name,
                                "parameter_keys": list(r.parameters),
                            }
                            for r in e.list_runs()
                        ],
                    }
                    for e in p.list_experiments()
                ],
            }
            for p in workspace.list_projects()
        ]

    @app.post("/api/sharing/worker/preview", response_model=PreviewResponse)
    def publication_preview(selection: PublicationSelection) -> dict[str, object]:
        try:
            preview = build_preview(workspace, selection)
        except ValueError as exc:
            raise SharingError(
                422, "Selected metadata must use scalar parameters and finite numeric metrics"
            ) from exc
        return {
            "preview": preview.model_dump(mode="json"),
            "digest": compute_definition_hash(preview.model_dump(mode="json")),
        }

    @app.post("/api/sharing/worker/publish", response_model=PublicationReceipt)
    def publish_project(body: PublishRequest) -> dict[str, object]:
        try:
            return publisher.publish(body.selection, body.preview_digest)
        except ValueError as exc:
            raise SharingError(
                422, "Selected metadata must use scalar parameters and finite numeric metrics"
            ) from exc

    @app.get("/api/sharing/worker/assets/capabilities", response_model=AssetSharingCapabilities)
    def asset_capabilities() -> AssetSharingCapabilities:
        storage = settings.asset_storage
        return AssetSharingCapabilities(
            enabled=storage is not None,
            backend=storage.backend if storage else None,
            group_id=storage.group_id if storage else None,
        )

    @app.get(
        "/api/sharing/worker/projects/{project_id}/assets", response_model=list[AssetInventoryItem]
    )
    def asset_inventory(project_id: str) -> list[AssetInventoryItem]:
        return assets.inventory(project_id)

    @app.post("/api/sharing/worker/assets", response_model=AssetShare, status_code=201)
    def publish_asset(body: AssetShareRequest) -> AssetShare:
        try:
            return assets.publish(body)
        except OSError as exc:
            raise SharingError(
                422, "The publication filesystem rejected the file operation"
            ) from exc

    @app.post("/api/sharing/worker/assets/reconcile", status_code=204)
    def reconcile_assets() -> None:
        assets.reconcile()

    @app.get("/api/sharing/worker/assets/{asset_share_id}/download")
    def download_asset(asset_share_id: str) -> StreamingResponse:
        transfer, handle = assets.open_download(asset_share_id)

        def chunks() -> Iterator[bytes]:
            try:
                while chunk := handle.read(1024 * 1024):
                    yield chunk
            finally:
                handle.close()

        return StreamingResponse(
            chunks(),
            media_type="application/octet-stream",
            headers={
                "Content-Length": str(transfer.size),
                "Content-Disposition": f"attachment; filename*=UTF-8''{quote(transfer.title, safe='')}",
                "X-Content-Type-Options": "nosniff",
            },
            background=BackgroundTask(handle.close),
        )

    if static_dir is not None:
        _mount_webapp(app, static_dir)
    return app
