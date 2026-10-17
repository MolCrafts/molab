"""Public-API regression for experiment workflow writers."""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient
from typer.testing import CliRunner

import molab.entry  # noqa: F401  (registers Experiment.define)
from molab.cli import app
from molab.server.app import create_app
from molab.server.dependencies import reset_workspace_cache, set_workspace_path_override
from molab.workflow import Task, TaskContext, Workflow, WorkflowCompiler
from molab.workspace import Workspace

DOC_A = {
    "workflow_id": "workflow_00000000",
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


def _doc_b() -> dict:
    document = {
        "workflow_id": DOC_A["workflow_id"],
        "name": DOC_A["name"],
        "task_configs": [
            {
                "task_id": "a",
                "task_type": "core.constant",
                "config": {"value": 2},
                "status": "pending",
            },
            {
                "task_id": "b",
                "task_type": "core.constant",
                "config": {"value": 4},
                "status": "pending",
            },
            {"task_id": "c", "task_type": "core.add", "config": {}, "status": "pending"},
        ],
        "links": list(DOC_A["links"]),
        "metadata": dict(DOC_A["metadata"]),
    }
    return document


def _bad() -> dict:
    document = _doc_b()
    document["task_configs"][1]["config"] = {"value": 3}
    document["links"] = [
        *DOC_A["links"],
        {"source": "ghost", "target": "c", "mapping": {}, "status": "pending"},
    ]
    return document


class _Step(Task):
    async def execute(self, _ctx: TaskContext) -> int:
        return 1


def _compiled() -> object:
    return WorkflowCompiler().compile(Workflow(name="wf").add(_Step(), name="step"))


def _check(cond: bool, message: str) -> None:
    if not cond:
        raise SystemExit(message)


def main() -> None:
    doc_b = _doc_b()
    bad = _bad()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "lab"
        ws = Workspace(root, name="lab")
        ws.materialize()
        project = ws.add_project("p")
        set_workspace_path_override(Path(str(ws.root)))
        try:
            with TestClient(create_app(serve_static=False)) as client:
                created = client.post(
                    f"/api/projects/{project.id}/experiments",
                    json={"name": "doc", "workflowSource": DOC_A},
                )
                _check(
                    created.status_code == 201, f"create doc {created.status_code} {created.text}"
                )
                doc = Workspace.load(root).get_project("p").get_experiment("doc")
                _check(doc.workflow_kind == "document", "doc kind")
                _check(doc.metadata.revision == 1, "doc rev")

                rejected = client.post(
                    f"/api/projects/{project.id}/experiments",
                    json={"name": "path", "workflowSource": "path/to/workflow.yaml"},
                )
                _check(rejected.status_code == 422, f"string {rejected.status_code}")

                invalid = client.post(
                    f"/api/projects/{project.id}/experiments",
                    json={"name": "bad", "workflowSource": bad},
                )
                _check(invalid.status_code == 400, f"bad {invalid.status_code} {invalid.text}")
                _check(
                    Workspace.load(root).get_project("p").has_experiment("bad") is False,
                    "bad dir exists",
                )

                clash = client.post(
                    f"/api/projects/{project.id}/experiments",
                    json={"name": "doc", "workflowSource": doc_b},
                )
                _check(clash.status_code == 409, f"clash {clash.status_code} {clash.text}")
                doc = Workspace.load(root).get_project("p").get_experiment("doc")
                _check(doc.metadata.revision == 1, "clash rev")

                url = f"/api/projects/{project.id}/experiments/{doc.id}/workflow"
                same = client.put(url, json={"document": DOC_A})
                _check(same.status_code == 200, f"put same {same.status_code} {same.text}")
                doc = Workspace.load(root).get_project("p").get_experiment("doc")
                _check(doc.metadata.revision == 1, "put same rev")
                changed = client.put(url, json={"document": doc_b})
                _check(changed.status_code == 200, f"put b {changed.status_code} {changed.text}")
                doc = Workspace.load(root).get_project("p").get_experiment("doc")
                _check(doc.metadata.revision == 2, f"put b rev {doc.metadata.revision}")

                code = Workspace.load(root).get_project("p").add_experiment("code")
                code.define(_compiled())
                _check(code.workflow_kind == "code" and code.metadata.revision == 1, "define")
                code_url = f"/api/projects/{project.id}/experiments/{code.id}/workflow"
                denied = client.put(code_url, json={"document": DOC_A})
                _check(denied.status_code == 409, f"code put {denied.status_code} {denied.text}")
                converted = client.put(
                    code_url, json={"document": DOC_A, "convertToDocument": True}
                )
                _check(
                    converted.status_code == 200,
                    f"convert {converted.status_code} {converted.text}",
                )
                code = Workspace.load(root).get_project("p").get_experiment("code")
                _check(code.workflow_kind == "document", "converted kind")
                _check(code.metadata.revision == 2, "converted rev")
                _check(code.metadata.workflow_entrypoint is None, "converted entry")

                bare = Workspace.load(root).get_project("p").add_experiment("bare")
                posted = client.post(
                    "/api/runs",
                    json={
                        "projectId": project.id,
                        "experimentId": bare.id,
                        "workflowJson": DOC_A,
                    },
                )
                _check(posted.status_code == 201, f"run {posted.status_code} {posted.text}")
                bare = Workspace.load(root).get_project("p").get_experiment("bare")
                _check(
                    bare.workflow_kind == "document" and bare.metadata.revision == 1, "bare bind"
                )
                runs = bare.list_runs()
                _check(len(runs) == 1, "bare runs")
                _check(
                    runs[0].metadata.experiment_revision_id == bare.metadata.revision_id,
                    "run revision",
                )
                differ = client.post(
                    "/api/runs",
                    json={
                        "projectId": project.id,
                        "experimentId": bare.id,
                        "workflowJson": doc_b,
                    },
                )
                _check(differ.status_code == 409, f"run differ {differ.status_code} {differ.text}")

                legacy = Workspace.load(root).get_project("p").add_experiment("legacy")
                legacy.metadata = legacy.metadata.model_copy(
                    update={"workflow_entrypoint": "wf.py:build"}
                )
                legacy.save()
                legacy_url = f"/api/projects/{project.id}/experiments/{legacy.id}/workflow"
                blocked = client.put(legacy_url, json={"document": DOC_A})
                message = blocked.json().get("error", {}).get("message", "")
                _check(blocked.status_code == 409, f"legacy {blocked.status_code} {blocked.text}")
                _check("molab migrate workflow-kind" in message, message)

                result = CliRunner().invoke(app, ["migrate", "workflow-kind", str(root)])
                _check(
                    result.exit_code == 0,
                    f"migrate {result.exit_code} {result.stdout} {result.stderr}",
                )
                legacy = Workspace.load(root).get_project("p").get_experiment("legacy")
                _check(legacy.workflow_kind == "code", f"migrated {legacy.workflow_kind}")
                _check(legacy.metadata.revision == 1, "migrated rev")
                reset_workspace_cache()
                after = client.put(legacy_url, json={"document": DOC_A, "convertToDocument": True})
                _check(after.status_code == 200, f"after {after.status_code} {after.text}")
                legacy = Workspace.load(root).get_project("p").get_experiment("legacy")
                _check(legacy.metadata.revision == 2, f"after rev {legacy.metadata.revision}")
        finally:
            set_workspace_path_override(None)
    print("arch-own-04b-writers: ok")


if __name__ == "__main__":
    main()
