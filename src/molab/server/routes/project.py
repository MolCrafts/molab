"""Project routes for Molab API."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from molab.workspace.refs import InvalidRefError

from ..dependencies import get_workspace
from ..exceptions import AssetNotFoundError, ProjectNotFoundError
from ..schemas import (
    AssetVersionResponse,
    ManagedAssetResponse,
    MessageResponse,
    ProjectCreateRequest,
    ProjectResponse,
)

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectResponse])
def list_projects(workspace=Depends(get_workspace)) -> list[ProjectResponse]:  # noqa: ANN001
    # experimentCount is what the UI shows before a project is expanded
    # ("3 exp" vs forever "…"); cheap list_experiments on open is intentional.
    return [
        ProjectResponse.from_model(p, experiment_count=len(p.list_experiments()))
        for p in workspace.list_projects()
    ]


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
    return ProjectResponse.from_model(new_project)


@router.delete("/{project_id}", response_model=MessageResponse)
def delete_project(project_id: str, workspace=Depends(get_workspace)) -> MessageResponse:  # noqa: ANN001
    try:
        workspace.remove_project(project_id)
    except KeyError:
        raise ProjectNotFoundError(project_id)  # noqa: B904
    return MessageResponse(message="Project deleted")


# ── Project Assets ──────────────────────────────────────────────────────────


@router.get("/{project_id}/assets", response_model=list[ManagedAssetResponse])
def list_project_assets(
    project_id: str,
    limit: int = 100,
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> list[ManagedAssetResponse]:
    """List long-lived Project data identities."""
    project = workspace.get_project(project_id)
    return [
        ManagedAssetResponse.from_model(asset, len(project.assets.versions(asset.id)))
        for asset in project.assets.list()[:limit]
    ]


@router.get("/{project_id}/assets/{asset_id}", response_model=ManagedAssetResponse)
def get_project_asset(
    project_id: str,
    asset_id: str,
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> ManagedAssetResponse:
    project = workspace.get_project(project_id)
    try:
        asset = project.assets.get(asset_id)
    except KeyError:
        raise AssetNotFoundError(asset_id) from None
    return ManagedAssetResponse.from_model(asset, len(project.assets.versions(asset.id)))


@router.get(
    "/{project_id}/assets/{asset_id}/versions",
    response_model=list[AssetVersionResponse],
)
def list_project_asset_versions(
    project_id: str,
    asset_id: str,
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> list[AssetVersionResponse]:
    """List immutable versions of a Project Asset."""
    project = workspace.get_project(project_id)
    try:
        project.assets.get(asset_id)
    except KeyError:
        raise AssetNotFoundError(asset_id) from None
    return [
        AssetVersionResponse.from_model(version) for version in project.assets.versions(asset_id)
    ]


@router.get("/{project_id}/assets/{asset_id}/download")
def download_project_asset(project_id: str, asset_id: str, workspace=Depends(get_workspace)):  # noqa: ANN001, ANN201
    project = workspace.get_project(project_id)
    try:
        payload = project.assets.payload_path(asset_id)
    except InvalidRefError:
        raise
    except (KeyError, ValueError):
        raise AssetNotFoundError(asset_id) from None
    if not payload or not workspace.fs.exists(payload) or workspace.fs.is_dir(payload):
        raise AssetNotFoundError(asset_id)
    versions = project.assets.versions(asset_id)
    media_type = versions[-1].media_type if versions else None
    return StreamingResponse(
        workspace.fs.open(payload, "rb"),
        media_type=media_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{asset_id}"'},
    )
