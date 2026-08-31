"""Run-root ``alive`` file — ownership heartbeat by mtime, not JSON.

A live owner touches an empty file named :data:`ALIVE_NAME` at the run
root every :data:`HEARTBEAT_INTERVAL_SECONDS`. Cross-host reapers treat
the run as stale only when that file exists and its mtime is older than
:data:`HEARTBEAT_STALE_SECONDS`. A missing file is **not** stale (the
worker may still be starting, or an HPC job may not have claimed yet).

All I/O goes through :meth:`Folder._disk` (``FileSystem.touch`` /
``stat`` / ``remove``).
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .run import Run

ALIVE_NAME = "alive"
HEARTBEAT_INTERVAL_SECONDS = 30.0
HEARTBEAT_STALE_SECONDS = 600.0

__all__ = [
    "ALIVE_NAME",
    "HEARTBEAT_INTERVAL_SECONDS",
    "HEARTBEAT_STALE_SECONDS",
    "alive_mtime",
    "is_alive_stale",
    "touch_alive",
    "unlink_alive",
]


def _alive_path(run: Run) -> str:
    fs = run._disk()
    return fs.join(run.run_dir, ALIVE_NAME)


def touch_alive(run: Run) -> None:
    """Create or refresh the empty run-root ``alive`` file (mtime heartbeat)."""
    fs = run._disk()
    fs.touch(_alive_path(run))


def alive_mtime(run: Run) -> float | None:
    """Return the ``alive`` file mtime, or ``None`` if it does not exist."""
    fs = run._disk()
    path = _alive_path(run)
    try:
        if not fs.exists(path):
            return None
        return fs.stat(path).mtime
    except FileNotFoundError:
        return None


def is_alive_stale(run: Run) -> bool:
    """Whether ``alive`` exists and is older than :data:`HEARTBEAT_STALE_SECONDS`.

    A missing file is **not** stale.
    """
    mtime = alive_mtime(run)
    if mtime is None:
        return False
    return (time.time() - mtime) > HEARTBEAT_STALE_SECONDS


def unlink_alive(run: Run) -> None:
    """Remove the ``alive`` file; missing is a no-op."""
    run._disk().remove(_alive_path(run))
