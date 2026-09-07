"""Private unified asset enumeration for the curation toolset.

Two disjoint asset systems: imported ``DataAsset`` inputs live in per-scope
``assets.json`` / ``assets/<id>/asset.json`` (read via ``assets.scan``), while
run-emitted products are the ``Artifact`` records inside each Execution.
Curation composes both without duplicating either scanner.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

from ..artifact_repository import scan_artifacts
from ..assets.base import AssetScope
from ..domain import Artifact

if TYPE_CHECKING:
    from ..workspace import Workspace

_SCOPE_KIND_RANK: dict[str, int] = {
    "workspace": 0,
    "project": 1,
    "experiment": 2,
    "run": 3,
}


def run_asset_scopes(workspace: Workspace) -> dict[str, AssetScope]:
    """Map every run id to its full run scope (project → experiment → run)."""
    scopes: dict[str, AssetScope] = {}
    for project in workspace.list_projects():
        for experiment in project.list_experiments():
            for run in experiment.list_runs():
                scopes[run.id] = AssetScope(kind="run", ids=(project.id, experiment.id, run.id))
    return scopes


def iter_emitted_artifacts(workspace: Workspace) -> Iterator[Artifact]:
    """Yield every ``Artifact`` emitted by any Execution in the workspace."""
    yield from scan_artifacts(workspace)


def artifact_kind(artifact: Artifact) -> str:
    """The curation ``kind`` label for an emitted artifact (default ``artifact``)."""
    return artifact.semantic_type or "artifact"


def scope_matches(asset_scope: AssetScope, scope: AssetScope, recursive: bool) -> bool:
    """Mirror ``assets.scan._scope_matches``: exact, or recursive id-prefix."""
    if not recursive:
        return asset_scope.kind == scope.kind and asset_scope.ids == scope.ids
    arank = _SCOPE_KIND_RANK.get(asset_scope.kind)
    srank = _SCOPE_KIND_RANK.get(scope.kind, 0)
    if arank is None or arank < srank:
        return False
    n = len(scope.ids)
    return asset_scope.ids[:n] == scope.ids


def count_emitted_artifacts(workspace: Workspace) -> int:
    """Total number of emitted artifacts across the workspace."""
    return sum(1 for _ in iter_emitted_artifacts(workspace))
