"""Workflow-document route HTTP contracts (the free-layout canvas write-back)."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from molab.workflow import WorkflowRecoveryError, compiled_workflow_for_run, execute_run
from molab.workspace import Experiment, Run, Workspace

ServedFactory = Callable[..., TestClient]
RunFixture = tuple[Workspace, Experiment, Run]


def _workflow_url(exp: Experiment) -> str:
    return f"/api/projects/{exp.project.id}/experiments/{exp.id}/workflow"


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

    @pytest.mark.xfail(
        strict=True,
        raises=AssertionError,
        reason=(
            "arch-own-04: PUT …/workflow — an unregistered task_type is a 4xx "
            "validation error, not a 500"
        ),
    )
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

    @pytest.mark.xfail(
        strict=True,
        raises=WorkflowRecoveryError,
        reason=(
            "arch-own-04: compiled_workflow_for_run after PUT …/workflow — a "
            "UI-authored document is decoded into the run's compiled workflow"
        ),
    )
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
        run = exp.add_run(params={"x": 2})
        compiled = compiled_workflow_for_run(run)
        assert set(compiled.registration_by_name) == {"echo"}
        assert execute_run(compiled, run).status == "succeeded"
