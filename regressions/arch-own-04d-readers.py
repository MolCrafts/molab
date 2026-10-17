"""Public-API goldens for arch-own-04d-readers.

This spec deletes the legacy experiment fields ``workflow_source``,
``workflow_type`` and ``git_commit``. An old workspace must run arch-own-04b's
``molab migrate workflow-kind`` first. That command classifies each experiment
and reports how many unbound experiments carried a non-IR ``workflow_source``
that this upgrade drops. Step 5 shows that drop: a handwritten
``workflow_source`` is ignored on load.

Expected stdout (exactly this line, exit code 0):

    arch-own-04d-readers: ok
"""

from __future__ import annotations

import inspect
import json
import tempfile
from pathlib import Path

from molab.server.schemas.responses import ExperimentResponse, RunResponse
from molab.workspace import Workspace
from molab.workspace.models import ExperimentMetadata

IR = {
    "name": "demo",
    "task_configs": [{"task_id": "prep", "task_type": "demo.prep"}],
    "links": [],
}
IR_JSON = (
    '{"links": [], "name": "demo", "task_configs": [{"task_id": "prep", "task_type": "demo.prep"}]}'
)


def main() -> None:
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        ws = Workspace(tmp / "ws", name="ws")
        project = ws.add_project("p")
        exp = project.add_experiment("calc")
        exp.bind_workflow("document", document=IR)
        loaded = Workspace(ws.root).get_project("p").get_experiment("calc")
        assert loaded.workflow_kind == "document"
        assert loaded.workflow_document == IR

        response = ExperimentResponse.from_model(loaded)
        assert response.workflowKind == "document"
        assert response.workflow == IR_JSON

        run = loaded.add_run(params={"seed": 1})
        run_body = RunResponse.from_model(run)
        assert run_body.workflow is not None
        assert run_body.workflow.source == "workflow.ir.json"
        assert run_body.workflow.gitCommit is None
        assert run_body.workflowSource == IR_JSON

        project.set_experiment("calc", description="x")
        after = Workspace(ws.root).get_project("p").get_experiment("calc")
        assert after.workflow_document == IR
        assert (Path(after.experiment_dir) / "workflow.ir.json").is_file()

        legacy = project.add_experiment("old")
        path = Path(legacy.experiment_dir) / "experiment.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["workflow_source"] = "train.py"
        path.write_text(json.dumps(payload), encoding="utf-8")
        (Path(legacy.experiment_dir) / "workflow.json").write_text(json.dumps(IR), encoding="utf-8")
        stale = Workspace(ws.root).get_project("p").get_experiment("old")
        assert stale.workflow_kind is None
        assert stale.workflow_document is None
        assert "workflow_source" not in stale.metadata.model_dump()

        banned = {"workflow_source", "workflow_type", "git_commit"}
        assert banned.isdisjoint(ExperimentMetadata.model_fields)
        assert banned.isdisjoint(inspect.signature(type(project).add_experiment).parameters)

    print("arch-own-04d-readers: ok")


if __name__ == "__main__":
    main()
