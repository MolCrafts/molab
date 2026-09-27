"""Tests for Project/Experiment/Run delete APIs and listing cascade."""

from __future__ import annotations

from pathlib import Path

import pytest

from molab.workspace import (
    RunNotFoundError,
    Workspace,
)
from molab.workspace.domain import ExecutionMode


def _build(tmp_path):
    ws = Workspace(root=tmp_path, name="lab")
    ws.materialize()
    p = ws.add_project("proj-a")
    e = p.add_experiment("exp-x", workflow_source="s.py", params={})
    r = e.add_run(params={"seed": 1})

    # Seed two terminal Executions (both succeeded) so the run has history
    # without becoming retryable.
    with r.start():
        pass
    with r.start(mode=ExecutionMode.RERUN):
        pass
    return ws, p, e, r


class TestDeleteRun:
    def test_removes_run_dir(self, tmp_path):
        _ws, _p, e, r = _build(tmp_path)
        run_dir = Path(r.run_dir)
        assert run_dir.exists()
        e.remove_run(r.id)
        assert not run_dir.exists()

    def test_unknown_run_raises(self, tmp_path):
        _ws, _p, e, _r = _build(tmp_path)
        with pytest.raises(RunNotFoundError):
            e.remove_run("nope")


class TestDeleteProject:
    def test_remove_project_clears_everything(self, tmp_path):
        ws, p, _e, _r = _build(tmp_path)
        ws.remove_project(p.id)
        assert not Path(p.project_dir).exists()
        assert all(proj.id != p.id for proj in ws.list_projects())
