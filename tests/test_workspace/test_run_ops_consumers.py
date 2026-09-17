"""Run hot-state read accessors derive from Executions, not ``run.json``.

``Run.status`` (scalar) is removed in schema v2 — it raises
``AttributeError``. The query surface is ``run.status_summary`` (a
:class:`~molab.workspace.domain.RunStatusSummary`) and ``run.executions``
(a list of :class:`~molab.workspace.domain.ExecutionState`).
``Run.is_retryable`` and ``Run.execution_history`` (deprecated read alias)
both read ``run.executions``. There is no ``ops/run.json`` sidecar.
"""

from __future__ import annotations

import pytest

from molab.workspace.domain import ExecutionStatus


class TestStatusReadsFromExecutions:
    def test_scalar_status_is_removed_in_favor_of_summary(self, run) -> None:
        with pytest.raises(AttributeError):
            _ = run.status

        summary = run.status_summary
        assert summary.total == 0
        assert summary.not_started is True
        assert summary.by_status == {}

    def test_is_retryable_reads_from_executions(self, run) -> None:
        assert run.is_retryable is False

        with pytest.raises(RuntimeError, match="boom"), run.start():
            raise RuntimeError("boom")
        assert run.is_retryable is True

        other = run.experiment.add_run(params={"lr": 2e-4})
        with other.start():
            pass
        assert other.is_retryable is False

    def test_execution_history_reads_from_executions(self, run) -> None:
        with run.start() as ctx:
            exec_id = ctx.id

        assert [e.id for e in run.execution_history] == [exec_id]
        assert [e.id for e in run.executions] == [exec_id]
        assert run.executions[0].status is ExecutionStatus.SUCCEEDED
