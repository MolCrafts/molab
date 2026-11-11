"""Run-route HTTP contracts: executions, assets, and harvest."""

from __future__ import annotations

import inspect
import re
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import ClassVar, get_args

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import molab as me
from molab.knowledge import Report
from molab.server.routes import run as run_routes
from molab.server.schemas.requests import RunHarvestRequest
from molab.workflow import Workflow
from molab.workspace import Experiment, Run, Workspace
from molab.workspace.domain import Asset, ExecutionMode, ExecutionStatus
from molab.workspace.history import AgentRef
from molab.workspace.models import ComputeTarget
from molab.workspace.targets import add_target
from tests.support.records import read_record, write_record

ServedFactory = Callable[..., TestClient]
RunFixture = tuple[Workspace, Experiment, Run]


def _prose(body: str) -> str:
    """The narrative. Trailing ``- [@…]`` lines are the source edges."""
    lines = body.splitlines()
    while lines and (not lines[-1].strip() or lines[-1].startswith("- [@")):
        lines.pop()
    return "\n".join(lines).strip()


def _run_url(exp: Experiment, run: Run) -> str:
    return f"/api/projects/{exp.project.id}/experiments/{exp.id}/runs/{run.id}"


def _add_hpc_target(ws: Workspace) -> None:
    add_target(
        ws,
        ComputeTarget(name="hpc", registry_id="reg", cluster_id="hpc", scratch_root="/scratch"),
    )


def _emit_metrics(run: Run) -> Asset:
    """Open ``e01``, register ``metrics.json``, and seal it succeeded."""
    with run.start() as ctx:
        asset = ctx.register({"loss": 0.1}, title="metrics.json")
    return asset


def _build_wf() -> Workflow:
    wf = Workflow(name="pipeline")

    @wf.task
    def double(x: int) -> int:
        return x * 2

    @wf.task(depends_on=["double"])
    def summarize(double: int) -> str:
        return f"got {double}"

    return wf


class _DispatchRecorder:
    """Stands in for ``_dispatch_to_molq``; snapshots the record at call time."""

    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[tuple[str, str | None, list[tuple[str, str]]]] = []
        self._error = error

    def __call__(self, target: ComputeTarget, run: Run, execution_id: str | None = None) -> None:
        seen = [(e.id, e.status.value) for e in run.executions]
        self.calls.append((target.name, execution_id, seen))
        if self._error is not None:
            raise self._error


class _SubmitRecorder:
    """Stands in for ``SubmitHandler``: records each submission, submits nothing."""

    calls: ClassVar[list[str | None]] = []

    def __init__(self, **_kwargs: object) -> None:
        pass

    def __call__(
        self,
        script: object,
        run: Run,
        experiment: Experiment,
        project: object,
        *,
        execution_id: str | None = None,
    ) -> None:
        type(self).calls.append(execution_id)


_REAL_DISPATCH = run_routes._dispatch_to_molq


_REAL_START_LOCALLY = run_routes._start_locally


@pytest.fixture(autouse=True)
def dispatched(monkeypatch: pytest.MonkeyPatch) -> _DispatchRecorder:
    """Every created attempt is submitted; record it instead of starting it.

    A local-target attempt is recorded under the target name ``local``.
    """
    recorder = _DispatchRecorder()
    monkeypatch.setattr(run_routes, "_dispatch_to_molq", recorder)

    def start_locally(run, execution_id: str) -> None:
        recorder.calls.append(
            ("local", execution_id, [(e.id, e.status.value) for e in run.executions])
        )

    monkeypatch.setattr(run_routes, "_start_locally", start_locally)
    return recorder


@pytest.fixture
def submit_recorder(monkeypatch: pytest.MonkeyPatch) -> Iterator[type[_SubmitRecorder]]:
    _SubmitRecorder.calls = []
    monkeypatch.setattr(run_routes, "SubmitHandler", _SubmitRecorder)
    yield _SubmitRecorder
    _SubmitRecorder.calls = []


class TestHarvestRunRoute:
    def test_cls_matches_harvest_targets(self) -> None:
        from molab.knowledge.concepts import HARVEST_TARGETS

        field = RunHarvestRequest.model_fields["cls"]
        assert set(get_args(field.annotation)) == set(HARVEST_TARGETS)
        assert "kind" not in RunHarvestRequest.model_fields

    def test_plan_is_not_a_harvest_target(
        self, served: ServedFactory, terminal_run: RunFixture
    ) -> None:
        ws, exp, run = terminal_run
        with served(ws) as client:
            response = client.post(
                f"{_run_url(exp, run)}/harvest",
                json={"cls": "Plan", "narrative": "a plan is not a harvest"},
            )
        assert response.status_code == 422

    def test_note_is_not_a_harvest_target(
        self, served: ServedFactory, terminal_run: RunFixture
    ) -> None:
        ws, exp, run = terminal_run
        with served(ws) as client:
            response = client.post(
                f"{_run_url(exp, run)}/harvest",
                json={"cls": "Note", "narrative": "a note is not a harvest"},
            )
        assert response.status_code == 422

    def test_finding_harvests(self, served: ServedFactory, terminal_run: RunFixture) -> None:
        ws, exp, run = terminal_run
        with served(ws) as client:
            response = client.post(
                f"{_run_url(exp, run)}/harvest",
                json={"cls": "Finding", "narrative": "Tg rose with cooling rate."},
            )
        assert response.status_code == 200, response.text
        assert response.json()["name"]


class TestHarvestRunRouteRedirect:
    """The harvest route parses + writes through ``molab.knowledge``."""

    def test_harvest_imports_knowledge_parse(self) -> None:
        src = inspect.getsource(run_routes.harvest_run_route)
        assert "molab.knowledge" in src
        assert ".harvest(" in src
        assert "molab.workspace.knowledge" not in src
        assert "run.harvest(" not in src


class TestFailureReportIsHarvest:
    def test_there_is_no_analyze_failure_verb(self) -> None:
        assert not hasattr(run_routes, "analyze_run_failure_route")

    def test_a_failed_run_harvests_a_report(
        self, served: ServedFactory, failed_run: RunFixture
    ) -> None:
        ws, exp, run = failed_run
        with served(ws) as client:
            gone = client.post(f"{_run_url(exp, run)}/analyze-failure", json={})
            response = client.post(
                f"{_run_url(exp, run)}/harvest",
                json={"cls": "Report", "narrative": "The box was smaller than the cutoff."},
            )
        assert gone.status_code == 404, gone.text
        assert response.status_code == 200, response.text
        item = next(
            i
            for i in __import__("molab.knowledge", fromlist=["Knowledge"]).Knowledge(ws.root).walk()
            if type(i) is Report
        )
        assert item.path.is_file()
        assert item.path.name == f"report-{run.id}.md"
        assert _prose(item.read()) == "The box was smaller than the cutoff."
        assert "unique-oom-marker" not in item.read()


class TestCancelAndPruneUseTheCores:
    def test_cancel_calls_cancel_run(self) -> None:
        src = inspect.getsource(run_routes.cancel_execution)
        assert "cancel_run" in src
        assert "repo.seal" not in src

    def test_cancel_queued_attempt(self, served: ServedFactory, fresh_run: RunFixture) -> None:
        ws, exp, run = fresh_run
        with served(ws) as client:
            created = client.post(f"{_run_url(exp, run)}/executions", json={})
            assert created.status_code == 201, created.text
            execution_id = created.json()["id"]
            response = client.post(f"{_run_url(exp, run)}/executions/{execution_id}/cancel")
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "cancelled"

    def test_cancel_terminal_attempt_is_409(
        self, served: ServedFactory, terminal_run: RunFixture
    ) -> None:
        ws, exp, run = terminal_run
        with served(ws) as client:
            response = client.post(f"{_run_url(exp, run)}/executions/e01/cancel")
        assert response.status_code == 409

    def test_cancel_missing_attempt_is_404(
        self, served: ServedFactory, fresh_run: RunFixture
    ) -> None:
        ws, exp, run = fresh_run
        with served(ws) as client:
            response = client.post(f"{_run_url(exp, run)}/executions/e99/cancel")
        assert response.status_code == 404

    def test_prune_calls_the_core(self) -> None:
        src = inspect.getsource(run_routes.prune_run_route)
        assert "plan_execution_prune" in src
        assert "apply_execution_prune" in src

    def test_prune_plan_of_a_sealed_attempt(
        self, served: ServedFactory, terminal_run: RunFixture
    ) -> None:
        ws, exp, run = terminal_run
        with served(ws) as client:
            response = client.post(f"{_run_url(exp, run)}/prune", json={})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["runId"] == run.id
        assert body["removed"] is None
        assert body["entries"][0]["executionId"] == "e01"

    def test_prune_refuses_a_live_attempt(
        self, served: ServedFactory, fresh_run: RunFixture
    ) -> None:
        ws, exp, run = fresh_run
        with served(ws) as client:
            created = client.post(f"{_run_url(exp, run)}/executions", json={})
            assert created.status_code == 201, created.text
            response = client.post(
                f"{_run_url(exp, run)}/prune",
                json={"executionIds": ["e01"]},
            )
        assert response.status_code == 409, response.text


class TestCreateExecution:
    """``create_execution``: one queued attempt, optionally handed to molq."""

    def test_create_queues_initial_execution(
        self, served: ServedFactory, fresh_run: RunFixture
    ) -> None:
        ws, exp, run = fresh_run
        with served(ws) as client:
            response = client.post(f"{_run_url(exp, run)}/executions", json={})
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["id"] == "e01"
        assert body["mode"] == "initial"
        assert body["status"] == "queued"
        assert "submit_cwd" in body["environment"]
        assert body["executor"] == {"backend": "local", "target": "local"}
        assert [e.status.value for e in run.executions] == ["queued"]

    def test_create_records_profile_keys(
        self, served: ServedFactory, fresh_run: RunFixture
    ) -> None:
        """arch-own-02a §6: the route creates through ``Run.create_execution``."""
        ws, exp, run = fresh_run
        with served(ws) as client:
            response = client.post(f"{_run_url(exp, run)}/executions", json={})
        assert response.status_code == 201, response.text
        body = response.json()
        environment = body["environment"]
        assert {"profile", "config", "config_hash", "submit_cwd"} <= set(environment)
        assert "python" not in environment
        assert "host" not in environment
        assert body["executor"] == {"backend": "local", "target": "local"}
        assert run.execution("e01").environment == environment

    def test_resume_after_a_dead_owner_reaps_it_first(
        self, served: ServedFactory, fresh_run: RunFixture
    ) -> None:
        """A running attempt whose same-host owner died is sealed, then resumed."""
        import os
        import platform

        ws, exp, run = fresh_run
        repo = run._execution_repository()
        state = repo.create(
            mode=ExecutionMode.INITIAL,
            created_by=AgentRef(id="t", type="person", name="t"),
            executor={"kind": "local", "host": platform.node(), "pid": 2**22 - 7},
        )
        repo.start(state.id)
        with pytest.raises(ProcessLookupError):
            os.kill(2**22 - 7, 0)
        with served(ws) as client:
            response = client.post(f"{_run_url(exp, run)}/executions", json={"mode": "resume"})
        assert response.status_code == 201, response.text
        assert response.json()["mode"] == "resume"
        dead = run.execution(state.id)
        assert dead.status is ExecutionStatus.FAILED
        assert dead.error is not None and dead.error["type"] == "ZombieRun"

    def test_initial_after_existing_attempt_is_422(
        self, served: ServedFactory, terminal_run: RunFixture
    ) -> None:
        ws, exp, run = terminal_run
        with served(ws) as client:
            response = client.post(f"{_run_url(exp, run)}/executions", json={"mode": "initial"})
        assert response.status_code == 422, response.text

    def test_rerun_after_terminal_is_created(
        self, served: ServedFactory, terminal_run: RunFixture
    ) -> None:
        ws, exp, run = terminal_run
        with served(ws) as client:
            response = client.post(
                f"{_run_url(exp, run)}/executions",
                json={"mode": "rerun", "basedOnExecutionId": "e01"},
            )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["id"] == "e02"
        assert body["basedOnExecutionId"] == "e01"

    def test_bypass_cache_is_recorded(self, served: ServedFactory, failed_run: RunFixture) -> None:
        ws, exp, run = failed_run
        with served(ws) as client:
            response = client.post(
                f"{_run_url(exp, run)}/executions",
                json={"mode": "rerun", "basedOnExecutionId": "e01", "bypassCache": True},
            )
        assert response.status_code == 201, response.text
        assert response.json()["id"] == "e02"
        assert run.execution("e02").bypass_cache is True

    def test_bypass_cache_defaults_false(
        self, served: ServedFactory, failed_run: RunFixture
    ) -> None:
        ws, exp, run = failed_run
        with served(ws) as client:
            response = client.post(
                f"{_run_url(exp, run)}/executions",
                json={"mode": "rerun", "basedOnExecutionId": "e01"},
            )
        assert response.status_code == 201, response.text
        assert run.execution("e02").bypass_cache is False

    def test_tasks_record_a_partial_rerun(
        self, served: ServedFactory, failed_run: RunFixture
    ) -> None:
        ws, exp, run = failed_run
        with served(ws) as client:
            response = client.post(
                f"{_run_url(exp, run)}/executions",
                json={"mode": "rerun", "basedOnExecutionId": "e01", "tasks": ["b", "b"]},
            )
        assert response.status_code == 201, response.text
        assert response.json()["selectedTasks"] == ["b"]
        assert run.execution("e02").selected_tasks == ("b",)

    def test_tasks_default_to_every_task(
        self, served: ServedFactory, failed_run: RunFixture
    ) -> None:
        ws, exp, run = failed_run
        with served(ws) as client:
            response = client.post(
                f"{_run_url(exp, run)}/executions",
                json={"mode": "rerun", "basedOnExecutionId": "e01"},
            )
        assert response.status_code == 201, response.text
        assert response.json()["selectedTasks"] == []
        assert run.execution("e02").selected_tasks == ()

    def test_tasks_outside_a_rerun_are_422(
        self, served: ServedFactory, failed_run: RunFixture
    ) -> None:
        ws, exp, run = failed_run
        with served(ws) as client:
            response = client.post(
                f"{_run_url(exp, run)}/executions",
                json={"mode": "resume", "basedOnExecutionId": "e01", "tasks": ["b"]},
            )
        assert response.status_code == 422, response.text
        assert [e.id for e in run.executions] == ["e01"]

    def test_task_executor_is_recorded(self, served: ServedFactory, failed_run: RunFixture) -> None:
        ws, exp, run = failed_run
        with served(ws) as client:
            refused = client.post(
                f"{_run_url(exp, run)}/executions",
                json={"mode": "rerun", "taskExecutor": "gpu"},
            )
            response = client.post(
                f"{_run_url(exp, run)}/executions",
                json={"mode": "rerun", "taskExecutor": "process", "maxWorkers": 3},
            )
        assert response.status_code == 201, response.text
        assert run.execution("e02").executor["task_executor"] == "process"
        assert run.execution("e02").executor["task_max_workers"] == 3
        assert refused.status_code == 422

    def test_openapi_declares_bypass_cache(self) -> None:
        from molab.server.app import create_app

        schema = create_app().openapi()["components"]["schemas"]["ExecutionAttemptCreateRequest"]
        assert schema["properties"]["bypassCache"]["default"] is False

    def test_retry_mode_is_rejected(self, served: ServedFactory, failed_run: RunFixture) -> None:
        ws, exp, run = failed_run
        with served(ws) as client:
            response = client.post(
                f"{_run_url(exp, run)}/executions",
                json={"mode": "retry", "basedOnExecutionId": "e01"},
            )
        assert response.status_code == 422, response.text

    def test_resume_without_checkpoint_is_created(
        self, served: ServedFactory, failed_run: RunFixture
    ) -> None:
        ws, exp, run = failed_run
        with served(ws) as client:
            response = client.post(
                f"{_run_url(exp, run)}/executions",
                json={"mode": "resume", "basedOnExecutionId": "e01"},
            )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["mode"] == "resume"
        assert body["basedOnExecutionId"] == "e01"
        assert body["status"] == "queued"

    def test_dispatch_hands_the_queued_id_to_molq(
        self, served: ServedFactory, fresh_run: RunFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ws, exp, run = fresh_run
        _add_hpc_target(ws)
        recorder = _DispatchRecorder()
        monkeypatch.setattr(run_routes, "_dispatch_to_molq", recorder)
        with served(ws) as client:
            response = client.post(
                f"{_run_url(exp, run)}/executions",
                json={"target": "hpc"},
            )
        assert response.status_code == 201, response.text
        assert recorder.calls == [("hpc", "e01", [("e01", "queued")])]

    def test_dispatch_failure_seals_failed(
        self, served: ServedFactory, fresh_run: RunFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ws, exp, run = fresh_run
        _add_hpc_target(ws)
        recorder = _DispatchRecorder(error=RuntimeError("scheduler down"))
        monkeypatch.setattr(run_routes, "_dispatch_to_molq", recorder)
        with served(ws, raise_server_exceptions=False) as client:
            response = client.post(
                f"{_run_url(exp, run)}/executions",
                json={"target": "hpc"},
            )
        assert response.status_code == 500
        [execution] = run.executions
        assert execution.id == "e01"
        assert execution.status.value == "failed"
        assert execution.error is not None
        assert execution.error["type"] == "RuntimeError"
        assert execution.error["message"] == "scheduler down"

    def test_an_attempt_without_a_target_is_submitted_locally(
        self, served: ServedFactory, fresh_run: RunFixture, dispatched: _DispatchRecorder
    ) -> None:
        ws, exp, run = fresh_run
        with served(ws) as client:
            response = client.post(f"{_run_url(exp, run)}/executions", json={})
        assert response.status_code == 201, response.text
        assert dispatched.calls == [("local", "e01", [("e01", "queued")])]

    def test_an_unknown_target_creates_nothing(
        self, served: ServedFactory, fresh_run: RunFixture
    ) -> None:
        ws, exp, run = fresh_run
        with served(ws) as client:
            response = client.post(f"{_run_url(exp, run)}/executions", json={"target": "nowhere"})
        assert response.status_code == 422, response.text
        assert run.executions == []

    def test_dispatch_accepts_ui_authored_document(
        self,
        served: ServedFactory,
        fresh_run: RunFixture,
        echo_document: dict[str, object],
        submit_recorder: type[_SubmitRecorder],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(run_routes, "_dispatch_to_molq", _REAL_DISPATCH)
        ws, exp, run = fresh_run
        _add_hpc_target(ws)
        with served(ws) as client:
            put = client.put(
                f"/api/projects/{exp.project.id}/experiments/{exp.id}/workflow",
                json={"document": echo_document},
            )
            assert put.status_code == 200, put.text
            response = client.post(
                f"{_run_url(exp, run)}/executions",
                json={"target": "hpc"},
            )
        assert response.status_code == 201, response.text
        assert submit_recorder.calls == [response.json()["id"]]
        assert [e.status.value for e in run.executions] == ["queued"]


_CONSTANT_ADD = {
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
        {"task_id": "c", "task_type": "core.add", "config": {}, "status": "pending"},
    ],
    "links": [
        {"source": "a", "target": "c", "mapping": {}, "status": "pending"},
        {"source": "b", "target": "c", "mapping": {}, "status": "pending"},
    ],
    "metadata": {"label": None, "description": None, "tags": [], "custom": {}},
}


class _MolqRecorder:
    """Stands in for ``SubmitHandler``: records one call and submits nothing."""

    calls: ClassVar[list[str | None]] = []

    def __init__(self, **_kwargs: object) -> None:
        pass

    def __call__(
        self,
        _script: object,
        _run: Run,
        _experiment: Experiment,
        _project: object,
        *,
        execution_id: str | None = None,
    ) -> None:
        type(self).calls.append(execution_id)


class TestDispatchToMolq:
    """``_dispatch_to_molq`` asks only ``can_recover_workflow``."""

    def test_document_bound_experiment_submits_once(
        self, fresh_run: RunFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _ws, exp, run = fresh_run
        exp.bind_workflow("document", document=_CONSTANT_ADD)
        _MolqRecorder.calls = []
        monkeypatch.setattr(run_routes, "SubmitHandler", _MolqRecorder)
        target = ComputeTarget(
            name="hpc", registry_id="reg", cluster_id="hpc", scratch_root="/scratch"
        )

        _REAL_DISPATCH(target, run)

        assert _MolqRecorder.calls == [None]

    def test_unbound_snapshot_is_422(
        self, fresh_run: RunFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _ws, _exp, run = fresh_run
        payload = read_record(run.run_dir)
        payload["workflow_snapshot"] = {"entrypoint": "/x.py:wf"}
        write_record(run.run_dir, payload)
        _MolqRecorder.calls = []
        monkeypatch.setattr(run_routes, "SubmitHandler", _MolqRecorder)
        target = ComputeTarget(
            name="hpc", registry_id="reg", cluster_id="hpc", scratch_root="/scratch"
        )

        with pytest.raises(HTTPException) as excinfo:
            _REAL_DISPATCH(target, run)

        assert excinfo.value.status_code == 422
        detail = str(excinfo.value.detail)
        assert "bind a workflow" in detail
        assert "molab migrate" not in detail
        assert "molab plan" not in detail
        assert _MolqRecorder.calls == []


class TestGetExecutionOutputs:
    """``get_execution_outputs``: stdio, assets, evidence of one attempt."""

    def test_reports_sealed_evidence(self, served: ServedFactory, fresh_run: RunFixture) -> None:
        ws, exp, run = fresh_run
        _emit_metrics(run)
        with served(ws) as client:
            response = client.get(f"{_run_url(exp, run)}/executions/e01/outputs")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["executionId"] == "e01"
        assert {"kind": "runtime", "path": "run.log"} in [
            {"kind": item["kind"], "path": item["path"]} for item in body["evidence"]
        ]

    def test_runtime_is_the_run_log_and_stdio_is_printed(
        self, served: ServedFactory, fresh_run: RunFixture
    ) -> None:
        ws, exp, run = fresh_run
        with run.start():
            me.print("printed")
        with served(ws) as client:
            body = client.get(f"{_run_url(exp, run)}/executions/e01/outputs").json()
        assert body["runtime"] == (run.execution_dir("e01") / "run.log").read_text(encoding="utf-8")
        assert "execution finished" in body["runtime"]
        assert body["stdout"] == "printed\n"

    def test_unknown_execution_is_404(self, served: ServedFactory, fresh_run: RunFixture) -> None:
        ws, exp, run = fresh_run
        _emit_metrics(run)
        with served(ws) as client:
            response = client.get(f"{_run_url(exp, run)}/executions/e99/outputs")
        assert response.status_code == 404

    def test_reports_driver_results(self, served: ServedFactory, fresh_run: RunFixture) -> None:
        ws, exp, run = fresh_run
        with run.start() as ctx:
            ctx.set_result("energy", -1.5)
            ctx.set_result("converged", True)
        with served(ws) as client:
            response = client.get(f"{_run_url(exp, run)}/executions/e01/outputs")
        assert response.status_code == 200, response.text
        assert response.json()["results"] == {"energy": -1.5, "converged": True}

    def test_results_empty_without_set_result(
        self, served: ServedFactory, fresh_run: RunFixture
    ) -> None:
        ws, exp, run = fresh_run
        run.execute(_build_wf())
        with served(ws) as client:
            response = client.get(f"{_run_url(exp, run)}/executions/e01/outputs")
        assert response.status_code == 200, response.text
        assert response.json()["results"] == {}

    def test_reads_through_run_results(self) -> None:
        source = inspect.getsource(run_routes.get_execution_outputs)
        assert "run.results(" in source
        assert "results.json" not in source
        assert "read_versioned_json" not in inspect.getsource(run_routes)

    def test_lists_registered_assets(self, served: ServedFactory, fresh_run: RunFixture) -> None:
        ws, exp, run = fresh_run
        asset = _emit_metrics(run)
        with served(ws) as client:
            response = client.get(f"{_run_url(exp, run)}/executions/e01/outputs")
        assert response.status_code == 200, response.text
        assert [item["id"] for item in response.json()["assets"]] == [asset.id]
        assert response.json()["assets"][0]["ref"] == asset.ref

    def test_lists_task_products_once(self, served: ServedFactory, fresh_run: RunFixture) -> None:
        """A task's ``out/<task>/`` files are listed; the registered payload is not."""
        ws, exp, run = fresh_run
        _emit_metrics(run)
        task_dir = run.path / "executions" / "e01" / "out" / "figures"
        task_dir.mkdir(parents=True)
        (task_dir / "fig1.png").write_bytes(b"\x89PNG")
        with served(ws) as client:
            response = client.get(f"{_run_url(exp, run)}/executions/e01/outputs")
        assert response.status_code == 200, response.text
        listed = [node["relPath"] for node in response.json()["unregistered"]]
        assert listed == ["out/figures/fig1.png"]


class TestExecutionLogs:
    """``get_run_execution_logs``: the attempt's own stdio files, then legacy ones (D92)."""

    def test_reads_root_stdio_written_by_molab_print(
        self, served: ServedFactory, fresh_run: RunFixture
    ) -> None:
        ws, exp, run = fresh_run
        with run.start():
            me.print("hello out")
            me.print("hello err", file=sys.stderr)
        with served(ws) as client:
            response = client.get(f"{_run_url(exp, run)}/executions/e01/logs")
        assert response.status_code == 200, response.text
        assert response.json() == {
            "executionId": "e01",
            "stdout": "hello out\n",
            "stderr": "hello err\n",
        }

    def test_empty_stdout_falls_back_to_run_log(
        self, served: ServedFactory, fresh_run: RunFixture
    ) -> None:
        ws, exp, run = fresh_run
        with run.start():
            pass
        with served(ws) as client:
            body = client.get(f"{_run_url(exp, run)}/executions/e01/logs").json()
        assert "execution started" in body["stdout"]
        assert body["stderr"] is None

    def test_legacy_job_files_answer_when_root_files_are_absent(
        self, served: ServedFactory, fresh_run: RunFixture
    ) -> None:
        ws, exp, run = fresh_run
        with run.start():
            pass
        jobs = run.execution_dir("e01") / "jobs"
        (jobs / "123").mkdir(parents=True)
        (jobs / "123" / "stdout.log").write_text("legacy out\n", encoding="utf-8")
        (jobs / "123.err").write_text("legacy err\n", encoding="utf-8")
        with served(ws) as client:
            body = client.get(f"{_run_url(exp, run)}/executions/e01/logs").json()
        assert (body["stdout"], body["stderr"]) == ("legacy out\n", "legacy err\n")

    def test_root_file_wins_over_legacy(self, served: ServedFactory, fresh_run: RunFixture) -> None:
        ws, exp, run = fresh_run
        with run.start():
            me.print("new")
        jobs = run.execution_dir("e01") / "jobs"
        jobs.mkdir(parents=True, exist_ok=True)
        (jobs / "123.out").write_text("old\n", encoding="utf-8")
        with served(ws) as client:
            body = client.get(f"{_run_url(exp, run)}/executions/e01/logs").json()
        assert body["stdout"] == "new\n"

    def test_stream_chunks_follow_by_offset(
        self, served: ServedFactory, fresh_run: RunFixture
    ) -> None:
        ws, exp, run = fresh_run
        with run.start():
            for n in range(3):
                me.print(f"line {n}")
        url = f"{_run_url(exp, run)}/executions/e01/logs"  # + /{stream}
        with served(ws) as client:
            first = client.get(f"{url}/stdout", params={"offset": 0}).json()
            second = client.get(f"{url}/stdout", params={"offset": 7}).json()
            past = client.get(f"{url}/stdout", params={"offset": 99}).json()
            bad = client.get(f"{url}/stdout", params={"offset": -1})
        assert first == {
            "stream": "stdout",
            "text": "line 0\nline 1\nline 2\n",
            "offset": 0,
            "nextOffset": 21,
            "size": 21,
            "eof": True,
        }
        assert (second["text"], second["nextOffset"], second["eof"]) == (
            "line 1\nline 2\n",
            21,
            True,
        )
        assert (past["text"], past["nextOffset"], past["eof"]) == ("", 99, True)
        assert bad.status_code == 422

    def test_stream_window_is_bounded_and_stops_on_a_character(
        self, served: ServedFactory, fresh_run: RunFixture
    ) -> None:
        ws, exp, run = fresh_run
        with run.start():
            pass
        log = run.execution_dir("e01") / "stdout.log"
        window = run_routes._LOG_CHUNK_BYTES
        # A 3-byte character straddles the window's end.
        log.write_bytes(b"a" * (window - 1) + "\u20ac".encode() + b"tail\n")
        url = f"{_run_url(exp, run)}/executions/e01/logs"  # + /{stream}
        with served(ws) as client:
            first = client.get(f"{url}/stdout").json()
            rest = client.get(f"{url}/stdout", params={"offset": first["nextOffset"]}).json()
        assert first["nextOffset"] == window - 1
        assert first["eof"] is False
        assert first["text"] == "a" * (window - 1)
        assert rest["text"] == "\u20actail\n"
        assert rest["eof"] is True
        assert rest["size"] == log.stat().st_size

    def test_stream_run_and_absent_stream(
        self, served: ServedFactory, fresh_run: RunFixture
    ) -> None:
        ws, exp, run = fresh_run
        with run.start():
            pass
        url = f"{_run_url(exp, run)}/executions/e01/logs"  # + /{stream}
        with served(ws) as client:
            run_log = client.get(f"{url}/run").json()
            stderr = client.get(f"{url}/stderr").json()
        assert "execution started" in run_log["text"]
        assert stderr == {
            "stream": "stderr",
            "text": "",
            "offset": 0,
            "nextOffset": 0,
            "size": 0,
            "eof": True,
        }


class TestDownloadAssetContent:
    """``download_asset_content``: stream one asset this attempt registered."""

    def test_streams_registered_asset(self, served: ServedFactory, fresh_run: RunFixture) -> None:
        ws, exp, run = fresh_run
        asset = _emit_metrics(run)
        with served(ws) as client:
            response = client.get(f"{_run_url(exp, run)}/executions/e01/assets/{asset.id}/content")
        assert response.status_code == 200, response.text
        assert response.content == Path(run.asset_path(asset.id)).read_bytes()

    def test_unknown_asset_is_404(self, served: ServedFactory, fresh_run: RunFixture) -> None:
        ws, exp, run = fresh_run
        _emit_metrics(run)
        with served(ws) as client:
            response = client.get(f"{_run_url(exp, run)}/executions/e01/assets/missing/content")
        assert response.status_code == 404

    def test_foreign_attempt_is_404(self, served: ServedFactory, fresh_run: RunFixture) -> None:
        ws, exp, run = fresh_run
        asset = _emit_metrics(run)
        with run.start(mode=ExecutionMode.RERUN):
            pass
        with served(ws) as client:
            response = client.get(f"{_run_url(exp, run)}/executions/e02/assets/{asset.id}/content")
        assert response.status_code == 404


class TestGetRunExecution:
    """``get_run_execution``: the per-node workflow journal of one attempt."""

    def test_returns_node_journal(self, served: ServedFactory, fresh_run: RunFixture) -> None:
        ws, exp, _ = fresh_run
        run = exp.add_run(params={"x": 3})
        run.execute(_build_wf())
        with served(ws) as client:
            response = client.get(f"{_run_url(exp, run)}/executions/e01/workflow")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["executionId"] == "e01"
        assert body["status"] == "succeeded"
        wf = body["workflow"]
        assert isinstance(wf, dict)
        assert wf["execution_id"] == "e01"
        assert wf["workflow_name"] == "pipeline"
        assert wf["based_on_execution_id"] is None
        assert re.fullmatch(r"sha256:[0-9a-f]{64}", wf["workflow_hash"])
        assert wf["workflow_hash"] == (_build_wf()).compile().workflow_hash
        assert {t["task_id"]: (t["status"], t["outputs"]) for t in wf["task_configs"]} == {
            "double": ("completed", 6),
            "summarize": ("completed", "got 6"),
        }
        assert "status" not in wf

    def test_reports_based_on_of_rerun(self, served: ServedFactory, failed_run: RunFixture) -> None:
        ws, exp, run = failed_run
        run.execute(_build_wf(), rerun=True)
        with served(ws) as client:
            second = client.get(f"{_run_url(exp, run)}/executions/e02/workflow")
            first = client.get(f"{_run_url(exp, run)}/executions/e01/workflow")
        assert second.status_code == 200, second.text
        assert second.json()["status"] == "succeeded"
        assert second.json()["workflow"]["execution_id"] == "e02"
        assert second.json()["workflow"]["based_on_execution_id"] == "e01"
        assert first.status_code == 200, first.text
        assert first.json()["status"] == "failed"
        assert first.json()["workflow"] is None

    def test_unknown_execution_is_404(self, served: ServedFactory, fresh_run: RunFixture) -> None:
        ws, exp, run = fresh_run
        run.execute(_build_wf())
        with served(ws) as client:
            response = client.get(f"{_run_url(exp, run)}/executions/e99/workflow")
        assert response.status_code == 404

    def test_reads_through_workflow_reader(self) -> None:
        source = inspect.getsource(run_routes.get_run_execution)
        assert "read_journal(" in source
        assert "workflow.json" not in source
        assert "read_versioned_json" not in source


class TestExecutionRequestKey:
    """``requestKey`` makes attempt creation idempotent per Run."""

    def test_same_key_returns_the_same_attempt(
        self, served: ServedFactory, fresh_run: RunFixture
    ) -> None:
        ws, exp, run = fresh_run
        body = {"requestKey": "tack:d1:w1", "requestedBy": "tack"}
        with served(ws) as client:
            first = client.post(f"{_run_url(exp, run)}/executions", json=body)
            second = client.post(f"{_run_url(exp, run)}/executions", json=body)
        assert first.status_code == 201, first.text
        assert second.status_code == 201, second.text
        assert first.json()["id"] == second.json()["id"] == "e01"
        assert first.json()["executor"]["request_key"] == "tack:d1:w1"
        assert len(run.executions) == 1
        assert run.executions[0].created_by.id == "tack"

    def test_different_keys_create_new_attempts(
        self, served: ServedFactory, fresh_run: RunFixture
    ) -> None:
        ws, exp, run = fresh_run
        with served(ws) as client:
            client.post(f"{_run_url(exp, run)}/executions", json={"requestKey": "a"})
            second = client.post(
                f"{_run_url(exp, run)}/executions",
                json={"requestKey": "b", "mode": "rerun", "basedOnExecutionId": "e01"},
            )
        # e01 is still queued, so a rerun is refused; the key never hides that.
        assert second.status_code in (201, 422), second.text
        if second.status_code == 201:
            assert second.json()["id"] == "e02"


class TestLocalAttemptRunsForReal:
    """No stand-ins: a local attempt is a detached worker that finishes on its own."""

    def test_a_local_attempt_reaches_a_terminal_state(
        self,
        served: ServedFactory,
        fresh_run: RunFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import time

        monkeypatch.setattr(run_routes, "_start_locally", _REAL_START_LOCALLY)
        ws, exp, run = fresh_run
        with served(ws) as client:
            exp.bind_workflow("document", document=_CONSTANT_ADD)
            created = client.post(f"{_run_url(exp, run)}/executions", json={})
            assert created.status_code == 201, created.text
            assert created.json()["executor"]["backend"] == "local"
            url = f"{_run_url(exp, run)}/executions/{created.json()['id']}"
            deadline = time.monotonic() + 90
            status = "queued"
            while time.monotonic() < deadline:
                status = client.get(url).json()["status"]
                if status in {"succeeded", "failed", "cancelled"}:
                    break
                time.sleep(0.5)
        attempt = Path(str(run.run_dir)) / "executions" / created.json()["id"]
        log = attempt / "jobs" / "worker.log"
        assert status == "succeeded", log.read_text() if log.exists() else "no worker.log"
        assert not (attempt / "worker.log").exists(), (
            "worker output is scheduler evidence, under jobs/"
        )
        from molab.workspace import Workspace

        assert not [
            issue
            for issue in Workspace(ws.root).validate().violations
            if "worker.log" in str(issue)
        ], "molab's own validate must not call the worker's log a stray"

    def test_a_worker_that_cannot_start_seals_the_attempt_failed(
        self,
        served: ServedFactory,
        fresh_run: RunFixture,
        echo_document: dict[str, object],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A document whose task type only this test process knows cannot start in a worker."""
        import time

        monkeypatch.setattr(run_routes, "_start_locally", _REAL_START_LOCALLY)
        ws, exp, run = fresh_run
        with served(ws) as client:
            put = client.put(
                f"/api/projects/{exp.project.id}/experiments/{exp.id}/workflow",
                json={"document": echo_document},
            )
            assert put.status_code == 200, put.text
            created = client.post(f"{_run_url(exp, run)}/executions", json={})
            assert created.status_code == 201, created.text
            url = f"{_run_url(exp, run)}/executions/{created.json()['id']}"
            deadline = time.monotonic() + 90
            body: dict[str, object] = {"status": "queued"}
            while time.monotonic() < deadline:
                body = client.get(url).json()
                if body["status"] != "queued":
                    break
                time.sleep(0.5)
        assert body["status"] == "failed"
        assert "Unknown task_type" in str(body["error"])
