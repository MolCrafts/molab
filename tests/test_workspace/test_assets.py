"""Invariant tests for the v2 artifact/asset model.

Covers the emitted-artifact surface (``ArtifactRepository`` + the owning
``Execution``) plus the retained asset-model classes (``Asset`` hierarchy,
``parse_asset``, ``DataAssetLibrary``) and their success criteria:

- Artifact records are self-contained (workspace-relative path + content digest).
- Emitted payloads hash to the digest recorded for them.
- Subclass dispatch survives serialization round-trips.
- The active task id populates ``Artifact.metadata``.
- Concurrent artifact writes all land on the Execution.
- The scope-bound ``AssetsView`` filters to its own scope; imports land there.

(Cross-cutting query shapes are owned by ``test_asset_scan.py``.)
"""

from __future__ import annotations

import json
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from molab.workspace import Workspace
from molab.workspace.artifact_repository import ArtifactRepository, content_ref, scan_artifacts
from molab.workspace.assets import (
    ArtifactAsset,
    AssetScope,
    CheckpointAsset,
    DataAsset,
    ErrorTraceAsset,
    LogAsset,
    parse_asset,
    scan,
)
from molab.workspace.domain import Artifact
from molab.workspace.execution_dirs import execution_dir_names

ARTIFACTS_PER_RUN = 2


def _seed_workspace(root: Path, n_runs: int = 2) -> Workspace:
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


def _query(ws: Workspace, *, run_id: str | None = None) -> list[Artifact]:
    out = [a for a in _all_artifacts(ws) if run_id is None or a.run_id == run_id]
    return sorted(out, key=lambda a: (a.created_at, a.id))


def _repo(ws: Workspace) -> ArtifactRepository:
    return ArtifactRepository(ws.root, fs=ws.fs)


class TestArtifactRecordPortability:
    def test_artifact_records_relocate_with_run_dir(self, tmp_path):
        """A run directory copied elsewhere carries its own artifact records —
        they live in the attempt's ``execution.json``, never in a side index."""
        ws = _seed_workspace(tmp_path / "source", n_runs=1)
        run = ws.project("demo").experiment("baseline").list_runs()[0]
        src_run_dir = Path(run.run_dir)

        dst_run_dir = tmp_path / "destination" / "runs" / src_run_dir.name
        dst_run_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src_run_dir, dst_run_dir)

        states = list(dst_run_dir.rglob("executions/*/execution.json"))
        assert len(states) == 1
        records = json.loads(states[0].read_text())["artifacts"]
        assert len(records) == ARTIFACTS_PER_RUN  # artifact + checkpoint
        for record in records:
            # Every product came from one of the attempt's own directories.
            assert record["source_path"].split("/")[0] in execution_dir_names()
            assert record["path"].startswith("projects/")
            assert record["content"]["digest"].startswith("sha256:")


class TestArtifactContent:
    def test_every_artifact_payload_verifies(self, tmp_path):
        ws = _seed_workspace(tmp_path / "lab", n_runs=2)
        artifacts = _all_artifacts(ws)
        assert len(artifacts) == 2 * ARTIFACTS_PER_RUN
        for artifact in artifacts:
            assert artifact.content.digest.startswith("sha256:")
            payload = ws.fs.join(str(ws.root), artifact.path)
            assert content_ref(ws.fs, payload) == artifact.content

    def test_parallel_emits_all_land_in_index(self, tmp_path):
        ws = Workspace(tmp_path / "lab", name="Test")
        run = ws.add_project("p").add_experiment("e").add_run()
        n = 20
        with run.start() as ctx, ThreadPoolExecutor(max_workers=4) as pool:
            futs = [
                pool.submit(
                    lambda i=i: ctx.emit_artifact(
                        {"i": i}, name=f"a{i}.json", semantic_type="artifact"
                    )
                )
                for i in range(n)
            ]
            results = [f.result() for f in as_completed(futs)]

        assert len(results) == n
        assert len(_query(ws, run_id=run.id)) == n
        assert len(run.executions[0].artifacts) == n


class TestParseAsset:
    def test_round_trip_preserves_each_subclass(self):
        scope = AssetScope(kind="run", ids=("p", "e", "run-1"))
        now = datetime.now()
        cases = [
            ArtifactAsset(
                asset_id="a1",
                name="m.json",
                scope=scope,
                path=Path("artifacts/m.json"),
                created_at=now,
                updated_at=now,
                mime="application/json",
                size=10,
            ),
            LogAsset(
                asset_id="l1",
                name="run",
                scope=scope,
                path=Path("executions/ex-1/logs/run.log"),
                created_at=now,
                updated_at=now,
            ),
            CheckpointAsset(
                asset_id="c1",
                name="ckpt1",
                scope=scope,
                path=Path(".ckpt/c1.json"),
                created_at=now,
                updated_at=now,
                ckpt_id="ckpt_abc",
                parent_ckpt_id=None,
            ),
            ErrorTraceAsset(
                asset_id="e1",
                name="err",
                scope=scope,
                path=Path("executions/ex-1/error.txt"),
                created_at=now,
                updated_at=now,
                exception_type="RuntimeError",
                message="oops",
                execution_id="ex-1",
            ),
            DataAsset(
                asset_id="d1",
                name="ds",
                scope=scope,
                path=Path("assets/d1/payload"),
                created_at=now,
                updated_at=now,
                source_path="/tmp/ds",
                import_action="copy",
            ),
        ]
        for asset in cases:
            revived = parse_asset(json.loads(asset.model_dump_json()))
            assert type(revived) is type(asset)
            assert revived.asset_id == asset.asset_id


class TestProducer:
    def test_active_task_sets_metadata_task_id(self, tmp_path):
        ws = Workspace(tmp_path / "lab", name="Test")
        run = ws.add_project("p").add_experiment("e").add_run()
        with run.start() as ctx:
            ctx.set_active_task("train")
            artifact = ctx.emit_artifact({"x": 1}, name="m.json")
        assert artifact.metadata.get("task_id") == "train"


class TestAssetsView:
    def test_scope_views_return_only_their_own_scope(self, tmp_path):
        ws = _seed_workspace(tmp_path / "lab", n_runs=2)
        proj = ws.list_projects()[0]
        exp = proj.list_experiments()[0]

        # Emitted artifacts are v2 provenance artifacts, not DataAssets nor
        # promoted Project Assets — so the data-asset / project views are empty.
        assert ws.assets.list() == []
        assert proj.assets.list() == []
        assert exp.assets.list() == []

        # Every emitted artifact is run-scoped and reachable via the v2 index.
        for run in exp.list_runs():
            assert {a.semantic_type for a in _query(ws, run_id=run.id)} == {
                "artifact",
                "checkpoint",
            }

    def test_imported_data_asset_lands_at_workspace_scope(self, tmp_path):
        ws = Workspace(tmp_path / "lab", name="Test")
        src = tmp_path / "input.txt"
        src.write_text("hello")
        asset = ws.data_assets.import_asset("greeting", src)
        assert isinstance(asset, DataAsset)
        assert asset.scope.kind == "workspace"

        # Visible through both the workspace view and the manifest scanner.
        assert ws.assets.get(asset.asset_id) is not None
        assert scan.get_asset(ws.root, asset.asset_id) is not None
