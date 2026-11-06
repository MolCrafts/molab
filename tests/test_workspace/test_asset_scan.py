"""Which assets an attempt produced is a walk of asset records.

There is no artifact index and no product list on ``execution.json``.
"""

from __future__ import annotations

from pathlib import Path

from molab.workspace import Workspace
from molab.workspace.asset_repository import asset_by_id, assets_produced_by
from molab.workspace.domain import ExecutionOrigin


def _seed(root: Path, n_runs: int = 3) -> Workspace:
    ws = Workspace(root=root, name="Test")
    experiment = ws.add_project("demo").add_experiment("baseline", params={"lr": 1e-3})
    for i in range(n_runs):
        run = experiment.add_run(params={"seed": i})
        with run.start() as ctx:
            ctx.register({"loss": 0.1 * i}, title="metrics.json")
            ctx.checkpoint("epoch1", data={"step": 1})
    return ws


class TestAssetsProducedBy:
    def test_one_attempt(self, tmp_path: Path) -> None:
        ws = _seed(tmp_path / "lab")
        run = ws.project("demo").experiment("baseline").list_runs()[0]
        execution = run.executions[0]
        produced = [
            asset
            for asset in assets_produced_by(ws, execution.id)
            if isinstance(asset.origin, ExecutionOrigin) and asset.origin.run_id == run.id
        ]
        assert len(produced) == 1
        origin = produced[0].origin
        assert isinstance(origin, ExecutionOrigin)
        assert origin.execution_id == execution.id
        assert origin.run_id == run.id

    def test_scan_sees_every_run(self, tmp_path: Path) -> None:
        ws = _seed(tmp_path / "lab")
        produced = []
        for run in ws.project("demo").experiment("baseline").list_runs():
            produced.extend(
                asset
                for asset in assets_produced_by(ws, run.executions[0].id)
                if isinstance(asset.origin, ExecutionOrigin) and asset.origin.run_id == run.id
            )
        assert len(produced) == 3

    def test_unknown_attempt_is_empty(self, tmp_path: Path) -> None:
        ws = _seed(tmp_path / "lab", n_runs=1)
        assert assets_produced_by(ws, "e99") == []


class TestAssetById:
    def test_found_or_none(self, tmp_path: Path) -> None:
        ws = _seed(tmp_path / "lab", n_runs=1)
        run = ws.project("demo").experiment("baseline").list_runs()[0]
        (asset,) = assets_produced_by(ws, run.executions[0].id)
        assert asset_by_id(ws, asset.id).id == asset.id
        assert asset_by_id(ws, "missing") is None


class TestNoDerivedIndex:
    def test_bytes_live_with_the_asset_record(self, tmp_path: Path) -> None:
        ws = _seed(tmp_path / "lab")
        root = Path(str(ws.root))
        assert not (root / "catalog").exists()
        assert not list(root.rglob("artifact.json"))
        assert not list(root.rglob("executions/e01/artifacts/*"))
        assert list(root.rglob("assets/*/asset.json"))
        assert list(root.rglob("executions/e01/checkpoints/epoch1.json"))
        assert ws.project("demo").experiment("baseline").list_runs()[0].execution("e01").id == "e01"
