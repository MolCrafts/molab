"""POST …/experiments/{id}/sweep seeds a grid and does not dispatch it."""

from __future__ import annotations

from pathlib import Path

from molab.workspace import Workspace


def test_sweep_seed_is_idempotent(tmp_path: Path, served) -> None:
    ws = Workspace(tmp_path / "ws", name="lab")
    ws.materialize()
    project = ws.add_project("p")
    experiment = project.add_experiment("e")
    url = f"/api/projects/{project.id}/experiments/{experiment.id}/sweep"
    body = {"axes": {"lr": [0.1, 0.2], "batch": [16, 32]}}

    with served(ws) as client:
        first = client.post(url, json=body)
        second = client.post(url, json=body)

    assert first.status_code == 200, first.text
    assert first.json()["cells"] == 4
    assert first.json()["skipped"] == 0
    assert len(first.json()["created"]) == 4
    assert second.status_code == 200, second.text
    assert second.json()["created"] == []
    assert second.json()["skipped"] == 4
    assert len(experiment.list_runs()) == 4


def test_sweep_seed_rejects_a_scalar_axis(tmp_path: Path, served) -> None:
    ws = Workspace(tmp_path / "ws", name="lab")
    ws.materialize()
    project = ws.add_project("p")
    experiment = project.add_experiment("e")
    url = f"/api/projects/{project.id}/experiments/{experiment.id}/sweep"

    with served(ws, raise_server_exceptions=False) as client:
        response = client.post(url, json={"axes": {"lr": 0.1}})

    assert response.status_code == 422


def test_sweep_seed_rejects_an_empty_axis(tmp_path: Path, served) -> None:
    ws = Workspace(tmp_path / "ws", name="lab")
    ws.materialize()
    project = ws.add_project("p")
    experiment = project.add_experiment("e")
    url = f"/api/projects/{project.id}/experiments/{experiment.id}/sweep"

    with served(ws, raise_server_exceptions=False) as client:
        response = client.post(url, json={"axes": {"lr": []}})

    assert response.status_code == 422
    assert experiment.list_runs() == []
