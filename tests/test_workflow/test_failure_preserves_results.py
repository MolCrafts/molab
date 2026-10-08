"""A failed run keeps the outputs of tasks that already finished.

When a task body raises, the exception propagates out of the graph runner.
``WorkflowRuntime.execute`` does not discard the (often expensive) results of
the tasks that already finished: the in-place-mutated ``WorkflowState`` holds
them, and the failed ``WorkflowResult`` carries them in ``outputs``, so the
caller can resume via ``seed_outputs=`` instead of recomputing from scratch.
"""

from __future__ import annotations

import pytest

from molexp.workflow import WorkflowCompiler, WorkflowRuntime


class TestWorkflowRuntimeFailure:
    @pytest.mark.asyncio
    async def test_failed_result_preserves_completed_upstream_output(self) -> None:
        """A raising downstream task leaves the completed upstream's output in
        the failed result's ``outputs`` (not an empty dict)."""
        wf = WorkflowCompiler(name="partial")

        @wf.task
        async def good(ctx) -> str:
            return "good-out"

        @wf.task(depends_on=["good"])
        async def boom(ctx) -> str:
            raise RuntimeError("kaboom")

        result = await WorkflowRuntime().execute(wf.compile())

        assert result.status == "failed"
        assert result.outputs.get("good") == "good-out"  # preserved, not dropped
