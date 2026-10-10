"""Public-API goldens for arch-own-04c-resolve.

Kind-dispatched resolution: a document experiment runs from workflow.ir.json
with the memo cleared, a package-root code locator loads under its own name
without writing ``__pycache__``, and an unbound experiment names
``molab migrate workflow-kind``.

Expected stdout (exactly this line, exit code 0):

    arch-own-04c-resolve: ok
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from molab.workflow import (
    WorkflowRecoveryError,
    can_recover_workflow,
    compiled_workflow_for_experiment,
    compiled_workflow_for_run,
    default_binding_registry,
)
from molab.workflow.execute import execute_run
from molab.workspace import Workspace

_IR = {
    "name": "constant_add",
    "task_configs": [
        {"task_id": "a", "task_type": "core.constant", "config": {"value": 2}, "status": "pending"},
        {"task_id": "b", "task_type": "core.constant", "config": {"value": 3}, "status": "pending"},
        {"task_id": "c", "task_type": "core.add", "config": {}, "status": "pending"},
    ],
    "links": [
        {"source": "a", "target": "c", "mapping": {}, "status": "pending"},
        {"source": "b", "target": "c", "mapping": {}, "status": "pending"},
    ],
    "metadata": {"label": None, "description": None, "tags": [], "custom": {}},
}


def main() -> None:
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        ws = Workspace(tmp / "ws", name="ws")
        exp = ws.add_project("p").add_experiment("calc")
        exp.bind_workflow("document", document=_IR)
        before = (exp.experiment_dir / "experiment.json").read_bytes()
        run = exp.add_run(params={"seed": 1})
        default_binding_registry.clear()

        assert can_recover_workflow(run) is True
        compiled = compiled_workflow_for_run(run)
        assert sorted(compiled.registration_by_name) == ["a", "b", "c"]
        assert execute_run(compiled, run).outputs["c"] == 5.0
        assert (exp.experiment_dir / "experiment.json").read_bytes() == before

        run2 = exp.add_run(params={"seed": 2})
        run2.execute()
        assert run2.executions[-1].status.value == "succeeded"

        package = tmp / "wfpkg" / "workflow"
        package.mkdir(parents=True)
        (package / "step.py").write_text('NAME = "pkg-demo"\n', encoding="utf-8")
        (package / "__init__.py").write_text(
            "from workflow.step import NAME\n"
            "from molab.workflow import Workflow\n"
            "\n"
            "def build_workflow():\n"
            "    return Workflow(name=NAME)\n",
            encoding="utf-8",
        )
        exp2 = ws.add_project("p2").add_experiment("code")
        exp2.bind_workflow("code", entrypoint=f"{package}:build_workflow")
        assert compiled_workflow_for_experiment(exp2).name == "pkg-demo"
        assert list((tmp / "wfpkg").rglob("__pycache__")) == []

        bare = ws.add_project("p3").add_experiment("bare").add_run(params={"seed": 0})
        try:
            compiled_workflow_for_run(bare)
        except WorkflowRecoveryError as exc:
            message = str(exc)
        else:
            raise AssertionError("compiled_workflow_for_run did not raise")
        assert "molab migrate workflow-kind" in message, message

    print("arch-own-04c-resolve: ok")


if __name__ == "__main__":
    main()
