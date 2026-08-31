"""Run hot-state read accessors resolve from ``RunMetadata`` on ``run.json``.

``Run.status`` / ``Run.is_retryable`` / ``Run.execution_history`` read
``self.metadata``. There is no ``ops/run.json`` sidecar.
"""

from __future__ import annotations

from datetime import UTC, datetime

from molexp.workspace.models import ExecutionRecord, RunStatus


class TestStatusReadsFromMetadata:
    def test_status_reads_from_run_json(self, run) -> None:
        run.materialize()
        run._update_metadata(status=RunStatus.FAILED)
        assert run.status == "failed"
        assert run.metadata.status is RunStatus.FAILED

    def test_is_retryable_reads_from_run_json(self, run) -> None:
        run.materialize()
        assert run.is_retryable is False
        run._update_metadata(status=RunStatus.CANCELLED)
        assert run.is_retryable is True
        run._update_metadata(status=RunStatus.SUCCEEDED)
        assert run.is_retryable is False

    def test_execution_history_reads_from_run_json(self, run) -> None:
        run.materialize()
        rec = ExecutionRecord(
            execution_id="exec-a",
            started_at=datetime(2026, 1, 1, tzinfo=UTC),
            status="failed",
        )
        run._update_metadata(status=RunStatus.FAILED, execution_history=(rec,))
        assert [r.execution_id for r in run.execution_history] == ["exec-a"]
        assert [r.execution_id for r in run.metadata.execution_history] == ["exec-a"]
