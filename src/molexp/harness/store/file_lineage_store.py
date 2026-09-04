"""File implementation of :class:`ArtifactLineageStore`.

Edges are immutable ``PlanArtifactRef.parent_ids`` on the child — there is no
``edges.json``. :meth:`add_edge` validates the edge declared at emit time.
Traversals are BFS over
``get_ref().parent_ids`` (backward) and :meth:`ArtifactStore.list_refs`
(forward reverse-index).
"""

from __future__ import annotations

from collections import deque

from molexp.harness.errors import ArtifactNotFoundError
from molexp.harness.schemas import PlanArtifactRef
from molexp.harness.store.artifact_store import ArtifactStore

__all__ = ["FileLineageStore"]


class FileLineageStore:
    """Lineage store that walks ``ArtifactStore`` parent_ids."""

    def __init__(self, artifact_store: ArtifactStore) -> None:
        self._artifacts = artifact_store

    def add_edge(
        self,
        parent_id: str,
        child_id: str,
        relation: str = "derived_from",
    ) -> None:
        if relation != "derived_from":
            raise ValueError(f"FileLineageStore only records derived_from edges, got {relation!r}")
        child = self._artifacts.get_ref(child_id)
        if parent_id not in child.parent_ids:
            raise ValueError(
                "Artifact lineage is append-only; parent_id must be supplied when emitting child"
            )

    def trace_backward(self, artifact_id: str) -> list[PlanArtifactRef]:
        return self._bfs(artifact_id, forward=False)

    def trace_forward(self, artifact_id: str) -> list[PlanArtifactRef]:
        return self._bfs(artifact_id, forward=True)

    def lineage_graph(self, artifact_id: str) -> dict[str, object]:
        ids = {
            artifact_id,
            *[ref.id for ref in self.trace_backward(artifact_id)],
            *[ref.id for ref in self.trace_forward(artifact_id)],
        }
        nodes: list[dict[str, str]] = []
        for aid in sorted(ids):
            try:
                ref = self._artifacts.get_ref(aid)
                nodes.append({"id": aid, "kind": ref.kind, "uri": ref.uri})
            except ArtifactNotFoundError:
                nodes.append({"id": aid})
        edges: list[dict[str, str]] = []
        for ref in self._artifacts.list_refs():
            if ref.id not in ids:
                continue
            for parent_id in ref.parent_ids:
                if parent_id in ids:
                    edges.append(
                        {
                            "parent_id": parent_id,
                            "child_id": ref.id,
                            "relation": "derived_from",
                        }
                    )
        return {"nodes": nodes, "edges": edges}

    def _bfs(self, start: str, *, forward: bool) -> list[PlanArtifactRef]:
        children: dict[str, list[str]] | None = None
        if forward:
            children = {}
            for ref in self._artifacts.list_refs():
                for parent_id in ref.parent_ids:
                    children.setdefault(parent_id, []).append(ref.id)

        order: list[PlanArtifactRef] = []
        seen: set[str] = {start}
        queue: deque[str] = deque([start])
        while queue:
            current = queue.popleft()
            neighbours = (
                children.get(current, [])
                if children is not None
                else self._artifacts.get_ref(current).parent_ids
            )
            for neighbour in neighbours:
                if neighbour in seen:
                    continue
                seen.add(neighbour)
                order.append(self._artifacts.get_ref(neighbour))
                queue.append(neighbour)
        return order
