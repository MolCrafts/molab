"""A dry run walks the graph and does not call task bodies.

``report_from_compiled`` is the document the CLI and the HTTP route share;
``compiled_for_simulation`` rebuilds a walkable workflow from a stored IR
(a code experiment's graph snapshot with stub bodies, or a document
experiment's wire IR through the codec).
"""

from __future__ import annotations

import pytest

from molab.workflow import Workflow, WorkflowError, WorkflowRuntime
from molab.workflow.dry_run import compiled_for_simulation, report_from_compiled, simulate
from molab.workflow.registry import default_registry

ECHO_TASK_TYPE = "dry_run_echo"


def _three_tasks() -> Workflow:
    wf = Workflow(name="pbix")

    @wf.task
    async def monomers() -> dict[str, int]:
        return {"n": 1}

    @wf.task
    async def pack() -> dict[str, int]:
        return {"n": 1}

    @wf.task(depends_on=["monomers", "pack"])
    async def equilibrate(n: int) -> dict[str, int]:
        return {"n": n}

    return wf


def _branchy() -> Workflow:
    wf = Workflow(name="pipeline", entry="fetch")

    @wf.task
    async def fetch(ctx):
        return 1

    @wf.task(depends_on=["fetch"], routes={"ok": "publish", "fail": "rollback"})
    async def validate(ctx):
        return 2

    @wf.task(depends_on=["validate"])
    async def publish(ctx):
        return 3

    @wf.task(depends_on=["validate"])
    async def rollback(ctx):
        return 4

    return wf


class _Echo:
    def __init__(self, config: dict[str, object]) -> None:
        self._task_config = dict(config)

    async def execute(self, ctx: object) -> dict[str, bool]:
        return {"ok": True}


def test_dry_run_orders_waves_and_skips_bodies() -> None:
    calls: list[str] = []
    wf = Workflow(name="pbix")

    @wf.task
    async def monomers() -> dict[str, int]:
        calls.append("monomers")
        return {"n": 1}

    @wf.task
    async def pack() -> dict[str, int]:
        calls.append("pack")
        return {"n": 1}

    @wf.task(depends_on=["monomers", "pack"])
    async def equilibrate(n: int) -> dict[str, int]:
        calls.append("equilibrate")
        return {"n": n}

    report = WorkflowRuntime().dry_run((wf).compile())

    assert calls == []
    assert report.name == "pbix"
    assert report.waves[0].tasks == ("monomers", "pack")
    assert report.waves[1].tasks == ("equilibrate",)


class TestReportFromCompiled:
    def test_the_document_carries_waves_tasks_branches_and_runs(self) -> None:
        document = report_from_compiled(
            (_branchy()).compile(),
            experiment={"id": "01HZ", "name": "e", "path": "projects/p/experiments/e"},
            runs=[{"seed": 1}, {"seed": 2}],
        )

        assert document == {
            "experiment": {"id": "01HZ", "name": "e", "path": "projects/p/experiments/e"},
            "workflow": {"name": "pipeline"},
            "waves": [["fetch"], ["validate"], ["publish", "rollback"]],
            "branches": [
                {"source": "validate", "label": "ok", "target": "publish"},
                {"source": "validate", "label": "fail", "target": "rollback"},
            ],
            "runs": [{"params": {"seed": 1}}, {"params": {"seed": 2}}],
            "tasks": [
                {"name": "fetch", "depends_on": []},
                {"name": "validate", "depends_on": ["fetch"]},
                {"name": "publish", "depends_on": ["validate"]},
                {"name": "rollback", "depends_on": ["validate"]},
            ],
        }

    def test_the_document_is_plain_json(self) -> None:
        import json

        document = report_from_compiled(
            (_three_tasks()).compile(), experiment={"id": None, "name": "e"}, runs=[]
        )
        assert json.loads(json.dumps(document)) == document
        assert document["runs"] == []


class TestCompiledForSimulation:
    def test_a_graph_snapshot_walks_like_the_workflow_it_came_from(self) -> None:
        compiled = (_branchy()).compile()
        snapshot = compiled.to_graph_ir().model_dump(mode="json")

        stubbed = compiled_for_simulation(snapshot)

        assert simulate(stubbed) == simulate(compiled)
        assert stubbed.boundary_names == {"fetch", "validate", "publish", "rollback"}

    def test_a_parallel_snapshot_keeps_its_fan_out_order(self) -> None:
        wf = Workflow(name="lp")

        @wf.task
        async def seed() -> list[int]:
            return [1, 2]

        @wf.task
        async def body() -> int:
            return 1

        @wf.task
        async def join() -> int:
            return 1

        wf.parallel(map_over="seed", body="body", join="join", max_concurrency=2)
        compiled = (wf).compile()

        stubbed = compiled_for_simulation(compiled.to_graph_ir().model_dump(mode="json"))

        assert [w.tasks for w in simulate(stubbed).waves] == [("seed",), ("body",), ("join",)]

    def test_a_wire_ir_compiles_through_the_codec(self) -> None:
        if not default_registry.has(ECHO_TASK_TYPE):
            default_registry.register(ECHO_TASK_TYPE, lambda config: _Echo(config))
        document = {
            "name": "ui-doc",
            "task_configs": [
                {"task_id": "a", "task_type": ECHO_TASK_TYPE, "config": {}},
                {"task_id": "b", "task_type": ECHO_TASK_TYPE, "config": {}},
            ],
            "links": [{"source": "a", "target": "b", "kind": "data"}],
        }

        compiled = compiled_for_simulation(document)

        assert [w.tasks for w in simulate(compiled).waves] == [("a",), ("b",)]

    def test_an_unregistered_task_type_is_a_value_error(self) -> None:
        document = {
            "name": "ui-doc",
            "task_configs": [{"task_id": "a", "task_type": "dry_run_nope", "config": {}}],
            "links": [],
        }
        with pytest.raises(ValueError, match="dry_run_nope"):
            compiled_for_simulation(document)

    def test_an_unknown_dependency_does_not_compile(self) -> None:
        snapshot = (_three_tasks()).compile().to_graph_ir().model_dump(mode="json")
        snapshot["tasks"][0]["depends_on"] = ["ghost"]
        with pytest.raises(WorkflowError, match="ghost"):
            compiled_for_simulation(snapshot)

    def test_a_malformed_document_is_a_value_error(self) -> None:
        with pytest.raises(ValueError, match="malformed"):
            compiled_for_simulation({"name": "g", "tasks": [{"task_id": "t"}], "edges": []})
        with pytest.raises(ValueError, match="not a workflow document"):
            compiled_for_simulation({"name": "g"})
