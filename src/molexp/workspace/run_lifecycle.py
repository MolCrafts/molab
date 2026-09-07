"""``RunLifecycle`` — RunContext's enter/exit state machine.

Tier-1 collaborator of :class:`~molexp.workspace.run.RunContext` (see the
``workspace-slim-03-runcontext`` decomposition). Drives the
context-manager protocol: claim process ownership, stamp profile
metadata, flip run status, allocate the execution attempt, and on exit
close the record + persist results / error trace. It is the only
collaborator that *orchestrates* the others, so it holds a back-reference
to the facade and reaches the Tier-2/3 collaborators through it; the
reverse dependency (a store reaching back into the lifecycle) is
forbidden.

Exit-status resolution (run-recovery): success is a positive signal, never
the default on a previously failed run. With no exception, the final status
is (1) FAILED / SUCCEEDED when the workflow signalled via ``mark_failed`` /
``mark_succeeded``; (2) otherwise SUCCEEDED when the attempt recorded new
results or the run was not previously failed/cancelled (the documented
manual-driver contract); (3) otherwise a **no-op attempt** — the run keeps
its prior failed/cancelled status, the ExecutionRecord closes as
``"aborted"``, and ``metadata.error`` is preserved. A SUCCEEDED terminal
clears ``metadata.error``; an exception-free FAILED terminal also persists
``executions/<exec_id>/error.txt`` (the engine swallows task exceptions, so
this is the only chance to land the trace file).
"""

from __future__ import annotations

import os
import platform
import threading
from datetime import datetime
from typing import TYPE_CHECKING

from mollog import get_logger

from .domain import ExecutionMode, ExecutionStatus
from .models import ErrorInfo, RunStatus
from .run_heartbeat import HEARTBEAT_INTERVAL_SECONDS, alive_mtime, touch_alive, unlink_alive
from .scientific_repository import SYSTEM_AGENT

if TYPE_CHECKING:
    from .runcontext import RunContext

logger = get_logger(__name__)


def _split_error_text(raw: str) -> tuple[str, str]:
    """Split a ``"ExceptionType: message"`` string into ``(type, message)``.

    The workflow engine records task failures type-prefixed (e.g.
    ``"ZeroDivisionError: division by zero"``). Recover the type when the prefix
    is a Python-exception-style identifier; otherwise keep the whole string as
    the message under a generic ``"WorkflowError"`` type — never fabricate a
    specific type we did not actually see.
    """
    head, sep, tail = raw.partition(": ")
    if sep and head.isidentifier() and head[:1].isupper():
        return head, tail
    return "WorkflowError", raw


def _error_info_from_context(ctx: RunContext, now: datetime) -> ErrorInfo | None:
    """Build an :class:`ErrorInfo` from the message ``mark_failed`` stashed.

    ``mark_failed`` records ``context.errors["run"] = {"message": ...}`` when a
    task fails without the exception propagating out of ``execute()``. Returns
    ``None`` when no such message is present (nothing to persist).
    """
    run_err = ctx._ctx_store.context.errors.get("run")
    raw = run_err.get("message") if isinstance(run_err, dict) else run_err
    if not raw:
        return None
    etype, message = _split_error_text(str(raw))
    return ErrorInfo(type=etype, message=message, timestamp=now)


def _traceback_from_context(ctx: RunContext) -> str | None:
    """The formatted task traceback ``mark_failed`` stashed, if any.

    The workflow runtime forwards the swallowed task exception's formatted
    stack via ``mark_failed(..., traceback_text=…)``; it lands in
    ``context.errors["run"]["traceback"]``. ``None`` when the failure signal
    carried no traceback (e.g. a manual ``mark_failed("msg")``).
    """
    run_err = ctx._ctx_store.context.errors.get("run")
    if isinstance(run_err, dict):
        return run_err.get("traceback") or None
    return None


class RunLifecycle:
    """Enter/exit orchestration for a :class:`RunContext`."""

    def __init__(
        self,
        ctx: RunContext,
        *,
        heartbeat_interval: float = HEARTBEAT_INTERVAL_SECONDS,
    ) -> None:
        self._ctx = ctx
        self._heartbeat_interval = heartbeat_interval
        self._heartbeat_stop: threading.Event | None = None
        self._heartbeat_thread: threading.Thread | None = None
        self._status_on_enter: RunStatus | None = None

    def enter(self) -> None:
        ctx = self._ctx
        ctx.run_dir.mkdir(parents=True, exist_ok=True)
        ctx._ctx_store.load_existing_results()
        ctx._ctx_store.reset_write_tracking()
        self._apply_profile_metadata()
        # Remember the status this attempt started from *before* claim writes
        # RUNNING: a signal-less no-op attempt must restore it instead of
        # defaulting to SUCCEEDED (bug 1).
        self._status_on_enter = ctx.run.metadata.status
        self._claim_ownership()
        ctx._start_time = datetime.now()
        ctx._entered = True

        # One attempt is one Execution, owned end-to-end by ExecutionRepository:
        # it allocates ``executions/eNN/`` and is the only writer of
        # ``execution.json``. A pre-allocated id that already exists is
        # reopened in place (resume); anything else opens a fresh attempt.
        repo = ctx._executions
        explicit = ctx._explicit_execution_id
        state = None
        if explicit is not None:
            try:
                state = repo.get(explicit)
            except KeyError:
                state = None
        if state is None:
            state = repo.create(
                mode=ExecutionMode.INITIAL if not repo.list() else ExecutionMode.RERUN,
                created_by=SYSTEM_AGENT,
                execution_id=explicit,
            )
        ctx._execution_id = state.id
        if state.status is ExecutionStatus.QUEUED:
            repo.start(state.id)
        elif state.sealed:
            raise RuntimeError(f"Execution {state.id!r} is sealed and cannot be reopened")
        ctx._assets.append_run_log(f"execution started  exec_id={ctx._execution_id}")
        ctx._ctx_store.save()
        assert ctx._execution_id is not None
        touch_alive(ctx.run, ctx._execution_id)
        self._start_heartbeat()

    def exit(self, exc_type, exc_val, exc_tb) -> bool:  # noqa: ANN001
        # Stop the heartbeat first so it cannot race the terminal-status
        # writes below (the reaper must never see a fresh heartbeat on a
        # run whose status is already terminal-in-progress).
        self._stop_heartbeat()
        ctx = self._ctx
        # ``enter()`` always runs first and assigns a non-None execution id.
        execution_id = ctx._execution_id
        assert execution_id is not None
        unlink_alive(ctx.run, execution_id)
        now = datetime.now()
        error_info: ErrorInfo | None = None
        noop = False
        if exc_type is None:
            # Three-state resolution (bug 1): FAILED / SUCCEEDED are explicit
            # workflow signals (``mark_failed`` / ``mark_succeeded``); with NO
            # signal, a previously failed/cancelled run that also recorded no
            # new results is a no-op attempt — it keeps its prior status and
            # its ExecutionRecord closes as "aborted". Success is never the
            # default on a run that already failed. A run that was never
            # failed keeps the legacy contract: a clean, exception-free
            # attempt (manual-driver / artifact-only usage) resolves to
            # SUCCEEDED.
            workflow_status = ctx._ctx_store.context.status.get("run")
            status_on_enter = self._status_on_enter
            if workflow_status == RunStatus.FAILED:
                final = RunStatus.FAILED
                # The engine caught the task exception into a FAILED workflow
                # status (it does NOT re-raise, so the run stays resumable) and
                # stashed the message on the context via ``mark_failed``. Lift it
                # into the workspace-owned canonical record, so run.json /
                # execution.json don't silently carry ``error: null`` while the
                # reason lives only in the workflow-layer document.
                error_info = _error_info_from_context(ctx, now)
                if error_info is not None:
                    ctx.run._update_metadata(error=error_info)
                    # The exception never propagated (the engine swallowed it),
                    # so this is the only chance to land error.txt (bug 3) —
                    # including the real traceback the runtime forwarded
                    # through ``mark_failed(..., traceback_text=…)``.
                    ctx._assets.save_error_report(
                        error_type=error_info.type,
                        message=error_info.message,
                        traceback_text=_traceback_from_context(ctx),
                    )
            elif workflow_status == RunStatus.SUCCEEDED:
                final = RunStatus.SUCCEEDED
            elif (
                status_on_enter in (RunStatus.FAILED, RunStatus.CANCELLED)
                and not ctx._ctx_store.wrote_results
            ):
                final = status_on_enter
                noop = True
            else:
                final = RunStatus.SUCCEEDED
        else:
            final = RunStatus.FAILED
            error_info = ErrorInfo(
                type=exc_type.__name__,
                message=str(exc_val),
                timestamp=now,
            )
            # ``error`` is identity/diagnostic — it stays in run.json (wsokf-10).
            ctx.run._update_metadata(error=error_info)
            ctx._assets.save_error_details(exc_type, exc_val, exc_tb)
        if final is RunStatus.SUCCEEDED and ctx.run.metadata.error is not None:
            # A successful terminal state must not keep describing an old
            # failure (bug 2) — the canonical record tells the truth.
            ctx.run._update_metadata(error=None)
        # A no-op attempt seals as "interrupted" — it neither succeeded nor
        # failed; the run-level status stays what it was.
        record_status = "aborted" if noop else final.value
        ctx.run._update_metadata(
            status=final,
            finished_at=now,
            owner_pid=None,
            owner_host=None,
        )
        terminal = {
            "succeeded": ExecutionStatus.SUCCEEDED,
            "failed": ExecutionStatus.FAILED,
            "cancelled": ExecutionStatus.CANCELLED,
            "aborted": ExecutionStatus.INTERRUPTED,
        }[record_status]
        ctx._executions.seal(
            execution_id,
            terminal,
            error=error_info.model_dump(mode="json") if error_info is not None else None,
        )
        ctx._assets.append_run_log(
            f"execution finished exec_id={ctx._execution_id}  status={record_status}"
        )
        ctx._ctx_store.save()
        ctx._entered = False
        return False

    def _apply_profile_metadata(self) -> None:
        """Persist the active profile name / data / hash into RunMetadata."""
        ctx = self._ctx
        cfg = ctx._profile_config
        ctx.run._update_metadata(
            profile=cfg.name,
            config=cfg.to_dict(),
            config_hash=cfg.content_hash() if len(cfg) > 0 or cfg.name else None,
        )

    def _claim_ownership(self) -> None:
        """Stamp ``run.json`` with this process's identity and touch ``alive``.

        Writes ``owner_pid`` / ``owner_host`` / ``status=running`` /
        ``started_at`` and creates the run-root ``alive`` file whose mtime
        is the cross-host heartbeat. A later ``molexp run`` invocation can
        consult these to tell a live run from a zombie left behind by a
        crashed process.
        """
        ctx = self._ctx
        now = datetime.now()
        ctx.run._update_metadata(
            owner_pid=os.getpid(),
            owner_host=platform.node(),
            status=RunStatus.RUNNING,
            started_at=ctx.run.metadata.started_at or now,
        )

    # ── Heartbeat ────────────────────────────────────────────────────────
    #
    # Cross-host observers (molq / SLURM submissions are the core scenario)
    # have only the ``alive`` file mtime to tell a live remote run from a
    # zombie — so it must be refreshed while the run executes. Same-host
    # reapers probe the pid directly.

    def _start_heartbeat(self) -> None:
        """Spawn the daemon thread that re-touches the ``alive`` file."""
        stop = threading.Event()
        thread = threading.Thread(
            target=self._heartbeat_loop,
            args=(stop,),
            name=f"molexp-heartbeat-{self._ctx.run.id}",
            daemon=True,
        )
        self._heartbeat_stop = stop
        self._heartbeat_thread = thread
        thread.start()

    def _stop_heartbeat(self) -> None:
        """Signal the heartbeat thread to exit and wait briefly for it."""
        if self._heartbeat_stop is not None:
            self._heartbeat_stop.set()
        if self._heartbeat_thread is not None:
            self._heartbeat_thread.join(timeout=5.0)
        self._heartbeat_stop = None
        self._heartbeat_thread = None

    def _heartbeat_loop(self, stop: threading.Event) -> None:
        while not stop.wait(self._heartbeat_interval):
            try:
                self.refresh_heartbeat()
            except Exception:
                # Never let a display/metadata hiccup kill the worker;
                # a missed beat only delays staleness detection.
                logger.debug(f"heartbeat refresh failed for run {self._ctx.run.id}", exc_info=True)

    def refresh_heartbeat(self) -> None:
        """Touch the run-root ``alive`` file; never rewrite ``run.json``.

        A run whose ``alive`` file has not been created yet (first beat
        before the lifecycle claimed ownership) is left untouched.
        """
        run = self._ctx.run
        execution_id = self._ctx._execution_id
        if execution_id is None or alive_mtime(run, execution_id) is None:
            return
        touch_alive(run, execution_id)
