"""Zombie-run reaping — flip a dead-owner ``running`` run back to ``failed``.

Lives in the workspace layer (next to the run-lifecycle modules) so every
verb entry point — CLI *and* server (run-recovery bug 5) — consults the same
policy before deciding what to do with a ``running`` run; it used to live in
``molexp.cli._common``, which left UI users facing a permanent 409 on runs
whose host process had died.

Policy (CLAUDE.md, "Run status x verb selection"):

* **Same host** — the recorded ``owner_pid`` is probed directly; a dead pid
  means the owner crashed and the run is reaped.
* **Cross host** (molq / SLURM workers — the normal remote scenario) — no pid
  probe is possible, so the run is reaped **only** when its ``alive`` file
  exists and the mtime is older than
  :data:`~molexp.workspace.run_heartbeat.HEARTBEAT_STALE_SECONDS`
  (refreshed every ``HEARTBEAT_INTERVAL_SECONDS`` ≈ 30 s by the owning
  worker). A fresh heartbeat, or no ``alive`` file at all, leaves the run
  alone — never kill a possibly-live HPC job on guesswork.
"""

from __future__ import annotations

import os
import platform
import time
from datetime import datetime
from typing import TYPE_CHECKING

from .models import ErrorInfo, RunStatus
from .run_heartbeat import HEARTBEAT_STALE_SECONDS, alive_mtime, is_alive_stale, unlink_alive

if TYPE_CHECKING:
    from .run import Run

__all__ = ["pid_alive", "reap_zombie_run"]


def pid_alive(pid: int) -> bool:
    """Return ``True`` if a process with *pid* exists on this host."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def reap_zombie_run(run: Run) -> bool:
    """Mark a stale ``RUNNING`` run as ``FAILED`` if its owner is dead.

    Same-host runs are pid-probed directly: a recorded ``owner_pid`` that no
    longer exists on this host means the owner died and the run is reaped.

    Cross-host runs are reaped **only** when ``alive`` exists and its mtime
    is older than :data:`~molexp.workspace.run_heartbeat.HEARTBEAT_STALE_SECONDS`.
    A fresh heartbeat, or a missing ``alive`` file, leaves the run alone.

    Reaping writes ``status=failed`` and clears ownership on ``run.json``,
    then unlinks ``alive``.

    Returns ``True`` when the run was reaped (status flipped from
    ``running`` to ``failed``), ``False`` when the owner is (or may still
    be) alive.
    """
    meta = run.metadata
    if meta.status is not RunStatus.RUNNING:
        return False

    host = meta.owner_host
    same_host = host == platform.node()

    if same_host:
        if meta.owner_pid is not None and pid_alive(meta.owner_pid):
            return False  # live owner on this host
        reason = (
            f"Run was left in 'running' state by a prior invocation "
            f"(pid={meta.owner_pid or '?'} host={host or '?'}) whose process is "
            "no longer alive.  Automatically marked FAILED."
        )
    else:
        if not is_alive_stale(run):
            # Fresh heartbeat, or no alive file yet (worker still
            # starting) — assume alive.
            return False
        mtime = alive_mtime(run)
        age_s = int(time.time() - mtime) if mtime is not None else 0
        reason = (
            f"Run was left in 'running' state on host {host or '?'} "
            f"(pid={meta.owner_pid or '?'}) and its alive heartbeat is "
            f"{age_s}s old "
            f"(threshold {int(HEARTBEAT_STALE_SECONDS)}s).  "
            "Automatically marked FAILED."
        )

    naive_now = datetime.now()
    run._update_metadata(
        status=RunStatus.FAILED,
        finished_at=naive_now,
        owner_pid=None,
        owner_host=None,
        error=ErrorInfo(
            type="ZombieRun",
            message=reason,
            timestamp=naive_now,
        ),
    )
    unlink_alive(run)
    return True
