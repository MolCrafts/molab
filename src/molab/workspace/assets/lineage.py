"""Asset lineage traversal.

Named assets and emitted artifacts form one directed graph. A named asset's
upstream ids come from its versions: an import contributes
``ImportOrigin.input_ids`` and a promotion contributes
``ArtifactOrigin.artifact_id``. An artifact's upstream ids are
``Artifact.input_entity_ids``. This module walks that one edge table.

Example::

    from molab.workspace.assets import lineage

    upstream = lineage.ancestors(workspace, leaf_asset.id)
    downstream = lineage.descendants(workspace, raw_input.id)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..workspace import Workspace


def _artifact_upstreams(workspace: Workspace) -> dict[str, tuple[str, ...]]:
    """Map artifact id to consumed entity ids, read from the owning Executions."""
    from ..artifact_repository import scan_artifacts

    return {artifact.id: tuple(artifact.input_entity_ids) for artifact in scan_artifacts(workspace)}


def _asset_upstreams(workspace: Workspace) -> dict[str, tuple[str, ...]]:
    """Map asset id to upstream ids taken from each version's origin.

    ``ImportOrigin`` contributes ``input_ids``. ``ArtifactOrigin`` contributes
    ``artifact_id``. Ids are kept in first-seen order. No reference is resolved.
    """
    from ..artifact_repository import scan_asset_repositories
    from ..domain import ArtifactOrigin, ImportOrigin

    edges: dict[str, tuple[str, ...]] = {}
    for repository in scan_asset_repositories(workspace):
        for asset in repository.list():
            seen: list[str] = []
            seen_set: set[str] = set()
            for version in repository.versions(asset.id):
                origin = version.origin
                if isinstance(origin, ImportOrigin):
                    incoming = origin.input_ids
                elif isinstance(origin, ArtifactOrigin):
                    incoming = (origin.artifact_id,)
                else:
                    continue
                for item in incoming:
                    if item in seen_set:
                        continue
                    seen_set.add(item)
                    seen.append(item)
            if seen:
                edges[asset.id] = tuple(seen)
    return edges


def _edges(workspace: Workspace) -> dict[str, tuple[str, ...]]:
    """Upstream ids for artifacts and named assets. The first id wins."""
    merged: dict[str, list[str]] = {}

    def add(entity_id: str, upstreams: tuple[str, ...]) -> None:
        bucket = merged.setdefault(entity_id, [])
        have = set(bucket)
        for item in upstreams:
            if item in have:
                continue
            have.add(item)
            bucket.append(item)

    for entity_id, upstreams in _artifact_upstreams(workspace).items():
        add(entity_id, upstreams)
    for entity_id, upstreams in _asset_upstreams(workspace).items():
        add(entity_id, upstreams)
    return {entity_id: tuple(upstreams) for entity_id, upstreams in merged.items()}


def ancestors(workspace: Workspace, asset_id: str) -> set[str]:
    """Return every id reachable upstream of *asset_id*.

    Walks the shared edge table. The starting id is not included. A self-loop
    stops because the id is already in the visited set.

    Args:
        workspace: Workspace whose records host the graph.
        asset_id: Leaf to walk back from.

    Returns:
        Upstream ids. Empty when the leaf has no upstream edges.
    """
    edges = _edges(workspace)
    visited: set[str] = {asset_id}
    found: set[str] = set()
    frontier: list[str] = [asset_id]
    while frontier:
        current = frontier.pop()
        for upstream in edges.get(current, ()):
            if upstream in visited:
                continue
            visited.add(upstream)
            found.add(upstream)
            frontier.append(upstream)
    return found


def descendants(workspace: Workspace, asset_id: str) -> set[str]:
    """Return every id reachable downstream of *asset_id*.

    Inverts the shared edge table, then walks forward. The starting id is
    excluded. A self-loop stops because the id is already in the visited set.

    Args:
        workspace: Workspace whose records host the graph.
        asset_id: Source to walk forward from.

    Returns:
        Downstream ids. Empty when nothing records *asset_id* as an upstream.
    """
    children: dict[str, list[str]] = {}
    for entity_id, upstreams in _edges(workspace).items():
        for upstream in upstreams:
            children.setdefault(upstream, []).append(entity_id)

    visited: set[str] = {asset_id}
    found: set[str] = set()
    frontier: list[str] = [asset_id]
    while frontier:
        current = frontier.pop()
        for child in children.get(current, ()):
            if child in visited:
                continue
            visited.add(child)
            found.add(child)
            frontier.append(child)
    return found
