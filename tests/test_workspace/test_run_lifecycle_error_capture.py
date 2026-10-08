"""A FAILED run persists WHY it failed in the canonical record.

When a task raises, the workflow engine catches the exception into a failed
``WorkflowResult`` and does NOT re-raise (so ``molexp run`` can resume). On that
engine-swallowed path ``RunContext.__exit__`` sets ``status=failed`` AND keeps
the error message ``mark_failed`` stashed, so ``run.json`` / ``execution.json``
never carry ``error: null`` for a failed run while the reason lives only in the
workflow-layer ``workflow.json`` — the authoritative record must not lie.

These pin that the failing-task error (type + message) lands in BOTH
workspace-owned canonical records. (The operator-facing ``failed_run`` health
flag is owned by ``tests/test_workspace/test_workspace_context.py``.)
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import molexp as me
from molexp.workflow import WorkflowRuntime, promote_callable


def _boom(inputs, config):
    return 1 / 0  # ZeroDivisionError: float division by zero


def _run_failing(tmp_path: Path):
    ws = me.Workspace(tmp_path / "ws", name="ws")
    exp = ws.add_project("demo").add_experiment("train")
    run = exp.add_run(params={"seed": 0})
    with run.start() as ctx:
        asyncio.run(
            WorkflowRuntime().execute(promote_callable(_boom, name="boom"), run_context=ctx)
        )
    # Reload fresh so we read what was persisted, not the in-memory instance.
    return ws.get_project("demo").get_experiment("train").get_run(run.id)


class TestFailedRunErrorCapture:
    def test_error_captured_into_run_metadata(self, tmp_path: Path) -> None:
        run = _run_failing(tmp_path)

        assert run.status == "failed"
        err = run.metadata.error
        assert err is not None, "a FAILED run must persist its error in run.json (was null)"
        assert "division by zero" in err.message
        assert err.type == "ZeroDivisionError", "the exception type must survive, not a placeholder"

    def test_error_captured_into_execution_metadata(self, tmp_path: Path) -> None:
        run = _run_failing(tmp_path)

        history = run.execution_history
        assert history, "the run must have an execution record"
        exec_id = history[-1].execution_id
        data = json.loads(
            (Path(run.run_dir) / "executions" / exec_id / "execution.json").read_text()
        )
        assert data.get("error") is not None, (
            "execution.json error must not be null on a failed run"
        )
        assert "division by zero" in data["error"]["message"]
