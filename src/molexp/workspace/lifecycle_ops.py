"""Run-lifecycle operation cores shared by CLI, server, and harness capabilities.

Workspace-layer homes for verb bodies that must be reachable from the harness
capability handlers (harness→workspace is legal; harness→services is not).
Each op enforces the frozen verb law itself — the capability layer adds
gating, never semantics.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from .run import Run

__all__ = ["cancel_run"]


def cancel_run(
    run: Run,
    *,
    signal_executor: Callable[[Run], str | None] | None = None,
    allow_pending: bool = False,
) -> str | None:
    """Cancel an actively-running *run* — the canonical intervene verb.

    The ONE cancel body shared by the CLI (``molexp runs cancel``), the
    server (``POST .../{run_id}/cancel``) and the harness lifecycle
    capability. Reaps first (every verb entry reaps — a stale ``running``
    with a dead owner flips to ``failed`` before the verb decides), then
    refuses any status outside the domain loudly: there is nothing to
    intervene on.

    Args:
        run: The run to cancel.
        signal_executor: Optional hook that signals the live executor
            (molq scheduler job / local worker pid) before the status flip —
            e.g. ``molexp.plugins.submit_molq.cancel.try_cancel``. It returns
            ``None`` on success or a warning string (never raises for
            caller-actionable reasons). Workspace stays scheduler-agnostic;
            the shells inject the plugin hook.
        allow_pending: Also cancel a ``pending`` run (mark it ``cancelled``
            so plain ``run`` never starts it) — bulk-cancel CLI semantics.
            The default keeps the strict intervene domain: ``running`` only.

    Returns:
        ``None`` on a clean cancel, or the executor-signal warning (the run's
        status is flipped to ``cancelled`` regardless, so the recorded state
        always reflects the user's intent).

    Raises:
        ValueError: The run's status is outside the verb domain after
            reaping. The message names the actual status and the verb that
            owns it (``resume`` / ``rerun`` for failed/cancelled; nothing
            for succeeded; plain ``run`` for pending unless
            ``allow_pending``).
    """
    from .run_reaper import reap_zombie_run

    reap_zombie_run(run)
    status = str(run.status).lower()
    if status == "pending" and allow_pending:
        run.cancel()
        return None
    if status != "running":
        owner = {
            "pending": "it has not started — `molexp run` owns pending runs",
            "failed": "it already stopped — resume/rerun own failed runs",
            "cancelled": "it is already cancelled — resume/rerun own cancelled runs",
            "succeeded": "it finished — read its results instead",
        }.get(status, "only a running run can be cancelled")
        raise ValueError(f"run {run.id} is {status!r}, not running; {owner}")
    warning = signal_executor(run) if signal_executor is not None else None
    if str(run.status).lower() == "running":
        # The signal hook flips the status itself on success; flip here for
        # the no-hook and warning paths so intent always lands on disk.
        run.cancel()
    return warning
