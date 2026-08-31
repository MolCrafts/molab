"""CLI re-export of ``run_reaper.reap_zombie_run`` (persist-one-02).

The policy lives in ``molexp.workspace.run_reaper``; ``molexp.cli._common``
re-exports it. Same-host owners are pid-probed; cross-host owners are reaped
only when ``alive`` exists and its mtime is older than 600.0 s.
"""

from __future__ import annotations

import os
import platform
import time
from pathlib import Path

import pytest

from molexp.cli._common import reap_zombie_run
from molexp.workspace import Workspace
from molexp.workspace.models import RunStatus
from molexp.workspace.run_reaper import reap_zombie_run as workspace_reap_zombie_run


@pytest.fixture
def running_run(tmp_path):
    ws = Workspace(root=tmp_path, name="lab")
    exp = ws.add_project("p").add_experiment("e", workflow_source="s.py", params={})
    run = exp.add_run(params={"seed": 1})
    run.materialize()
    return run


def _mark_running(run, *, pid: int, host: str) -> None:
    run._update_metadata(status=RunStatus.RUNNING, owner_pid=pid, owner_host=host)


def _write_alive(run, *, age_seconds: float | None = 0.0) -> Path:
    alive = Path(str(run.run_dir)) / "alive"
    alive.write_text("")
    if age_seconds:
        stamp = time.time() - age_seconds
        os.utime(alive, (stamp, stamp))
    return alive


def _dead_pid() -> int:
    pid = 2**22 - 7
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
    return pid


class TestReapZombieRun:
    def test_cli_reexport_is_workspace_reaper(self) -> None:
        assert reap_zombie_run is workspace_reap_zombie_run

    def test_same_host_live_pid_is_left_alone(self, running_run) -> None:
        _mark_running(running_run, pid=os.getpid(), host=platform.node())
        _write_alive(running_run)
        assert reap_zombie_run(running_run) is False
        assert running_run.status == "running"

    def test_same_host_dead_pid_is_reaped_and_ownership_cleared(self, running_run) -> None:
        _mark_running(running_run, pid=_dead_pid(), host=platform.node())
        alive = _write_alive(running_run)
        assert reap_zombie_run(running_run) is True
        assert running_run.status == "failed"
        assert running_run.metadata.owner_pid is None
        assert running_run.metadata.owner_host is None
        assert not alive.exists()

    def test_cross_host_fresh_alive_is_left_alone(self, running_run) -> None:
        _mark_running(running_run, pid=12345, host="hpc-login-01")
        _write_alive(running_run)
        assert reap_zombie_run(running_run) is False
        assert running_run.status == "running"

    def test_cross_host_missing_alive_is_left_alone(self, running_run) -> None:
        _mark_running(running_run, pid=12345, host="hpc-login-01")
        assert reap_zombie_run(running_run) is False
        assert running_run.status == "running"

    def test_cross_host_stale_alive_is_reaped(self, running_run) -> None:
        # HEARTBEAT_STALE_SECONDS == 600.0
        _mark_running(running_run, pid=12345, host="hpc-login-01")
        _write_alive(running_run, age_seconds=601.0)
        assert reap_zombie_run(running_run) is True
        assert running_run.status == "failed"
