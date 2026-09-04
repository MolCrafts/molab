"""Engine-automatic artifact lineage (vision-loop-09).

THE FAIR anchor: a tracked run's workflow DAG projects into Artifact
``input_entity_ids`` with ZERO task-author annotation — the engine
(``_engine.node_cache._upstream_asset_ids``) records each task's upstream
artifact ids, so "which input produced this result?" is answerable for every
tracked run through ``lineage.ancestors``.
"""

from __future__ import annotations

from pathlib import Path

from molexp.workflow import TaskContext, Workflow
from molexp.workspace import Workspace
from molexp.workspace.assets import lineage


def _workspace(tmp_path: Path) -> Workspace:
    ws = Workspace(tmp_path / "lab", name="lab")
    ws.materialize()
    return ws


def _artifact_for(run, task: str):
    execution_id = run.executions[-1].id
    artifacts = run._execution_repository().artifacts.list_for_execution(execution_id)
    found = [a for a in artifacts if a.metadata.get("task_id") == task]
    assert found, f"no artifact registered for task {task!r}"
    return found[0]


def _chain_workflow() -> Workflow:
    wf = Workflow(name="chain")

    @wf.task
    async def upstream(ctx: TaskContext) -> dict:
        out = {"value": 21}
        ctx.register_artifact(out, name="upstream.json")
        return out

    @wf.task(depends_on=["upstream"])
    async def downstream(ctx: TaskContext, value: int) -> dict:
        out = {"doubled": value * 2}
        ctx.register_artifact(out, name="downstream.json")
        return out

    return wf


class TestEngineAutomaticLineage:
    def test_chain_projects_upstream_id_into_downstream_producer_inputs(
        self, tmp_path: Path
    ) -> None:
        """THE test: downstream's input_entity_ids carries upstream's artifact id and
        the ``lineage.ancestors`` traversal answers it — zero task annotation."""
        ws = _workspace(tmp_path)
        run = ws.add_project("p").add_experiment("e").add_run(params=None)
        run.execute(_chain_workflow())

        up = _artifact_for(run, "upstream")
        down = _artifact_for(run, "downstream")
        assert up.id in down.input_entity_ids
        assert up.id in lineage.ancestors(ws, down.id)

    def test_root_task_artifact_has_empty_inputs(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        run = ws.add_project("p").add_experiment("e").add_run(params=None)
        run.execute(_chain_workflow())
        up = _artifact_for(run, "upstream")
        assert up.input_entity_ids == ()

    def test_diamond_fan_in_records_both_upstreams_deduped(self, tmp_path: Path) -> None:
        wf = Workflow(name="diamond")

        @wf.task
        async def left(ctx: TaskContext) -> dict:
            out = {"l": 1}
            ctx.register_artifact(out, name="left.json")
            return out

        @wf.task
        async def right(ctx: TaskContext) -> dict:
            out = {"r": 2}
            ctx.register_artifact(out, name="right.json")
            return out

        @wf.task(depends_on=["left", "right"])
        async def join(ctx: TaskContext, l: int, r: int) -> dict:  # noqa: E741
            out = {"sum": l + r}
            ctx.register_artifact(out, name="join.json")
            return out

        ws = _workspace(tmp_path)
        run = ws.add_project("p").add_experiment("e").add_run(params=None)
        run.execute(wf)

        join_artifact = _artifact_for(run, "join")
        inputs = set(join_artifact.input_entity_ids)
        left_id = _artifact_for(run, "left").id
        right_id = _artifact_for(run, "right").id
        assert {left_id, right_id} <= inputs
        assert len(join_artifact.input_entity_ids) == len(inputs)  # deduped
        # Independent parallel tasks record no cross-edges.
        left_artifact = _artifact_for(run, "left")
        assert right_id not in left_artifact.input_entity_ids

    def test_cache_hit_upstream_still_chains_downstream(self, tmp_path: Path) -> None:
        """A second run whose upstream cache-hits still chains downstream→upstream."""
        ws = _workspace(tmp_path)
        exp = ws.add_project("p").add_experiment("e")

        run1 = exp.add_run(params=None, id="first")
        run1.execute(_chain_workflow())

        run2 = exp.add_run(params=None, id="second")
        run2.execute(_chain_workflow())

        down2 = _artifact_for(run2, "downstream")
        up2 = _artifact_for(run2, "upstream")
        assert up2.id in down2.input_entity_ids
        assert up2.id in lineage.ancestors(ws, down2.id)

    def test_raising_lineage_computation_never_fails_the_run(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Fail-soft: lineage rides the persistence bonus channel — a raising
        upstream-id computation degrades (persist skipped, debug log) and the
        run still succeeds with its results intact."""
        from molexp.workflow._engine import node_cache

        def _boom(deps, registration):
            raise RuntimeError("lineage computation broken")

        monkeypatch.setattr(node_cache, "_upstream_asset_ids", _boom)
        ws = _workspace(tmp_path)
        run = ws.add_project("p").add_experiment("e").add_run(params=None)
        result = run.execute(_chain_workflow())
        assert result.status == "succeeded"
        assert result.outputs["downstream"] == {"doubled": 42}
