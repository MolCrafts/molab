"""Asset lineage.

An asset produced by a run points at the asset ids that run named as
``inputs``. A run that names an asset as an input points forward to the
assets that run produced. An import has no upstream asset.

Example::

    from molab.workspace.assets import lineage

    upstream = lineage.ancestors(workspace, leaf.id)
    downstream = lineage.descendants(workspace, raw.id)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..workspace import Workspace


def _edges(workspace: Workspace) -> dict[str, tuple[str, ...]]:
    """Map a produced asset id to the input asset ids of its run."""
    from ..asset_repository import scan_asset_repositories
    from ..domain import ExecutionOrigin

    inputs_by_run: dict[str, tuple[str, ...]] = {}
    for project in workspace.list_projects():
        for experiment in project.list_experiments():
            for run in experiment.list_runs():
                inputs_by_run[run.id] = tuple(run.inputs)

    edges: dict[str, tuple[str, ...]] = {}
    for repository in scan_asset_repositories(workspace):
        for asset in repository.list():
            origin = asset.origin
            if not isinstance(origin, ExecutionOrigin):
                continue
            upstream = inputs_by_run.get(origin.run_id, ())
            if upstream:
                edges[asset.id] = upstream
    return edges


def ancestors(workspace: Workspace, asset_id: str) -> set[str]:
    """Return every asset id reachable upstream of *asset_id*.

    The starting id is not included.

    Args:
        workspace: Workspace whose records host the graph.
        asset_id: Leaf to walk back from.

    Returns:
        Upstream asset ids. Empty when the leaf has no upstream edges.
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
    """Return every asset id reachable downstream of *asset_id*.

    The starting id is excluded.

    Args:
        workspace: Workspace whose records host the graph.
        asset_id: Source to walk forward from.

    Returns:
        Downstream asset ids. Empty when no run names *asset_id* as an input.
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
