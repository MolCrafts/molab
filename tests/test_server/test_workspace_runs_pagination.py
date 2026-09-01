from __future__ import annotations


def test_workspace_runs_paginates_without_truncating_aggregates(client, experiment) -> None:
    for index in range(3):
        experiment.add_run(params={"index": index})

    response = client.get("/api/workspace/runs", params={"offset": 1, "limit": 1})

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["runs"]) == 1
    assert payload["total"] == 3
    assert payload["stats"]["total"] == 3
    assert payload["stats"]["pending"] == 3
    assert payload["truncated"] is True


def test_workspace_runs_marks_the_last_page_complete(client, experiment) -> None:
    for index in range(3):
        experiment.add_run(params={"index": index})

    response = client.get("/api/workspace/runs", params={"offset": 2, "limit": 2})

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["runs"]) == 1
    assert payload["total"] == 3
    assert payload["truncated"] is False
