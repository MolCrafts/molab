"""Catalog routes — reverse lookup from a path to the Execution that emitted it.

``catalog_by_path`` walks Execution artifact records (``walk_artifacts``).
Given a path, the UI learns which run produced it, which experiment groups
it, which project owns it, and what other outputs share its task.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from molab.workspace.artifact_repository import (
    ArtifactLocation,
    scan_asset_repositories,
    walk_artifacts,
)
from molab.workspace.domain import Asset, AssetScope
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

    locations = list(walk_artifacts(workspace))
    artifact_hit: CatalogByPathResponse | None = None
    for loc in locations:
        if loc.location is None:
            continue
        try:
            if Path(loc.location).resolve() != target:
                continue
        except OSError:
            continue
        artifact_hit = _artifact_catalog_hit(root, loc, locations, workspace_rel)
        break

    named = _named_asset_at(workspace, target)
    if artifact_hit is not None:
        if named is None:
            return artifact_hit
        return artifact_hit.model_copy(update={"assetId": named.id, "assetKind": named.kind})
    if named is not None:
        return CatalogByPathResponse(
            matched=True,
            workspaceRelPath=workspace_rel,
            assetId=named.id,
            assetKind=named.kind,
            producer=None,
            scope=_scope_info(named.scope),
            siblings=[],
        )

    return CatalogByPathResponse(
        matched=False,
        workspaceRelPath=workspace_rel,
        scope=_scope_for_path(workspace, target),
    )


def _task_id(metadata: object) -> str | None:
    if not isinstance(metadata, dict):
        return None
    raw = metadata.get("task_id")
    return raw if isinstance(raw, str) and raw else None


def _path_under_root(root: Path, location: str) -> str:
    resolved = Path(location).resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError:
        return resolved.as_posix()


def _artifact_catalog_hit(
    root: Path,
    loc: ArtifactLocation,
    locations: list[ArtifactLocation],
    workspace_rel: str,
) -> CatalogByPathResponse:
    """Catalog row for one emitted Artifact matched by absolute path."""
    artifact = loc.artifact
    task_id = _task_id(artifact.metadata)
    siblings: list[CatalogSibling] = []
    if task_id is not None:
        for peer in locations:
            peer_location = peer.location
            if (
                peer.project_id != loc.project_id
                or peer.experiment_id != loc.experiment_id
                or peer.run_id != loc.run_id
                or peer.execution_id != loc.execution_id
                or peer.artifact.id == artifact.id
                or peer_location is None
                or _task_id(peer.artifact.metadata) != task_id
            ):
                continue
            siblings.append(
                CatalogSibling(
                    assetId=peer.artifact.id,
                    name=peer.artifact.name,
                    kind=peer.artifact.semantic_type or "artifact",
                    relPath=_path_under_root(root, peer_location),
                )
            )
    return CatalogByPathResponse(
        matched=True,
        workspaceRelPath=workspace_rel,
        assetId=artifact.id,
        assetKind=artifact.semantic_type or "artifact",
        producer=CatalogProducerInfo(
            runId=loc.run_id,
            taskId=task_id,
            executionId=loc.execution_id,
        ),
        scope=CatalogScopeInfo(
            kind="run",
            projectId=loc.project_id,
            experimentId=loc.experiment_id,
            runId=loc.run_id,
        ),
        siblings=siblings,
    )


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
    entity JSON ids, never directory names. Compares directories; it does
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
