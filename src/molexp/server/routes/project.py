"""Project routes for MolExp API."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile
from fastapi.responses import StreamingResponse

from molexp.services.workspace_read_model import WorkspaceReadModel

from ..dependencies import get_workspace
from ..deps.read_model import get_read_model
from ..exceptions import AssetNotFoundError, ProjectNotFoundError
from ..http_cache import not_modified, weak_etag
from ..mutations import after_mutation
from ..schemas import (
    AssetResponse,
    MessageResponse,
    ProjectCreateRequest,
    ProjectResponse,
)

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectResponse])
def list_projects(workspace=Depends(get_workspace)) -> list[ProjectResponse]:  # noqa: ANN001
    return [ProjectResponse.from_model(p) for p in workspace.list_projects()]


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str, workspace=Depends(get_workspace)) -> ProjectResponse:  # noqa: ANN001
    project = workspace.get_project(project_id)
    return ProjectResponse.from_model(project, experiment_count=len(project.list_experiments()))


@router.post("", response_model=ProjectResponse, status_code=201)
def create_project(
    project: ProjectCreateRequest,
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> ProjectResponse:
    new_project = workspace.add_project(project.name)
    after_mutation(workspace, "project", ref=new_project.id, project_id=new_project.id)
    return ProjectResponse.from_model(new_project)


@router.delete("/{project_id}", response_model=MessageResponse)
def delete_project(project_id: str, workspace=Depends(get_workspace)) -> MessageResponse:  # noqa: ANN001
    try:
        workspace.remove_project(project_id)
    except KeyError:
        raise ProjectNotFoundError(project_id)  # noqa: B904
    after_mutation(workspace, "project", ref=project_id, project_id=project_id)
    return MessageResponse(message="Project deleted")


# ── Project Assets ──────────────────────────────────────────────────────────


@router.get("/{project_id}/assets", response_model=list[AssetResponse])
def list_project_assets(
    project_id: str,
    request: Request,
    response: Response,
    limit: int = 100,
    workspace=Depends(get_workspace),  # noqa: ANN001
    read_model: WorkspaceReadModel = Depends(get_read_model),
) -> list[AssetResponse]:
    """List every asset (any kind) in the project scope.

    Served from the read-model snapshot's per-scope index, so the project page
    no longer re-reads a manifest on every visit.
    """
    project = workspace.get_project(project_id)
    snapshot = read_model.assets()
    cached = not_modified(
        request, response, weak_etag("project-assets", snapshot.version, project_id, limit)
    )
    if cached is not None:
        return cached  # type: ignore[return-value]
    scope_dir = str(project.resolve())
    assets = snapshot.by_scope_dir.get(scope_dir, ())
    return [AssetResponse.from_model(a) for a in assets[:limit]]


@router.get("/{project_id}/assets/{asset_id}", response_model=AssetResponse)
def get_project_asset(
    project_id: str,
    asset_id: str,
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> AssetResponse:
    project = workspace.get_project(project_id)
    asset = project.assets.get(asset_id)
    if not asset:
        raise AssetNotFoundError(asset_id)
    return AssetResponse.from_model(asset)


@router.post("/{project_id}/assets/upload", response_model=AssetResponse, status_code=201)
async def upload_project_asset(
    project_id: str,
    file: UploadFile = File(...),
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> AssetResponse:
    """Upload a file into the project's ``DataAssetLibrary``."""
    project = workspace.get_project(project_id)

    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)

    try:
        filename = file.filename or "untitled"
        asset = project.data_assets.import_asset(
            name=filename,
            src=tmp_path,
            action="move",
            meta={"original_filename": filename},
        )
        after_mutation(workspace, "asset", ref=asset.asset_id, project_id=project_id)
        return AssetResponse.from_model(asset)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise


@router.get("/{project_id}/assets/{asset_id}/download")
def download_project_asset(project_id: str, asset_id: str, workspace=Depends(get_workspace)):  # noqa: ANN001, ANN201
    project = workspace.get_project(project_id)
    asset = project.assets.get(asset_id)
    if not asset:
        raise AssetNotFoundError(asset_id)

    payload_dir = asset.absolute_path(project.project_dir)
    if not payload_dir.exists():
        raise AssetNotFoundError(asset_id)

    if payload_dir.is_dir():
        files = list(payload_dir.iterdir())
        if not files:
            raise AssetNotFoundError(asset_id)
        file_path = files[0]
    else:
        file_path = payload_dir

    filename = asset.tags.get("original_filename") or file_path.name
    return StreamingResponse(
        open(file_path, "rb"),  # noqa: PTH123
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
