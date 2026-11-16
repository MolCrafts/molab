"""Dedicated metadata gateway. No workspace routers or plugin discovery."""

from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Query, Request
from fastapi import Path as ApiPath
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from starlette.staticfiles import StaticFiles

from molab.sharing.models import (
    AssetShare,
    AssetTransfer,
    BeginPublication,
    Invitation,
    InvitationRequest,
    PrepareAssetShare,
    Principal,
    ProjectMembers,
    PublicationBatch,
    PublicationReceipt,
    PublishedExperiment,
    PublishedRun,
    SharedPage,
    SharedProject,
)
from molab.sharing.settings import GatewaySettings
from molab.sharing.store import SharingError, SharingStore

from .openapi_ids import molab_operation_id
from .sharing_boundary import SharingBoundary


def create_sharing_app(settings: GatewaySettings, *, static_dir: Path | None = None) -> FastAPI:
    store = SharingStore(settings.state_dir, local_state_confirmed=settings.local_state_confirmed)
    app = FastAPI(
        title="Molab Project Sharing",
        version="1",
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/sharing/openapi.json",
        generate_unique_id_function=molab_operation_id,
    )
    app.state.sharing_store = store
    app.add_middleware(SharingBoundary, settings=settings)

    @app.exception_handler(SharingError)
    async def sharing_error(_request: Request, exc: SharingError) -> JSONResponse:
        return JSONResponse(
            {"detail": exc.message}, status_code=exc.status, headers={"Cache-Control": "no-store"}
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        # Do not echo input values (a rejected field could contain a secret).
        return JSONResponse(
            {"detail": [{"loc": e["loc"], "msg": e["msg"]} for e in exc.errors()]}, status_code=422
        )

    def principal(request: Request) -> Principal:
        return store.principal(settings.issuer, request.state.sharing_subject)

    def source_credential(request: Request) -> str:
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer "):
            raise SharingError(401, "Source authentication required")
        return auth[7:]

    User = Annotated[Principal, Depends(principal)]
    Credential = Annotated[str, Depends(source_credential)]

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "project-sharing"}

    @app.get("/api/sharing/me")
    def sharing_me(user: User) -> Principal:
        return user

    @app.get("/api/sharing/projects", response_model=SharedPage[SharedProject])
    def sharing_projects(
        user: User,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 100,
    ) -> dict[str, object]:
        return store.list_projects(user.id, offset=offset, limit=limit)

    @app.get("/api/sharing/projects/{project_id}", response_model=SharedProject)
    def sharing_project(project_id: str, user: User) -> dict[str, object]:
        return store.get_project(user.id, project_id)

    @app.get(
        "/api/sharing/projects/{project_id}/experiments",
        response_model=SharedPage[PublishedExperiment],
    )
    def sharing_experiments(
        project_id: str,
        user: User,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 100,
    ) -> dict[str, object]:
        return store.objects(user.id, project_id, "experiment", offset=offset, limit=limit)

    @app.get("/api/sharing/projects/{project_id}/runs", response_model=SharedPage[PublishedRun])
    def sharing_runs(
        project_id: str,
        user: User,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 100,
    ) -> dict[str, object]:
        return store.objects(user.id, project_id, "run", offset=offset, limit=limit)

    @app.get("/api/sharing/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/metrics")
    def sharing_metrics(
        project_id: str, experiment_id: str, run_id: str, user: User
    ) -> dict[str, object]:
        return store.metrics(user.id, project_id, experiment_id, run_id)

    @app.delete("/api/sharing/projects/{project_id}/publication", status_code=204)
    def stop_sharing(project_id: str, user: User) -> None:
        store.stop_publication(user.id, project_id)

    @app.get("/api/sharing/projects/{project_id}/members", response_model=ProjectMembers)
    def sharing_members(project_id: str, user: User) -> dict[str, object]:
        return store.members(user.id, project_id)

    @app.post(
        "/api/sharing/projects/{project_id}/invitations", status_code=201, response_model=Invitation
    )
    def invite_viewer(project_id: str, body: InvitationRequest, user: User) -> dict[str, object]:
        return store.invite(user.id, project_id, body.recipient_id)

    @app.get("/api/sharing/invitations", response_model=list[Invitation])
    def sharing_invitations(user: User) -> list[dict[str, object]]:
        return store.invitations(user.id)

    @app.post("/api/sharing/invitations/{invitation_id}/accept", status_code=204)
    def accept_sharing(invitation_id: str, user: User) -> None:
        store.respond(user.id, invitation_id, accept=True)

    @app.post("/api/sharing/invitations/{invitation_id}/decline", status_code=204)
    def decline_sharing(invitation_id: str, user: User) -> None:
        store.respond(user.id, invitation_id, accept=False)

    @app.delete("/api/sharing/invitations/{invitation_id}", status_code=204)
    def revoke_invitation(invitation_id: str, user: User) -> None:
        store.revoke_invitation(user.id, invitation_id)

    @app.delete("/api/sharing/projects/{project_id}/members/{recipient_id}", status_code=204)
    def remove_viewer(project_id: str, recipient_id: str, user: User) -> None:
        store.revoke_member(user.id, project_id, recipient_id)

    @app.get("/api/sharing/projects/{project_id}/assets", response_model=SharedPage[AssetShare])
    def sharing_assets(
        project_id: str,
        user: User,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 100,
    ) -> dict[str, object]:
        return store.list_assets(user.id, project_id, offset=offset, limit=limit)

    @app.delete("/api/sharing/assets/{asset_share_id}", status_code=204)
    def revoke_asset(asset_share_id: str, user: User) -> None:
        store.revoke_asset(user.id, asset_share_id)

    @app.post("/internal/sharing/assets", response_model=AssetTransfer, status_code=201)
    def prepare_asset(body: PrepareAssetShare, credential: Credential) -> dict[str, object]:
        return store.prepare_asset(credential, body)

    @app.get("/internal/sharing/assets/cleanup")
    def asset_cleanup(
        credential: Credential, after_id: Annotated[str, Query(max_length=160)] = ""
    ) -> dict[str, object]:
        return store.asset_cleanup(credential, after_id=after_id)

    @app.post("/internal/sharing/assets/{asset_share_id}/commit", response_model=AssetShare)
    def commit_asset(asset_share_id: str, credential: Credential) -> dict[str, object]:
        return store.commit_asset(credential, asset_share_id)

    @app.get("/internal/sharing/assets/{asset_share_id}/access", response_model=AssetTransfer)
    def asset_access(asset_share_id: str, credential: Credential) -> dict[str, object]:
        return store.asset_access(credential, asset_share_id)

    @app.post("/internal/sharing/assets/{asset_share_id}/removed", status_code=204)
    def removed_asset(asset_share_id: str, credential: Credential) -> None:
        store.finish_asset_cleanup(credential, asset_share_id)

    @app.get("/internal/sharing/source")
    def source_identity(credential: Credential) -> dict[str, object]:
        return store.source_identity(credential)

    @app.get("/internal/sharing/source/project")
    def source_project(
        workspace_id: str, project_id: str, credential: Credential
    ) -> dict[str, object]:
        return store.source_project(credential, workspace_id, project_id)

    @app.post("/internal/sharing/publications", status_code=201, response_model=PublicationReceipt)
    def begin_publication(body: BeginPublication, credential: Credential) -> dict[str, object]:
        return store.begin_publication(credential, body)

    @app.put("/internal/sharing/publications/{version_id}/batches/{batch_id}", status_code=204)
    def publication_batch(
        version_id: str,
        batch_id: Annotated[int, ApiPath(ge=0)],
        body: PublicationBatch,
        credential: Credential,
    ) -> None:
        store.add_batch(credential, version_id, batch_id, body)

    @app.delete("/internal/sharing/publications/{version_id}", status_code=204)
    def abort_publication(version_id: str, credential: Credential) -> None:
        store.abort_publication(credential, version_id)

    @app.post(
        "/internal/sharing/publications/{version_id}/commit", response_model=PublicationReceipt
    )
    def commit_publication(version_id: str, credential: Credential) -> dict[str, object]:
        return store.commit_publication(credential, version_id)

    if static_dir is not None:
        if not (static_dir / "index.html").is_file():
            raise ValueError("static_dir must contain the built web UI")
        if (static_dir / "static").is_dir():
            app.mount(
                "/static", StaticFiles(directory=static_dir / "static"), name="sharing-static"
            )

        @app.get("/", include_in_schema=False)
        def sharing_home() -> RedirectResponse:
            return RedirectResponse("/shared")

        @app.get("/{path:path}", include_in_schema=False)
        def sharing_ui(path: str) -> Response:
            if path.startswith(("api/", "internal/")) or path in {"api", "internal"}:
                return JSONResponse({"detail": "Not found"}, status_code=404)
            return FileResponse(static_dir / "index.html", headers={"Cache-Control": "no-store"})

    return app
