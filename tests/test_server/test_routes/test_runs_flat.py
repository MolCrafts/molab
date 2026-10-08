"""POST /api/runs — flat workflow-document binding on an experiment."""

from __future__ import annotations

import copy

from molab.workflow import default_binding_registry
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

DOC_B = {
    "workflow_id": "workflow_00000000",
    "name": "constant_add",
    "task_configs": [
        {"task_id": "a", "task_type": "core.constant", "config": {"value": 2}, "status": "pending"},
        {"task_id": "b", "task_type": "core.constant", "config": {"value": 4}, "status": "pending"},
        {"task_id": "c", "task_type": "core.add", "config": {}, "status": "pending"},
    ],
    "links": [
        {"source": "a", "target": "c", "mapping": {}, "status": "pending"},
        {"source": "b", "target": "c", "mapping": {}, "status": "pending"},
    ],
    "metadata": {"label": None, "description": None, "tags": [], "custom": {}},
}

BAD_DOC = {
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
        {"source": "ghost", "target": "c", "mapping": {}, "status": "pending"},
    ],
    "metadata": {"label": None, "description": None, "tags": [], "custom": {}},
}

_CODE_DOC = {
    "name": "g",
    "tasks": [{"task_id": "t", "task_type": "core.constant"}],
    "edges": [],
}


def _reload(ws, exp):
    return Workspace(ws.root).get_project(exp.project.id).get_experiment(exp.id)


def _run_ids(exp) -> list[str]:
    return sorted(str(run.id) for run in exp.list_runs())


def _clear_registry() -> None:
    default_binding_registry.clear()


def _persist_legacy_entrypoint(exp) -> None:
    exp.metadata = exp.metadata.model_copy(update={"workflow_entrypoint": "wf.py:build"})
    exp.save()


def _post_run(served, ws, exp, *, workflow=None, include_workflow: bool = True):
    body: dict = {
        "projectId": str(exp.project.id),
        "experimentId": str(exp.id),
        "params": {},
    }
    if include_workflow:
        body["workflowJson"] = copy.deepcopy(workflow)
    with served(ws, raise_server_exceptions=False) as client:
        return client.post("/api/runs", json=body)


class TestCreateRun:
    def test_unbound_document_sets_revision_and_skips_registry(self, fresh_run, served) -> None:
        ws, exp, _run = fresh_run
        _clear_registry()
        before = _run_ids(exp)
        response = _post_run(served, ws, exp, workflow=DOC_A)
        assert response.status_code == 201
        reloaded = _reload(ws, exp)
        assert reloaded.metadata.workflow_kind == "document"
        assert reloaded.metadata.revision == 1
        created = set(_run_ids(reloaded)) - set(before)
        assert len(created) == 1
        new_run = next(run for run in reloaded.list_runs() if str(run.id) in created)
        assert new_run.metadata.experiment_revision_id == reloaded.metadata.revision_id
        assert default_binding_registry.for_experiment(exp) is None

    def test_same_document_keeps_revision(self, fresh_run, served) -> None:
        ws, exp, _run = fresh_run
        exp.bind_workflow("document", document=copy.deepcopy(DOC_A))
        response = _post_run(served, ws, exp, workflow=DOC_A)
        assert response.status_code == 201
        reloaded = _reload(ws, exp)
        assert reloaded.metadata.revision == 1

    def test_changed_document_is_conflict(self, fresh_run, served) -> None:
        ws, exp, _run = fresh_run
        exp.bind_workflow("document", document=copy.deepcopy(DOC_A))
        before = _run_ids(exp)
        response = _post_run(served, ws, exp, workflow=DOC_B)
        assert response.status_code == 409
        reloaded = _reload(ws, exp)
        assert _run_ids(reloaded) == before
        assert reloaded.metadata.revision == 1

    def test_without_workflow_json_does_not_memoize(self, fresh_run, served) -> None:
        ws, exp, _run = fresh_run
        exp.bind_workflow("document", document=copy.deepcopy(DOC_A))
        _clear_registry()
        response = _post_run(served, ws, exp, include_workflow=False)
        assert response.status_code == 201
        assert default_binding_registry.for_experiment(exp) is None

    def test_code_binding_rejects_document_post(self, fresh_run, served) -> None:
        ws, exp, _run = fresh_run
        exp.bind_workflow(
            "code",
            entrypoint="train.py:build",
            document=copy.deepcopy(_CODE_DOC),
        )
        ir_path = exp.experiment_dir / "workflow.ir.json"
        before_ir = ir_path.read_bytes()
        response = _post_run(served, ws, exp, workflow=DOC_A)
        assert response.status_code == 409
        assert ir_path.read_bytes() == before_ir
        reloaded = _reload(ws, exp)
        assert reloaded.metadata.workflow_kind == "code"
        assert reloaded.metadata.workflow_entrypoint == "train.py:build"

    def test_legacy_entrypoint_rejects_document_post(self, fresh_run, served) -> None:
        ws, exp, _run = fresh_run
        _persist_legacy_entrypoint(exp)
        response = _post_run(served, ws, exp, workflow=DOC_A)
        assert response.status_code == 409
        assert "molab migrate workflow-kind" in response.json()["error"]["message"]
        reloaded = _reload(ws, exp)
        assert reloaded.metadata.workflow_kind is None
        assert reloaded.metadata.workflow_entrypoint == "wf.py:build"

    def test_legacy_entrypoint_without_workflow_json_creates_run(self, fresh_run, served) -> None:
        ws, exp, _run = fresh_run
        _persist_legacy_entrypoint(exp)
        response = _post_run(served, ws, exp, include_workflow=False)
        assert response.status_code == 201

    def test_invalid_document_is_400(self, fresh_run, served) -> None:
        ws, exp, _run = fresh_run
        before = _run_ids(exp)
        response = _post_run(served, ws, exp, workflow=BAD_DOC)
        assert response.status_code == 400
        reloaded = _reload(ws, exp)
        assert _run_ids(reloaded) == before
        assert reloaded.metadata.workflow_kind is None
