"""Run-lifecycle operation cores shared by CLI, server, and harness capabilities.

Workspace-layer homes for verb bodies that must be reachable from the harness
capability handlers (harness→workspace is legal; harness→services is not).
Each op enforces the frozen verb law itself — the capability layer adds
gating, never semantics.

Schema v2: a :class:`Run` is immutable intent, so ``cancel`` intervenes on the
active physical :class:`~molexp.workspace.domain.Execution` objects —
never on a scalar run status.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from .run import Run

__all__ = ["cancel_run"]


def _scalar_status(run: Run) -> str:
    """Derive the single run-status label the verb law speaks in."""
    summary = run.status_summary
    if summary.not_started:
        return "pending"
    if summary.active > 0:
        return "running"
    for status in ("failed", "cancelled", "interrupted", "succeeded"):
        if summary.by_status.get(status):
            return status
    return "succeeded" if summary.total else "pending"


def cancel_run(
    run: Run,
    *,
    signal_executor: Callable[[Run], str | None] | None = None,
    allow_pending: bool = False,
) -> str | None:
    """Cancel the actively-running Executions of *run* — the intervene verb.

    The ONE cancel body shared by the CLI (``molexp runs cancel``), the
    server and the harness lifecycle capability. Reaps first (every verb
    entry reaps — a stale active Execution with a dead owner flips to
    ``failed`` before the verb decides), then refuses anything outside the
    domain loudly: there is nothing to intervene on.

    Args:
        run: The run to cancel.
        signal_executor: Optional hook that signals the live executor
            (molq scheduler job / local worker pid) before the status flip.
            It returns ``None`` on success or a warning string (never raises
            for caller-actionable reasons). Workspace stays scheduler-agnostic;
            the shells inject the plugin hook.
        allow_pending: Also cancel a ``pending`` run — record a CANCELLED
            initial Execution so plain ``run`` never starts it (bulk-cancel
            CLI semantics). The default keeps the strict intervene domain:
            ``running`` only.

    Returns:
        ``None`` on a clean cancel, or the executor-signal warning (the
        workspace state is flipped to ``cancelled`` regardless, so the
        recorded state always reflects the user's intent).

    Raises:
        ValueError: The run has no active Execution after reaping. The message
            names the actual status and the verb that owns it (``resume`` /
            ``rerun`` for failed/cancelled; nothing for succeeded; plain
            ``run`` for pending unless ``allow_pending``).
    """
    from .domain import ACTIVE_EXECUTION_STATUSES, ExecutionMode, ExecutionStatus
    from .history import AgentRef
    from .run_reaper import reap_zombie_run

    reap_zombie_run(run)
    active = [state for state in run.executions if state.status in ACTIVE_EXECUTION_STATUSES]
    if not active:
        status = _scalar_status(run)
        if status == "pending" and allow_pending:
            repo = run._execution_repository()
            state = repo.create(
                mode=ExecutionMode.INITIAL,
                created_by=AgentRef(id="operator", type="person", name="operator"),
            )
            repo.seal(state.id, ExecutionStatus.CANCELLED)
            return None
        owner = {
            "pending": "it has not started — `molexp run` owns pending runs",
            "failed": "it already stopped — resume/rerun own failed runs",
            "cancelled": "it is already cancelled — resume/rerun own cancelled runs",
            "interrupted": "it is already interrupted — resume owns interrupted runs",
            "succeeded": "it finished — read its results instead",
        }.get(status, "only a running run can be cancelled")
        raise ValueError(f"run {run.id} is {status!r}, not running; {owner}")

    warning = signal_executor(run) if signal_executor is not None else None
    for state in active:
        run.cancel(state.id)
    return warning
