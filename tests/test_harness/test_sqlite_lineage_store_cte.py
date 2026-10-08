"""Traversal-contract tests for :class:`SQLiteArtifactLineageStore`.

The lineage store walks ``artifact_edges`` with a single ``WITH RECURSIVE``
CTE. These tests own the traversal semantics — BFS level order, shallowest-depth
dedup, cycle termination, the ``lineage_graph`` node/edge shape.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from molexp.harness.store.file_artifact_store import FileArtifactStore
from molexp.harness.store.sqlite_lineage_store import SQLiteArtifactLineageStore


@pytest.fixture()
def artifact_store(tmp_path: Path) -> FileArtifactStore:
    return FileArtifactStore(root=tmp_path / "artifacts")


@pytest.fixture()
def store(tmp_path: Path, artifact_store: FileArtifactStore) -> SQLiteArtifactLineageStore:
    return SQLiteArtifactLineageStore(
        path=tmp_path / "events.sqlite", artifact_store=artifact_store
    )


def _make_node(artifact_store: FileArtifactStore, label: str) -> str:
    """Create a distinct real artifact for ``label`` and return its id.

    Traversals hydrate every visited id through ``get_ref``, so each graph node
    must back onto a real ``PlanArtifactRef``; the label keeps content-addressed
    ids distinct.
    """
    ref = artifact_store.put_json(
        kind="workflow_ir",
        obj={"label": label},
        created_by="test",
        parent_ids=[],
    )
    return ref.id


class TestSQLiteArtifactLineageStore:
    def test_trace_backward_returns_ancestors_in_level_order(
        self, store: SQLiteArtifactLineageStore, artifact_store: FileArtifactStore
    ) -> None:
        a = _make_node(artifact_store, "A")
        b = _make_node(artifact_store, "B")
        c = _make_node(artifact_store, "C")
        d = _make_node(artifact_store, "D")
        store.add_edge(parent_id=a, child_id=b)
        store.add_edge(parent_id=b, child_id=c)
        store.add_edge(parent_id=c, child_id=d)

        assert [r.id for r in store.trace_backward(d)] == [c, b, a]

    def test_trace_forward_returns_descendants_in_level_order(
        self, store: SQLiteArtifactLineageStore, artifact_store: FileArtifactStore
    ) -> None:
        a = _make_node(artifact_store, "A")
        b = _make_node(artifact_store, "B")
        c = _make_node(artifact_store, "C")
        d = _make_node(artifact_store, "D")
        store.add_edge(parent_id=a, child_id=b)
        store.add_edge(parent_id=b, child_id=c)
        store.add_edge(parent_id=c, child_id=d)

        assert [r.id for r in store.trace_forward(a)] == [b, c, d]

    def test_trace_backward_dedups_shared_ancestor_at_shallowest_depth(
        self, store: SQLiteArtifactLineageStore, artifact_store: FileArtifactStore
    ) -> None:
        a = _make_node(artifact_store, "A")
        b = _make_node(artifact_store, "B")
        c = _make_node(artifact_store, "C")
        d = _make_node(artifact_store, "D")
        # Diamond: A->B, A->C, B->D, C->D. From D upward: depth1 = {B, C}, depth2 = {A}.
        store.add_edge(parent_id=a, child_id=b)
        store.add_edge(parent_id=a, child_id=c)
        store.add_edge(parent_id=b, child_id=d)
        store.add_edge(parent_id=c, child_id=d)

        result_ids = [r.id for r in store.trace_backward(d)]

        # Shared ancestor A appears exactly once; depth-1 frontier precedes it.
        assert len(result_ids) == 3
        assert result_ids.count(a) == 1
        assert set(result_ids[:2]) == {b, c}
        assert result_ids[2] == a

    def test_traversal_terminates_on_cycle_without_duplicates(
        self, store: SQLiteArtifactLineageStore, artifact_store: FileArtifactStore
    ) -> None:
        a = _make_node(artifact_store, "A")
        b = _make_node(artifact_store, "B")
        # Malformed cycle: A->B and B->A.
        store.add_edge(parent_id=a, child_id=b)
        store.add_edge(parent_id=b, child_id=a)

        backward = [r.id for r in store.trace_backward(a)]
        forward = [r.id for r in store.trace_forward(a)]

        # Reachable set from A (exclusive of A itself) is just {B}, once.
        assert backward == [b]
        assert forward == [b]

    def test_lineage_graph_returns_subgraph_nodes_and_stampless_edges(
        self, store: SQLiteArtifactLineageStore, artifact_store: FileArtifactStore
    ) -> None:
        a = _make_node(artifact_store, "A")
        b = _make_node(artifact_store, "B")
        c = _make_node(artifact_store, "C")
        d = _make_node(artifact_store, "D")
        store.add_edge(parent_id=a, child_id=b)
        store.add_edge(parent_id=a, child_id=c)
        store.add_edge(parent_id=b, child_id=d)
        store.add_edge(parent_id=c, child_id=d)

        graph = store.lineage_graph(d)

        # Nodes: sorted by id, each {id, kind, uri}.
        expected_nodes = [
            {
                "id": aid,
                "kind": artifact_store.get_ref(aid).kind,
                "uri": artifact_store.get_ref(aid).uri,
            }
            for aid in sorted([a, b, c, d])
        ]
        assert graph["nodes"] == expected_nodes
        # Edges written without pipeline context carry stage/run_id as None.
        assert {(e["parent_id"], e["child_id"], e["relation"]) for e in graph["edges"]} == {
            (a, b, "derived_from"),
            (a, c, "derived_from"),
            (b, d, "derived_from"),
            (c, d, "derived_from"),
        }
        assert all(
            set(e.keys()) == {"parent_id", "child_id", "relation", "stage", "run_id"}
            and e["stage"] is None
            and e["run_id"] is None
            for e in graph["edges"]
        )
