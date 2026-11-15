"""Run-lifecycle operation cores shared by the CLI and the server.

Each op enforces the frozen verb law itself — a caller adds gating, never
semantics. ``molab runs cancel`` and ``POST …/executions/{id}/cancel`` both
call :func:`cancel_run`.

Schema v2: a :class:`Run` is immutable intent, so ``cancel`` intervenes on the
active physical :class:`~molab.workspace.domain.Execution` objects —
never on a scalar run status.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from .domain import Execution
    from .run import Run

__all__ = ["CANCEL_REQUESTED", "cancel_run", "refuse_attempts_away"]

#: ``executor`` key on an attempt left open by a cancel the scheduler accepted.
#: Its reconcile reads it: a job the scheduler then no longer knows (not
#: listed, no accounting) ended by that cancel.
CANCEL_REQUESTED = "cancel_requested_at"


def cancel_run(
    run: Run,
    *,
    signal_executor: Callable[[Run], str | None] | None = None,
    allow_pending: bool = False,
    execution_id: str | None = None,
) -> str | None:
    """Cancel the actively-running Executions of *run* — the intervene verb.

    Called by ``molab runs cancel`` and by the server cancel route. Reaps
    first (every verb entry reaps — a stale active Execution with a dead
    owner flips to ``failed`` before the verb decides), then refuses anything
    outside the domain loudly: there is nothing to intervene on.

    Args:
        run: The run to cancel.
        signal_executor: Optional hook that signals the live executor
            (molq scheduler job / local worker pid) before the status flip.
            It returns ``None`` on success or a warning string (never raises
            for caller-actionable reasons). It must not seal the attempt;
            this function seals, except an attempt left to its stage-out
            (:func:`_seal_cancelled`). Workspace stays scheduler-agnostic;
            the shells inject the plugin hook.
        allow_pending: Also cancel a ``pending`` run — record a CANCELLED
            initial Execution so plain ``run`` never starts it (bulk-cancel
            CLI semantics). The default keeps the strict intervene domain:
            ``running`` only. Ignored when *execution_id* is set.
        execution_id: Cancel this attempt only. ``None`` cancels every active
            attempt of the run, which is the CLI's run-scoped cancel.

    Returns:
        ``None`` on a clean cancel, or the executor-signal warning (the
        workspace state is then flipped to ``cancelled`` regardless, so the
        recorded state always reflects the user's intent).

    Raises:
        KeyError: *execution_id* names no attempt of this run.
        ValueError: The run has no active Execution after reaping, or
            *execution_id* is not active. The message names the actual status
            and the verb that owns it (``resume`` / ``rerun`` for
            failed/cancelled; nothing for succeeded; plain ``run`` for pending
            unless ``allow_pending``).
    """
    from .domain import ACTIVE_EXECUTION_STATUSES
    from .history import AgentRef
    from .run_reaper import reap_zombie_run

    reap_zombie_run(run)
    if execution_id is not None:
        state = run.execution(execution_id)
        if state.status not in ACTIVE_EXECUTION_STATUSES:
            raise ValueError(
                f"execution {execution_id!r} of run {run.id} is {state.status.value!r}, not running"
            )
        warning = signal_executor(run) if signal_executor is not None else None
        _seal_cancelled(run, state, signalled=warning is None)
        return warning

    active = [state for state in run.executions if state.status in ACTIVE_EXECUTION_STATUSES]
    if not active:
        status = run.status_label
        if status == "pending" and allow_pending:
            state = run._create_execution(
                created_by=AgentRef(id="operator", type="person", name="operator")
            )
            run.cancel(state.id)
            return None
        owner = {
            "pending": "it has not started — `molab run` owns pending runs",
            "failed": "it already stopped — resume/rerun own failed runs",
            "cancelled": "it is already cancelled — resume/rerun own cancelled runs",
            "interrupted": "it is already interrupted — resume owns interrupted runs",
            "succeeded": "it finished — read its results instead",
        }.get(status, "only a running run can be cancelled")
        raise ValueError(f"run {run.id} is {status!r}, not running; {owner}")

    warning = signal_executor(run) if signal_executor is not None else None
    for state in active:
        _seal_cancelled(run, state, signalled=warning is None)
    return warning


def _seal_cancelled(run: Run, state: Execution, *, signalled: bool) -> None:
    """Seal *state* CANCELLED, unless its job was signalled on a compute target.

    An attempt dispatched to a compute target (``executor["target"]``) is a
    local copy of the record its worker writes there. It is sealed where it
    comes home: the reconcile every status reader runs stages the attempt out
    once the scheduler reports the job ended, merges the worker's record and
    seals it CANCELLED, so a cancelled attempt's records, logs and job files
    take the path of every other ended job. A local seal now would make that
    merge a no-op and leave the attempt on the target. The open record says
    the cancel was accepted (:data:`CANCEL_REQUESTED`), so a job the scheduler
    then forgets is still sealed CANCELLED. When the signal failed nothing
    will end the job, and the local seal records the user's intent.
    """
    from .timestamps import utc_now

    if signalled and state.executor.get("target") is not None:
        run._execution_repository().update_operational(
            state.id, executor={CANCEL_REQUESTED: utc_now().isoformat()}
        )
        return
    run.cancel(state.id)


def refuse_attempts_away(runs: Iterable[Run]) -> None:
    """Refuse to delete *runs* while one of their attempts is still away.

    The one delete rule, for a run and for the experiment or project that
    holds it: an attempt dispatched to a compute target and still open here
    has not come home (its job is running, or ended and not yet reconciled).
    A caller that can bring it home (the reconcile every status read runs)
    does so first.

    Raises:
        AttemptNotHomeError: An attempt of one of *runs* is still away.
    """
    from .domain import ACTIVE_EXECUTION_STATUSES
    from .errors import AttemptNotHomeError

    for run in runs:
        for state in run.executions:
            target = state.executor.get("target")
            if target is not None and state.status in ACTIVE_EXECUTION_STATUSES:
                raise AttemptNotHomeError(
                    f"run {run.id} is not deleted: attempt {state.id} is not home from "
                    f"compute target {target!r} yet ({state.status.value}). It comes home "
                    "once its job has ended (any status read brings it); delete it then."
                )
