"""Unit tests for ``molab.cli.tui.tree_monitor`` (the ``molab explore`` delete flow).

arch-own-01-cleanup removed ``Run.delete_execution``: execution records are
append-only, so deleting an execution node from the TUI keeps the record and
surfaces exactly one warning that says so, instead of a "delete failed" error.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from molab.cli.tui.tree_model import TreeNode
from molab.cli.tui.tree_monitor import _execute_delete, _prepare_dialog
from molab.workspace import Workspace
from molab.workspace.domain import ExecutionMode, ExecutionStatus
from molab.workspace.execution_repository import ExecutionRepository
from molab.workspace.history import AgentRef
from molab.workspace.run import Run

_TEST_AGENT = AgentRef(id="test", type="person", name="test")


def _run_with_succeeded_e01(root: Path) -> Run:
    ws = Workspace(root=root, name="tui-lab")
    exp = ws.add_project("proj-a").add_experiment("exp-x", params={})
    run = exp.add_run(params={"seed": 1})
    repo = ExecutionRepository(
        ws.root, run.run_dir, run_id=run.id, project_id=run.experiment.project.id, fs=ws.fs
    )
    state = repo.create(mode=ExecutionMode.INITIAL, created_by=_TEST_AGENT)
    repo.start(state.id)
    repo.seal(state.id, ExecutionStatus.SUCCEEDED)
    assert state.id == "e01"
    return run


class TestExecuteDelete:
    def test_execution_delete_keeps_record_and_warns(self, tmp_path: Path) -> None:
        run = _run_with_succeeded_e01(tmp_path)
        node = TreeNode(
            kind="execution",
            node_id=("execution", "e01"),
            display_label="e01",
            status="succeeded",
            ref=(run, "e01"),
        )

        warnings = _execute_delete(_prepare_dialog([node]))

        assert len(warnings) == 1, warnings
        assert "append-only" in warnings[0]
        assert (Path(str(run.run_dir)) / "executions" / "e01" / "execution.json").is_file()


def _run_with_queued_e01(root: Path) -> Run:
    ws = Workspace(root=root, name="tui-lab")
    exp = ws.add_project("proj-a").add_experiment("exp-x", params={})
    run = exp.add_run(params={"seed": 1})
    state = run._create_execution(created_by=_TEST_AGENT)
    assert state.status is ExecutionStatus.QUEUED
    return run


class TestDeleteGatesOnActiveAttempts:
    """arch-own-02e: ``Run.status_label`` reports ``queued`` / ``finalizing`` as
    themselves, so the delete flow must gate on the run's active attempts, not
    on the label being ``running`` — a queued run may own a live scheduler job.
    """

    def test_queued_run_is_planned_for_cancel(self, tmp_path: Path) -> None:
        run = _run_with_queued_e01(tmp_path)
        node = TreeNode(
            kind="run",
            node_id=("run", run.id),
            display_label=run.id[:6],
            status=run.status_label,
            ref=run,
        )

        dialog = _prepare_dialog([node])

        (marker, _target, detail) = dialog.plan_lines[0]
        assert marker != "✓", dialog.plan_lines
        assert "cancel" in detail, dialog.plan_lines

    def test_queued_run_is_cancelled_before_removal(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        run = _run_with_queued_e01(tmp_path)
        run_dir = Path(str(run.run_dir))
        calls: list[bool] = []

        def _record_cancel(target: Run) -> str | None:
            calls.append(run_dir.is_dir())
            return None

        monkeypatch.setattr("molab.cli.tui.tree_monitor.try_cancel", _record_cancel)
        node = TreeNode(
            kind="run",
            node_id=("run", run.id),
            display_label=run.id[:6],
            status=run.status_label,
            ref=run,
        )

        _execute_delete(_prepare_dialog([node]))

        assert calls == [True], "try_cancel must run while the run still exists"
        assert not run_dir.exists()

    def test_queued_execution_node_is_cancelled(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        run = _run_with_queued_e01(tmp_path)
        calls: list[str] = []

        def _record_cancel(target: Run) -> str | None:
            calls.append(target.id)
            return None

        monkeypatch.setattr("molab.cli.tui.tree_monitor.try_cancel", _record_cancel)
        node = TreeNode(
            kind="execution",
            node_id=("execution", "e01"),
            display_label="e01",
            status="queued",
            ref=(run, "e01"),
        )

        _execute_delete(_prepare_dialog([node]))

        assert calls == [run.id]
