"""Run reconciliation lifecycle over molab's shared terminal tree viewer."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from rich.console import Console

from .tree_monitor import TreeMonitor

if TYPE_CHECKING:
    from molab.workspace.run import Run

_RECONCILE_THREAD_NAME = "molab-run-monitor-reconcile"
_RECONCILE_JOIN_TIMEOUT = 5.0


class RunMonitor:
    """Watch selected runs without importing molq UI or owning transport state."""

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
        self._reconcile_errors: dict[str, tuple[str | None, str]] = {}
        self._reconcile_lock = threading.Lock()

    def watch(self, runs: list[Run]) -> None:
        if not runs:
            return
        workspace = runs[0].experiment.project.workspace
        if any(str(run.experiment.project.workspace.root) != str(workspace.root) for run in runs):
            raise ValueError("A run monitor watches one workspace")
        stop = threading.Event()
        worker = threading.Thread(
            target=self._reconcile_loop,
            args=(list(runs), stop),
            name=_RECONCILE_THREAD_NAME,
            daemon=True,
        )
        worker.start()
        console = Console()
        try:
            warnings = TreeMonitor(
                run_ids=frozenset(run.id for run in runs),
                refresh_interval=self._refresh_interval,
                console=console,
            ).watch(workspace)
            for warning in warnings:
                console.print(warning, markup=False)
        finally:
            stop.set()
            worker.join(timeout=_RECONCILE_JOIN_TIMEOUT)
            with self._reconcile_lock:
                errors = list(self._reconcile_errors.values())
            for _, message in errors:
                console.print(message, markup=False)

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
