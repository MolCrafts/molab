"""Tests for ``FileLineageStore`` (parent_ids walk, no ``edges.json``).

Locks persist-one-03-harness-files: A→B→C ``trace_backward(C)`` ids equal
``[B, A]`` (captured from ``FileArtifactStore.put_*`` return values);
``add_edge`` never writes ``edges.json``; a relation other than
``derived_from`` raises ``ValueError``.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from molexp.harness.store.file_artifact_store import FileArtifactStore

if TYPE_CHECKING:
    from molexp.harness.schemas import PlanArtifactRef
    from molexp.harness.store.file_lineage_store import FileLineageStore


@pytest.fixture()
def artifacts(tmp_path: Path) -> FileArtifactStore:
    return FileArtifactStore(root=tmp_path / "artifacts")


@pytest.fixture()
def lineage(artifacts: FileArtifactStore) -> FileLineageStore:
    from molexp.harness.store.file_lineage_store import FileLineageStore

    return FileLineageStore(artifact_store=artifacts)


@pytest.fixture()
def chain_abc(
    artifacts: FileArtifactStore, lineage: FileLineageStore
) -> tuple[PlanArtifactRef, PlanArtifactRef, PlanArtifactRef]:
    """A → B → C chain (``derived_from`` via parent_ids + ``add_edge``)."""
    a = artifacts.put_json(kind="user_plan", obj={"a": 1}, created_by="user", parent_ids=[])
    b = artifacts.put_json(
        kind="experiment_report", obj={"b": 1}, created_by="harness", parent_ids=[a.id]
    )
    c = artifacts.put_json(
        kind="workflow_ir", obj={"c": 1}, created_by="harness", parent_ids=[b.id]
    )
    lineage.add_edge(a.id, b.id)
    lineage.add_edge(b.id, c.id)
    return a, b, c


class TestFileLineageStore:
    def test_trace_backward_ids_are_parent_then_root(
        self,
        chain_abc: tuple[PlanArtifactRef, PlanArtifactRef, PlanArtifactRef],
        lineage: FileLineageStore,
    ) -> None:
        a, b, c = chain_abc
        assert [ref.id for ref in lineage.trace_backward(c.id)] == [b.id, a.id]

    def test_add_edge_does_not_create_edges_json(
        self,
        chain_abc: tuple[PlanArtifactRef, PlanArtifactRef, PlanArtifactRef],
        tmp_path: Path,
    ) -> None:
        assert chain_abc is not None
        assert list(tmp_path.rglob("edges.json")) == []

    def test_add_edge_rejects_relation_other_than_derived_from(
        self, artifacts: FileArtifactStore, lineage: FileLineageStore
    ) -> None:
        a = artifacts.put_json(kind="user_plan", obj={"a": 1}, created_by="user", parent_ids=[])
        b = artifacts.put_json(
            kind="experiment_report", obj={"b": 1}, created_by="harness", parent_ids=[]
        )
        with pytest.raises(ValueError):
            lineage.add_edge(a.id, b.id, relation="copied_from")

    def test_list_refs_returns_put_artifacts(self, artifacts: FileArtifactStore) -> None:
        a = artifacts.put_json(kind="user_plan", obj={"a": 1}, created_by="user", parent_ids=[])
        b = artifacts.put_json(
            kind="experiment_report", obj={"b": 1}, created_by="harness", parent_ids=[a.id]
        )
        c = artifacts.put_json(
            kind="workflow_ir", obj={"c": 1}, created_by="harness", parent_ids=[b.id]
        )
        refs = artifacts.list_refs()
        assert {ref.id for ref in refs} == {a.id, b.id, c.id}
