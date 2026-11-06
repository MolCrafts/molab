"""Catalog routes — reverse lookup from a path to the asset that holds it.

``catalog_by_path`` walks registered assets. Given a path, the UI learns
which attempt produced it and which other assets share its task.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from molab.workspace.asset_repository import scan_asset_repositories
from molab.workspace.domain import Asset, AssetScope, ExecutionOrigin
from molab.workspace.errors import AmbiguousRefError, RefNotFoundError

from ..dependencies import get_workspace
from ..schemas import (
    CatalogByPathResponse,
    CatalogProducerInfo,
    CatalogScopeInfo,
    CatalogSibling,
)

router = APIRouter(prefix="/catalog", tags=["catalog"])

_PAYLOAD_MISS = (OSError, KeyError, ValueError, RefNotFoundError, AmbiguousRefError)


def _scope_info(scope: AssetScope) -> CatalogScopeInfo:
    ids = scope.ids
    return CatalogScopeInfo(
        kind=scope.kind,
        projectId=ids[0] if len(ids) >= 1 else None,
        experimentId=ids[1] if len(ids) >= 2 else None,
        runId=ids[2] if len(ids) >= 3 else None,
    )


def _named_asset_at(workspace, target: Path) -> Asset | None:  # noqa: ANN001
    """The named asset whose payload resolves to *target*, if any."""
    for repository in scan_asset_repositories(workspace):
        for asset in repository.list():
            try:
                payload = Path(repository.payload_path(asset.id)).resolve()
            except _PAYLOAD_MISS:
                continue
            if payload == target:
                return asset
    return None


@router.get("/by-path", response_model=CatalogByPathResponse)
def catalog_by_path(
    path: str = Query(..., description="Workspace-relative or absolute path"),
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> CatalogByPathResponse:
    """Reverse lookup: find the producer for a given workspace path.

    Accepts either an absolute path (must be inside the workspace) or a
    workspace-relative path. Rejects absolute paths outside the workspace
    root with HTTP 400.
    """
    root = Path(workspace.root).resolve()
    raw = Path(path).expanduser()
    if raw.is_absolute():
        target = raw.resolve()
    else:
        target = (root / path.lstrip("/")).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Path is outside workspace root") from exc

    workspace_rel = str(target.relative_to(root))

    named = _named_asset_at(workspace, target)
    if named is not None:
        origin = named.origin
        producer = None
        siblings: list[CatalogSibling] = []
        if isinstance(origin, ExecutionOrigin):
            producer = CatalogProducerInfo(
                runId=origin.run_id,
                taskId=origin.task,
                executionId=origin.execution_id,
            )
            siblings = _task_siblings(workspace, root, named)
        return CatalogByPathResponse(
            matched=True,
            workspaceRelPath=workspace_rel,
            assetId=named.id,
            assetKind=named.media_type or "asset",
            producer=producer,
            scope=_scope_info(named.scope),
            siblings=siblings,
        )

    return CatalogByPathResponse(
        matched=False,
        workspaceRelPath=workspace_rel,
        scope=_scope_for_path(workspace, target),
    )


def _path_under_root(root: Path, location: str) -> str:
    resolved = Path(location).resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError:
        return resolved.as_posix()


def _task_siblings(workspace, root: Path, asset: Asset) -> list[CatalogSibling]:  # noqa: ANN001
    """Other assets the same task of the same attempt registered."""
    origin = asset.origin
    if not isinstance(origin, ExecutionOrigin) or origin.task is None:
        return []
    siblings: list[CatalogSibling] = []
    for repository in scan_asset_repositories(workspace):
        for peer in repository.list():
            peer_origin = peer.origin
            if (
                peer.id == asset.id
                or not isinstance(peer_origin, ExecutionOrigin)
                or peer_origin.execution_id != origin.execution_id
                or peer_origin.run_id != origin.run_id
                or peer_origin.task != origin.task
            ):
                continue
            try:
                location = repository.payload_path(peer.id)
            except _PAYLOAD_MISS:
                continue
            siblings.append(
                CatalogSibling(
                    assetId=peer.id,
                    name=peer.title,
                    kind=peer.media_type or "asset",
                    relPath=_path_under_root(root, location),
                )
            )
    return siblings


def _within(directory: Path, target: Path) -> bool:
    """True when *target* is *directory* or a path under it. No symlink resolve."""
    try:
        target.relative_to(directory)
    except ValueError:
        return False
    return True


def _scope_for_path(workspace, target: Path) -> CatalogScopeInfo | None:  # noqa: ANN001
    """Entity ids of the directory that contains *target*.

    Descends ``list_projects`` / ``list_experiments`` / ``list_runs`` and
    enters only the branch whose directory contains *target*. Ids are the
    entity record ids, never directory names. Compares directories; it does
    not resolve paths and it does not walk artifacts.
    """
    for project in workspace.list_projects():
        if not _within(Path(str(project.resolve())), target):
            continue
        experiment_id: str | None = None
        run_id: str | None = None
        for experiment in project.list_experiments():
            if not _within(Path(str(experiment.resolve())), target):
                continue
            experiment_id = experiment.id
            for run in experiment.list_runs():
                if not _within(Path(str(run.resolve())), target):
                    continue
                run_id = run.id
                break
            break
        if run_id is not None:
            kind = "run"
        elif experiment_id is not None:
            kind = "experiment"
        else:
            kind = "project"
        return CatalogScopeInfo(
            kind=kind,
            projectId=project.id,
            experimentId=experiment_id,
            runId=run_id,
        )
    return None
