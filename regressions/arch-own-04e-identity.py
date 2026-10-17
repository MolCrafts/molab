"""Identity after arch-own-04e.

Documents bound raw by 04b `molab migrate workflow-kind` still carry workflow_id,
so their one revision bump lands at the first PUT after this spec.

Golden (captured, not recomputed): ``compute_run_definition_hash`` still inserts
the frozen key ``workflow_snapshot: None``. Provenance: arch-own-04e-identity
spec, 2026-10-01, literal
sha256:30119ce961ee6a1797296eea0ce32d1509d4a93b4b2adfe3af8ff56888001fad.
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path

from molab.workflow import (
    CompiledWorkflow,
    Task,
    TaskContext,
    TaskTypeRegistry,
    Workflow,
    WorkflowBindingRegistry,
    WorkflowCompiler,
)
from molab.workspace import Workspace
from molab.workspace.run import compute_run_definition_hash

_GOLDEN = "sha256:30119ce961ee6a1797296eea0ce32d1509d4a93b4b2adfe3af8ff56888001fad"
_RETIRED = ("workflow_snapshot", "workflow_id", "workflow_version")
_DOC: dict[str, object] = {
    "name": "d",
    "task_configs": [
        {"task_id": "s", "task_type": "test.step", "config": {"value": 1}},
    ],
    "links": [],
    "metadata": {},
}


def _alpha() -> str:
    return "alpha"


def _beta() -> str:
    return "beta"


def _compile_ordered(name: str, order: tuple[str, ...]) -> CompiledWorkflow:
    bodies = {"alpha": _alpha, "beta": _beta}
    wf = Workflow(name=name)
    for task_name in order:
        wf.task(bodies[task_name])
    return WorkflowCompiler().compile(wf)


class _StepA(Task):
    def __init__(self, value: int) -> None:
        self.value = value

    async def execute(self, ctx: TaskContext) -> int:
        _ = ctx
        return self.value


class _StepB(Task):
    def __init__(self, value: int) -> None:
        self.value = value

    async def execute(self, ctx: TaskContext) -> int:
        _ = ctx
        return self.value + 1


class _Exp:
    """Duck-typed experiment (``.id`` only), as in ``test_compiler.py``."""

    def __init__(self, exp_id: str) -> None:
        self.id = exp_id


def _compile_document(cls: type[Task]) -> CompiledWorkflow:
    registry = TaskTypeRegistry()
    registry.register("test.step", cls)
    return CompiledWorkflow.from_ir(_DOC, registry=registry)


def _has_key(blob: object, key: str) -> bool:
    if isinstance(blob, dict):
        return key in blob or any(_has_key(value, key) for value in blob.values())
    if isinstance(blob, list | tuple):
        return any(_has_key(item, key) for item in blob)
    return False


def main() -> None:
    first = _compile_ordered("alpha-wf", ("alpha", "beta"))
    second = _compile_ordered("beta-wf", ("beta", "alpha"))
    assert first.workflow_digest == second.workflow_digest

    compiled_a = _compile_document(_StepA)
    compiled_b = _compile_document(_StepB)
    assert compiled_a.workflow_digest != compiled_b.workflow_digest
    ir_a = json.dumps(compiled_a.to_ir(), sort_keys=True)
    ir_b = json.dumps(compiled_b.to_ir(), sort_keys=True)
    assert ir_a == ir_b
    for compiled in (compiled_a, compiled_b):
        ir = compiled.to_ir()
        graph = compiled.to_graph_ir().model_dump()
        assert not _has_key(ir, "workflow_id")
        assert not _has_key(ir, "workflow_digest")
        assert not _has_key(graph, "workflow_id")
        assert not _has_key(graph, "workflow_digest")

    experiment = _Exp("exp-04e")
    registry = WorkflowBindingRegistry()
    bound_wf = Workflow(name="bound")
    bound_wf.task(_alpha)
    bound = WorkflowCompiler().compile(bound_wf, experiment=experiment, registry=registry)
    binding = bound.binding
    assert binding is not None
    assert binding.workflow_digest == bound.workflow_digest

    assert importlib.util.find_spec("molab.workflow.version") is None

    golden = compute_run_definition_hash(
        experiment_revision_id="rev-golden", parameters={"seed": 1}
    )
    assert golden == _GOLDEN

    with tempfile.TemporaryDirectory() as tmp:
        ws = Workspace(root=Path(tmp), name="lab")
        run = ws.add_project("p").add_experiment("e").add_run(params={"seed": 1})
        path = Path(run.run_dir) / "run.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(document, dict)
        for key in _RETIRED:
            assert key not in document
        before = run.metadata.definition_hash
        document["workflow_snapshot"] = {"git_commit": "zzz"}
        document["workflow_id"] = "wf-old"
        document["workflow_version"] = 3
        path.write_text(json.dumps(document), encoding="utf-8")
        fresh = Workspace(root=ws.root)
        loaded = fresh.get_project("p").get_experiment("e").get_run(run.id)
        assert loaded.metadata.definition_hash == before

    print("arch-own-04e-identity: ok")


if __name__ == "__main__":
    main()
