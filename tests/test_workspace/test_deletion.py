"""Tests for Project/Experiment/Run delete APIs and listing cascade."""

from __future__ import annotations

from pathlib import Path

import pytest

from molexp.workspace import (
    RunNotFoundError,
    Workspace,
)
from molexp.workspace.domain import ExecutionMode


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


class TestDeleteExecution:
    def test_delete_execution_is_an_immutability_tombstone(self, tmp_path):
        _ws, _p, _e, r = _build(tmp_path)
        first_exec = r.executions[0].id
        with pytest.raises(RuntimeError):
            r.delete_execution(first_exec)
        # Provenance is immutable — the execution dir survives.
        assert (Path(r.run_dir) / "executions" / first_exec).exists()

    def test_unknown_execution_also_raises(self, tmp_path):
        _ws, _p, _e, r = _build(tmp_path)
        with pytest.raises(RuntimeError):
            r.delete_execution("exec-does-not-exist")


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


class TestRemoveFailedRuns:
    def test_deletes_only_failed(self, tmp_path):
        _ws, _p, e, seeded = _build(tmp_path)
        ok = e.add_run(params={"seed": 2})
        fail = e.add_run(params={"seed": 3})
        with ok.start():
            pass
        with fail.start() as ctx:
            ctx.mark_failed("boom")
        deleted = e.remove_failed_runs()
        assert fail.id in deleted
        assert ok.id not in deleted
        assert seeded.id not in deleted
        assert e.has_run(ok.id)
        assert e.has_run(seeded.id)
        assert not e.has_run(fail.id)

    def test_noop_when_nothing_failed(self, tmp_path):
        _ws, _p, e, r = _build(tmp_path)
        assert e.remove_failed_runs() == []
        assert e.has_run(r.id)


class TestDeleteProject:
    def test_remove_project_clears_everything(self, tmp_path):
        ws, p, _e, _r = _build(tmp_path)
        ws.remove_project(p.id)
        assert not Path(p.project_dir).exists()
        assert all(proj.id != p.id for proj in ws.list_projects())
