"""Provenance/index-backed artifact query layer (``artifact_repository`` + ``index_store``).

The derived SQLite ``AssetCatalog`` was replaced by the append-only provenance
event log and its disposable JSON index (spec: workspace-git-projection-01-drop-catalog).
Every query shape is answered by the ``JsonIndexStore`` sharded entities
(``index/entities/artifact/*.json``), which ``ArtifactRepository`` reads — and
rebuilds from provenance when empty. Emitted artifacts are created by
:meth:`molexp.workspace.execution_context.ExecutionContext.emit_artifact`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from molexp.workspace import Workspace
from molexp.workspace.artifact_repository import ArtifactRepository
from molexp.workspace.domain import Artifact
from molexp.workspace.index_store import JsonIndexStore

# Each started run persists two artifacts: the user's "artifact" + a checkpoint.
ARTIFACTS_PER_RUN = 2


def _seed_workspace(root: Path, n_runs: int = 3) -> Workspace:
    ws = Workspace(root=root, name="Test")
    proj = ws.add_project("demo")
    exp = proj.add_experiment("baseline", params={"lr": 1e-3})
    for i in range(n_runs):
        r = exp.add_run(params={"seed": i})
        with r.start() as ctx:
            ctx.emit_artifact({"loss": 0.1 * i}, name="metrics.json", semantic_type="artifact")
            ctx.checkpoint("epoch1", data={"step": 1})
    return ws


def _all_artifacts(ws: Workspace) -> list[Artifact]:
    index = JsonIndexStore(ws.root, fs=ws.fs)
    return [Artifact.model_validate(raw) for raw in index.list_entities("artifact")]


def _repo(ws: Workspace) -> ArtifactRepository:
    return ArtifactRepository(ws.root, fs=ws.fs)


class TestQueryArtifacts:
    def test_run_scope_matches_only_that_run(self, tmp_path):
        ws = _seed_workspace(tmp_path / "lab")
        run = ws.project("demo").experiment("baseline").list_runs()[0]
        execution_id = run.executions[0].id
        scoped = _repo(ws).list_for_execution(execution_id)
        assert len(scoped) == ARTIFACTS_PER_RUN
        assert all(a.execution_id == execution_id and a.run_id == run.id for a in scoped)


class TestGetArtifact:
    def test_returns_artifact_by_id_else_keyerror(self, tmp_path):
        ws = _seed_workspace(tmp_path / "lab")
        some = _all_artifacts(ws)[0]
        assert _repo(ws).get(some.id).id == some.id
        with pytest.raises(KeyError):
            _repo(ws).get("nonexistent")


class TestNoDerivedSqliteIndex:
    """Invariant lock: the derived SQLite ``AssetCatalog`` is gone — the
    authoritative on-disk records are the append-only provenance events plus
    their disposable JSON index (One-source-of-truth law)."""

    def test_seeded_workspace_writes_json_index_not_sqlite(self, tmp_path):
        ws = _seed_workspace(tmp_path / "lab")  # 3 runs, artifacts persisted
        root = Path(str(ws.root))
        # Artifacts are queryable …
        assert len(_all_artifacts(ws)) == 3 * ARTIFACTS_PER_RUN
        # … yet nothing was written to a derived SQLite index.
        assert not (root / "catalog").exists()
        assert not list(root.rglob("*.sqlite"))
        # The authoritative records are the provenance events + JSON index.
        assert list(root.rglob("index/entities/artifact/*.json"))
        assert list(root.rglob("provenance/events/*/*/*.json"))
