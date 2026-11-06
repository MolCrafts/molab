"""Asset lineage follows ``run.inputs``.

An asset produced by a run points at the asset ids that run named as inputs.
``lineage.ancestors`` / ``lineage.descendants`` walk that edge. A cache hit
returns the recorded ref and does not register another asset.
"""

from __future__ import annotations

from pathlib import Path

from molab.workflow import TaskContext, Workflow
from molab.workspace import Workspace
from molab.workspace.asset_repository import assets_produced_by
from molab.workspace.assets import lineage
from molab.workspace.domain import ExecutionMode, ExecutionOrigin


def _workspace(tmp_path: Path) -> Workspace:
    ws = Workspace(tmp_path / "lab", name="lab")
    ws.materialize()
    return ws


def _produced(run, execution_id: str | None = None):
    workspace = run.experiment.project.workspace
    execution_id = execution_id or run.executions[-1].id
    found = [
        asset
        for asset in assets_produced_by(workspace, execution_id)
        if isinstance(asset.origin, ExecutionOrigin) and asset.origin.run_id == run.id
    ]
    assert found, f"no asset registered on {run.id}"
    return found


def _chain(title: str) -> Workflow:
    wf = Workflow(name="chain")

    @wf.task
    async def measure(ctx: TaskContext) -> dict:
        out = ctx.workdir / f"{title}.txt"
        out.write_text(title)
        return {"file": ctx.register(out, title=title)}

    return wf


class TestRunInputLineage:
    def test_produced_asset_names_the_run_inputs(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        project = ws.add_project("p")
        raw = tmp_path / "raw.txt"
        raw.write_text("raw", encoding="utf-8")
        upstream = project.assets.import_asset("raw", raw)
        run = project.add_experiment("e").add_run(inputs=(upstream.id,))
        run.execute(_chain("leaf"))

        (leaf,) = _produced(run)
        assert isinstance(leaf.origin, ExecutionOrigin)
        assert leaf.origin.task == "measure"
        assert lineage.ancestors(ws, leaf.id) == {upstream.id}
        assert leaf.id in lineage.descendants(ws, upstream.id)

    def test_a_run_with_no_inputs_has_no_ancestors(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        run = ws.add_project("p").add_experiment("e").add_run()
        run.execute(_chain("alone"))
        (leaf,) = _produced(run)
        assert lineage.ancestors(ws, leaf.id) == set()

    def test_two_inputs_are_both_ancestors(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        project = ws.add_project("p")
        left = tmp_path / "left.txt"
        right = tmp_path / "right.txt"
        left.write_text("L", encoding="utf-8")
        right.write_text("R", encoding="utf-8")
        left_asset = project.assets.import_asset("left", left)
        right_asset = project.assets.import_asset("right", right)
        run = project.add_experiment("e").add_run(inputs=(left_asset.id, right_asset.id))
        run.execute(_chain("join"))

        (leaf,) = _produced(run)
        assert lineage.ancestors(ws, leaf.id) == {left_asset.id, right_asset.id}
        assert lineage.descendants(ws, left_asset.id) == {leaf.id}

    def test_cache_hit_does_not_mint_another_asset(self, tmp_path: Path) -> None:
        calls = {"measure": 0}

        def build() -> Workflow:
            wf = Workflow(name="chain")

            @wf.task
            async def measure(ctx: TaskContext) -> dict:
                calls["measure"] += 1
                out = ctx.workdir / "leaf.txt"
                out.write_text("leaf")
                return {"file": ctx.register(out, title="leaf")}

            return wf

        ws = _workspace(tmp_path)
        project = ws.add_project("p")
        raw = tmp_path / "raw.txt"
        raw.write_text("raw", encoding="utf-8")
        upstream = project.assets.import_asset("raw", raw)
        run = project.add_experiment("e").add_run(inputs=(upstream.id,))
        compiled = build().compile()
        first = run.execute(compiled)
        second = run.execute(compiled, rerun=True)

        assert calls["measure"] == 1
        assert [item.id for item in run.executions] == ["e01", "e02"]
        assert run.executions[1].mode is ExecutionMode.RERUN
        (leaf,) = _produced(run, "e01")
        assert first.outputs["measure"]["file"] == second.outputs["measure"]["file"] == leaf.ref
        assert lineage.ancestors(ws, leaf.id) == {upstream.id}
        assert [
            asset
            for asset in assets_produced_by(ws, "e02")
            if isinstance(asset.origin, ExecutionOrigin) and asset.origin.run_id == run.id
        ] == []
