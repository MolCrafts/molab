"""RunMonitor: lifecycle controller for the full-screen run dashboard.

molab owns when the dashboard opens, closes, and can be reopened.
molq owns the dashboard renderer (:class:`~molq.dashboard.RunDashboard`).

Usage (from CLI or programmatic code)::

    from molab.cli.tui import RunMonitor

    monitor = RunMonitor(title="my-experiment")
    monitor.watch(runs)  # blocks until user presses 'q'
    # jobs keep running after this returns
"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import TYPE_CHECKING

from molab._run_display import elapsed as _elapsed
from molab.plugins.submit_molq.metadata import normalize_executor_info

if TYPE_CHECKING:
    from molq.dashboard import DashboardState

    from molab.workspace.run import Run


# ── Helpers ───────────────────────────────────────────────────────────────────


def _overall_status(running: int, pending: int, failed: int, done: int) -> str:
    if running > 0:
        return "running"
    if pending > 0:
        return "pending"
    if failed > 0 and done == 0:
        return "failed"
    if failed > 0:
        return "mixed"
    return "done"


def _run_label(r: Run) -> str | None:
    """Human-meaningful row label (experiment name + optional replica)."""
    exp_name = r.experiment.name
    replica = r.metadata.parameters.get("replica")
    if replica is not None and exp_name:
        return f"{exp_name}#{replica}"
    return exp_name or None


# ── RunMonitor ────────────────────────────────────────────────────────────────


_RECONCILE_THREAD_NAME = "molab-run-monitor-reconcile"
# How long closing the dashboard waits for an in-flight reconcile pass. The
# worker is a daemon, so a pass stuck on a hung transport never blocks exit.
_RECONCILE_JOIN_TIMEOUT = 5.0


class RunMonitor:
    """Lifecycle controller for the full-screen run dashboard.

    Owns when the dashboard is opened and closed.  Delegates all rendering
    to :class:`~molq.dashboard.RunDashboard` from the molq package.

    Status is refreshed by re-reading each :class:`~molab.workspace.run.Run`
    through its FileSystem on every tick — works for local *and* remote
    workspaces (no local ``Path(run_dir)`` open). Rendering does file reads
    only. Reconciliation — asking molq about a job, possibly over SSH — runs on
    a background worker that, at most once per *reconcile_interval*, passes
    every run whose newest attempt is still QUEUED and was submitted through
    molq to :func:`~molab.plugins.submit_molq.submit.reconcile_submission`, so
    a job that ended before its worker started is sealed while being watched.
    A RUNNING attempt is left to the reaper. A failed check is shown in that
    run's row message; it never stops the dashboard.

    Args:
        title: Display title shown in the monitor header.
        refresh_interval: Seconds between automatic data refreshes.
        reconcile_interval: Minimum seconds between two reconcile passes.
    """

    def __init__(
        self,
        title: str = "molab",
        *,
        refresh_interval: float = 2.0,
        reconcile_interval: float = 30.0,
    ) -> None:
        self._title = title
        self._refresh_interval = refresh_interval
        self._reconcile_interval = reconcile_interval
        # Run id → (attempt id or None when it could not be read, message) of
        # the latest reconcile pass that failed for that run. Written by the
        # worker, read by the render thread.
        self._reconcile_errors: dict[str, tuple[str | None, str]] = {}
        self._reconcile_lock = threading.Lock()

    def watch(self, runs: list[Run]) -> None:
        """Open the full-screen dashboard and block until the user presses ``q``.

        Closing the dashboard does **not** cancel any running jobs — it only
        closes the viewer.  The caller is responsible for any post-close
        messaging (e.g. "reopen with molab watch …"). The reconcile worker
        starts with the dashboard (its first pass runs immediately) and is
        stopped when this returns.

        Args:
            runs: Run objects to monitor.  Status is polled via each Run's
                  FileSystem on every refresh (local or remote).
        """
        from molq.dashboard import RunDashboard

        # Keep live Run handles so each tick re-reads ops through ``fs``.
        run_list = list(runs)
        stop = threading.Event()
        worker = threading.Thread(
            target=self._reconcile_loop,
            args=(run_list, stop),
            name=_RECONCILE_THREAD_NAME,
            daemon=True,
        )
        worker.start()
        try:
            RunDashboard().watch(
                lambda: self._build_state(run_list),
                refresh_interval=self._refresh_interval,
            )
        finally:
            stop.set()
            worker.join(timeout=_RECONCILE_JOIN_TIMEOUT)

    def _reconcile_loop(self, runs: list[Run], stop: threading.Event) -> None:
        """Run a reconcile pass now, then once per interval until *stop* is set."""
        while True:
            self._reconcile_pass(runs)
            if stop.wait(self._reconcile_interval):
                return

    def _reconcile_pass(self, runs: list[Run]) -> None:
        """Reconcile every run's newest QUEUED molq attempt once, in order.

        Each run is guarded on its own: an error reported by
        ``reconcile_submission``, or anything raised while reading or checking
        the run, is kept as that run's row message and the pass moves on.
        """
        for r in runs:
            failure = self._reconcile_one(r)
            with self._reconcile_lock:
                if failure is None:
                    self._reconcile_errors.pop(r.id, None)
                else:
                    self._reconcile_errors[r.id] = failure

    @staticmethod
    def _reconcile_one(r: Run) -> tuple[str | None, str] | None:
        """Reconcile *r*'s newest attempt if eligible; return the failure, if any."""
        from molab.plugins.submit_molq import submit as submit_molq
        from molab.workspace.domain import ExecutionStatus

        execution_id: str | None = None
        try:
            executions = r.executions
            if not executions:
                return None
            latest = executions[-1]
            execution_id = latest.id
            if (
                latest.status is not ExecutionStatus.QUEUED
                or latest.executor.get("backend") != "molq"
            ):
                return None
            outcome = submit_molq.reconcile_submission(r, latest.id)
            if outcome.error is None:
                return None
            return (execution_id, outcome.error)
        except Exception as exc:  # one run's failure must not stop the dashboard
            attempt = f" attempt {execution_id}" if execution_id else ""
            return (
                execution_id,
                f"could not reconcile run {r.id}{attempt}: {type(exc).__name__}: {exc}",
            )

    def _build_state(self, run_list: list[Run]) -> DashboardState:
        """Build one dashboard frame from the runs' files (no scheduler calls)."""
        from molq.dashboard import DashboardState, JobRow

        with self._reconcile_lock:
            reconcile_errors = dict(self._reconcile_errors)

        rows: list[JobRow] = []
        running = pending = done = failed = 0

        for r in run_list:
            run_id = r.id
            run_name = _run_label(r)
            try:
                status = str(r.status)
            except Exception:
                status = "pending"

            created_at = r.metadata.created_at.isoformat() if r.metadata.created_at else None
            finished = r.finished_at
            finished_at = finished.isoformat() if finished is not None else None
            elapsed = _elapsed(created_at, finished_at)

            labels_raw = getattr(r.metadata, "labels", None)
            executor_info = normalize_executor_info(
                r.metadata.executor_info if isinstance(r.metadata.executor_info, dict) else None,
                (
                    {str(k): v for k, v in labels_raw.items() if isinstance(v, str)}
                    if isinstance(labels_raw, dict)
                    else None
                ),
            )
            sched_id = executor_info.get("scheduler_job_id")

            messages: list[str] = []
            err = r.metadata.error
            if err is not None:
                messages.append(getattr(err, "message", None) or str(err))
            reconcile_error = reconcile_errors.get(run_id)
            if reconcile_error is not None:
                messages.append(reconcile_error[1])
            error_msg = "; ".join(messages) if messages else None

            profile_name = r.metadata.profile or None
            extras: tuple[tuple[str, str], ...] = (
                (("profile", profile_name),) if profile_name else ()
            )

            # ``run_name`` is folded into ``extras`` because molq's
            # ``JobRow`` has no dedicated name field — the dashboard
            # already groups by ``run_id`` and surfaces ``extras`` in
            # the row's secondary line.
            if run_name and run_name != run_id:
                extras = (*extras, ("name", run_name))
            rows.append(
                JobRow(
                    state=status,
                    run_id=run_id,
                    cluster=executor_info.get("cluster_name"),
                    scheduler_id=sched_id,
                    elapsed=elapsed,
                    message=error_msg,
                    extras=extras,
                )
            )

            s = status.lower()
            if s == "running":
                running += 1
            elif s == "pending":
                pending += 1
            elif s in ("succeeded", "done"):
                done += 1
            elif s in ("failed", "cancelled"):
                failed += 1
            else:
                pending += 1  # unknown → treat as pending

        return DashboardState(
            title=self._title,
            overall_status=_overall_status(running, pending, failed, done),
            total=len(run_list),
            running=running,
            pending=pending,
            done=done,
            failed=failed,
            updated_at=datetime.now().strftime("%H:%M:%S"),
            jobs=tuple(rows),
        )
