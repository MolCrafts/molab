"""POST /api/projects/{id}/experiments workflow-source binding."""

from __future__ import annotations

from pathlib import Path

from molab.workspace import Workspace

DOC_A = {
    "workflow_id": "workflow_00000000",
    "name": "constant_add",
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
            "config": {"value": 3},
            "status": "pending",
        },
        {
            "task_id": "c",
            "task_type": "core.add",
            "config": {},
            "status": "pending",
        },
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
        {
            "task_id": "c",
            "task_type": "core.add",
            "config": {},
            "status": "pending",
        },
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
        {
            "task_id": "a",
            "task_type": "core.constant",
            "config": {"value": 2},
            "status": "pending",
        },
        {
            "task_id": "b",
            "task_type": "core.constant",
            "config": {"value": 3},
            "status": "pending",
        },
        {
            "task_id": "c",
            "task_type": "core.add",
            "config": {},
            "status": "pending",
        },
    ],
    "links": [
        {"source": "a", "target": "c", "mapping": {}, "status": "pending"},
        {"source": "b", "target": "c", "mapping": {}, "status": "pending"},
        {"source": "ghost", "target": "c", "mapping": {}, "status": "pending"},
    ],
    "metadata": {"label": None, "description": None, "tags": [], "custom": {}},
}

_CODE_DOCUMENT = {
    "name": "g",
    "tasks": [{"task_id": "t", "task_type": "core.constant"}],
    "edges": [],
}


def _collection_url(project_id: str) -> str:
    return f"/api/projects/{project_id}/experiments"


def _open_experiment(ws, project_id: str, key: str):
    return Workspace(ws.root).get_project(project_id).get_experiment(key)


def _entity_bytes(experiment_dir: Path) -> tuple[bytes, bytes | None]:
    ir_path = experiment_dir / "workflow.ir.json"
    ir_bytes = ir_path.read_bytes() if ir_path.is_file() else None
    return (experiment_dir / "experiment.json").read_bytes(), ir_bytes


def _stamp_legacy(exp) -> None:
    exp.metadata = exp.metadata.model_copy(update={"workflow_entrypoint": "wf.py:build"})
    exp.save()


class TestCreateExperiment:
    def test_document_source_binds_kind_and_returns_workflow(self, fresh_run, served) -> None:
        ws, exp, _run = fresh_run
        with served(ws, raise_server_exceptions=False) as client:
            response = client.post(
                _collection_url(exp.project.id),
                json={"name": "doc", "workflowSource": DOC_A},
            )
        assert response.status_code == 201, response.text
        assert response.json()["workflow"]
        reloaded = _open_experiment(ws, exp.project.id, "doc")
        assert reloaded.workflow_kind == "document"
        assert reloaded.metadata.revision == 1

    def test_yaml_path_workflow_source_is_422(self, fresh_run, served) -> None:
        ws, exp, _run = fresh_run
        with served(ws, raise_server_exceptions=False) as client:
            response = client.post(
                _collection_url(exp.project.id),
                json={"name": "yaml", "workflowSource": "path/to/workflow.yaml"},
            )
        assert response.status_code == 422, response.text

    def test_invalid_document_is_400_and_not_persisted(self, fresh_run, served) -> None:
        ws, exp, _run = fresh_run
        with served(ws, raise_server_exceptions=False) as client:
            response = client.post(
                _collection_url(exp.project.id),
                json={"name": "bad", "workflowSource": BAD_DOC},
            )
        assert response.status_code == 400, response.text
        project = Workspace(ws.root).get_project(exp.project.id)
        assert project.has_experiment("bad") is False

    def test_missing_workflow_source_leaves_kind_unset(self, fresh_run, served) -> None:
        ws, exp, _run = fresh_run
        with served(ws, raise_server_exceptions=False) as client:
            response = client.post(
                _collection_url(exp.project.id),
                json={"name": "plain"},
            )
        assert response.status_code == 201, response.text
        reloaded = _open_experiment(ws, exp.project.id, "plain")
        assert reloaded.workflow_kind is None

    def test_legacy_entrypoint_with_document_source_is_409(self, fresh_run, served) -> None:
        ws, exp, _run = fresh_run
        _stamp_legacy(exp)
        with served(ws, raise_server_exceptions=False) as client:
            response = client.post(
                _collection_url(exp.project.id),
                json={"name": "e", "workflowSource": DOC_A},
            )
        assert response.status_code == 409, response.text

    def test_legacy_entrypoint_without_source_is_idempotent_201(self, fresh_run, served) -> None:
        ws, exp, _run = fresh_run
        _stamp_legacy(exp)
        with served(ws, raise_server_exceptions=False) as client:
            response = client.post(
                _collection_url(exp.project.id),
                json={"name": "e"},
            )
        assert response.status_code == 201, response.text

    def test_same_document_on_bound_experiment_keeps_revision_and_bytes(
        self, fresh_run, served
    ) -> None:
        ws, exp, _run = fresh_run
        bound = exp.project.add_experiment(name="bound", workflow_document=DOC_A)
        before_json = (bound.experiment_dir / "experiment.json").read_bytes()
        with served(ws, raise_server_exceptions=False) as client:
            response = client.post(
                _collection_url(exp.project.id),
                json={"name": "bound", "workflowSource": DOC_A},
            )
        assert response.status_code == 201, response.text
        reloaded = _open_experiment(ws, exp.project.id, "bound")
        assert reloaded.metadata.revision == 1
        assert (reloaded.experiment_dir / "experiment.json").read_bytes() == before_json

    def test_different_document_on_bound_experiment_is_409(self, fresh_run, served) -> None:
        ws, exp, _run = fresh_run
        bound = exp.project.add_experiment(name="bound", workflow_document=DOC_A)
        before = _entity_bytes(bound.experiment_dir)
        with served(ws, raise_server_exceptions=False) as client:
            response = client.post(
                _collection_url(exp.project.id),
                json={"name": "bound", "workflowSource": DOC_B},
            )
        assert response.status_code == 409, response.text
        assert response.json()["error"]["details"]["workflow_kind"] == "document"
        reloaded = _open_experiment(ws, exp.project.id, "bound")
        assert _entity_bytes(reloaded.experiment_dir) == before

    def test_document_source_on_existing_unbound_name_is_409(self, fresh_run, served) -> None:
        ws, exp, _run = fresh_run
        before = _entity_bytes(exp.experiment_dir)
        with served(ws, raise_server_exceptions=False) as client:
            response = client.post(
                _collection_url(exp.project.id),
                json={"name": "e", "workflowSource": DOC_A},
            )
        assert response.status_code == 409, response.text
        reloaded = _open_experiment(ws, exp.project.id, "e")
        assert reloaded.workflow_kind is None
        assert _entity_bytes(reloaded.experiment_dir) == before

    def test_document_source_on_code_experiment_is_409(self, fresh_run, served) -> None:
        ws, exp, _run = fresh_run
        exp.bind_workflow(
            "code",
            entrypoint="train.py:build",
            document=_CODE_DOCUMENT,
        )
        before = _entity_bytes(exp.experiment_dir)
        with served(ws, raise_server_exceptions=False) as client:
            response = client.post(
                _collection_url(exp.project.id),
                json={"name": "e", "workflowSource": DOC_A},
            )
        assert response.status_code == 409, response.text
        reloaded = _open_experiment(ws, exp.project.id, "e")
        assert reloaded.workflow_kind == "code"
        assert _entity_bytes(reloaded.experiment_dir) == before
