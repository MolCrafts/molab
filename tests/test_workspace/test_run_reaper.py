"""Zombie-Execution reaping (``molab.workspace.run_reaper.reap_zombie_run``).

A started attempt with a missing or stale ``alive`` file is reaped on every
host. A queued attempt with no ``alive`` file has not claimed, so it is left
alone. A same-host pid that is already dead is reaped too. Reaping seals the
attempt as ``failed`` and unlinks its ``alive``.
"""

from __future__ import annotations

import os
import platform
import time
from pathlib import Path

import pytest

from molab.workspace.domain import ExecutionMode, ExecutionStatus
from molab.workspace.execution_repository import ExecutionRepository
from molab.workspace.history import AgentRef
from molab.workspace.run_heartbeat import ALIVE_NAME, HEARTBEAT_STALE_SECONDS, touch_alive
from molab.workspace.run_reaper import reap_zombie_run

_TEST_AGENT = AgentRef(id="test", type="person", name="test")


def _repo(run) -> ExecutionRepository:
    ws = run.experiment.project.workspace
    return ExecutionRepository(
        ws.root,
        run.run_dir,
        run_id=run.id,
        project_id=run.experiment.project.id,
        fs=ws.fs,
    )


def _seed_running(run, *, pid: int, host: str, heartbeat: bool = False) -> str:
    state = _repo(run).create(
        mode=ExecutionMode.INITIAL,
        created_by=_TEST_AGENT,
        executor={"kind": "local", "host": host, "pid": pid},
    )
    _repo(run).start(state.id)
    if heartbeat:
        touch_alive(run, state.id)
    return state.id


def _alive_path(run, execution_id: str) -> Path:
    return Path(str(run.run_dir)) / "executions" / execution_id / ALIVE_NAME


def _dead_pid() -> int:
    pid = 2**22 - 7
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
    return pid


class TestReapZombieRun:
    def test_same_host_live_pid_is_not_reaped(self, run) -> None:
        run.materialize()
        execution_id = _seed_running(run, pid=os.getpid(), host=platform.node(), heartbeat=True)
        assert reap_zombie_run(run) is False
        assert _repo(run).get(execution_id).status is ExecutionStatus.RUNNING
        assert _alive_path(run, execution_id).is_file()

    def test_same_host_dead_pid_is_reaped_to_failed_and_alive_unlinked(self, run) -> None:
        run.materialize()
        execution_id = _seed_running(run, pid=_dead_pid(), host=platform.node(), heartbeat=True)
        assert _alive_path(run, execution_id).is_file()

        assert reap_zombie_run(run) is True
        state = _repo(run).get(execution_id)
        assert state.status is ExecutionStatus.FAILED
        assert state.error is not None
        assert state.error["type"] == "ZombieRun"
        assert not _alive_path(run, execution_id).exists()

    def test_cross_host_running_without_alive_is_reaped(self, run) -> None:
        run.materialize()
        execution_id = _seed_running(run, pid=12345, host="hpc-login-01")
        assert not _alive_path(run, execution_id).exists()
        assert reap_zombie_run(run) is True
        state = _repo(run).get(execution_id)
        assert state.status is ExecutionStatus.FAILED
        assert state.error is not None
        assert state.error["type"] == "ZombieRun"

    def test_cross_host_queued_without_alive_is_not_reaped(self, run) -> None:
        run.materialize()
        state = _repo(run).create(
            mode=ExecutionMode.INITIAL,
            created_by=_TEST_AGENT,
            executor={"kind": "local", "host": "hpc-login-01"},
        )
        assert reap_zombie_run(run) is False
        assert _repo(run).get(state.id).status is ExecutionStatus.QUEUED

    def test_same_host_live_pid_without_alive_is_not_reaped(self, run) -> None:
        run.materialize()
        execution_id = _seed_running(run, pid=os.getpid(), host=platform.node())
        assert not _alive_path(run, execution_id).exists()
        assert reap_zombie_run(run) is False
        assert _repo(run).get(execution_id).status is ExecutionStatus.RUNNING

    def test_cross_host_fresh_alive_is_not_reaped(self, run) -> None:
        run.materialize()
        execution_id = _seed_running(run, pid=12345, host="hpc-login-01", heartbeat=True)
        assert reap_zombie_run(run) is False
        assert _repo(run).get(execution_id).status is ExecutionStatus.RUNNING

    def test_cross_host_mtime_older_than_600s_is_reaped(self, run) -> None:
        assert HEARTBEAT_STALE_SECONDS == 600.0
        run.materialize()
        execution_id = _seed_running(run, pid=12345, host="hpc-login-01", heartbeat=True)
        alive = _alive_path(run, execution_id)
        old = time.time() - 601.0
        os.utime(alive, (old, old))

        assert reap_zombie_run(run) is True
        state = _repo(run).get(execution_id)
        assert state.status is ExecutionStatus.FAILED
        assert not alive.exists()
