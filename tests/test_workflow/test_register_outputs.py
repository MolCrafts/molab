"""RegisterAsset promotion — a task output becomes an asset ref.

A body writes under ``ctx.workdir`` and returns ``ctx.register`` /
``RegisterAsset``. The engine registers the file and records
``molab:asset/<id>``. A later task receives the payload path. The working
file stays under ``out/<task>/``. A cache hit returns that ref and does not
register again.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from molab.workflow import (
    RegisterAsset,
    TaskContext,
    Workflow,
    WorkflowRuntime,
)
from molab.workflow.cache import Caching
from molab.workspace import Workspace
from molab.workspace.asset_repository import AssetRepository, assets_produced_by
from molab.workspace.domain import ExecutionMode, ExecutionOrigin
from molab.workspace.execution_dirs import OUT


def _new_run(tmp_path: Path, params: dict | None = None):
    ws = Workspace(tmp_path / "lab")
    return ws.add_project(name="p").add_experiment(name="e").add_run(params=params or {})


def _produced(run, execution_id: str):
    workspace = run.experiment.project.workspace
    return [
        asset
        for asset in assets_produced_by(workspace, execution_id)
        if isinstance(asset.origin, ExecutionOrigin) and asset.origin.run_id == run.id
    ]


class TestPromoteRegisterAsset:
    @pytest.mark.asyncio
    async def test_returned_marker_records_the_asset_ref(self, tmp_path: Path) -> None:
        captured: dict[str, Path] = {}
        wf = Workflow(name="reg")

        @wf.task
        async def export(ctx: TaskContext) -> dict:
            out = ctx.workdir / "system.data"
            out.write_text("atoms")
            captured["scratch"] = out
            return {"data": RegisterAsset(out, title="system", mime="chemical/x-lammps-data")}

        @wf.task(depends_on=["export"])
        async def consume(data: Path) -> str:
            return data.read_text(encoding="utf-8")

        run = _new_run(tmp_path)
        with run.start() as ctx:
            result = await WorkflowRuntime().execute((wf).compile(), run_context=ctx)

        assert result.status == "succeeded"
        eid = run.executions[-1].id
        (asset,) = _produced(run, eid)
        assert result.outputs["export"]["data"] == asset.ref
        assert asset.ref.startswith("molab:asset/")
        assert asset.title == "system"
        assert asset.media_type == "chemical/x-lammps-data"
        assert isinstance(asset.origin, ExecutionOrigin)
        assert asset.origin.task == "export"
        scratch = captured["scratch"]
        assert scratch.parent.name == "export"
        assert OUT.name in scratch.parts
        assert scratch.read_text(encoding="utf-8") == "atoms"
        assert Path(run.asset_path(asset.id)).read_text(encoding="utf-8") == "atoms"
        assert result.outputs["consume"] == "atoms"

    @pytest.mark.asyncio
    async def test_scalar_marker_return_is_the_ref(self, tmp_path: Path) -> None:
        wf = Workflow(name="scalar")

        @wf.task
        async def export(ctx: TaskContext) -> RegisterAsset:
            out = ctx.workdir / "a.txt"
            out.write_text("x")
            return RegisterAsset(out, title="a")

        run = _new_run(tmp_path)
        with run.start() as ctx:
            result = await WorkflowRuntime().execute((wf).compile(), run_context=ctx)

        (asset,) = _produced(run, run.executions[-1].id)
        assert result.outputs["export"] == asset.ref
        assert Path(run.asset_path(asset.id)).read_text(encoding="utf-8") == "x"

    @pytest.mark.asyncio
    async def test_ctx_register_in_return_dict(self, tmp_path: Path) -> None:
        wf = Workflow(name="verb")

        @wf.task
        async def export(ctx: TaskContext) -> dict:
            out = ctx.workdir / "report.txt"
            out.write_text("ok")
            return {"report": ctx.register(out, title="report", mime="text/plain")}

        run = _new_run(tmp_path)
        with run.start() as ctx:
            result = await WorkflowRuntime().execute((wf).compile(), run_context=ctx)

        (asset,) = _produced(run, run.executions[-1].id)
        assert result.outputs["export"]["report"] == asset.ref
        assert asset.media_type == "text/plain"

    @pytest.mark.asyncio
    async def test_pending_only_still_registers(self, tmp_path: Path) -> None:
        wf = Workflow(name="pending")

        @wf.task
        async def export(ctx: TaskContext) -> int:
            out = ctx.workdir / "side.txt"
            out.write_text("side")
            ctx.register(out, title="side")
            return 1

        run = _new_run(tmp_path)
        with run.start() as ctx:
            result = await WorkflowRuntime().execute((wf).compile(), run_context=ctx)

        assert result.outputs["export"] == 1
        eid = run.executions[-1].id
        (asset,) = [item for item in _produced(run, eid) if item.title == "side"]
        assert Path(run.asset_path(asset.id)).read_text(encoding="utf-8") == "side"
        assert (
            Path(run.run_dir) / "executions" / eid / OUT.name / "export" / "side.txt"
        ).read_text() == "side"

    @pytest.mark.asyncio
    async def test_register_metric_appends_wal(self, tmp_path: Path) -> None:
        wf = Workflow(name="metric")

        @wf.task
        async def measure(ctx: TaskContext) -> dict:
            return {"n": ctx.register_metric("n_atoms", 42.0)}

        run = _new_run(tmp_path)
        with run.start() as ctx:
            result = await WorkflowRuntime().execute((wf).compile(), run_context=ctx)

        assert result.outputs["measure"]["n"] == 42.0
        eid = run.executions[-1].id
        wal = Path(run.run_dir) / "executions" / eid / "metrics.mlp.jsonl"
        assert wal.is_file()
        assert "n_atoms" in wal.read_text(encoding="utf-8")
        assert _produced(run, eid) == []

    @pytest.mark.asyncio
    async def test_cache_hit_returns_the_ref_without_a_new_asset(self, tmp_path: Path) -> None:
        counters = {"export": 0}
        wf = Workflow(name="cached-reg")

        @wf.task
        async def export(ctx: TaskContext) -> str:
            counters["export"] += 1
            out = ctx.workdir / "cached.txt"
            out.write_text("cached")
            return ctx.register(out, title="cached")

        compiled = (wf).compile()
        cache = Caching(store_dir=tmp_path / "shared-cache")
        proj = Workspace(tmp_path / "lab").add_project(name="p")
        run1 = proj.add_experiment(name="e1").add_run()
        with run1.start() as ctx1:
            r1 = await WorkflowRuntime().execute(compiled, run_context=ctx1, cache=cache)
        run2 = proj.add_experiment(name="e2").add_run()
        with run2.start() as ctx2:
            r2 = await WorkflowRuntime().execute(compiled, run_context=ctx2, cache=cache)

        assert counters["export"] == 1
        (asset,) = _produced(run1, run1.executions[-1].id)
        assert r1.outputs["export"] == r2.outputs["export"] == asset.ref
        assert _produced(run2, run2.executions[-1].id) == []
        export_dir = run2.execution_dir(run2.executions[-1].id) / OUT.name / "export"
        assert not (export_dir / "cached.txt").exists()

    @pytest.mark.asyncio
    async def test_title_lands_on_the_experiment(self, tmp_path: Path) -> None:
        wf = Workflow(name="asset")

        @wf.task
        async def export(ctx: TaskContext) -> dict:
            out = ctx.workdir / "portrait.png"
            out.write_bytes(b"png")
            return {"file": ctx.register(out, title="portrait", mime="image/png")}

        run = _new_run(tmp_path)
        with run.start() as ctx:
            result = await WorkflowRuntime().execute((wf).compile(), run_context=ctx)

        assert result.status == "succeeded"
        (asset,) = run.experiment.assets.list()
        assert asset.title == "portrait"
        assert isinstance(asset.origin, ExecutionOrigin)
        assert asset.origin.task == "export"
        assert result.outputs["export"]["file"] == asset.ref

    @pytest.mark.asyncio
    async def test_cache_hit_and_fresh_rerun_keep_one_asset(self, tmp_path: Path) -> None:
        counters = {"export": 0}
        wf = Workflow(name="asset-cache")

        @wf.task
        async def export(ctx: TaskContext) -> dict:
            counters["export"] += 1
            out = ctx.workdir / "portrait.png"
            out.write_bytes(b"png")
            return {"file": ctx.register(out, title="portrait", mime="image/png")}

        compiled = (wf).compile()
        run = _new_run(tmp_path)
        with run.start() as ctx:
            await WorkflowRuntime().execute(compiled, run_context=ctx)
        with run.start(mode=ExecutionMode.RERUN) as ctx:
            hit = await WorkflowRuntime().execute(compiled, run_context=ctx)
        with run.start(mode=ExecutionMode.RERUN, bypass_cache=True) as ctx:
            fresh = await WorkflowRuntime().execute(compiled, run_context=ctx)

        assert hit.status == fresh.status == "succeeded"
        assert counters["export"] == 2
        assets = run.experiment.assets.list()
        assert [asset.title for asset in assets] == ["portrait"]
        assert hit.outputs["export"]["file"] == fresh.outputs["export"]["file"] == assets[0].ref
        assert _produced(run, "e02") == []

    @pytest.mark.asyncio
    async def test_register_failure_fails_the_task(self, tmp_path: Path, monkeypatch) -> None:
        def boom(self, source: object, **kwargs: object) -> None:
            del self, source, kwargs
            raise RuntimeError("library down")

        monkeypatch.setattr(AssetRepository, "register", boom)
        wf = Workflow(name="asset-fail")

        @wf.task
        async def export(ctx: TaskContext) -> dict:
            out = ctx.workdir / "portrait.png"
            out.write_bytes(b"png")
            return {"file": ctx.register(out, title="portrait", mime="image/png")}

        run = _new_run(tmp_path)
        with run.start() as ctx:
            result = await WorkflowRuntime().execute((wf).compile(), run_context=ctx)

        assert result.status == "failed"
        assert run.experiment.assets.list() == []
