"""Zombie-Execution reaping — flip a dead-owner active Execution to ``failed``.

Lives in the workspace layer (next to the run-lifecycle modules) so every
verb entry point — CLI *and* server (run-recovery bug 5) — consults the same
policy before deciding what to do with a ``running`` Execution; it used to
live in ``molexp.cli._common``, which left UI users facing a permanent 409 on
runs whose host process had died.

Schema v2: a :class:`Run` is immutable intent; the "live" unit is a physical
:class:`~molexp.workspace.domain.Execution` whose status is in
:data:`~molexp.workspace.domain.ACTIVE_EXECUTION_STATUSES`. Reaping seals each
stale active Execution as ``FAILED`` — it never mutates the Run definition.

Policy (CLAUDE.md, "Run status x verb selection"):

* **Same host** — the Execution's recorded ``executor.host`` is probed
  directly via ``executor.pid``; a dead pid means the owner crashed and the
  Execution is reaped.
* **Cross host** (molq / SLURM workers — the normal remote scenario) — no pid
  probe is possible, so the Execution is reaped **only** when its per-Execution
  ``alive`` file exists and the mtime is older than
  :data:`~molexp.workspace.run_heartbeat.HEARTBEAT_STALE_SECONDS`
  (refreshed every ``HEARTBEAT_INTERVAL_SECONDS`` ≈ 30 s by the owning
  worker). A fresh heartbeat, or no ``alive`` file at all, leaves the
  Execution alone — never kill a possibly-live HPC job on guesswork.
"""

from __future__ import annotations

import os
import platform
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from .domain import ACTIVE_EXECUTION_STATUSES, ExecutionStatus
from .run_heartbeat import HEARTBEAT_STALE_SECONDS, alive_mtime, is_alive_stale, unlink_alive

if TYPE_CHECKING:
    from .domain import Execution
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


def _executor_field(state: Execution, key: str) -> object | None:
    for container in (state.executor, state.environment):
        if isinstance(container, dict):
            value = container.get(key)
            if value is not None:
                return value
    return None


def _owner_is_live(state: Execution, run: Run) -> bool:
    host = _executor_field(state, "host")
    pid = _executor_field(state, "pid")
    if host == platform.node():
        # Same host: a recorded pid is probed directly; a missing pid means
        # the owner never claimed the attempt and it is treated as dead.
        return isinstance(pid, int) and pid > 0 and pid_alive(pid)
    return not is_alive_stale(run, state.id)


def _build_reason(state: Execution, run: Run) -> str:
    host = _executor_field(state, "host")
    pid = _executor_field(state, "pid")
    if host == platform.node():
        return (
            f"Execution {state.id} was left in 'running' state by a prior "
            f"invocation (pid={pid or '?'} host={host or '?'}) whose process is "
            "no longer alive.  Automatically marked FAILED."
        )
    mtime = alive_mtime(run, state.id)
    age_s = int(time.time() - mtime) if mtime is not None else 0
    return (
        f"Execution {state.id} was left in 'running' state on host {host or '?'} "
        f"(pid={pid or '?'}) and its alive heartbeat is {age_s}s old "
        f"(threshold {int(HEARTBEAT_STALE_SECONDS)}s).  "
        "Automatically marked FAILED."
    )


def reap_zombie_run(run: Run) -> bool:
    """Seal every stale active Execution of *run* as ``FAILED``.

    Same-host Executions are pid-probed directly: a recorded ``executor.pid``
    that no longer exists on this host means the owner died and the Execution
    is reaped.

    Cross-host Executions are reaped **only** when their per-Execution
    ``alive`` file exists and its mtime is older than
    :data:`~molexp.workspace.run_heartbeat.HEARTBEAT_STALE_SECONDS`. A fresh
    heartbeat, or a missing ``alive`` file, leaves the Execution alone.

    Returns ``True`` when at least one Execution was reaped, ``False`` when
    every active owner is (or may still be) alive.
    """
    reaped = False
    repo = run._execution_repository()
    for state in run.executions:
        if state.status not in ACTIVE_EXECUTION_STATUSES:
            continue
        if _owner_is_live(state, run):
            continue
        repo.seal(
            state.id,
            ExecutionStatus.FAILED,
            error={
                "type": "ZombieRun",
                "message": _build_reason(state, run),
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )
        unlink_alive(run, state.id)
        reaped = True
    return reaped
