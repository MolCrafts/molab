"""``molab.workspace.lifecycle_ops.cancel_run`` — the canonical intervene verb.

vision-loop-07 §2: the workspace-layer core the ``molab.lifecycle.run_cancel``
capability (and any future CLI/server rewiring) shares. Its own contract, tested
once here:

* **reap first** — every verb entry reaps (`workspace.run_reaper`): a stale
  active Execution with a dead same-host owner flips to ``failed`` *before* the
  verb decides, so a zombie is never "cancelled";
* **running only** — any non-running status after reaping refuses loudly
  (``ValueError``);
* a genuine cancel seals every active Execution ``cancelled``.

Schema v2: a Run is immutable intent, so "cancel" acts on the physical
:class:`~molab.workspace.domain.ExecutionState` objects.
"""

from __future__ import annotations

import os
import platform
from pathlib import Path

import pytest

from molab.workspace import Workspace
from molab.workspace.domain import ExecutionMode, ExecutionStatus
from molab.workspace.execution_repository import ExecutionRepository
from molab.workspace.history import AgentRef
from molab.workspace.lifecycle_ops import cancel_run
from molab.workspace.run import Run

_TEST_AGENT = AgentRef(id="test", type="person", name="test")


@pytest.fixture
def run(tmp_path: Path) -> Run:
    ws = Workspace(root=tmp_path, name="cancel-lab")
    exp = ws.add_project("p").add_experiment("e", workflow_source="s.py", params={})
    new_run = exp.add_run(params={"seed": 1})
    new_run.materialize()
    return new_run


def _repo(run: Run) -> ExecutionRepository:
    ws = run.experiment.project.workspace
    return ExecutionRepository(
        ws.root,
        run.run_dir,
        run_id=run.id,
        project_id=run.experiment.project.id,
        fs=ws.fs,
    )


def _seed_running(run: Run, *, pid: int, host: str) -> str:
    state = _repo(run).create(
        mode=ExecutionMode.INITIAL,
        created_by=_TEST_AGENT,
        executor={"kind": "local", "host": host, "pid": pid},
    )
    _repo(run).start(state.id)
    return state.id


def _seed_terminal(run: Run, status: ExecutionStatus) -> str:
    state = _repo(run).create(mode=ExecutionMode.INITIAL, created_by=_TEST_AGENT)
    _repo(run).start(state.id)
    _repo(run).seal(state.id, status)
    return state.id


def _dead_pid() -> int:
    """A pid that is exceedingly unlikely to exist on this host."""
    pid = 2**22 - 7
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
    return pid


class TestCancelRunning:
    def test_live_running_run_is_cancelled(self, run: Run) -> None:
        execution_id = _seed_running(run, pid=os.getpid(), host=platform.node())
        cancel_run(run)
        assert _repo(run).get(execution_id).status is ExecutionStatus.CANCELLED
        assert run.status_summary.active == 0
        assert run.status_summary.by_status["cancelled"] == 1

    def test_cancel_clears_the_active_attempt(self, run: Run) -> None:
        execution_id = _seed_running(run, pid=os.getpid(), host=platform.node())
        cancel_run(run)
        state = _repo(run).get(execution_id)
        assert state.status is ExecutionStatus.CANCELLED
        assert state.finished_at is not None
        assert run.status_summary.active == 0


class TestRefusesNonRunning:
    def test_pending_run_refuses_and_stays_unstarted(self, run: Run) -> None:
        with pytest.raises(ValueError, match="pending"):
            cancel_run(run)
        assert run.status_summary.not_started is True

    @pytest.mark.parametrize(
        "status",
        [ExecutionStatus.SUCCEEDED, ExecutionStatus.FAILED, ExecutionStatus.CANCELLED],
        ids=["succeeded", "failed", "cancelled"],
    )
    def test_terminal_run_refuses_and_preserves_status(
        self, run: Run, status: ExecutionStatus
    ) -> None:
        execution_id = _seed_terminal(run, status)
        with pytest.raises(ValueError, match=status.value):
            cancel_run(run)
        assert _repo(run).get(execution_id).status is status


class TestZombieReapedFirst:
    def test_dead_owner_is_reaped_then_refused(self, run: Run) -> None:
        """Same-host dead pid → reap flips to failed → cancel refuses (not running)."""
        execution_id = _seed_running(run, pid=_dead_pid(), host=platform.node())
        with pytest.raises(ValueError, match="failed"):
            cancel_run(run)
        assert _repo(run).get(execution_id).status is ExecutionStatus.FAILED


class TestCancelPending:
    def test_pending_cancel_creates_through_run(self, run: Run) -> None:
        """arch-own-02a §6: the pending-cancel attempt is created by ``Run.create_execution``."""
        assert cancel_run(run, allow_pending=True) is None

        [execution] = run.executions
        assert execution.mode is ExecutionMode.INITIAL
        assert execution.status is ExecutionStatus.CANCELLED
        assert "config_hash" in execution.environment
        assert execution.created_by.id == "operator"
