"""``WorkflowRuntime.run_on(experiment, ...)`` convenience one-liner.

Covers ``oop-api-rectification`` ac-007: ``run_on`` wraps build-run-execute into
one call — it creates a fresh ``Run`` under the experiment, returns a
``WorkflowResult``, does NOT auto-bind the workflow to the experiment (binding is
the caller's choice), and on failure re-raises a ``RuntimeError`` carrying the
workflow name + final status while recording the run as failed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from molab.workflow import (
    CompiledWorkflow,
    Workflow,
    WorkflowCompiler,
    WorkflowRuntime,
    default_binding_registry,
)
from molab.workspace import Workspace

if TYPE_CHECKING:
    from molab.workflow.context import TaskContext


@pytest.fixture(autouse=True)
def _isolate_registry():
    default_binding_registry.clear()
    yield
    default_binding_registry.clear()


def _trivial_workflow() -> CompiledWorkflow:
    builder = Workflow(name="trivial")

    @builder.task
    async def emit(ctx: TaskContext[None, None, None]) -> int:
        return 42

    return WorkflowCompiler().compile(builder)


def _failing_workflow() -> CompiledWorkflow:
    builder = Workflow(name="failing")

    @builder.task
    async def boom(ctx: TaskContext[None, None, None]) -> None:
        raise RuntimeError("intentional failure")

    return WorkflowCompiler().compile(builder)


class TestRunOn:
    @pytest.mark.asyncio
    async def test_executes_and_creates_a_fresh_run(self, tmp_path):
        """run_on runs the workflow against a fresh Run and returns its result."""
        ws = Workspace(root=tmp_path, name="ws")
        exp = ws.add_project(name="demo").add_experiment(name="trivial-exp")

        runs_before = exp.list_runs()
        result = await WorkflowRuntime().run_on(_trivial_workflow(), exp, params={"lr": 1e-3})

        assert result.outputs.get("emit") == 42
        assert len(exp.list_runs()) == len(runs_before) + 1

    @pytest.mark.asyncio
    async def test_does_not_auto_bind(self, tmp_path):
        """run_on must NOT auto-bind the workflow — that is ``bind_to``'s job."""
        ws = Workspace(root=tmp_path, name="ws")
        exp = ws.add_project(name="demo").add_experiment(name="trivial-exp")

        assert default_binding_registry.for_experiment(exp) is None
        await WorkflowRuntime().run_on(_trivial_workflow(), exp)
        assert default_binding_registry.for_experiment(exp) is None

    @pytest.mark.asyncio
    async def test_reraises_and_records_failed_run(self, tmp_path):
        """A task failure re-raises a RuntimeError naming the workflow + status,
        and the created run is left FAILED."""
        ws = Workspace(root=tmp_path, name="ws")
        exp = ws.add_project(name="demo").add_experiment(name="failing-exp")

        with pytest.raises(RuntimeError, match=r"failing.*status 'failed'"):
            await WorkflowRuntime().run_on(_failing_workflow(), exp)

        runs = exp.list_runs()
        assert len(runs) == 1
        assert runs[0].status_summary.by_status == {"failed": 1}
        assert runs[0].is_retryable is True

    @pytest.mark.asyncio
    async def test_failure_message_carries_execution_error(self, tmp_path):
        """The re-raised RuntimeError quotes the Execution error type and message."""
        ws = Workspace(root=tmp_path, name="ws")
        exp = ws.add_project(name="demo").add_experiment(name="failing-exp")

        with pytest.raises(RuntimeError, match=r"failing.*status 'failed'") as exc:
            await WorkflowRuntime().run_on(_failing_workflow(), exp)

        err = exp.list_runs()[0].executions[-1].error
        assert err is not None
        assert f"{err['type']}: {err['message']}" in str(exc.value)
