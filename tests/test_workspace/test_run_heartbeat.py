"""Alive-file heartbeat (``molexp.workspace.run_heartbeat``).

Ownership heartbeat is the mtime of an empty run-root ``alive`` file, not a
JSON field. ``touch_alive`` / ``is_alive_stale`` / ``unlink_alive`` go through
``Folder._disk()``. A missing ``alive`` is not stale. ``refresh_heartbeat``
touches ``alive`` and must not rewrite ``run.json``.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from molexp.workspace.run_heartbeat import (
    ALIVE_NAME,
    HEARTBEAT_INTERVAL_SECONDS,
    HEARTBEAT_STALE_SECONDS,
    is_alive_stale,
    touch_alive,
    unlink_alive,
)


def _alive_path(run) -> Path:
    return Path(str(run.run_dir)) / ALIVE_NAME


class TestTouchAlive:
    def test_touch_creates_empty_file_and_updates_mtime(self, run) -> None:
        assert ALIVE_NAME == "alive"
        run.materialize()
        alive = _alive_path(run)
        assert not alive.exists()

        touch_alive(run)
        assert alive.is_file()
        assert alive.stat().st_size == 0

        os.utime(alive, (alive.stat().st_mtime - 10.0, alive.stat().st_mtime - 10.0))
        before = alive.stat().st_mtime
        touch_alive(run)
        assert alive.stat().st_size == 0
        assert alive.stat().st_mtime > before


class TestIsAliveStale:
    def test_missing_file_is_not_stale(self, run) -> None:
        run.materialize()
        assert not _alive_path(run).exists()
        assert is_alive_stale(run) is False

    def test_fresh_mtime_is_not_stale(self, run) -> None:
        run.materialize()
        touch_alive(run)
        assert is_alive_stale(run) is False

    def test_old_mtime_is_stale(self, run) -> None:
        assert HEARTBEAT_STALE_SECONDS == 600.0
        run.materialize()
        touch_alive(run)
        alive = _alive_path(run)
        old = time.time() - 601.0
        os.utime(alive, (old, old))
        assert is_alive_stale(run) is True


class TestUnlinkAlive:
    def test_unlink_removes_alive_and_is_idempotent(self, run) -> None:
        run.materialize()
        touch_alive(run)
        alive = _alive_path(run)
        assert alive.is_file()
        unlink_alive(run)
        assert not alive.exists()
        unlink_alive(run)
        assert not alive.exists()


class TestRefreshHeartbeat:
    def test_refresh_touches_alive_without_rewriting_run_json(self, run) -> None:
        assert HEARTBEAT_INTERVAL_SECONDS == 30.0
        ctx = run.start()
        with ctx:
            alive = _alive_path(run)
            run_json = Path(str(run.run_dir)) / "run.json"
            assert alive.is_file()
            assert alive.stat().st_size == 0
            os.utime(alive, (alive.stat().st_mtime - 10.0, alive.stat().st_mtime - 10.0))
            before_mtime = alive.stat().st_mtime
            before_bytes = run_json.read_bytes()

            ctx._lifecycle.refresh_heartbeat()

            assert alive.stat().st_mtime > before_mtime
            assert alive.stat().st_size == 0
            assert run_json.read_bytes() == before_bytes

    def test_refresh_is_noop_before_claim(self, experiment) -> None:
        fresh = experiment.add_run(params={"lr": 9e-9})
        ctx = fresh.start()
        ctx._lifecycle.refresh_heartbeat()
        assert not _alive_path(fresh).exists()
