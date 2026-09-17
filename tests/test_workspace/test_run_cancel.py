"""Tests for ``Run.cancel()`` — the canonical stop verb (workspace-owned)."""

from __future__ import annotations

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

    def test_cancel_leaves_run_json_provenance_untouched(self, run):
        run._update_metadata(executor_info={"job_id": "uuid-123", "scheduler_job_id": "456"})
        with run.start() as ctx:
            run.cancel(ctx.id)
        assert run.metadata.executor_info["job_id"] == "uuid-123"
        assert run.metadata.executor_info["scheduler_job_id"] == "456"
        assert run.executions[0].status == ExecutionStatus.CANCELLED
