"""Workflow resume seeding sources ``run.executions`` (persist-one-02).

``last_resumable_execution_id`` / ``seed_from_execution`` pick the most-recent
non-succeeded Execution and read its persisted ``workflow.json`` node outputs.
"""

from __future__ import annotations

import json
from pathlib import Path

import molab as me
from molab.workflow._engine.persistence import (
    last_resumable_execution_id,
    seed_from_execution,
)
from molab.workspace.domain import ExecutionMode


def _make_run(tmp_path: Path):
    ws = me.Workspace(tmp_path / "ws")
    return ws.add_project("demo").add_experiment("train").add_run(params={"seed": 0})


def _make_execution(run, *, failed: bool, mode: ExecutionMode = ExecutionMode.INITIAL) -> str:
    """Create and seal one real Execution, returning its id."""
    ctx = run.start(mode=mode)
    ctx.__enter__()
    execution_id = ctx.id
    try:
        if failed:
            ctx.mark_failed("boom")
        else:
            ctx.mark_succeeded()
    finally:
        ctx.__exit__(None, None, None)
    return execution_id


class TestLastResumableExecutionId:
    def test_picks_last_non_succeeded(self, tmp_path: Path) -> None:
        run = _make_run(tmp_path)
        id1 = _make_execution(run, failed=True)
        id2 = _make_execution(run, failed=False, mode=ExecutionMode.RERUN)
        id3 = _make_execution(run, failed=True, mode=ExecutionMode.RERUN)
        assert last_resumable_execution_id(run) == id3
        assert [e.id for e in run.executions] == [id1, id2, id3]

    def test_empty_history_returns_none(self, tmp_path: Path) -> None:
        run = _make_run(tmp_path)
        run.materialize()
        assert last_resumable_execution_id(run) is None


class TestSeedFromExecutionHistory:
    def test_seeds_completed_outputs_from_execution_history(self, tmp_path: Path) -> None:
        run = _make_run(tmp_path)
        exec_id = _make_execution(run, failed=True)
        exec_dir = Path(run.run_dir) / "executions" / exec_id
        (exec_dir / "workflow.json").write_text(
            json.dumps(
                {
                    "task_configs": [
                        {"task_id": "prep", "status": "completed", "outputs": {"value": 7}}
                    ]
                }
            )
        )

        selected, seeds = seed_from_execution(run)
        assert selected == exec_id
        assert seeds == {"prep": {"value": 7}}

    def test_pending_run_yields_no_seed(self, tmp_path: Path) -> None:
        run = _make_run(tmp_path)
        run.materialize()
        assert seed_from_execution(run) == (None, None)
