"""Per-Execution alive-file heartbeat (``molab.workspace.run_heartbeat``).

Ownership heartbeat is the mtime of an empty ``alive`` file inside one
physical Execution directory, not a JSON field. ``touch_alive`` /
``is_alive_stale`` / ``unlink_alive`` go through ``Folder._disk()``. A missing
``alive`` is not stale. Refreshing the heartbeat must not rewrite ``run.json``.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from molab.workspace.domain import ExecutionMode
from molab.workspace.execution_repository import ExecutionRepository
from molab.workspace.history import AgentRef
from molab.workspace.run_heartbeat import (
    ALIVE_NAME,
    HEARTBEAT_INTERVAL_SECONDS,
    HEARTBEAT_STALE_SECONDS,
    is_alive_stale,
    touch_alive,
    unlink_alive,
)

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


def _new_execution_id(run) -> str:
    return _repo(run).create(mode=ExecutionMode.INITIAL, created_by=_TEST_AGENT).id


def _alive_path(run, execution_id: str) -> Path:
    return Path(str(run.run_dir)) / "executions" / execution_id / ALIVE_NAME


class TestTouchAlive:
    def test_touch_creates_empty_file_and_updates_mtime(self, run) -> None:
        assert ALIVE_NAME == "alive"
        run.materialize()
        execution_id = _new_execution_id(run)
        alive = _alive_path(run, execution_id)
        assert not alive.exists()

        touch_alive(run, execution_id)
        assert alive.is_file()
        assert alive.stat().st_size == 0

        os.utime(alive, (alive.stat().st_mtime - 10.0, alive.stat().st_mtime - 10.0))
        before = alive.stat().st_mtime
        touch_alive(run, execution_id)
        assert alive.stat().st_size == 0
        assert alive.stat().st_mtime > before


class TestIsAliveStale:
    def test_missing_file_is_not_stale(self, run) -> None:
        run.materialize()
        execution_id = _new_execution_id(run)
        assert not _alive_path(run, execution_id).exists()
        assert is_alive_stale(run, execution_id) is False

    def test_fresh_mtime_is_not_stale(self, run) -> None:
        run.materialize()
        execution_id = _new_execution_id(run)
        touch_alive(run, execution_id)
        assert is_alive_stale(run, execution_id) is False

    def test_old_mtime_is_stale(self, run) -> None:
        assert HEARTBEAT_STALE_SECONDS == 600.0
        run.materialize()
        execution_id = _new_execution_id(run)
        touch_alive(run, execution_id)
        alive = _alive_path(run, execution_id)
        old = time.time() - 601.0
        os.utime(alive, (old, old))
        assert is_alive_stale(run, execution_id) is True


class TestUnlinkAlive:
    def test_unlink_removes_alive_and_is_idempotent(self, run) -> None:
        run.materialize()
        execution_id = _new_execution_id(run)
        touch_alive(run, execution_id)
        alive = _alive_path(run, execution_id)
        assert alive.is_file()
        unlink_alive(run, execution_id)
        assert not alive.exists()
        unlink_alive(run, execution_id)
        assert not alive.exists()


class TestRefreshHeartbeat:
    def test_heartbeat_touches_per_execution_alive_without_rewriting_run_json(self, run) -> None:
        assert HEARTBEAT_INTERVAL_SECONDS == 30.0
        ctx = run.start()
        with ctx:
            alive = Path(str(run.run_dir)) / "executions" / ctx.id / "alive"
            run_json = Path(str(run.run_dir)) / "run.json"
            assert alive.is_file()
            assert alive.stat().st_size == 0
            os.utime(alive, (alive.stat().st_mtime - 10.0, alive.stat().st_mtime - 10.0))
            before_mtime = alive.stat().st_mtime
            before_bytes = run_json.read_bytes()

            # One heartbeat beat refreshes the per-execution alive mtime.
            touch_alive(run, ctx.id)

            assert alive.stat().st_mtime > before_mtime
            assert alive.stat().st_size == 0
            assert run_json.read_bytes() == before_bytes

    def test_heartbeat_is_noop_before_execution_entered(self, experiment) -> None:
        fresh = experiment.add_run(params={"lr": 9e-9})
        fresh.start()  # constructed but not entered → no execution, no alive file
        assert not (Path(str(fresh.run_dir)) / "executions").exists()
