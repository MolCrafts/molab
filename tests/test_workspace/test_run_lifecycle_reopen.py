"""Resume-reopen branch of ExecutionContext entry (preallocated Execution).

``run.start(execution_id=X)`` where X matches an EXISTING QUEUED execution
REOPENS that slot — flips it to RUNNING and reuses the ``executions/<X>/``
dir — instead of appending a fresh execution. A ``start()`` with no id, or
with an id matching nothing, creates a new execution (rerun / first attempt).
A sealed (terminal) execution is NOT reopenable — the preallocated slot
contract is queued-only.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from molexp.workspace.domain import ExecutionMode, ExecutionStatus
from molexp.workspace.history import AgentRef


class TestReopenExecution:
    def test_sealed_execution_cannot_be_reopened(self, run) -> None:
        with run.start() as ctx:
            sealed_id = ctx.id

        with pytest.raises(ValueError, match="not queued"), run.start(execution_id=sealed_id):
            pass

    def test_reopen_rewrites_execution_json_status_running(self, run) -> None:
        repo = run._execution_repository()
        state = repo.create(mode=ExecutionMode.INITIAL, created_by=AgentRef(id="t", type="system"))
        exec_json = Path(run.run_dir) / "executions" / state.id / "execution.json"
        assert exec_json.exists()

        with run.start(execution_id=state.id):
            payload = json.loads(exec_json.read_text())
            assert payload["status"] == "running"
            # A genuine reopen, not a fresh append onto the same dir.
            assert len(run.executions) == 1

    def test_reopen_starts_queued_execution(self, run) -> None:
        repo = run._execution_repository()
        state = repo.create(mode=ExecutionMode.INITIAL, created_by=AgentRef(id="t", type="system"))
        assert state.status is ExecutionStatus.QUEUED
        assert state.started_at is None

        with run.start(execution_id=state.id):
            rec = repo.get(state.id)
            assert rec.status is ExecutionStatus.RUNNING
            assert rec.started_at is not None
            assert rec.finished_at is None

    def test_start_without_execution_id_creates_new_execution(self, run) -> None:
        with run.start():
            pass
        assert len(run.executions) == 1

        with run.start(mode=ExecutionMode.RERUN):
            assert len(run.executions) == 2

    def test_unknown_execution_id_creates_new_execution(self, run) -> None:
        with run.start():
            pass
        assert len(run.executions) == 1

        with run.start(execution_id="exec-custom", mode=ExecutionMode.RERUN):
            assert len(run.executions) == 2
            assert run.executions[-1].id == "exec-custom"
