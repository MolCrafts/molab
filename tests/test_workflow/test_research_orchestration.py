"""Workflow-layer primitives for research pipelines.

The agent-coupled primitives (``register_task_path`` and
``sanity_check``) have been removed from the workflow layer; their
tests live with the agent layer instead. This file retains
``dependent_params=`` on ``Workflow.add()`` / ``@wf.task``.
Cross-replicate aggregation is ``RunSet``, not a second reducer on the graph.
"""

from __future__ import annotations

import pytest

from molab.workflow import TaskContext, Workflow, WorkflowRuntime

# ── ac-001 ── dependent_params ───────────────────────────────────────────────


@pytest.mark.asyncio
class TestDependentParams:
    async def test_resolves_from_upstream_output_into_config(self) -> None:
        """A dependent_params(prev) overlay binds to the downstream body's param by name."""
        wf = Workflow(name="dep-params")

        @wf.task
        async def cooling(ctx: TaskContext) -> dict:
            return {"Tg": 0.6}

        @wf.task(
            depends_on=["cooling"],
            dependent_params=lambda prev: {"T": 0.7 * prev["cooling"].output["Tg"]},
        )
        async def mechanical(T: float) -> float:  # 'T' is delivered by dependent_params
            return float(T)

        result = await WorkflowRuntime().execute((wf).compile())
        assert result.status == "succeeded"
        assert result.outputs["mechanical"] == pytest.approx(0.42)

    async def test_upstream_view_exposes_output_only(self) -> None:
        seen: list[object] = []
        wf = Workflow(name="output-only")

        @wf.task
        async def cooling(ctx: TaskContext) -> dict:
            return {"Tg": 0.6}

        @wf.task(
            depends_on=["cooling"],
            dependent_params=lambda prev: seen.append(prev["cooling"]) or {"T": 1.0},
        )
        async def mechanical(T: float) -> float:
            return float(T)

        result = await WorkflowRuntime().execute((wf).compile())
        assert result.status == "succeeded"
        assert seen[0].output == {"Tg": 0.6}
        assert not hasattr(seen[0], "assets")
