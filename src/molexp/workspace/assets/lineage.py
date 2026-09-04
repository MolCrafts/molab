"""Asset lineage traversal.

Each :class:`~molexp.workspace.assets.base.Asset` carries an optional
:class:`~molexp.workspace.assets.base.Producer` whose
:attr:`Producer.inputs` lists the upstream ``asset_id``s consumed to
build it. Together they form a directed acyclic graph spanning the
entire workspace; this module exposes two BFS walkers over it.

Example::
10→
    from molexp.workspace.assets import lineage

    upstream = lineage.ancestors(workspace, leaf_asset.asset_id)
    downstream = lineage.descendants(workspace, raw_input.asset_id)

Since schema v2, run-produced outputs are emitted as provenance-backed
:class:`~molexp.workspace.domain.Artifact` records (see
:mod:`molexp.workspace.artifact_repository`) whose upstream edges are the
``input_entity_ids`` field rather than ``Producer.inputs``.  The walkers
below resolve both surfaces, so a v2 ``Artifact`` may consume a legacy
``DataAsset`` (and vice versa) and the DAG stays connected.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from . import scan

if TYPE_CHECKING:
    from ..fs import FileSystem
    from ..workspace import Workspace


def _workspace_fs(workspace: Workspace) -> FileSystem | None:
    """Return the workspace FileSystem when it is not the local default.

    Local workspaces keep the historical Path-based scan; remote workspaces
    pass their RemoteFileSystem so asset walks go over the transport.
    """
    from ..fs_local import LocalFileSystem

    fs = getattr(workspace, "fs", None)
    if fs is None or isinstance(fs, LocalFileSystem):
        return None
    return fs


def _fs_arg(workspace: Workspace) -> FileSystem | None:
    """Return the workspace's FileSystem (``None`` leaves local default)."""
    return getattr(workspace, "fs", None)


def _artifact_upstreams(workspace: Workspace) -> dict[str, tuple[str, ...]]:
    """Map v2 ``Artifact`` id → consumed entity ids from the provenance index.

    The provenance index is a derived view; when empty it is rebuilt from the
    append-only event log so a fresh workspace scan still resolves edges.
    """
    from ..index_store import JsonIndexStore
    from ..provenance import ProvenanceStore

    fs = _fs_arg(workspace)
    index = JsonIndexStore(workspace.root, fs=fs)
    records = index.list_entities("artifact")
    if not records:
        provenance = ProvenanceStore(workspace.root, fs=fs)
        if provenance.iter_events():
            index.rebuild(provenance)
            records = index.list_entities("artifact")
    out: dict[str, tuple[str, ...]] = {}
    for raw in records:
        artifact_id = raw.get("id")
        inputs = raw.get("input_entity_ids") or ()
        if isinstance(artifact_id, str):
            out[artifact_id] = (
                tuple(str(item) for item in inputs) if isinstance(inputs, (list, tuple)) else ()
            )
    return out


def _upstream_ids(
    workspace: Workspace, entity_id: str, v2_artifacts: dict[str, tuple[str, ...]]
) -> tuple[str, ...]:
    """Return the entity ids consumed by *entity_id*, if any."""
    if entity_id in v2_artifacts:
        return v2_artifacts[entity_id]
    asset = scan.get_asset(workspace.root, entity_id, fs=_workspace_fs(workspace))
    if asset is not None and asset.producer is not None:
        return asset.producer.inputs
    return ()


def ancestors(workspace: Workspace, asset_id: str) -> set[str]:
    """Return every ``asset_id`` reachable upstream of *asset_id*.

    Walks the upstream edges (``input_entity_ids`` for v2 ``Artifact``s,
    :attr:`Producer.inputs` for legacy ``Asset``s) in breadth-first order.
    The starting ``asset_id`` itself is **not** included; defensive
    self-loops (an edge pointing back at the asset's own id) are silently
    skipped.

    Args:
        workspace: Workspace whose catalog hosts the asset graph.
        asset_id: Leaf to walk back from.

    Returns:
        Set of upstream ``asset_id``s. Empty when the leaf has no
        producer or no inputs.
    """
    v2_artifacts = _artifact_upstreams(workspace)
    visited: set[str] = set()
    frontier: list[str] = [asset_id]
    while frontier:
        cur = frontier.pop()
        for upstream in _upstream_ids(workspace, cur, v2_artifacts):
            if upstream == asset_id or upstream in visited:
                continue
            visited.add(upstream)
            frontier.append(upstream)
    return visited


def descendants(workspace: Workspace, asset_id: str) -> set[str]:
    """Return every ``asset_id`` reachable downstream of *asset_id*.

    Inverts the upstream edge index across the workspace catalog
    (legacy ``Producer.inputs`` plus v2 ``Artifact.input_entity_ids``),
    then walks forward breadth-first. The starting ``asset_id`` is
    excluded from the result; self-loops terminate.

    Args:
        workspace: Workspace whose catalog hosts the asset graph.
        asset_id: Source to walk forward from.

    Returns:
        Set of downstream ``asset_id``s. Empty when no asset records
        *asset_id* in its inputs.
    """
    fs = _workspace_fs(workspace)
    children_of: dict[str, list[str]] = {}
    for asset in scan.scan_assets(workspace.root, fs=fs):
        if asset.producer is None:
            continue
        for inp in asset.producer.inputs:
            children_of.setdefault(inp, []).append(asset.asset_id)
    for artifact_id, inputs in _artifact_upstreams(workspace).items():
        for inp in inputs:
            children_of.setdefault(inp, []).append(artifact_id)

    visited: set[str] = set()
    frontier: list[str] = [asset_id]
    while frontier:
        cur = frontier.pop()
        for child in children_of.get(cur, ()):
            if child == asset_id or child in visited:
                continue
            visited.add(child)
            frontier.append(child)
    return visited
