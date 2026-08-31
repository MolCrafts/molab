"""Workflow resume seeding sources ``run.execution_history`` (persist-one-02).

``last_resumable_execution_id`` / ``seed_from_execution`` pick the most-recent
non-succeeded execution from ``run.execution_history`` (``RunMetadata`` on
``run.json``).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import molexp as me
from molexp.workflow._engine.persistence import (
    last_resumable_execution_id,
    seed_from_execution,
)
from molexp.workspace.models import ExecutionRecord, RunStatus


def _make_run(tmp_path: Path):
    ws = me.Workspace(tmp_path / "ws")
    return ws.add_project("demo").add_experiment("train").add_run(params={"seed": 0})


def _write_execution_history(run, records: list[dict]) -> None:
    history = tuple(ExecutionRecord.model_validate(item) for item in records)
    run._update_metadata(status=RunStatus.FAILED, execution_history=history)


class TestLastResumableExecutionId:
    def test_picks_last_non_succeeded(self, tmp_path: Path) -> None:
        run = _make_run(tmp_path)
        _write_execution_history(
            run,
            [
                {
                    "execution_id": "exec-1",
                    "started_at": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
                    "status": "failed",
                },
                {
                    "execution_id": "exec-2",
                    "started_at": datetime(2026, 1, 2, tzinfo=UTC).isoformat(),
                    "status": "succeeded",
                },
                {
                    "execution_id": "exec-3",
                    "started_at": datetime(2026, 1, 3, tzinfo=UTC).isoformat(),
                    "status": "failed",
                },
            ],
        )
        assert last_resumable_execution_id(run) == "exec-3"
        assert [r.execution_id for r in run.execution_history] == ["exec-1", "exec-2", "exec-3"]

    def test_empty_history_returns_none(self, tmp_path: Path) -> None:
        run = _make_run(tmp_path)
        run.materialize()
        assert last_resumable_execution_id(run) is None


class TestSeedFromExecutionHistory:
    def test_seeds_completed_outputs_from_execution_history(self, tmp_path: Path) -> None:
        run = _make_run(tmp_path)
        exec_id = "exec-seed"
        _write_execution_history(
            run,
            [
                {
                    "execution_id": exec_id,
                    "started_at": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
                    "status": "failed",
                }
            ],
        )
        exec_dir = Path(run.run_dir) / "executions" / exec_id
        exec_dir.mkdir(parents=True, exist_ok=True)
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
