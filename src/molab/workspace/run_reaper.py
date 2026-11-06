"""Zombie-Execution reaping — flip a dead-owner active Execution to ``failed``.

Lives in the workspace layer (next to the run-lifecycle modules) so every
verb entry point — CLI *and* server (run-recovery bug 5) — consults the same
policy before deciding what to do with a ``running`` Execution; it used to
live in ``molab.cli._common``, which left UI users facing a permanent 409 on
runs whose host process had died.

Schema v2: a :class:`Run` is immutable intent; the "live" unit is a physical
:class:`~molab.workspace.domain.Execution` whose status is in
:data:`~molab.workspace.domain.ACTIVE_EXECUTION_STATUSES`. Reaping seals each
stale active Execution as ``FAILED`` — it never mutates the Run definition.

Policy (CLAUDE.md, "Run status x verb selection"):

* **Not started** (``queued``, no ``alive`` yet) — left alone. A missing
  heartbeat means the worker has not claimed the attempt.
* **Started on another host** — a missing ``alive`` file means the owner is
  gone. The file is deleted only after ``seal``. A file older than
  :data:`~molab.workspace.run_heartbeat.HEARTBEAT_STALE_SECONDS` is stale on
  every host.
* **Same host** — a recorded ``executor.pid`` that is not alive is reaped. A
  live pid is the owner even in the moment before the first touch.
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


def _started(state: Execution) -> bool:
    """Whether the owner has claimed this attempt.

    ``start`` writes ``running`` before the first heartbeat touch. A queued
    attempt has not claimed, so a missing ``alive`` file is not evidence
    that it died.
    """
    return state.status in {ExecutionStatus.RUNNING, ExecutionStatus.FINALIZING}


def _heartbeat_dead(state: Execution, run: Run) -> bool:
    """A claimed attempt whose heartbeat is missing on another host, or stale.

    On this machine a live pid is the owner, so a missing file in the moment
    before the first touch does not reap it. A remote host that has already
    claimed the attempt deletes ``alive`` only after ``seal``; no file means
    that owner is gone.
    """
    if not _started(state):
        return False
    mtime = alive_mtime(run, state.id)
    if mtime is None:
        host = _executor_field(state, "host")
        return isinstance(host, str) and host != platform.node()
    return (time.time() - mtime) > HEARTBEAT_STALE_SECONDS


def _owner_is_live(state: Execution, run: Run) -> bool:
    if _heartbeat_dead(state, run):
        return False
    host = _executor_field(state, "host")
    pid = _executor_field(state, "pid")
    if host == platform.node():
        # Same host: a recorded pid is probed directly; a missing pid means
        # the owner never claimed the attempt and it is treated as dead.
        return isinstance(pid, int) and pid > 0 and pid_alive(pid)
    # Cross-host and not heartbeat-dead: a queued attempt with no file, or
    # a started attempt with a fresh file.
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
    if mtime is None:
        heartbeat = "missing"
    else:
        heartbeat = f"{int(time.time() - mtime)}s old (threshold {int(HEARTBEAT_STALE_SECONDS)}s)"
    return (
        f"Execution {state.id} was left in 'running' state on host {host or '?'} "
        f"(pid={pid or '?'}) and its alive heartbeat is {heartbeat}.  "
        "Automatically marked FAILED."
    )


def reap_zombie_run(run: Run) -> bool:
    """Seal every stale active Execution of *run* as ``FAILED``.

    Same-host Executions are pid-probed directly: a recorded ``executor.pid``
    that no longer exists on this host means the owner died and the Execution
    is reaped.

    Cross-host Executions are reaped **only** when their per-Execution
    ``alive`` file exists and its mtime is older than
    :data:`~molab.workspace.run_heartbeat.HEARTBEAT_STALE_SECONDS`. A fresh
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
