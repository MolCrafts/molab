"""Per-Execution ``alive`` heartbeat — ownership by mtime, not JSON.

A live owner touches an empty file named :data:`ALIVE_NAME` inside the
physical Execution directory every :data:`HEARTBEAT_INTERVAL_SECONDS`.
Cross-host reapers treat an Execution as stale only when that file exists
and its mtime is older than :data:`HEARTBEAT_STALE_SECONDS`. A missing
file is **not** stale (the worker may still be starting, or an HPC job may
not have claimed yet).

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


def _alive_path(run: Run, execution_id: str) -> str:
    fs = run._disk()
    return fs.join(run.run_dir, "executions", execution_id, ALIVE_NAME)


def touch_alive(run: Run, execution_id: str) -> None:
    """Create or refresh the empty per-Execution ``alive`` file."""
    run._disk().touch(_alive_path(run, execution_id))


def alive_mtime(run: Run, execution_id: str) -> float | None:
    """Return the Execution's ``alive`` mtime, or ``None`` if it does not exist."""
    fs = run._disk()
    path = _alive_path(run, execution_id)
    try:
        if not fs.exists(path):
            return None
        return fs.stat(path).mtime
    except FileNotFoundError:
        return None


def is_alive_stale(run: Run, execution_id: str) -> bool:
    """Whether the Execution's ``alive`` exists and is older than the threshold.

    A missing file is **not** stale.
    """
    mtime = alive_mtime(run, execution_id)
    if mtime is None:
        return False
    return (time.time() - mtime) > HEARTBEAT_STALE_SECONDS


def unlink_alive(run: Run, execution_id: str) -> None:
    """Remove the Execution's ``alive`` file; missing is a no-op."""
    run._disk().remove(_alive_path(run, execution_id))
