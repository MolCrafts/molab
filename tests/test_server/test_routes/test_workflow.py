"""Workflow-document route HTTP contracts (the free-layout canvas write-back)."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from molab.workflow import (
    Task,
    TaskContext,
    Workflow,
    WorkflowCompiler,
    compiled_workflow_for_run,
    default_binding_registry,
)
from molab.workspace import Experiment, Run, Workspace

ServedFactory = Callable[..., TestClient]
RunFixture = tuple[Workspace, Experiment, Run]


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
    **DOC_A,
    "links": [
        *DOC_A["links"],
        {"source": "ghost", "target": "c", "mapping": {}, "status": "pending"},
    ],
}
GRAPH = {"name": "g", "tasks": [{"task_id": "t", "task_type": "core.constant"}], "edges": []}


def _workflow_url(exp: Experiment) -> str:
    return f"/api/projects/{exp.project.id}/experiments/{exp.id}/workflow"


def _reload(ws: Workspace, exp: Experiment) -> Experiment:
    return Workspace(ws.root).get_project(exp.project.id).get_experiment(exp.id)


def _compiled():
    class Step(Task):
        async def execute(self, ctx: TaskContext) -> int:
            return 1

    return WorkflowCompiler().compile(Workflow(name="memo").add(Step(), name="step"))


class TestPutWorkflowDocument:
    """``put_workflow_document``: validate, normalize, persist an IR document."""

    def test_put_then_get_round_trips(
        self,
        served: ServedFactory,
        fresh_run: RunFixture,
        echo_document: dict[str, object],
    ) -> None:
        ws, exp, _run = fresh_run
        with served(ws) as client:
            put = client.put(_workflow_url(exp), json={"document": echo_document})
            got = client.get(_workflow_url(exp))
        assert put.status_code == 200, put.text
        document = put.json()["document"]
        assert [task["task_id"] for task in document["task_configs"]] == ["echo"]
        assert got.status_code == 200, got.text
        assert got.json()["document"] == document

    def test_dangling_link_is_4xx(
        self,
        served: ServedFactory,
        fresh_run: RunFixture,
        echo_document: dict[str, object],
    ) -> None:
        ws, exp, _run = fresh_run
        invalid = dict(echo_document)
        invalid["links"] = [{"source": "ghost", "target": "echo"}]
        with served(ws, raise_server_exceptions=False) as client:
            response = client.put(_workflow_url(exp), json={"document": invalid})
            got = client.get(_workflow_url(exp))
        assert response.status_code == 400, response.text
        assert got.status_code == 404

    def test_invalid_document_is_4xx(
        self,
        served: ServedFactory,
        fresh_run: RunFixture,
        echo_document: dict[str, object],
    ) -> None:
        ws, exp, _run = fresh_run
        invalid = dict(echo_document)
        invalid["task_configs"] = [
            {"task_id": "echo", "task_type": "arch_own_unregistered", "config": {}}
        ]
        with served(ws, raise_server_exceptions=False) as client:
            response = client.put(_workflow_url(exp), json={"document": invalid})
        assert 400 <= response.status_code < 500, response.text

    def test_get_without_document_is_404(
        self, served: ServedFactory, fresh_run: RunFixture
    ) -> None:
        ws, exp, _run = fresh_run
        with served(ws) as client:
            response = client.get(_workflow_url(exp))
        assert response.status_code == 404

    def test_document_is_recoverable_and_runs(
        self,
        served: ServedFactory,
        fresh_run: RunFixture,
        echo_document: dict[str, object],
    ) -> None:
        ws, exp, _run = fresh_run
        with served(ws) as client:
            put = client.put(_workflow_url(exp), json={"document": echo_document})
        assert put.status_code == 200, put.text
        # The route binds nothing in-process, so recovery here sees exactly
        # what a fresh worker process would.
        exp = _reload(ws, exp)
        run = exp.add_run(params={"x": 2})
        compiled = compiled_workflow_for_run(run)
        assert set(compiled.registration_by_name) == {"echo"}
        assert run.execute(compiled).status == "succeeded"

    def test_put_document_revisions(self, served: ServedFactory, fresh_run: RunFixture) -> None:
        ws, exp, _run = fresh_run
        with served(ws) as client:
            first = client.put(_workflow_url(exp), json={"document": DOC_A})
        assert first.status_code == 200, first.text
        bound = _reload(ws, exp)
        assert bound.workflow_kind == "document"
        assert bound.metadata.revision == 1
        revision_id = bound.metadata.revision_id
        with served(ws) as client:
            again = client.put(_workflow_url(exp), json={"document": DOC_A})
        assert again.status_code == 200, again.text
        same = _reload(ws, exp)
        assert same.metadata.revision_id == revision_id
        with served(ws) as client:
            changed = client.put(_workflow_url(exp), json={"document": DOC_B})
        assert changed.status_code == 200, changed.text
        revised = _reload(ws, exp)
        assert revised.metadata.revision == 2
        assert revised.metadata.revision_id != revision_id

    def test_code_put_without_flag_is_409(
        self, served: ServedFactory, fresh_run: RunFixture
    ) -> None:
        ws, exp, _run = fresh_run
        exp.bind_workflow("code", entrypoint="train.py:build", document=GRAPH)
        entity = (exp.experiment_dir / "experiment.json").read_bytes()
        ir = (exp.experiment_dir / "workflow.ir.json").read_bytes()
        with served(ws, raise_server_exceptions=False) as client:
            response = client.put(_workflow_url(exp), json={"document": DOC_A})
        assert response.status_code == 409, response.text
        assert response.json()["error"]["details"]["workflow_kind"] == "code"
        assert (exp.experiment_dir / "experiment.json").read_bytes() == entity
        assert (exp.experiment_dir / "workflow.ir.json").read_bytes() == ir

    def test_code_put_convert_to_document(
        self, served: ServedFactory, fresh_run: RunFixture
    ) -> None:
        ws, exp, _run = fresh_run
        exp.bind_workflow("code", entrypoint="train.py:build", document=GRAPH)
        with served(ws) as client:
            response = client.put(
                _workflow_url(exp),
                json={"document": DOC_A, "convertToDocument": True},
            )
        assert response.status_code == 200, response.text
        bound = _reload(ws, exp)
        assert bound.workflow_kind == "document"
        assert bound.metadata.workflow_entrypoint is None
        assert bound.metadata.revision == 2

    def test_legacy_put_is_409_even_with_convert(
        self, served: ServedFactory, fresh_run: RunFixture
    ) -> None:
        ws, exp, _run = fresh_run
        exp.metadata = exp.metadata.model_copy(update={"workflow_entrypoint": "wf.py:build"})
        exp.save()
        entity = (exp.experiment_dir / "experiment.json").read_bytes()
        with served(ws, raise_server_exceptions=False) as client:
            plain = client.put(_workflow_url(exp), json={"document": DOC_A})
            converted = client.put(
                _workflow_url(exp),
                json={"document": DOC_A, "convertToDocument": True},
            )
        assert plain.status_code == 409, plain.text
        assert "molab migrate workflow-kind" in plain.json()["error"]["message"]
        assert converted.status_code == 409, converted.text
        assert (exp.experiment_dir / "experiment.json").read_bytes() == entity
        assert _reload(ws, exp).workflow_kind is None

    def test_bad_doc_is_400_and_writes_nothing(
        self, served: ServedFactory, fresh_run: RunFixture
    ) -> None:
        ws, exp, _run = fresh_run
        entity = (exp.experiment_dir / "experiment.json").read_bytes()
        with served(ws, raise_server_exceptions=False) as client:
            response = client.put(_workflow_url(exp), json={"document": BAD_DOC})
        assert response.status_code == 400, response.text
        assert (exp.experiment_dir / "experiment.json").read_bytes() == entity
        assert _reload(ws, exp).workflow_kind is None

    def test_put_clears_binding_memo(self, served: ServedFactory, fresh_run: RunFixture) -> None:
        ws, exp, _run = fresh_run
        default_binding_registry.clear()
        default_binding_registry.bind(exp, _compiled())
        with served(ws) as client:
            response = client.put(_workflow_url(exp), json={"document": DOC_A})
        assert response.status_code == 200, response.text
        assert default_binding_registry.for_experiment(exp) is None

    def test_resave_after_task_code_edit_keeps_document_bytes(
        self,
        served: ServedFactory,
        fresh_run: RunFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The same IR document stays byte-identical after the task body changes."""
        from molab.workflow.codec import default_codec
        from molab.workflow.registry import default_registry

        class StepV1(Task):
            def __init__(self, value: int = 0) -> None:
                self.value = value

            async def execute(self, ctx: TaskContext) -> int:
                return self.value

        class StepV2(Task):
            def __init__(self, value: int = 0) -> None:
                self.value = value

            async def execute(self, ctx: TaskContext) -> int:
                return self.value + 1

        slug = "test.identity_step"
        document = {
            "name": "d",
            "task_configs": [
                {"task_id": "s", "task_type": slug, "config": {"value": 1}},
            ],
            "links": [],
            "metadata": {"label": None, "description": None, "tags": [], "custom": {}},
        }
        ws, exp, _run = fresh_run
        monkeypatch.delitem(default_registry._factories, slug, raising=False)
        try:
            default_registry.register(slug, StepV1)
            with served(ws) as client:
                first = client.put(_workflow_url(exp), json={"document": document})
            assert first.status_code == 200, first.text
            bound = _reload(ws, exp)
            raw = (bound.experiment_dir / "workflow.ir.json").read_bytes()
            revision = bound.metadata.revision
            revision_id = bound.metadata.revision_id
            digest_v1 = default_codec.ir_to_spec(document).workflow_digest
            del default_registry._factories[slug]
            default_registry.register(slug, StepV2)
            assert default_codec.ir_to_spec(document).workflow_digest != digest_v1
            with served(ws) as client:
                second = client.put(_workflow_url(exp), json={"document": document})
            assert second.status_code == 200, second.text
            again = _reload(ws, exp)
            assert (again.experiment_dir / "workflow.ir.json").read_bytes() == raw
            assert again.metadata.revision == revision
            assert again.metadata.revision_id == revision_id
        finally:
            default_registry._factories.pop(slug, None)


class TestGetWorkflowDocument:
    def test_document_binding_returns_the_ir(self, served, fresh_run) -> None:
        ws, exp, _run = fresh_run
        exp.bind_workflow(
            "document",
            document={
                "name": "demo",
                "task_configs": [{"task_id": "prep", "task_type": "demo.prep"}],
                "links": [],
            },
        )
        with served(ws) as client:
            response = client.get(_workflow_url(exp))
        assert response.status_code == 200, response.text
        assert response.json()["document"] == {
            "name": "demo",
            "task_configs": [{"task_id": "prep", "task_type": "demo.prep"}],
            "links": [],
        }

    def test_unbound_is_404(self, served, fresh_run) -> None:
        ws, exp, _run = fresh_run
        with served(ws) as client:
            response = client.get(_workflow_url(exp))
        assert response.status_code == 404

    def test_legacy_workflow_json_is_404(self, served, fresh_run) -> None:
        ws, exp, _run = fresh_run
        (exp.experiment_dir / "workflow.json").write_text("{}", encoding="utf-8")
        with served(ws) as client:
            response = client.get(_workflow_url(exp))
        assert response.status_code == 404
