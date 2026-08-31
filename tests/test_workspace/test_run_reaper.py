"""Zombie-run reaping (``molexp.workspace.run_reaper.reap_zombie_run``).

Same-host owners are pid-probed. Cross-host owners are reaped only when
``alive`` exists and its mtime is older than 600.0 s; a missing ``alive`` is
not stale. Reaping writes ``run.json`` failed, clears ownership, and unlinks
``alive``.
"""

from __future__ import annotations

import os
import platform
import time
from pathlib import Path

import pytest

from molexp.workspace.models import RunStatus
from molexp.workspace.run_heartbeat import (
    ALIVE_NAME,
    HEARTBEAT_STALE_SECONDS,
    touch_alive,
)
from molexp.workspace.run_reaper import reap_zombie_run


def _mark_running(run, *, pid: int, host: str) -> None:
    run._update_metadata(
        status=RunStatus.RUNNING,
        owner_pid=pid,
        owner_host=host,
    )


def _alive_path(run) -> Path:
    return Path(str(run.run_dir)) / ALIVE_NAME


def _dead_pid() -> int:
    pid = 2**22 - 7
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
    return pid


class TestReapZombieRun:
    def test_same_host_live_pid_is_not_reaped(self, run) -> None:
        run.materialize()
        _mark_running(run, pid=os.getpid(), host=platform.node())
        touch_alive(run)
        assert reap_zombie_run(run) is False
        assert run.status == "running"
        assert run.metadata.owner_pid == os.getpid()

    def test_same_host_dead_pid_is_reaped_to_failed_ownership_cleared_alive_unlinked(
        self, run
    ) -> None:
        run.materialize()
        _mark_running(run, pid=_dead_pid(), host=platform.node())
        touch_alive(run)
        assert _alive_path(run).is_file()

        assert reap_zombie_run(run) is True
        assert run.status == "failed"
        assert run.metadata.owner_pid is None
        assert run.metadata.owner_host is None
        assert not _alive_path(run).exists()

    def test_cross_host_missing_alive_is_not_reaped(self, run) -> None:
        run.materialize()
        _mark_running(run, pid=12345, host="hpc-login-01")
        assert not _alive_path(run).exists()
        assert reap_zombie_run(run) is False
        assert run.status == "running"

    def test_cross_host_fresh_alive_is_not_reaped(self, run) -> None:
        run.materialize()
        _mark_running(run, pid=12345, host="hpc-login-01")
        touch_alive(run)
        assert reap_zombie_run(run) is False
        assert run.status == "running"

    def test_cross_host_mtime_older_than_600s_is_reaped(self, run) -> None:
        assert HEARTBEAT_STALE_SECONDS == 600.0
        run.materialize()
        _mark_running(run, pid=12345, host="hpc-login-01")
        touch_alive(run)
        alive = _alive_path(run)
        old = time.time() - 601.0
        os.utime(alive, (old, old))

        assert reap_zombie_run(run) is True
        assert run.status == "failed"
        assert run.metadata.owner_pid is None
        assert run.metadata.owner_host is None
        assert not alive.exists()
