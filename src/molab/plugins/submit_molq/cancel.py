"""Cancel helpers for Run / latest-Execution.

Used by the server cancel route and by the interactive tree monitor
before deleting a still-running run.
Design rule: *never force*.  If we can't cancel cleanly (molq job id
missing, host mismatch, dead pid, molq not installed), we return a
warning string and the caller falls back to skipping the delete.

Three outcomes:

- ``("molq", cluster_name, molq_job_id)`` — cancel via ``molq.Submitor``
- ``("local", pid)`` — send ``SIGTERM`` on the same host
- ``("none", reason)`` — cannot cancel; caller should warn, not delete
"""

from __future__ import annotations

import contextlib
import os
import platform
import signal
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from molab.workspace.domain import ACTIVE_EXECUTION_STATUSES, Execution

from .metadata import normalize_executor_info

if TYPE_CHECKING:
    from molab.workspace.run import Run


@dataclass(frozen=True)
class CancelPlan:
    """Classification of how to cancel a run."""

    kind: Literal["molq", "local", "none"]
    detail: str  # pid-as-str / reason / cluster label
    job_id: str | None = None  # molq internal job_id (only for kind=="molq")
    scheduler: str | None = None  # molq scheduler backend (kind=="molq")
    cluster: str | None = None  # molq cluster name (kind=="molq")
    scheduler_job_id: str | None = None  # native scheduler id fallback


def _active_execution(run: Run) -> Execution | None:
    """Newest non-terminal Execution realizing *run*, else ``None``."""
    active = [ex for ex in run.executions if ex.status in ACTIVE_EXECUTION_STATUSES]
    return active[-1] if active else None


def classify(run: Run) -> CancelPlan:
    """Decide how to cancel *run* without executing anything.

    Pure inspection — reads only Execution state.  The returned plan tells
    the caller exactly what to do (or why it can't).
    """
    active = _active_execution(run)
    if active is None:
        detail = "already terminal" if run.executions else "no active execution"
        return CancelPlan(kind="none", detail=detail)

    executor = dict(active.executor or {})
    info = normalize_executor_info(executor, {})
    if info.get("backend") == "molq" and (info.get("job_id") or info.get("scheduler_job_id")):
        return CancelPlan(
            kind="molq",
            detail=info.get("cluster_name", ""),
            job_id=info.get("job_id"),
            scheduler=info.get("scheduler"),
            cluster=info.get("cluster_name"),
            scheduler_job_id=info.get("scheduler_job_id"),
        )

    pid = executor.get("pid")
    host = executor.get("host")
    if pid is not None and host == platform.node():
        return CancelPlan(kind="local", detail=str(pid))

    reason = "no molq job id"
    if pid is not None and host and host != platform.node():
        reason = f"pid on different host ({host!r})"
    elif pid is None:
        reason = "no pid / scheduler info recorded"
    return CancelPlan(kind="none", detail=reason)


def try_cancel(
    run: Run,
    *,
    fallback_scheduler: str = "local",
    fallback_cluster: str = "default",
) -> str | None:
    """Attempt to cancel *run*.  Return ``None`` on success, a warning
    message otherwise.  Never raises for caller-actionable reasons.

    ``fallback_scheduler`` / ``fallback_cluster`` fill in when the run's
    recorded executor_info lacks them (the CLI forwards its ``--scheduler`` /
    ``--cluster`` flags here).
    """
    plan = classify(run)
    if plan.kind == "none":
        return f"cannot cancel {run.id[:6]}: {plan.detail}"

    active = _active_execution(run)
    if active is None:  # pragma: no cover — classify() guarantees an active Execution here
        return f"cannot cancel {run.id[:6]}: no active execution"

    if plan.kind == "local":
        pid = int(plan.detail)
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            # Already dead — seal the attempt and move on.
            run.cancel(active.id)
            return None
        except PermissionError:
            return f"cannot signal pid {pid}: permission denied"
        run.cancel(active.id)
        return None

    # plan.kind == "molq"
    from molq import Cluster, Submitor

    scheduler = plan.scheduler or fallback_scheduler
    cluster = plan.cluster or fallback_cluster
    submitor = Submitor(Cluster(name=cluster, scheduler=scheduler))
    try:
        if plan.job_id is not None:
            submitor.cancel_job(plan.job_id)
        elif plan.scheduler_job_id is not None:
            submitor._scheduler_impl.cancel(plan.scheduler_job_id)
        else:  # pragma: no cover — classify() guarantees one of the two ids
            return f"cannot cancel {run.id[:6]}: no molq job metadata"
    except Exception as exc:  # molq raises a hierarchy, but surface all
        return f"molq cancel failed for {run.id[:6]}: {exc}"
    finally:
        with contextlib.suppress(Exception):
            submitor.close()
    run.cancel(active.id)
    return None
