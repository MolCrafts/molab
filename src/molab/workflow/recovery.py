"""``compiled_workflow_for_run`` — rebuild a persisted run's executable workflow.

A run that is executed *by id* (``molab run`` on a run that has no defining
script in hand, ``molab runs resume|rerun``, a molq worker replaying
``molab execute``) must have its workflow reconstructed from what is on disk.

**The workflow belongs to the experiment, not to the run.** Every run of an
experiment executes the workflow that experiment was defined with, so the
locator is recorded once — ``ExperimentMetadata.workflow_entrypoint``, written
by the single binding seam in :mod:`molab.entry` — and a run reaches it
through its parent. Nothing is copied onto the run, which is what previously
let ``Experiment.define`` and the HTTP API disagree about a run's identity.

There is one shape: the experiment's ``workflow_entrypoint`` (the
``"<file>:<qualname>"`` locator), resolved through
:func:`molab.entry.load_workflow_from_entrypoint`. A run whose experiment
records no entrypoint raises :class:`WorkflowRecoveryError` naming the run —
never a silent ``None``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from molab.workflow.types import WorkflowError

if TYPE_CHECKING:
    from molab.workflow.compiled import CompiledWorkflow
    from molab.workspace.run import Run

__all__ = [
    "WorkflowRecoveryError",
    "can_recover_workflow",
    "compiled_workflow_for_run",
]


class WorkflowRecoveryError(WorkflowError):
    """Raised when a run carries no recoverable workflow identity.

    The error says what the run actually carries, so a run whose experiment
    records no entrypoint is distinguishable from one whose entrypoint is
    broken.
    """


def _entrypoint_of(run: Run) -> str | None:
    """Return the workflow locator for *run* — its experiment's, by design.

    The legacy per-run ``workflow_snapshot.entrypoint`` is still read, but only
    as a fallback for runs written before the locator moved to the experiment.
    Nothing writes it any more; the experiment is the authority.
    """
    experiment = getattr(run, "experiment", None)
    entrypoint = getattr(getattr(experiment, "metadata", None), "workflow_entrypoint", None)
    if isinstance(entrypoint, str) and entrypoint:
        return entrypoint

    legacy = getattr(run.metadata, "workflow_snapshot", None) or {}
    if not isinstance(legacy, dict):
        return None
    entrypoint = legacy.get("entrypoint")
    return entrypoint if isinstance(entrypoint, str) and entrypoint else None


def can_recover_workflow(run: Run) -> bool:
    """True if *run* can be executed by id alone.

    Cheap by contract: it neither loads nor compiles the workflow.
    """
    return _entrypoint_of(run) is not None


def compiled_workflow_for_run(run: Run) -> CompiledWorkflow:
    """Rebuild the compiled workflow a persisted *run* was declared with.

    Args:
        run: The workspace Run whose workflow identity is reconstructed.

    Returns:
        The compiled workflow, ready for :func:`molab.workflow.execute_run`.

    Raises:
        WorkflowRecoveryError: The run's experiment records no entrypoint,
            or the entrypoint is unloadable.
    """
    entrypoint = _entrypoint_of(run)
    if entrypoint is not None:
        from molab.entry import load_workflow_from_entrypoint

        try:
            # Contract: the qualname resolves to a COMPILED workflow
            # (load_workflow_from_entrypoint rejects a bare compiler).
            return load_workflow_from_entrypoint(entrypoint)
        except Exception as exc:
            raise WorkflowRecoveryError(
                f"run {run.id}: workflow entrypoint {entrypoint!r} could not be loaded: {exc}"
            ) from exc

    raise WorkflowRecoveryError(
        f"run {run.id} has no recoverable workflow: its experiment records no "
        "'workflow_entrypoint' (set when a workflow is bound via "
        "Experiment.define/sweep/run). Re-declare the experiment by running its script."
    )
