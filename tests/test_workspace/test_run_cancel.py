"""Tests for ``Run.cancel()`` — the canonical stop verb (workspace-owned)."""

from __future__ import annotations

import json
from pathlib import Path

from molab.workspace.domain import ExecutionStatus


class TestRunCancel:
    def test_pending_run_becomes_cancelled(self, run):
        assert run.status_summary.not_started
        with run.start() as ctx:
            run.cancel(ctx.id)
        assert run.executions[0].status == ExecutionStatus.CANCELLED

    def test_cancel_is_idempotent(self, run):
        with run.start() as ctx:
            run.cancel(ctx.id)
            run.cancel(ctx.id)
        assert run.executions[0].status == ExecutionStatus.CANCELLED

    def test_cancel_keeps_the_executor_on_the_execution_record(self, run):
        state = run.create_execution(executor={"job_id": "uuid-123", "scheduler_job_id": "456"})
        with run.start(execution_id=state.id):
            run.cancel(state.id)
        record = run.execution(state.id)
        assert record.executor["job_id"] == "uuid-123"
        assert record.executor["scheduler_job_id"] == "456"
        assert record.status == ExecutionStatus.CANCELLED
        assert "executor_info" not in json.loads((Path(str(run.run_dir)) / "run.json").read_text())
