"""One-step tracked execution — ``execute_run`` / ``Run.execute`` (runset-api sub-task 1).

``molab.workflow.run.execute(workflow)`` folds the seven-touchpoint
driver dance (``run.start()`` + ``WorkflowRuntime().execute(run_context=...)``
+ asyncio plumbing) into one call that reuses the exact same execution path
as ``molab run``: RunContext lifecycle (status machine, ``ops`` sidecar,
heartbeat) + the workflow engine. ``Run.execute`` is the workspace-side sugar
reached through the ``set_run_executor`` inversion seam (workspace never
imports workflow).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import molab as me
from molab.workflow import (
    RunFailedError,
    RunNotExecutableError,
    Workflow,
    WorkflowCompiler,
)


def _make_run(tmp_path: Path, params: dict | None = None):
    ws = me.Workspace(tmp_path / "ws", name="lab")
    exp = ws.add_project("demo").add_experiment("pipeline")
    return exp.add_run(params=params if params is not None else {"x": 3})


def _build_wf() -> Workflow:
    wf = Workflow(name="pipeline")

    @wf.task
    def double(x: int) -> int:
        return x * 2

    @wf.task(depends_on=["double"])
    def summarize(double: int) -> str:
        return f"got {double}"

    return wf


class TestExecuteRun:
    def test_one_step_execute_returns_per_task_outputs(self, tmp_path: Path) -> None:
        run = _make_run(tmp_path)
        result = run.execute(WorkflowCompiler().compile(_build_wf()))
        assert result.status == "succeeded"
        assert result.outputs["double"] == 6
        assert result.outputs["summarize"] == "got 6"
        assert run.status_summary.by_status == {"succeeded": 1}
        assert [e.status.value for e in run.executions] == ["succeeded"]
        assert len(run.executions) == 1

    def test_task_failure_raises_and_persists_failed_run(self, tmp_path: Path) -> None:
        wf = Workflow(name="boom")

        @wf.task
        def explode(x: int) -> int:
            raise ZeroDivisionError("bad cell")

        run = _make_run(tmp_path)
        with pytest.raises(RunFailedError) as excinfo:
            run.execute(wf)
        assert run.status_summary.by_status == {"failed": 1}
        assert run.is_retryable is True
        assert [e.status.value for e in run.executions] == ["failed"]
        # The exception surfaces WHY and carries the partial WorkflowResult.
        assert "ZeroDivisionError" in str(excinfo.value)
        assert excinfo.value.result.status == "failed"

    def test_task_failure_persists_real_traceback_in_error_txt(self, tmp_path: Path) -> None:
        """The engine swallows the task exception, but its live traceback must
        still reach ``executions/<exec_id>/traceback.txt`` — the documented "with
        traceback" trace file, not a placeholder note."""
        wf = Workflow(name="boom")

        @wf.task
        def explode(x: int) -> int:
            raise ZeroDivisionError("bad cell")

        run = _make_run(tmp_path)
        with pytest.raises(RunFailedError):
            run.execute(wf)

        exec_id = run.executions[-1].id
        error_txt = Path(str(run.run_dir)) / "executions" / exec_id / "traceback.txt"
        assert error_txt.exists()
        content = error_txt.read_text()
        assert "Traceback (most recent call last):" in content
        assert "ZeroDivisionError: bad cell" in content
        # The task-body frame is part of the stack — this is a REAL traceback.
        assert 'raise ZeroDivisionError("bad cell")' in content
        assert "No Python traceback was captured" not in content

    def test_succeeded_refuses_even_with_rerun(self, tmp_path: Path) -> None:
        """A succeeded run is refused with or without ``rerun`` — the succeeded
        check precedes the verb domain, so ``rerun=True`` cannot resurrect a
        done run (verb domain is failed/cancelled only)."""
        run = _make_run(tmp_path)
        run.execute(_build_wf())
        with pytest.raises(RunNotExecutableError, match="succeeded"):
            run.execute(_build_wf(), rerun=True)
        assert len(run.executions) == 1

    def test_fresh_requires_rerun(self, tmp_path: Path) -> None:
        run = _make_run(tmp_path)
        with pytest.raises(ValueError, match="rerun=True"):
            run.execute(_build_wf(), fresh=True)

    def test_failed_then_explicit_retry_verbs(self, tmp_path: Path) -> None:
        """Retrying is explicit: a failed run refuses a plain call, resume is
        checkpoint-gated, and ``rerun=True`` opens a fresh Execution."""
        flag = tmp_path / "healed"

        def build() -> Workflow:
            wf = Workflow(name="healing")

            @wf.task
            def stage_a(x: int) -> int:
                return x + 1

            @wf.task(depends_on=["stage_a"])
            def stage_b(stage_a: int) -> int:
                if not Path(str(flag)).exists():
                    raise RuntimeError("not healed yet")
                return stage_a * 100

            return wf

        run = _make_run(tmp_path, params={"x": 1})
        with pytest.raises(RunFailedError):
            run.execute(build())
        assert run.status_summary.by_status == {"failed": 1}
        assert len(run.executions) == 1

        flag.write_text("ok")
        # A plain call on a retryable run refuses — retrying is an explicit verb.
        with pytest.raises(RunNotExecutableError, match="rerun=True"):
            run.execute(build())
        # resume is checkpoint-gated in schema v2 — no checkpoint, no resume.
        with pytest.raises(RunNotExecutableError, match="checkpoint"):
            run.execute(build(), resume=True)
        result = run.execute(build(), rerun=True)
        assert result.status == "succeeded"
        assert result.outputs["stage_b"] == 200
        # A retry opens a NEW execution (v2 never reopens an attempt).
        assert len(run.executions) == 2
        assert [e.mode.value for e in run.executions] == ["initial", "rerun"]

    def test_running_run_raises(self, tmp_path: Path) -> None:
        run = _make_run(tmp_path)
        ctx = run.start()
        ctx.__enter__()
        try:
            with pytest.raises(RunNotExecutableError, match="cancel"):
                run.execute(_build_wf(), rerun=True)
        finally:
            ctx.__exit__(None, None, None)

    def test_sync_facade_inside_event_loop_raises(self, tmp_path: Path) -> None:
        run = _make_run(tmp_path)

        async def inner() -> None:
            run.execute(_build_wf())

        with pytest.raises(RuntimeError, match="aexecute"):
            asyncio.run(inner())

    def test_async_variant(self, tmp_path: Path) -> None:
        run = _make_run(tmp_path)
        result = asyncio.run(run.aexecute(_build_wf()))
        assert result.status == "succeeded"
        assert result.outputs["summarize"] == "got 6"
