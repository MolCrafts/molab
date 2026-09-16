"""``/runs/{id}/execution`` bands ``workflow.json`` by size.

Inline below the inline ceiling, summarised (graph kept, outputs dropped)
below the hard ceiling, refused above it. Without this a run whose tasks
returned large outputs could make one request allocate hundreds of MB.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from molexp.server.routes.run import (
    EXECUTION_JSON_INLINE_BYTES,
    EXECUTION_JSON_MAX_BYTES,
)


def _record(run, execution_id: str) -> None:
    from molexp.workspace.models import ExecutionRecord

    rec = ExecutionRecord(execution_id=execution_id, started_at=datetime.now(UTC))
    run.update_ops(lambda s: s.model_copy(update={"executions": (*s.executions, rec)}))


def _write_workflow(run, execution_id: str, doc: dict) -> Path:
    exec_dir = Path(str(run.run_dir)) / "executions" / execution_id
    exec_dir.mkdir(parents=True, exist_ok=True)
    target = exec_dir / "workflow.json"
    target.write_text(json.dumps(doc), encoding="utf-8")
    _record(run, execution_id)
    return target


def _doc(payload: str) -> dict:
    return {
        "execution_id": "exec-1",
        "status": "completed",
        "task_configs": [
            {
                "task_id": "step",
                "status": "completed",
                "snapshot_key": "abc:def",
                "started_at": "2026-01-01T00:00:00Z",
                "finished_at": "2026-01-01T00:00:01Z",
                "outputs": payload,
            }
        ],
        "links": [{"source": "a", "target": "b"}],
    }


@pytest.fixture
def url(project, experiment, run):
    return f"/api/projects/{project.id}/experiments/{experiment.id}/runs/{run.id}/execution"


class TestInlineBand:
    def test_small_document_is_returned_whole(self, client, run, url):
        _write_workflow(run, "exec-1", _doc("small"))
        body = client.get(url).json()
        assert body["workflowTruncated"] is False
        assert body["workflow"]["task_configs"][0]["outputs"] == "small"
        assert body["workflowBytes"] > 0

    def test_legacy_completed_status_is_normalized(self, client, run, url):
        _write_workflow(run, "exec-1", _doc("small"))
        assert client.get(url).json()["status"] == "succeeded"


class TestSummaryBand:
    @pytest.fixture
    def big_run(self, run):
        _write_workflow(run, "exec-1", _doc("y" * (EXECUTION_JSON_INLINE_BYTES + 1000)))
        return run

    def test_outputs_are_dropped_but_the_graph_survives(self, client, big_run, url):
        body = client.get(url).json()
        assert body["workflowTruncated"] is True
        node = body["workflow"]["task_configs"][0]
        assert "outputs" not in node
        assert node["outputs_omitted"] is True
        # Everything a graph view renders is still there.
        assert node["status"] == "completed"
        assert node["snapshot_key"] == "abc:def"
        assert node["started_at"] and node["finished_at"]
        assert body["workflow"]["links"] == [{"source": "a", "target": "b"}]

    def test_response_is_far_smaller_than_the_document(self, client, big_run, url):
        body = client.get(url).json()
        assert len(json.dumps(body["workflow"])) < body["workflowBytes"] // 100


class TestRefusalBand:
    def test_document_above_the_hard_ceiling_is_413(self, client, run, url):
        exec_dir = Path(str(run.run_dir)) / "executions" / "exec-1"
        exec_dir.mkdir(parents=True, exist_ok=True)
        # Write past the ceiling without building the string in memory twice.
        with (exec_dir / "workflow.json").open("wb") as fh:
            fh.write(b'{"task_configs": [{"task_id": "s", "outputs": "')
            block = b"z" * (1 << 20)
            for _ in range((EXECUTION_JSON_MAX_BYTES // (1 << 20)) + 1):
                fh.write(block)
            fh.write(b'"}]}')
        _record(run, "exec-1")

        resp = client.get(url)
        assert resp.status_code == 413
        assert str(EXECUTION_JSON_MAX_BYTES) in resp.json()["detail"]


class TestMissing:
    def test_no_history_is_empty_response(self, client, url):
        assert client.get(url).json()["execution_id"] is None

    def test_missing_workflow_json_reports_the_execution(self, client, run, url):
        _record(run, "exec-1")
        body = client.get(url).json()
        assert body["execution_id"] == "exec-1"
        assert body["workflow"] is None

    def test_unknown_execution_id_is_404(self, client, run, url):
        _write_workflow(run, "exec-1", _doc("small"))
        assert client.get(url, params={"execution_id": "exec-nope"}).status_code == 404
