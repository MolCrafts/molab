"""``TaskContext.metrics``, the task tag, node-cache replay and the producer tag (D93).

Under an execution a task body writes through the execution's own metrics
writer: live, tagged ``tags.task``. The node cache stores a task's records
beside its result and replays them on a hit, tagged ``replayed_from``.
Without molab the body gets an in-memory ``BufferedMetrics``. An asset
records the task that registered it even when same-level tasks run in parallel.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from molab.plugins.metrics import read_run_metrics
from molab.workflow import TaskContext, Workflow, WorkflowRuntime
from molab.workflow.cache import Caching
from molab.workspace import Workspace, tracking
from molab.workspace.asset_repository import assets_produced_by
from molab.workspace.domain import ExecutionMode, ExecutionOrigin
from molab.workspace.tracking import BufferedMetrics, TrackedMetrics


def _new_run(tmp_path: Path):
    ws = Workspace(tmp_path / "lab")
    return ws.add_project(name="p").add_experiment(name="e").add_run(params={})


def _records(run, execution_id: str) -> list[dict]:
    return read_run_metrics(run.execution_dir(execution_id)).records


class _SpyCache(Caching):
    """A ``Caching`` that keeps every payload it was asked to put."""

    def __init__(self, store_dir: Path, *, strip_metrics: bool = False) -> None:
        super().__init__(store_dir=store_dir)
        self.puts: list[dict] = []
        self._strip = strip_metrics

    def put(self, snapshot, inputs, result) -> None:
        self.puts.append(result)
        if self._strip:
            result = {k: v for k, v in result.items() if k not in {"metrics", "producer_execution"}}
        super().put(snapshot, inputs, result)


def _metric_workflow(counter: dict[str, int]) -> Workflow:
    wf = Workflow(name="metrics")

    @wf.task
    def train(ctx: TaskContext) -> int:
        counter["train"] += 1
        for step in range(3):
            ctx.metrics.scalar("loss", 1.0 / (step + 1), step)
        ctx.register_metric("final", 0.25, step=3)
        return 3

    return wf


class TestFromATask:
    @pytest.mark.asyncio
    async def test_five_types_round_trip_with_the_task_tag(self, tmp_path: Path) -> None:
        wf = Workflow(name="types")

        @wf.task
        async def measure(ctx: TaskContext) -> str:
            assert isinstance(ctx.metrics, TrackedMetrics)
            ctx.metrics.scalar("loss", 0.5, 1)
            ctx.metrics.histogram("forces", [0.0, 1.0], [2], 1)
            ctx.metrics.text("note", "ok", 1)
            ctx.metrics.json("config", {"lr": 0.1}, 1)
            ref = ctx.metrics.image("frame", b"\x89PNG", 1, name="frame.png")
            return str(ref["v"]["path"])

        run = _new_run(tmp_path)
        with run.start() as ctx:
            result = await WorkflowRuntime().execute((wf).compile(), run_context=ctx)
        eid = run.executions[-1].id
        records = _records(run, eid)
        assert [r["t"] for r in records] == ["scalar", "histogram", "text", "json", "image_ref"]
        assert all(r["tags"] == {"task": "measure"} for r in records)
        (image,) = [
            asset
            for asset in assets_produced_by(run.experiment.project.workspace, eid)
            if asset.title == "frame.png"
        ]
        assert image.media_type == "image/png"
        assert isinstance(image.origin, ExecutionOrigin)
        assert image.origin.task == "measure"
        assert result.outputs["measure"] == image.ref

    @pytest.mark.asyncio
    async def test_a_record_is_on_disk_before_the_body_returns(self, tmp_path: Path) -> None:
        seen: dict[str, bool] = {}
        wf = Workflow(name="live")

        @wf.task
        def watch(ctx: TaskContext) -> int:
            ctx.metrics.scalar("loss", 0.75, 0)
            current = tracking.current()
            assert current is not None
            wal = current.execution_dir / "metrics.mlp.jsonl"
            lines = wal.read_text(encoding="utf-8").splitlines()
            seen["live"] = any(json.loads(line)["k"] == "loss" for line in lines)
            return 1

        run = _new_run(tmp_path)
        with run.start() as ctx:
            await WorkflowRuntime().execute((wf).compile(), run_context=ctx)
        assert seen == {"live": True}

    @pytest.mark.asyncio
    async def test_parallel_tasks_tag_their_own_records(self, tmp_path: Path) -> None:
        wf = Workflow(name="parallel")

        async def _body(ctx: TaskContext, label: str) -> int:
            for step in range(30):
                ctx.metrics.scalar(f"{label}_loss", float(step), step)
                await asyncio.sleep(0)
            return 30

        @wf.task
        async def left(ctx: TaskContext) -> int:
            return await _body(ctx, "left")

        @wf.task
        async def right(ctx: TaskContext) -> int:
            return await _body(ctx, "right")

        @wf.task
        def middle(ctx: TaskContext) -> int:
            for step in range(30):
                ctx.metrics.scalar("middle_loss", float(step), step)
            return 30

        run = _new_run(tmp_path)
        with run.start() as ctx:
            await WorkflowRuntime().execute((wf).compile(), run_context=ctx)
        records = _records(run, run.executions[-1].id)
        assert len(records) == 90
        for record in records:
            assert record["tags"]["task"] == str(record["k"]).removesuffix("_loss")

    @pytest.mark.asyncio
    async def test_register_metric_is_tagged_with_the_task(self, tmp_path: Path) -> None:
        wf = Workflow(name="deferred")

        @wf.task
        async def measure(ctx: TaskContext) -> dict:
            return {"n": ctx.register_metric("n_atoms", 42.0, tags={"unit": "count"})}

        run = _new_run(tmp_path)
        with run.start() as ctx:
            result = await WorkflowRuntime().execute((wf).compile(), run_context=ctx)
        assert result.outputs["measure"]["n"] == 42.0
        (record,) = _records(run, run.executions[-1].id)
        assert record["tags"] == {"task": "measure", "unit": "count"}


class TestOffWorkspace:
    @pytest.mark.asyncio
    async def test_buffered_metrics_collect_records(self) -> None:
        wf = Workflow(name="offline")

        @wf.task
        def fit(ctx: TaskContext) -> list:
            assert isinstance(ctx.metrics, BufferedMetrics)
            assert ctx.metrics is ctx.metrics
            ctx.metrics.scalar("loss", 0.5, 0)
            ctx.metrics.image("frame", "frame.png", 0)
            return list(ctx.metrics.records)

        result = await WorkflowRuntime().execute((wf).compile())
        scalar, image = result.outputs["fit"]
        assert scalar["v"] == 0.5 and scalar["tags"] == {"task": "fit"}
        assert image["t"] == "image_ref" and image["v"]["path"] == "frame.png"


class TestNodeCacheReplay:
    @pytest.mark.asyncio
    async def test_a_hit_replays_the_records_of_the_miss(self, tmp_path: Path) -> None:
        counter = {"train": 0}
        compiled = (_metric_workflow(counter)).compile()
        cache = _SpyCache(tmp_path / "cache")
        run = _new_run(tmp_path)
        with run.start() as ctx:
            await WorkflowRuntime().execute(compiled, run_context=ctx, cache=cache)
        with run.start(mode=ExecutionMode.RERUN) as ctx:
            await WorkflowRuntime().execute(compiled, run_context=ctx, cache=cache)

        assert counter["train"] == 1
        (payload,) = cache.puts
        assert payload["producer_execution"] == "e01"
        first = _records(run, "e01")
        assert payload["metrics"] == first
        assert [r["k"] for r in first] == ["loss", "loss", "loss", "final"]

        replayed = _records(run, "e02")
        assert len(replayed) == len(first)
        for original, again in zip(first, replayed, strict=True):
            assert again["tags"] == {**original["tags"], "replayed_from": "e01"}
            assert {k: v for k, v in again.items() if k != "tags"} == {
                k: v for k, v in original.items() if k != "tags"
            }
        wal = run.execution_dir("e02") / "metrics.mlp.jsonl"
        assert wal.is_file()
        assert assets_produced_by(run.experiment.project.workspace, "e02") == []

    @pytest.mark.asyncio
    async def test_over_the_cap_nothing_is_replayed(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(tracking, "TASK_RECORD_CAP", 2)
        counter = {"train": 0}
        compiled = (_metric_workflow(counter)).compile()
        cache = _SpyCache(tmp_path / "cache")
        run = _new_run(tmp_path)
        with run.start() as ctx:
            await WorkflowRuntime().execute(compiled, run_context=ctx, cache=cache)
        with run.start(mode=ExecutionMode.RERUN) as ctx:
            result = await WorkflowRuntime().execute(compiled, run_context=ctx, cache=cache)

        (payload,) = cache.puts
        assert "metrics" not in payload
        assert counter["train"] == 1  # the put succeeded, so the rerun hit
        assert result.outputs["train"] == 3
        assert len(_records(run, "e01")) == 4
        assert _records(run, "e02") == []

    @pytest.mark.asyncio
    async def test_an_old_payload_replays_nothing(self, tmp_path: Path) -> None:
        counter = {"train": 0}
        compiled = (_metric_workflow(counter)).compile()
        cache = _SpyCache(tmp_path / "cache", strip_metrics=True)
        run = _new_run(tmp_path)
        with run.start() as ctx:
            await WorkflowRuntime().execute(compiled, run_context=ctx, cache=cache)
        with run.start(mode=ExecutionMode.RERUN) as ctx:
            await WorkflowRuntime().execute(compiled, run_context=ctx, cache=cache)

        assert counter["train"] == 1
        assert _records(run, "e02") == []

    @pytest.mark.asyncio
    async def test_the_auto_cache_replays_too(self, tmp_path: Path) -> None:
        counter = {"train": 0}
        compiled = (_metric_workflow(counter)).compile()
        run = _new_run(tmp_path)
        with run.start() as ctx:
            await WorkflowRuntime().execute(compiled, run_context=ctx)
        with run.start(mode=ExecutionMode.RERUN) as ctx:
            await WorkflowRuntime().execute(compiled, run_context=ctx)
        assert counter["train"] == 1
        replayed = _records(run, "e02")
        assert len(replayed) == 4
        assert {r["tags"]["replayed_from"] for r in replayed} == {"e01"}


class TestProducerTask:
    """Fixes the ``set_active_task`` race: the producer tag is per task body."""

    @pytest.mark.asyncio
    async def test_parallel_tasks_each_tag_their_own_asset(self, tmp_path: Path) -> None:
        wf = Workflow(name="race")

        # ``fast`` starts, ``slow`` starts, then ``fast`` returns first and
        # its marker is registered while ``slow`` is still running.
        @wf.task
        async def fast(ctx: TaskContext) -> int:
            out = ctx.workdir / "fast.txt"
            out.write_text("fast")
            ctx.register(out, title="fast.txt")
            await asyncio.sleep(0.05)
            return 1

        @wf.task
        async def slow(ctx: TaskContext) -> int:
            out = ctx.workdir / "slow.txt"
            out.write_text("slow")
            ctx.register(out, title="slow.txt")
            await asyncio.sleep(0.3)
            return 2

        run = _new_run(tmp_path)
        with run.start() as ctx:
            await WorkflowRuntime().execute((wf).compile(), run_context=ctx)
        produced = {
            asset.title: asset.origin.task
            for asset in assets_produced_by(run.experiment.project.workspace, run.executions[-1].id)
            if isinstance(asset.origin, ExecutionOrigin)
            and asset.origin.run_id == run.id
            and asset.title in {"fast.txt", "slow.txt"}
        }
        assert produced == {"fast.txt": "fast", "slow.txt": "slow"}
