"""Unit tests for ``molab.cli.prune`` (``molab runs prune``, ``prune_runs``).

The interactive walk project -> experiment -> run -> executions, driven through
``molab.cli.app`` with scripted input. arch-own-01-cleanup pins two things:

* the run table reads ``Run.status_label`` — ``Run.status`` raises by design,
  so reading it crashed the command on any workspace with a run;
* pruning removes bulk directories only; the execution record is kept.

Output assertions are made on the whitespace-collapsed output so rich table
wrapping cannot split a phrase.
"""

from __future__ import annotations

import os
import platform
from pathlib import Path

import pytest
from typer.testing import CliRunner

import molab.cli
from molab.workspace import Workspace
from molab.workspace.domain import ExecutionMode, ExecutionStatus
from molab.workspace.execution_repository import ExecutionRepository
from molab.workspace.history import AgentRef
from molab.workspace.run import Run

_TEST_AGENT = AgentRef(id="test", type="person", name="test")


def _repo(run: Run) -> ExecutionRepository:
    ws = run.experiment.project.workspace
    return ExecutionRepository(
        ws.root,
        run.run_dir,
        run_id=run.id,
        project_id=run.experiment.project.id,
        fs=ws.fs,
    )


def _single_run(root: Path) -> Run:
    ws = Workspace(root=root, name="prune-cli-lab")
    exp = ws.add_project("proj-a").add_experiment("exp-x", params={})
    return exp.add_run(params={"seed": 1})


def _invoke(root: Path, script: str) -> tuple[int, BaseException | None, str]:
    result = CliRunner().invoke(molab.cli.app, ["runs", "prune", "--path", str(root)], input=script)
    return result.exit_code, result.exception, " ".join(result.output.split())


class TestPruneRuns:
    def test_run_table_uses_status_label(self, tmp_path: Path) -> None:
        _single_run(tmp_path)

        exit_code, exception, output = _invoke(tmp_path, "1\n1\n1\n")

        assert not isinstance(exception, AttributeError), repr(exception)
        assert exit_code == 0, output
        assert "pending" in output
        assert "has no execution history" in output

    def test_prunes_bulk_and_keeps_record(self, tmp_path: Path) -> None:
        run = _single_run(tmp_path)
        repo = _repo(run)
        state = repo.create(mode=ExecutionMode.INITIAL, created_by=_TEST_AGENT)
        repo.start(state.id)
        exec_dir = Path(str(run.run_dir)) / "executions" / state.id
        (exec_dir / "out").mkdir(parents=True, exist_ok=True)
        (exec_dir / "out" / "x").write_text("x", encoding="utf-8")
        repo.seal(state.id, ExecutionStatus.FAILED)
        assert state.id == "e01"

        exit_code, exception, output = _invoke(tmp_path, "1\n1\n1\nfailed\ny\n")

        assert not isinstance(exception, AttributeError), repr(exception)
        assert exit_code == 0, output
        assert "failed" in output
        assert "records are kept" in output
        assert (exec_dir / "execution.json").is_file()
        assert not (exec_dir / "out").exists()

    def test_reaps_dead_owner_running_execution_before_pruning(self, tmp_path: Path) -> None:
        run = _single_run(tmp_path)
        repo = _repo(run)
        dead_pid = 2**22 - 7
        with pytest.raises(ProcessLookupError):
            os.kill(dead_pid, 0)
        state = repo.create(
            mode=ExecutionMode.INITIAL,
            created_by=_TEST_AGENT,
            executor={"kind": "local", "host": platform.node(), "pid": dead_pid},
        )
        repo.start(state.id)
        exec_dir = Path(str(run.run_dir)) / "executions" / state.id
        (exec_dir / "out").mkdir(parents=True, exist_ok=True)
        (exec_dir / "out" / "x").write_text("x", encoding="utf-8")
        assert state.id == "e01"

        exit_code, _exception, output = _invoke(tmp_path, "1\n1\n1\n1\ny\n")

        assert exit_code == 0, output
        assert repo.get(state.id).status == ExecutionStatus.FAILED
        assert "records are kept" in output
        assert (exec_dir / "execution.json").is_file()
        assert not (exec_dir / "out").exists()


def _seal(run: Run, statuses: tuple[str, ...]) -> None:
    repo = _repo(run)
    for i, status in enumerate(statuses):
        mode = ExecutionMode.INITIAL if i == 0 else ExecutionMode.RERUN
        state = repo.create(mode=mode, created_by=_TEST_AGENT)
        repo.start(state.id)
        repo.seal(state.id, ExecutionStatus(status))


def _flags(root: Path, *flags: str) -> tuple[int, str]:
    result = CliRunner().invoke(molab.cli.app, ["runs", "prune", "--path", str(root), *flags])
    return result.exit_code, " ".join(result.output.split())


class TestPruneFailed:
    def test_dry_run_lists_and_keeps_everything(self, tmp_path: Path) -> None:
        run = _single_run(tmp_path)
        _seal(run, ("succeeded", "failed"))

        exit_code, output = _flags(tmp_path, "--failed", "--dry-run")

        assert exit_code == 0, output
        assert "would discard e02" in output
        assert [item.id for item in run.executions] == ["e01", "e02"]

    def test_failed_keeps_the_success(self, tmp_path: Path) -> None:
        run = _single_run(tmp_path)
        _seal(run, ("succeeded", "failed"))

        exit_code, output = _flags(tmp_path, "--failed")

        assert exit_code == 0, output
        assert "discarded e02" in output
        assert [item.id for item in run.executions] == ["e01"]

    def test_failed_and_superseded_are_exclusive(self, tmp_path: Path) -> None:
        _single_run(tmp_path)

        exit_code, output = _flags(tmp_path, "--failed", "--superseded")

        assert exit_code != 0
        assert "--failed" in output and "--superseded" in output

    def test_dry_run_needs_a_sweep(self, tmp_path: Path) -> None:
        _single_run(tmp_path)

        exit_code, output = _flags(tmp_path, "--dry-run")

        assert exit_code != 0
        assert "--dry-run" in output


class TestPruneScratchAndEnv:
    def test_env_removes_environment_directories(self, tmp_path: Path) -> None:
        _single_run(tmp_path)
        (tmp_path / ".venv" / "bin").mkdir(parents=True)
        (tmp_path / "projects" / "proj-a" / "experiments" / "exp-x" / "__pycache__").mkdir()

        exit_code, output = _flags(tmp_path, "--env")

        assert exit_code == 0, output
        assert "Removed 2 environment" in output
        assert not (tmp_path / ".venv").exists()

    def test_scratch_empties_every_experiment_scratch(self, tmp_path: Path) -> None:
        _single_run(tmp_path)
        entry = tmp_path / "projects" / "proj-a" / "experiments" / "exp-x" / "scratch" / "probe"
        entry.mkdir(parents=True)
        (entry / "t.py").write_text("x")

        exit_code, output = _flags(tmp_path, "--scratch")

        assert exit_code == 0, output
        assert "Removed 1 scratch" in output
        assert not entry.exists()

    def test_dry_run_lists_and_keeps_everything(self, tmp_path: Path) -> None:
        _single_run(tmp_path)
        (tmp_path / ".venv").mkdir()
        entry = tmp_path / "projects" / "proj-a" / "experiments" / "exp-x" / "scratch" / "probe"
        entry.mkdir(parents=True)

        exit_code, output = _flags(tmp_path, "--scratch", "--env", "--dry-run")

        assert exit_code == 0, output
        assert "would remove .venv" in output
        assert "would remove projects/proj-a/experiments/exp-x/scratch/probe" in output
        assert (tmp_path / ".venv").exists() and entry.exists()

    def test_sweeps_combine(self, tmp_path: Path) -> None:
        run = _single_run(tmp_path)
        _seal(run, ("succeeded", "failed"))
        (tmp_path / ".venv").mkdir()

        exit_code, output = _flags(tmp_path, "--failed", "--env")

        assert exit_code == 0, output
        assert [item.id for item in run.executions] == ["e01"]
        assert not (tmp_path / ".venv").exists()
