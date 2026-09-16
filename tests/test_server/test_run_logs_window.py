"""``/runs/{id}/logs`` returns a bounded tail window, not the whole file.

A run's ``stdout.log`` can be gigabytes. These tests pin the three properties
that make the route safe: the response is capped regardless of file size, the
server never *allocates* more than the cap, and the byte cursors let a poller
fetch only what was appended.
"""

from __future__ import annotations

import tracemalloc
from pathlib import Path

import pytest

from molexp.server.routes.run import DEFAULT_LOG_WINDOW_BYTES


def _write_execution_log(run, execution_id: str, name: str, text: str) -> None:
    """Write ``executions/<id>/<name>`` under the run, creating parents."""
    exec_dir = Path(str(run.run_dir)) / "executions" / execution_id
    exec_dir.mkdir(parents=True, exist_ok=True)
    (exec_dir / name).write_text(text, encoding="utf-8")


def _record_execution(run, execution_id: str) -> None:
    """Put *execution_id* in the run's ops history so the route selects it."""
    from datetime import UTC, datetime

    from molexp.workspace.models import ExecutionRecord

    record = ExecutionRecord(execution_id=execution_id, started_at=datetime.now(UTC))
    run.update_ops(lambda s: s.model_copy(update={"executions": (*s.executions, record)}))


@pytest.fixture
def run_with_logs(run):
    """A run whose latest execution has a 4 MB stdout and a small stderr."""
    exec_id = "exec-test-1"
    # Numbered lines make it verifiable *which* part of the file came back.
    big = "".join(f"line {i:07d}\n" for i in range(250_000))
    assert len(big) > 3_000_000
    _write_execution_log(run, exec_id, "stdout.log", big)
    _write_execution_log(run, exec_id, "stderr.log", "a warning\n")
    _record_execution(run, exec_id)
    return run, exec_id, big


class TestLogWindowBounds:
    def test_returns_tail_not_whole_file(self, client, project, experiment, run_with_logs):
        run, _exec_id, big = run_with_logs
        resp = client.get(
            f"/api/projects/{project.id}/experiments/{experiment.id}/runs/{run.id}/logs"
        )
        assert resp.status_code == 200
        body = resp.json()

        assert body["stdout_total"] == len(big)
        assert body["stdout_truncated"] is True
        assert len(body["stdout"].encode()) <= DEFAULT_LOG_WINDOW_BYTES
        # The *tail* is what a log viewer wants: the last line must be present
        # and the first must not.
        assert body["stdout"].rstrip("\n").endswith("line 0249999")
        assert "line 0000000\n" not in body["stdout"]

    def test_small_log_comes_back_whole_and_untruncated(
        self, client, project, experiment, run_with_logs
    ):
        run, _exec_id, _big = run_with_logs
        resp = client.get(
            f"/api/projects/{project.id}/experiments/{experiment.id}/runs/{run.id}/logs"
        )
        body = resp.json()
        assert body["stderr"] == "a warning\n"
        assert body["stderr_truncated"] is False
        assert body["stderr_offset"] == 0
        assert body["stderr_end"] == body["stderr_total"]

    def test_max_bytes_is_honoured(self, client, project, experiment, run_with_logs):
        run, _exec_id, _big = run_with_logs
        resp = client.get(
            f"/api/projects/{project.id}/experiments/{experiment.id}/runs/{run.id}/logs",
            params={"max_bytes": 5000},
        )
        body = resp.json()
        assert len(body["stdout"].encode()) <= 5000

    def test_max_bytes_above_ceiling_is_rejected(self, client, project, experiment, run_with_logs):
        run, _exec_id, _big = run_with_logs
        resp = client.get(
            f"/api/projects/{project.id}/experiments/{experiment.id}/runs/{run.id}/logs",
            params={"max_bytes": 50_000_000},
        )
        assert resp.status_code == 422


class TestIncrementalFollow:
    def test_since_cursor_returns_only_the_append(self, client, project, experiment, run_with_logs):
        run, exec_id, _big = run_with_logs
        url = f"/api/projects/{project.id}/experiments/{experiment.id}/runs/{run.id}/logs"

        first = client.get(url).json()
        cursor = first["stdout_end"]

        log = Path(str(run.run_dir)) / "executions" / exec_id / "stdout.log"
        with log.open("a", encoding="utf-8") as fh:
            fh.write("FRESH LINE\n")

        second = client.get(url, params={"since_stdout": cursor}).json()
        assert second["stdout"] == "FRESH LINE\n"
        assert second["stdout_offset"] == cursor
        assert second["stdout_end"] == cursor + len("FRESH LINE\n")

    def test_cursor_at_eof_returns_empty_not_a_replay(
        self, client, project, experiment, run_with_logs
    ):
        run, _exec_id, _big = run_with_logs
        url = f"/api/projects/{project.id}/experiments/{experiment.id}/runs/{run.id}/logs"
        first = client.get(url).json()
        second = client.get(url, params={"since_stdout": first["stdout_total"]}).json()
        assert second["stdout"] == ""


class TestLogWindowMemory:
    def test_hundred_mb_log_allocates_only_the_window(self, client, project, experiment, run):
        """The contract is *peak memory*, not just response size.

        Reading the file whole and slicing afterwards would satisfy every
        assertion above while still allocating 100 MB, which is the bug this
        route exists to fix.
        """
        exec_id = "exec-huge"
        chunk = ("x" * 999 + "\n").encode()
        exec_dir = Path(str(run.run_dir)) / "executions" / exec_id
        exec_dir.mkdir(parents=True, exist_ok=True)
        with (exec_dir / "stdout.log").open("wb") as fh:
            for _ in range(100_000):  # 100 MB
                fh.write(chunk)
        _record_execution(run, exec_id)

        url = f"/api/projects/{project.id}/experiments/{experiment.id}/runs/{run.id}/logs"
        tracemalloc.start()
        try:
            resp = client.get(url)
            _current, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()

        assert resp.status_code == 200
        assert resp.json()["stdout_total"] == 100_000_000
        # Generous headroom for framework overhead, but two orders of
        # magnitude below reading the file whole.
        assert peak < 16 * 1024 * 1024, f"peak allocation {peak} suggests a whole-file read"


class TestRunLogFallback:
    def test_falls_back_to_runtime_log_when_stdout_absent(self, client, project, experiment, run):
        exec_id = "exec-fallback"
        exec_dir = Path(str(run.run_dir)) / "executions" / exec_id / "logs"
        exec_dir.mkdir(parents=True, exist_ok=True)
        (exec_dir / "run.log").write_text("from the runtime log\n", encoding="utf-8")
        _record_execution(run, exec_id)

        resp = client.get(
            f"/api/projects/{project.id}/experiments/{experiment.id}/runs/{run.id}/logs"
        )
        assert resp.json()["stdout"] == "from the runtime log\n"

    def test_no_history_returns_empty_response(self, client, project, experiment, run):
        resp = client.get(
            f"/api/projects/{project.id}/experiments/{experiment.id}/runs/{run.id}/logs"
        )
        assert resp.status_code == 200
        assert resp.json()["stdout"] is None
