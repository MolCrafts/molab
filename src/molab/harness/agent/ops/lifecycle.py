"""Workspace-local lifecycle tools (gated ``operation_mode=lifecycle``).

``molab.harness.agent`` may not import ``molab.harness``. The full harness
lifecycle catalog stays in plan/curate. This module only exposes verbs
that are workspace-owned:

* ``cancel_run`` — :func:`molab.workspace.lifecycle_ops.cancel_run`
* ``harvest_run`` — :func:`molab.workspace.harvest_run`

Mounted only when the ReAct surface is ``lifecycle``.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from molab.workspace.run import Run

__all__ = ["LIFECYCLE_TOOL_NAMES", "lifecycle_tools"]

LIFECYCLE_TOOL_NAMES = frozenset({"cancel_run", "harvest_run"})


def _as_tool_error(exc: Exception) -> str:
    """Turn a tool failure into a model-visible string (never crash the loop)."""
    return f"error: {type(exc).__name__}: {exc}"


def _scalar_status(run: Run) -> str:
    """Derive the single run-status label from the Execution aggregate."""
    summary = run.status_summary
    if summary.not_started:
        return "pending"
    if summary.active > 0:
        return "running"
    for status in ("failed", "cancelled", "interrupted", "succeeded"):
        if summary.by_status.get(status):
            return status
    return "succeeded" if summary.total else "pending"


def lifecycle_tools(*, workspace_root: Path) -> tuple[Any, ...]:
    """Return bare callables for workspace cancel + harvest (no harness import).

    Failures return ``error: …`` strings (same contract as read-only ops tools)
    so a precondition miss (e.g. harvest on a non-terminal run) is visible to
    the model instead of aborting the whole agentic turn.
    """
    root = Path(workspace_root).resolve()

    def cancel_run(project_id: str, experiment_id: str, run_id: str) -> str:
        """Cancel a live running run (workspace cancel verb; same as CLI).

        Returns an ``error: …`` string if the run is not cancellable.
        """
        from molab.workspace import Workspace
        from molab.workspace.lifecycle_ops import cancel_run as cancel_core

        try:
            ws = Workspace(root)
            run = ws.get_project(project_id).get_experiment(experiment_id).get_run(run_id)
            cancel_core(run)
            return f"cancelled run {run_id} (status={_scalar_status(run)})"
        except Exception as exc:
            return _as_tool_error(exc)

    def harvest_run(
        project_id: str,
        experiment_id: str,
        run_id: str,
        narrative: str,
        created_by: str = "agent",
    ) -> str:
        """Harvest a *terminal* run into a Finding.

        Only terminal runs have an outcome to interpret. Pending/running runs
        return ``error: …`` so the model can run/wait first instead of crashing
        the turn.
        """
        from molab.knowledge import Finding
        from molab.workspace import Workspace

        try:
            ws = Workspace(root)
            run = ws.get_project(project_id).get_experiment(experiment_id).get_run(run_id)
            item = run.harvest(
                Finding,
                narrative=narrative,
                created_by=created_by,
            )
            return f"harvested Finding {item.name}"
        except Exception as exc:
            return _as_tool_error(exc)

    cancel_run.__name__ = "cancel_run"
    harvest_run.__name__ = "harvest_run"
    return (cancel_run, harvest_run)
