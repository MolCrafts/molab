"""Artifact queries answered by the Executions that own the artifacts.

There is no artifact index. An Execution records its own products in its
``execution.json``, so "which artifacts exist" is a walk of the run tree
(:func:`molexp.workspace.artifact_repository.scan_artifacts`) and "which
artifacts did this attempt emit" is one file read. Emitted artifacts are
created by
:meth:`molexp.workspace.execution_context.ExecutionContext.emit_artifact`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from molexp.workspace import Workspace
from molexp.workspace.artifact_repository import scan_artifacts
from molexp.workspace.domain import Artifact

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
    return scan_artifacts(ws)


class TestQueryArtifacts:
    def test_run_scope_matches_only_that_run(self, tmp_path):
        ws = _seed_workspace(tmp_path / "lab")
        run = ws.project("demo").experiment("baseline").list_runs()[0]
        execution = run.executions[0]
        assert len(execution.artifacts) == ARTIFACTS_PER_RUN
        assert all(
            a.execution_id == execution.id and a.run_id == run.id for a in execution.artifacts
        )

    def test_scan_sees_every_run(self, tmp_path):
        ws = _seed_workspace(tmp_path / "lab")
        assert len(_all_artifacts(ws)) == 3 * ARTIFACTS_PER_RUN


class TestGetArtifact:
    def test_execution_resolves_its_own_artifact_else_keyerror(self, tmp_path):
        ws = _seed_workspace(tmp_path / "lab")
        run = ws.project("demo").experiment("baseline").list_runs()[0]
        execution = run.executions[0]
        some = execution.artifacts[0]
        assert execution.artifact(some.id).id == some.id
        with pytest.raises(KeyError):
            execution.artifact("nonexistent")


class TestNoDerivedArtifactIndex:
    """Invariant lock: nothing re-encodes an artifact outside its Execution."""

    def test_seeded_workspace_keeps_artifacts_only_in_executions(self, tmp_path):
        ws = _seed_workspace(tmp_path / "lab")
        root = Path(str(ws.root))
        assert len(_all_artifacts(ws)) == 3 * ARTIFACTS_PER_RUN
        assert not (root / "catalog").exists()
        assert not (root / "index").exists()
        assert not (root / "provenance").exists()
        assert not (root / "content").exists()
        assert not list(root.rglob("*.sqlite"))
        assert not list(root.rglob("artifact.json"))
        # The bytes live where a person would look for them.
        assert list(root.rglob("executions/e01/artifacts/metrics.json"))
