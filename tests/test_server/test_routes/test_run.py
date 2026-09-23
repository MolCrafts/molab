"""Harvest / analyze-failure HTTP contracts."""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import get_args

from fastapi.testclient import TestClient

from molab.knowledge import Report
from molab.server.app import create_app
from molab.server.dependencies import set_workspace_path_override
from molab.server.routes import run as run_routes
from molab.server.schemas.requests import RunHarvestRequest
from molab.workspace import Workspace


def _terminal_run(tmp_path: Path):
    ws = Workspace(tmp_path / "ws", name="lab")
    ws.materialize()
    exp = ws.add_project("p").add_experiment("e")
    run = exp.add_run(params={"x": 1})
    with run.start() as ctx:
        ctx.mark_succeeded()
    return ws, exp, run


def _failed_run(tmp_path: Path):
    ws = Workspace(tmp_path / "ws", name="lab")
    ws.materialize()
    exp = ws.add_project("p").add_experiment("e")
    run = exp.add_run(params={"x": 1})
    with run.start() as ctx:
        ctx.mark_failed("unique-oom-marker")
    return ws, exp, run


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

    def test_plan_is_not_a_harvest_target(self, tmp_path: Path) -> None:
        ws, exp, run = _terminal_run(tmp_path)
        set_workspace_path_override(Path(str(ws.root)))
        app = create_app(serve_static=False)
        with TestClient(app) as client:
            response = client.post(
                f"/api/projects/{exp.project.id}/experiments/{exp.id}/runs/{run.id}/harvest",
                json={"cls": "Plan", "narrative": "a plan is not a harvest"},
            )
        set_workspace_path_override(None)
        assert response.status_code == 422
        assert "is not a harvest target" in str(response.json())

    def test_finding_harvests(self, tmp_path: Path) -> None:
        ws, exp, run = _terminal_run(tmp_path)
        set_workspace_path_override(Path(str(ws.root)))
        app = create_app(serve_static=False)
        with TestClient(app) as client:
            response = client.post(
                f"/api/projects/{exp.project.id}/experiments/{exp.id}/runs/{run.id}/harvest",
                json={"cls": "Finding", "narrative": "Tg rose with cooling rate."},
            )
        set_workspace_path_override(None)
        assert response.status_code == 200, response.text
        assert response.json()["name"]


class TestAnalyzeRunFailureRoute:
    def test_no_failure_analysis_identifier(self) -> None:
        src = inspect.getsource(run_routes.analyze_run_failure_route)
        assert "FailureAnalysis" not in src
        assert "analyze_run_failure" in src
        from molab.server.schemas import requests as reqs

        assert "FailureAnalysis" not in inspect.getsource(reqs.RunAnalyzeFailureRequest)

    def test_analyze_writes_report(self, tmp_path: Path) -> None:
        ws, exp, run = _failed_run(tmp_path)
        set_workspace_path_override(Path(str(ws.root)))
        app = create_app(serve_static=False)
        with TestClient(app) as client:
            response = client.post(
                f"/api/projects/{exp.project.id}/experiments/{exp.id}/runs/{run.id}/analyze-failure",
                json={},
            )
        set_workspace_path_override(None)
        assert response.status_code == 200, response.text
        item = next(
            i
            for i in __import__("molab.knowledge", fromlist=["Knowledge"]).Knowledge(ws.root).walk()
            if type(i) is Report
        )
        assert (item.path / "report.json").is_file()
