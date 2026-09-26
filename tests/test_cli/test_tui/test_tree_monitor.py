"""Unit tests for ``molab.cli.tui.tree_monitor`` (the ``molab explore`` delete flow).

arch-own-01-cleanup removed ``Run.delete_execution``: execution records are
append-only, so deleting an execution node from the TUI keeps the record and
surfaces exactly one warning that says so, instead of a "delete failed" error.
"""

from __future__ import annotations

from pathlib import Path

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
    exp = ws.add_project("proj-a").add_experiment("exp-x", workflow_source="s.py", params={})
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
