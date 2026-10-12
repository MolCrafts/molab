"""HTTP scope: listings and opens stop at the directory molab serve opened."""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from molab.server.app import create_app
from molab.server.dependencies import (
    ServedWorkspace,
    set_served_workspaces,
    set_workspace_path_override,
)
from molab.workspace import Workspace
from molab.workspace.folder import (
    WORKSPACE_EXPERIMENT_KIND,
    WORKSPACE_PROJECT_KIND,
    WORKSPACE_ROOT_KIND,
    WORKSPACE_RUN_KIND,
)


@pytest.fixture
def client_at(tmp_path: Path) -> Iterator[tuple[Workspace, object]]:
    """A lab plus a client factory bound to whatever directory the test serves."""
    ws = Workspace(tmp_path / "lab", name="lab")
    alpha = ws.add_project("alpha")
    experiment = alpha.add_experiment("baseline")
    run = experiment.add_run(params={"x": 1})
    beta = ws.add_project("beta")

    def open_at(directory: Path) -> TestClient:
        set_workspace_path_override(directory)
        return TestClient(create_app(serve_static=False))

    try:
        yield ws, alpha, experiment, run, beta, open_at
    finally:
        set_workspace_path_override(None)
        set_served_workspaces([])


class TestServeScopeHttp:
    def test_scope_kind_follows_the_served_directory(self, client_at: tuple) -> None:
        ws, alpha, experiment, run, _beta, open_at = client_at
        cases = (
            (Path(str(ws.root)), WORKSPACE_ROOT_KIND, ws.id),
            (Path(str(alpha.resolve())), WORKSPACE_PROJECT_KIND, alpha.id),
            (Path(str(experiment.resolve())), WORKSPACE_EXPERIMENT_KIND, experiment.id),
            (Path(str(run.resolve())), WORKSPACE_RUN_KIND, run.id),
        )
        for directory, kind, ident in cases:
            with open_at(directory) as client:
                response = client.get("/api/workspace/scope")
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["kind"] == kind
            assert body["id"] == ident

    def test_served_project_lists_itself_and_hides_the_sibling(self, client_at: tuple) -> None:
        _ws, alpha, experiment, _run, beta, open_at = client_at
        with open_at(Path(str(alpha.resolve()))) as client:
            listed = client.get("/api/projects")
            assert listed.status_code == 200, listed.text
            assert [row["id"] for row in listed.json()] == [alpha.id]
            experiments = client.get(f"/api/projects/{alpha.id}/experiments")
            assert experiments.status_code == 200, experiments.text
            assert [row["id"] for row in experiments.json()] == [experiment.id]
            missing = client.get(f"/api/projects/{beta.id}")
            assert missing.status_code == 404

    def test_served_experiment_has_no_project_and_returns_its_run(self, client_at: tuple) -> None:
        _ws, alpha, experiment, run, _beta, open_at = client_at
        with open_at(Path(str(experiment.resolve()))) as client:
            projects = client.get("/api/projects")
            assert projects.status_code == 200, projects.text
            assert projects.json() == []
            detail = client.get(f"/api/projects/{alpha.id}/experiments/{experiment.id}")
            assert detail.status_code == 200, detail.text
            assert detail.json()["projectId"] == ""
            assert detail.json()["id"] == experiment.id
            got = client.get(f"/api/projects/-/experiments/-/runs/{run.id}")
            assert got.status_code == 200, got.text
            assert got.json()["id"] == run.id
            assert got.json()["projectId"] == ""
            assert got.json()["experimentId"] == experiment.id
            sibling = client.get("/api/projects/-/experiments/not-this")
            assert sibling.status_code == 404

    def test_served_run_get_accepts_omitted_ancestors(self, client_at: tuple) -> None:
        _ws, _alpha, _experiment, run, _beta, open_at = client_at
        with open_at(Path(str(run.resolve()))) as client:
            got = client.get(f"/api/projects/-/experiments/-/runs/{run.id}")
            assert got.status_code == 200, got.text
            body = got.json()
            assert body["id"] == run.id
            assert body["projectId"] == ""
            assert body["experimentId"] == ""
            rows = client.get("/api/workspace/runs")
            assert rows.status_code == 200, rows.text
            assert [item["id"] for item in rows.json()["runs"]] == [run.id]

    def test_workspace_still_lists_both_projects(self, client_at: tuple) -> None:
        ws, alpha, _experiment, _run, beta, open_at = client_at
        with open_at(Path(str(ws.root))) as client:
            listed = client.get("/api/projects")
        assert listed.status_code == 200, listed.text
        assert {row["id"] for row in listed.json()} == {alpha.id, beta.id}

    def test_open_outside_a_non_empty_served_set_is_forbidden(
        self, client_at: tuple, tmp_path: Path
    ) -> None:
        ws, _alpha, _experiment, _run, _beta, open_at = client_at
        outside = tmp_path / "outside"
        outside.mkdir()
        set_served_workspaces(
            [
                ServedWorkspace(
                    key="lab",
                    label=str(ws.root),
                    is_remote=False,
                    path=str(ws.root),
                )
            ]
        )
        with open_at(Path(str(ws.root))) as client:
            blocked = client.post(
                "/api/workspace/open",
                json={"kind": "local", "path": str(outside)},
            )
            assert blocked.status_code == 403, blocked.text
            allowed = client.post(
                "/api/workspace/open",
                json={"kind": "local", "path": str(ws.root)},
            )
            assert allowed.status_code == 200, allowed.text

    def test_parentless_project_serves_without_a_workspace(
        self, client_at: tuple, tmp_path: Path
    ) -> None:
        _ws, alpha, experiment, _run, _beta, open_at = client_at
        alone = tmp_path / "alone"
        shutil.copytree(alpha.resolve(), alone)
        with open_at(alone) as client:
            scope = client.get("/api/workspace/scope")
            assert scope.status_code == 200, scope.text
            assert scope.json()["kind"] == WORKSPACE_PROJECT_KIND
            assert scope.json()["id"] == alpha.id
            projects = client.get("/api/projects")
            assert [row["id"] for row in projects.json()] == [alpha.id]
            experiments = client.get(f"/api/projects/{alpha.id}/experiments")
            assert [row["id"] for row in experiments.json()] == [experiment.id]
            assert experiments.json()[0]["projectId"] == alpha.id
            assert not (alone / "workspace.json").exists()
