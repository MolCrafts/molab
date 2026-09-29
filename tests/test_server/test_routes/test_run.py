"""Run-route HTTP contracts: executions, artifacts, harvest / analyze-failure."""

from __future__ import annotations

import inspect
import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import ClassVar, get_args

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from molab.knowledge import Report
from molab.server.routes import run as run_routes
from molab.server.schemas.requests import RunHarvestRequest
from molab.workflow import Workflow, WorkflowCompiler
from molab.workspace import Experiment, Run, Workspace
from molab.workspace.domain import Artifact
from molab.workspace.models import ComputeTarget
from molab.workspace.targets import add_target

ServedFactory = Callable[..., TestClient]
RunFixture = tuple[Workspace, Experiment, Run]


def _run_url(exp: Experiment, run: Run) -> str:
    return f"/api/projects/{exp.project.id}/experiments/{exp.id}/runs/{run.id}"


def _add_hpc_target(ws: Workspace) -> None:
    add_target(
        ws,
        ComputeTarget(name="hpc", host="me@h", scheduler="slurm", scratch_root="/scratch"),
    )


def _emit_metrics(run: Run) -> Artifact:
    """Open ``e01``, emit ``metrics.json`` into ``artifacts/`` and seal it succeeded."""
    with run.start() as ctx:
        artifact = ctx.emit_artifact({"loss": 0.1}, name="metrics.json")
    return artifact


def _build_wf() -> Workflow:
    wf = Workflow(name="pipeline")

    @wf.task
    def double(x: int) -> int:
        return x * 2

    @wf.task(depends_on=["double"])
    def summarize(double: int) -> str:
        return f"got {double}"

    return wf


def _find_node(nodes: list[dict[str, object]], rel_path: str) -> dict[str, object] | None:
    for node in nodes:
        if node.get("relPath") == rel_path:
            return node
        children = node.get("children")
        if isinstance(children, list):
            found = _find_node(children, rel_path)
            if found is not None:
                return found
    return None


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


@pytest.fixture
def submit_recorder(monkeypatch: pytest.MonkeyPatch) -> Iterator[type[_SubmitRecorder]]:
    _SubmitRecorder.calls = []
    monkeypatch.setattr(run_routes, "SubmitHandler", _SubmitRecorder)
    yield _SubmitRecorder
    _SubmitRecorder.calls = []


class TestHarvestRunRoute:
    def test_cls_literal_is_six_classes(self) -> None:
        field = RunHarvestRequest.model_fields["cls"]
        values = set(get_args(field.annotation))
        assert values == {
            "Note",
            "Literature",
            "Report",
            "Finding",
            "Plan",
            "Observation",
        }
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
        assert "is not a harvest target" in str(response.json())

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
        assert "harvest_run(" in src
        assert "molab.workspace.knowledge" not in src
        assert "run.harvest(" not in src


class TestAnalyzeRunFailureRoute:
    def test_no_failure_analysis_identifier(self) -> None:
        src = inspect.getsource(run_routes.analyze_run_failure_route)
        assert "FailureAnalysis" not in src
        assert "analyze_run_failure" in src
        from molab.server.schemas import requests as reqs

        assert "FailureAnalysis" not in inspect.getsource(reqs.RunAnalyzeFailureRequest)

    def test_analyze_writes_report(self, served: ServedFactory, failed_run: RunFixture) -> None:
        ws, exp, run = failed_run
        with served(ws) as client:
            response = client.post(f"{_run_url(exp, run)}/analyze-failure", json={})
        assert response.status_code == 200, response.text
        item = next(
            i
            for i in __import__("molab.knowledge", fromlist=["Knowledge"]).Knowledge(ws.root).walk()
            if type(i) is Report
        )
        # A Knowledge document is a file (``knowledges/<name>.md``), never a
        # directory carrying a ``report.json`` head.
        assert item.path.is_file()
        assert item.path.name == f"{item.name}.md"
        assert item.name.startswith("failure-analysis-")


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
        assert body["executor"] == {"backend": "molq", "target": None}
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
        assert body["executor"] == {"backend": "molq", "target": None}
        assert run.execution("e01").environment == environment

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

    def test_retry_request_is_stored_as_rerun(
        self, served: ServedFactory, failed_run: RunFixture
    ) -> None:
        """arch-own-03a §1: a RETRY request is created as a RERUN."""
        ws, exp, run = failed_run
        with served(ws) as client:
            response = client.post(
                f"{_run_url(exp, run)}/executions",
                json={"mode": "retry", "basedOnExecutionId": "e01"},
            )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["mode"] == "rerun"
        assert body["id"] == "e02"

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
                json={"target": "hpc", "dispatch": True},
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
                json={"target": "hpc", "dispatch": True},
            )
        assert response.status_code == 500
        [execution] = run.executions
        assert execution.id == "e01"
        assert execution.status.value == "failed"
        assert execution.error is not None
        assert execution.error["type"] == "RuntimeError"
        assert execution.error["message"] == "scheduler down"

    def test_dispatch_without_target_is_422(
        self, served: ServedFactory, fresh_run: RunFixture
    ) -> None:
        ws, exp, run = fresh_run
        with served(ws) as client:
            response = client.post(f"{_run_url(exp, run)}/executions", json={"dispatch": True})
        assert response.status_code == 422, response.text
        assert run.executions == []

    @pytest.mark.xfail(
        strict=True,
        raises=AssertionError,
        reason=(
            "arch-own-04: POST …/executions dispatch=true — a UI-authored workflow "
            "document is a dispatchable workflow; SubmitHandler receives the queued id"
        ),
    )
    def test_dispatch_accepts_ui_authored_document(
        self,
        served: ServedFactory,
        fresh_run: RunFixture,
        echo_document: dict[str, object],
        submit_recorder: type[_SubmitRecorder],
    ) -> None:
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
                json={"target": "hpc", "dispatch": True},
            )
        assert response.status_code == 201, response.text
        assert submit_recorder.calls == [response.json()["id"]]
        assert [e.status.value for e in run.executions] == ["queued"]


class TestDispatchToMolq:
    """``_dispatch_to_molq``: a run is dispatchable only through its experiment's entrypoint."""

    def test_unbound_experiment_is_422_naming_the_entrypoint(self, fresh_run: RunFixture) -> None:
        _ws, _exp, run = fresh_run
        target = ComputeTarget(name="hpc", host="me@h", scheduler="slurm", scratch_root="/scratch")

        with pytest.raises(HTTPException) as excinfo:
            run_routes._dispatch_to_molq(target, run)

        assert excinfo.value.status_code == 422
        detail = str(excinfo.value.detail)
        assert "workflow entrypoint" in detail
        assert "Experiment.define" in detail
        assert "molab plan" not in detail
        assert "generated" not in detail


class TestGetExecutionOutputs:
    """``get_execution_outputs``: stdio, artifacts, evidence of one attempt."""

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

    @pytest.mark.xfail(
        strict=True,
        raises=AssertionError,
        reason=(
            "arch-own-05: GET …/executions/{id}/outputs — artifacts are read from "
            "execution.json, so the emitted artifact is listed"
        ),
    )
    def test_lists_emitted_artifacts(self, served: ServedFactory, fresh_run: RunFixture) -> None:
        ws, exp, run = fresh_run
        artifact = _emit_metrics(run)
        with served(ws) as client:
            response = client.get(f"{_run_url(exp, run)}/executions/e01/outputs")
        assert response.status_code == 200, response.text
        assert [a["id"] for a in response.json()["artifacts"]] == [artifact.id]


class TestDownloadArtifactContent:
    """``download_artifact_content``: stream one emitted artifact's bytes."""

    @pytest.mark.xfail(
        strict=True,
        raises=AssertionError,
        reason=(
            "arch-own-05: GET …/artifacts/{id}/content — an artifact recorded in "
            "execution.json streams its bytes"
        ),
    )
    def test_streams_emitted_artifact(self, served: ServedFactory, fresh_run: RunFixture) -> None:
        ws, exp, run = fresh_run
        artifact = _emit_metrics(run)
        with served(ws) as client:
            response = client.get(
                f"{_run_url(exp, run)}/executions/e01/artifacts/{artifact.id}/content"
            )
        assert response.status_code == 200, response.text
        on_disk = Path(run.run_dir) / "executions" / "e01" / "artifacts" / "metrics.json"
        assert response.content == on_disk.read_bytes()


class TestGetRunFiles:
    """``get_run_files``: the attempt tree, enriched from ``execution.json``."""

    def test_artifact_node_carries_artifact_id(
        self, served: ServedFactory, fresh_run: RunFixture
    ) -> None:
        ws, exp, run = fresh_run
        artifact = _emit_metrics(run)
        with served(ws) as client:
            response = client.get(f"{_run_url(exp, run)}/executions/e01/files")
        assert response.status_code == 200, response.text
        node = _find_node(response.json()["nodes"], "artifacts/metrics.json")
        assert node is not None
        assert node["assetId"] == artifact.id


class TestPromoteArtifact:
    """``promote_artifact``: an emitted artifact becomes a project asset version."""

    def test_promote_creates_asset_version(
        self, served: ServedFactory, fresh_run: RunFixture
    ) -> None:
        ws, exp, run = fresh_run
        artifact = _emit_metrics(run)
        with served(ws) as client:
            response = client.post(
                f"{_run_url(exp, run)}/executions/e01/artifacts/{artifact.id}/promote",
                json={},
            )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["version"]["sourceArtifactId"] == artifact.id
        assert body["version"]["digest"] == artifact.content.digest
        assert body["asset"]["versionCount"] == 1

    def test_unknown_artifact_is_404(self, served: ServedFactory, fresh_run: RunFixture) -> None:
        ws, exp, run = fresh_run
        _emit_metrics(run)
        with served(ws) as client:
            response = client.post(
                f"{_run_url(exp, run)}/executions/e01/artifacts/no-such-artifact/promote",
                json={},
            )
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
        assert re.fullmatch(r"sha256:[0-9a-f]{64}", wf["workflow_digest"])
        assert wf["workflow_digest"] == WorkflowCompiler().compile(_build_wf()).workflow_digest
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
