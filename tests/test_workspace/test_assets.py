"""Registered files are assets of a scope, not rows on an attempt."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from molab.workspace import Workspace
from molab.workspace.asset_repository import (
    AssetRepository,
    assets_produced_by,
    content_ref,
    payload_path_for,
)
from molab.workspace.domain import ExecutionOrigin


def _seed(root: Path, n_runs: int = 2) -> Workspace:
    ws = Workspace(root=root, name="Test")
    experiment = ws.add_project("demo").add_experiment("baseline", params={"lr": 1e-3})
    for i in range(n_runs):
        run = experiment.add_run(params={"seed": i})
        with run.start() as ctx:
            ctx.register({"loss": 0.1 * i}, title="metrics.json")
            ctx.checkpoint("epoch1", data={"step": 1})
    return ws


class TestAssetLivesWithItsRecord:
    def test_the_run_directory_does_not_hold_the_asset(self, tmp_path: Path) -> None:
        ws = _seed(tmp_path / "source", n_runs=1)
        run = ws.project("demo").experiment("baseline").list_runs()[0]
        execution = json.loads(
            (Path(run.run_dir) / "executions" / "e01" / "execution.json").read_text()
        )
        assert "artifacts" not in execution
        assert list(Path(run.run_dir).rglob("asset.json")) == []
        assert list(Path(str(run.experiment.experiment_dir)).glob("assets/*/asset.json"))
        assert (Path(run.run_dir) / "executions" / "e01" / "checkpoints" / "epoch1.json").is_file()


class TestAssetContent:
    def test_every_payload_verifies(self, tmp_path: Path) -> None:
        ws = _seed(tmp_path / "lab", n_runs=2)
        found = []
        for run in ws.project("demo").experiment("baseline").list_runs():
            found.extend(
                asset
                for asset in assets_produced_by(ws, run.executions[0].id)
                if isinstance(asset.origin, ExecutionOrigin) and asset.origin.run_id == run.id
            )
        assert len(found) == 2
        for asset in found:
            assert isinstance(asset.origin, ExecutionOrigin)
            location = payload_path_for(ws, asset.id)
            assert content_ref(ws.fs, location) == asset.content

    def test_parallel_registers_all_land(self, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "lab", name="Test")
        run = ws.add_project("p").add_experiment("e").add_run()
        n = 20
        with run.start() as ctx, ThreadPoolExecutor(max_workers=4) as pool:
            futures = [
                pool.submit(lambda i=i: ctx.register({"i": i}, title=f"a{i}.json"))
                for i in range(n)
            ]
            results = [future.result() for future in as_completed(futures)]
            execution_id = ctx.id
        assert len(results) == n
        assert len(assets_produced_by(ws, execution_id)) == n


class TestProducer:
    def test_active_task_is_the_origin_task(self, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "lab", name="Test")
        run = ws.add_project("p").add_experiment("e").add_run()
        with run.start() as ctx:
            ctx.set_active_task("train")
            asset = ctx.register({"x": 1}, title="m.json")
        assert asset.origin.task == "train"


class TestScopeAssets:
    def test_assets_is_the_scope_repository(self, workspace, project, experiment) -> None:
        for scope in (workspace, project, experiment):
            assert type(scope.assets) is AssetRepository
            assert scope.assets.scope == scope.scope
            assert not hasattr(scope, "data_assets")

    def test_an_experiment_import_stays_on_that_experiment(
        self, workspace, experiment, tmp_path: Path
    ) -> None:
        source = tmp_path / "hello.txt"
        source.write_bytes(b"hello\n")
        asset = experiment.assets.import_asset("d", source)
        assert asset.id in {item.id for item in experiment.assets.list()}
        assert asset.id not in {item.id for item in workspace.assets.list()}

    def test_data_asset_library_is_gone(self) -> None:
        import molab.workspace as workspace
        import molab.workspace.assets as assets_pkg

        assert not hasattr(workspace, "DataAssetLibrary")
        data_py = Path(assets_pkg.__file__).resolve().parent / "data.py"
        assert not data_py.is_file()
