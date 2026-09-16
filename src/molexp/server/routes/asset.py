"""Asset routes — unified typed Asset API under ``/api/assets``.

The old routes only served ``DataAsset`` uploads.  The new surface is
backed by the workspace manifest scanner (``assets.scan``, reading the
authoritative per-scope ``assets.json``) and supports every kind
(``data``, ``artifact``, ``log``, ``checkpoint``, …).
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import PlainTextResponse, StreamingResponse

from molexp.services.workspace_read_model import WorkspaceReadModel
from molexp.workspace.assets import AssetScope, LogAsset, lineage, scan

from ..dependencies import get_workspace
from ..deps.read_model import get_read_model
from ..exceptions import AssetNotFoundError, InvalidPathError
from ..http_cache import not_modified, weak_etag
from ..mutations import after_mutation
from ..preview import asset_has_sidecar
from ..schemas import (
    AssetLineageNode,
    AssetLineageResponse,
    AssetResponse,
    DataAssetRegisterRequest,
)
from ._scope import resolve_scope_dir, split_workspace_relpath

router = APIRouter(prefix="/assets", tags=["assets"])


def _require_asset(workspace, asset_id: str, *, assets=None):  # noqa: ANN001, ANN202
    """Resolve *asset_id* or 404 — from *assets* when the caller already scanned."""
    asset = scan.get_asset(workspace.root, asset_id, assets=assets)
    if asset is None:
        raise AssetNotFoundError(asset_id)
    return asset


def _require_from_snapshot(read_model: WorkspaceReadModel, asset_id: str):  # noqa: ANN202
    """Resolve *asset_id* against the snapshot, rescanning once on a miss.

    A miss is the interesting case: an id the snapshot has not seen is either
    brand new (written since the last sweep) or genuinely absent. One forced
    refresh separates the two, so a just-registered asset is never reported
    missing and a bogus id still 404s.
    """
    asset = read_model.assets().by_id.get(asset_id)
    if asset is None:
        read_model.invalidate("assets")
        asset = read_model.assets().by_id.get(asset_id)
    if asset is None:
        raise AssetNotFoundError(asset_id)
    return asset


def _resolve_scope_dir(workspace, scope: AssetScope) -> Path:  # noqa: ANN001
    path = resolve_scope_dir(workspace, scope)
    if path is None:
        raise HTTPException(400, f"Could not resolve scope: {scope!r}")
    return path


# ── Query ────────────────────────────────────────────────────────────────


@router.get("", response_model=list[AssetResponse])
def list_assets(
    request: Request,
    response: Response,
    kind: str | None = None,
    scope_kind: str | None = None,
    run_id: str | None = None,
    task_id: str | None = None,
    content_hash: str | None = None,
    limit: int = 100,
    workspace=Depends(get_workspace),  # noqa: ANN001
    read_model: WorkspaceReadModel = Depends(get_read_model),
) -> list[AssetResponse]:
    """Query assets from the workspace catalog with optional filters.

    Answered from the read-model asset snapshot: the manifests are scanned
    once and every filter — including the ``content_hash`` lookup, which is a
    dict hit on the snapshot's hash index — is applied in memory.
    """
    snapshot = read_model.assets()
    cached = not_modified(
        request,
        response,
        weak_etag(
            "assets", snapshot.version, kind, scope_kind, run_id, task_id, content_hash, limit
        ),
    )
    if cached is not None:
        return cached  # type: ignore[return-value]

    if content_hash is not None:
        found = snapshot.by_hash.get(content_hash)
        return (
            [
                AssetResponse.from_model(
                    found, has_preview_sidecar=asset_has_sidecar(workspace, found)
                )
            ]
            if found is not None
            else []
        )

    assets = list(snapshot.assets)
    if scope_kind == "workspace":
        # Note: project/experiment/run scoping is better served by the
        # per-scope routes below (they carry the full ids tuple).
        assets = snapshot.in_scope(AssetScope(kind="workspace", ids=()))
    if kind is not None:
        assets = [a for a in assets if getattr(a, "kind", None) == kind]
    if run_id:
        assets = [a for a in assets if a.producer is not None and a.producer.run_id == run_id]
    if task_id:
        assets = [a for a in assets if a.producer is not None and a.producer.task_id == task_id]
    return [
        AssetResponse.from_model(a, has_preview_sidecar=asset_has_sidecar(workspace, a))
        for a in assets[:limit]
    ]


@router.get("/{asset_id}", response_model=AssetResponse)
def get_asset(
    asset_id: str,
    workspace=Depends(get_workspace),  # noqa: ANN001
    read_model: WorkspaceReadModel = Depends(get_read_model),
) -> AssetResponse:
    """One asset by id — a dict hit on the snapshot, not a workspace walk."""
    asset = _require_from_snapshot(read_model, asset_id)
    return AssetResponse.from_model(asset, has_preview_sidecar=asset_has_sidecar(workspace, asset))


@router.get("/{asset_id}/lineage", response_model=AssetLineageResponse)
def get_asset_lineage(
    asset_id: str,
    workspace=Depends(get_workspace),  # noqa: ANN001
    read_model: WorkspaceReadModel = Depends(get_read_model),
) -> AssetLineageResponse:
    """Return the asset's transitive ancestors and descendants.

    Walks the ``Producer.inputs`` DAG built by run-time tasks that
    declare ``consumed=[...]`` on artifact / data registration. The
    starting asset is excluded from both lists.

    Lineage edges may cross scopes, so the manifests are scanned **once**
    here and that list is threaded through the traversal and the node
    rendering — never one scan per lineage node.
    """
    snapshot = read_model.assets()
    assets = list(snapshot.assets)
    _require_from_snapshot(read_model, asset_id)
    by_id = snapshot.by_id

    def _node(aid: str) -> AssetLineageNode | None:
        a = by_id.get(aid)
        if a is None:
            return None
        return AssetLineageNode(id=a.asset_id, name=a.name, kind=a.kind, scope_kind=a.scope.kind)

    ancestor_ids = sorted(lineage.ancestors(workspace, asset_id, assets=assets))
    descendant_ids = sorted(lineage.descendants(workspace, asset_id, assets=assets))
    return AssetLineageResponse(
        asset_id=asset_id,
        ancestors=[n for n in (_node(i) for i in ancestor_ids) if n is not None],
        descendants=[n for n in (_node(i) for i in descendant_ids) if n is not None],
    )


# ── Download / tail / stream ──────────────────────────────────────────────


@router.get("/{asset_id}/content")
def asset_content(asset_id: str, workspace=Depends(get_workspace)):  # noqa: ANN001, ANN201
    """Download the asset's file content."""
    asset = _require_asset(workspace, asset_id)
    scope_dir = _resolve_scope_dir(workspace, asset.scope)
    path = asset.absolute_path(scope_dir)

    # DataAsset has a payload directory; serve the first file inside it
    if path.is_dir():
        files = list(path.iterdir())
        if not files:
            raise AssetNotFoundError(asset_id)
        path = files[0]

    if not path.exists():
        raise AssetNotFoundError(asset_id)

    return StreamingResponse(
        open(path, "rb"),  # noqa: PTH123
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{path.name}"'},
    )


@router.get("/{asset_id}/tail", response_class=PlainTextResponse)
def asset_tail(asset_id: str, n: int = 100, workspace=Depends(get_workspace)) -> str:  # noqa: ANN001
    """Return the last N lines (``LogAsset`` only)."""
    asset = _require_asset(workspace, asset_id)
    if not isinstance(asset, LogAsset):
        raise HTTPException(400, f"tail only supported for log assets (got {asset.kind})")
    scope_dir = _resolve_scope_dir(workspace, asset.scope)
    return "\n".join(asset.tail(scope_dir, n))


# ── DataAsset import ──────────────────────────────────────────────────────


@router.post("/data/import", response_model=AssetResponse, status_code=201)
async def import_data_asset(
    file: UploadFile = File(...),
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> AssetResponse:
    """Upload a file and register it as a workspace-scoped ``DataAsset``."""
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)

    try:
        filename = file.filename or "untitled"
        asset = workspace.data_assets.import_asset(
            name=filename,
            src=tmp_path,
            action="move",
            meta={"original_filename": filename},
        )
        after_mutation(workspace, "asset", ref=asset.asset_id)
        return AssetResponse.from_model(asset)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


@router.post("/data/register", response_model=AssetResponse, status_code=201)
def register_data_asset(
    body: DataAssetRegisterRequest,
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> AssetResponse:
    """Register an existing workspace file in place as a ``DataAsset``.

    The file stays where it is — only an index entry is created — so a
    same-stem preview sidecar remains a real sibling of the resolved path.
    """
    try:
        target = split_workspace_relpath(workspace, body.path)
    except ValueError as exc:
        raise InvalidPathError(body.path, "path is outside the workspace") from exc
    if not target.exists():
        raise InvalidPathError(body.path, "file does not exist")

    asset = workspace.data_assets.register_in_place(
        name=body.name or target.name,
        src=target,
        meta=body.metadata,
    )
    after_mutation(workspace, "asset", ref=asset.asset_id)
    return AssetResponse.from_model(asset, has_preview_sidecar=asset_has_sidecar(workspace, asset))
