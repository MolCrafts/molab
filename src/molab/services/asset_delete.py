"""Delete one registered asset — the one path ``molab asset delete`` takes.

An asset is named by its id, its ``molab:asset/<id>`` ref, or its slot
directory (workspace-relative, e.g. ``projects/P/experiments/E/assets/<run>--<title>``).
A cited asset is refused: a knowledge document (or TeX manuscript) whose text
names the id, or a run that declares it as an input — which is also what makes
an asset an ancestor in :mod:`molab.workspace.assets.lineage`. An attempt's own
journal is evidence, not a citation, so it does not block the delete.

The slot directory is removed by :meth:`AssetRepository.remove`, the same call
``molab runs prune --superseded`` uses, and the removal is one ``AssetDeleted``
history commit. Assets appear in no derived ``index:`` block, so nothing else
is rebuilt.

It composes ``knowledge`` (the citation scan) with ``workspace``, so it lives
in the service layer above both.
"""

from __future__ import annotations

import json
import posixpath
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from molab.workspace import Workspace
    from molab.workspace.asset_repository import AssetRepository
    from molab.workspace.domain import Asset

__all__ = ["AssetCitedError", "DeletedAsset", "asset_citations", "delete_asset", "resolve_asset"]


class AssetCitedError(RuntimeError):
    """The asset is still cited; ``citations`` names each citing place."""

    def __init__(self, asset_id: str, citations: tuple[str, ...]) -> None:
        listed = "; ".join(citations)
        super().__init__(f"asset {asset_id} is still cited by {listed}")
        self.asset_id = asset_id
        self.citations = citations


@dataclass(frozen=True)
class DeletedAsset:
    """What :func:`delete_asset` removed."""

    asset: Asset
    path: str
    """The removed slot directory."""


def _relative(ws: Workspace, path: str) -> str:
    return posixpath.relpath(posixpath.normpath(str(path)), posixpath.normpath(str(ws.root)))


def _asset_in_slot(ws: Workspace, spec: str) -> tuple[Asset, AssetRepository]:
    """The asset whose slot directory is *spec* (workspace-relative or absolute)."""
    from molab.workspace.asset_repository import scan_asset_repositories
    from molab.workspace.errors import RefNotFoundError

    root = posixpath.normpath(str(ws.root))
    target = posixpath.normpath(spec if posixpath.isabs(spec) else posixpath.join(root, spec))
    for repository in scan_asset_repositories(ws):
        if posixpath.dirname(target) != posixpath.normpath(repository.assets_dir):
            continue
        record = ws.fs.join(target, "asset.json")
        if not ws.fs.exists(record):
            break
        asset_id = json.loads(ws.fs.read_text(record)).get("id")
        if isinstance(asset_id, str):
            return repository.get(asset_id), repository
        break
    raise RefNotFoundError(None, "asset", spec)


def resolve_asset(ws: Workspace, spec: str) -> tuple[Asset, AssetRepository]:
    """The asset *spec* names, with the repository that holds it.

    Raises:
        RefNotFoundError: No asset matches.
        AmbiguousRefError: The id exists in more than one scope.
        InvalidRefError: *spec* is a ``molab:`` reference that is not an asset ref.
    """
    from molab.workspace.domain import Asset
    from molab.workspace.refs import MolabRef, is_ref, parse_ref

    if is_ref(spec):
        ref = parse_ref(spec, kind="asset")
    elif "/" in spec:
        return _asset_in_slot(ws, spec)
    else:
        ref = MolabRef(asset_id=spec)
    asset = ws.find(ref)
    if not isinstance(asset, Asset):  # an asset ref always resolves to an Asset
        raise TypeError(f"{ref} resolved to {type(asset).__name__}, not an asset")
    return asset, ws.assets_at(asset.scope)


def asset_citations(ws: Workspace, asset_id: str) -> tuple[str, ...]:
    """Every place in *ws* that cites *asset_id*, as workspace-relative labels."""
    from molab.knowledge import Knowledge
    from molab.knowledge.tex_docs import iter_tex_documents

    documents = [str(item.path) for item in Knowledge(ws.root, fs=ws.fs).walk()]
    documents.extend(iter_tex_documents(ws.root, ws.fs))
    found = [
        f"document {_relative(ws, path)}" for path in documents if asset_id in ws.fs.read_text(path)
    ]
    for project in ws.list_projects():
        for experiment in project.list_experiments():
            for run in experiment.list_runs():
                if asset_id in run.inputs:
                    found.append(f"run {_relative(ws, str(run.path))} (input)")
    return tuple(found)


def delete_asset(ws: Workspace, spec: str) -> DeletedAsset:
    """Delete the asset *spec* names, unless something cites it.

    Raises:
        RefNotFoundError: No asset matches *spec*.
        AmbiguousRefError: The id exists in more than one scope.
        InvalidRefError: *spec* is a ``molab:`` reference that is not an asset ref.
        AssetCitedError: A knowledge document or a run input still cites it.
    """
    from molab.workspace.errors import RefNotFoundError
    from molab.workspace.history import EntityRef, GitHistory

    asset, repository = resolve_asset(ws, spec)
    citations = asset_citations(ws, asset.id)
    if citations:
        raise AssetCitedError(asset.id, citations)
    removed = repository.remove(asset.id)
    if removed is None:
        raise RefNotFoundError(None, "asset", asset.id)
    GitHistory(str(ws.root)).record(
        "AssetDeleted",
        subject=EntityRef(id=asset.id, type="asset"),
        summary=f"{asset.title} {_relative(ws, removed)}",
        paths=(removed,),
    )
    return DeletedAsset(asset=asset, path=removed)
