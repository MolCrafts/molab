"""Project routes for Molab API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import Field

from molab.fs.window import iter_file_chunks
from molab.workspace.refs import InvalidRefError

from ..dependencies import get_workspace
from ..deps.served import active_served_key, assert_workspace_writable
from ..exceptions import AssetNotFoundError, ProjectNotFoundError
from ..schemas import (
    ManagedAssetResponse,
    MessageResponse,
    ProjectCreateRequest,
    ProjectResponse,
)
from ..schemas._wire import ApiModel

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
    return [ManagedAssetResponse.from_model(asset) for asset in project.assets.list()[:limit]]


class AssetImportRequest(ApiModel):
    """Import a file already in the served workspace as a project asset."""

    name: str = Field(..., min_length=1, description="Asset title.")
    path: str = Field(..., min_length=1, description="Workspace-relative path of the file.")


def _require_writable(request: Request) -> None:
    """Reject a mutating request against a remote (read-only) served workspace."""
    assert_workspace_writable(active_served_key() or "", request.method)


@router.post(
    "/{project_id}/assets",
    response_model=ManagedAssetResponse,
    status_code=201,
    dependencies=[Depends(_require_writable)],
)
def import_project_asset(
    project_id: str,
    body: AssetImportRequest,
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> ManagedAssetResponse:
    """Import a workspace file as a project asset — the same verb as ``molab asset import``.

    422 when the path is not a file inside the served directory.
    """
    from pathlib import Path as _LocalPath
    from pathlib import PurePosixPath

    pure = PurePosixPath(body.path)
    if pure.is_absolute() or ".." in pure.parts:
        raise HTTPException(422, f"{body.path!r} must be a path inside the served directory")
    root = _LocalPath(str(workspace.root)).resolve()
    source = (root / pure).resolve()
    if not source.is_relative_to(root) or not source.is_file():
        raise HTTPException(422, f"{body.path!r} is not a file in the served directory")
    project = workspace.get_project(project_id)
    try:
        asset = project.import_asset(body.name, source, tags={"role": "import"})
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return ManagedAssetResponse.from_model(asset)


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
    return ManagedAssetResponse.from_model(asset)


@router.get("/{project_id}/assets/{asset_id}/download")
def download_project_asset(project_id: str, asset_id: str, workspace=Depends(get_workspace)):  # noqa: ANN001, ANN201
    project = workspace.get_project(project_id)
    try:
        asset = project.assets.get(asset_id)
        payload = project.assets.payload_path(asset_id)
    except InvalidRefError:
        raise
    except (KeyError, ValueError):
        raise AssetNotFoundError(asset_id) from None
    if not payload or not workspace.fs.exists(payload) or workspace.fs.is_dir(payload):
        raise AssetNotFoundError(asset_id)
    return StreamingResponse(
        iter_file_chunks(workspace.fs, payload, size=workspace.fs.getsize(payload)),
        media_type=asset.media_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{asset_id}"'},
    )
