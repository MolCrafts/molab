"""Invariant tests for emitted artifacts and the scope asset repository.

- Artifact records travel with the run directory.
- Emitted payloads hash to the digest recorded for them.
- The active task id populates ``Artifact.metadata``.
- Concurrent artifact writes all land on the Execution.
- ``data_assets`` is the scope ``AssetRepository``.
"""

from __future__ import annotations

import json
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from molab.workspace import Run, Workspace
from molab.workspace.artifact_repository import ArtifactRepository, content_ref, scan_artifacts
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


def _owning_run(ws: Workspace, artifact: Artifact) -> Run:
    for project in ws.list_projects():
        for experiment in project.list_experiments():
            for run in experiment.list_runs():
                if run.id == artifact.run_id:
                    return run
    raise AssertionError(artifact.run_id)


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
            assert record["path"].startswith("artifacts/")
            assert record["content"]["digest"].startswith("sha256:")


class TestArtifactContent:
    def test_every_artifact_payload_verifies(self, tmp_path):
        ws = _seed_workspace(tmp_path / "lab", n_runs=2)
        artifacts = _all_artifacts(ws)
        assert len(artifacts) == 2 * ARTIFACTS_PER_RUN
        for artifact in artifacts:
            assert artifact.content.digest.startswith("sha256:")
            owner = _owning_run(ws, artifact)
            location = owner.artifact_location(artifact.execution_id, artifact)
            assert content_ref(ws.fs, location) == artifact.content

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


class TestProducer:
    def test_active_task_sets_metadata_task_id(self, tmp_path):
        ws = Workspace(tmp_path / "lab", name="Test")
        run = ws.add_project("p").add_experiment("e").add_run()
        with run.start() as ctx:
            ctx.set_active_task("train")
            artifact = ctx.emit_artifact({"x": 1}, name="m.json")
        assert artifact.metadata.get("task_id") == "train"


class TestScopeAssets:
    """``data_assets`` is the scope repository. ``DataAssetLibrary`` is gone."""

    def test_data_assets_is_the_scope_repository(self, workspace, project, experiment):
        from molab.workspace.artifact_repository import AssetRepository

        for scope in (workspace, project, experiment):
            assert type(scope.data_assets) is AssetRepository
            assert scope.data_assets.scope == scope.scope
            assert not hasattr(scope, "_data_assets")

    def test_an_experiment_import_stays_on_that_experiment(self, workspace, experiment, tmp_path):
        source = tmp_path / "hello.txt"
        source.write_bytes(b"hello\n")
        asset = experiment.data_assets.import_asset("d", source)
        assert asset.id in {item.id for item in experiment.assets.list()}
        assert asset.id not in {item.id for item in workspace.assets.list()}

    def test_data_asset_library_is_gone(self):
        import molab.workspace as workspace
        import molab.workspace.assets as assets_pkg

        assert not hasattr(workspace, "DataAssetLibrary")
        data_py = Path(assets_pkg.__file__).resolve().parent / "data.py"
        assert not data_py.is_file()
