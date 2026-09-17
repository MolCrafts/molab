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

Two shapes reach this module:

1. **script experiment** — the experiment's ``workflow_entrypoint``, resolved
   through :func:`molab.entry.load_workflow_from_entrypoint`. molab's own
   shape, built in here.
2. **generated run** — the workflow *source* was produced by a tool that owns
   its own on-disk format (today: the ``workflow_source`` artifact written by
   the harness ``plan`` pipeline). molab does not parse formats it does not
   own, so that shape arrives through the :func:`set_workflow_recoverer`
   inversion seam — the same pattern as
   :func:`molab.workspace.run.set_run_executor` and
   :func:`molab.workspace.metrics_seam.set_metrics_writer_factory`.

Dispatch is deterministic and loud: the registered recoverer is consulted
first, the experiment's entrypoint second, and a run with neither raises
:class:`WorkflowRecoveryError` naming both — never a silent ``None``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from molab.workflow.types import WorkflowError

if TYPE_CHECKING:
    from molab.workflow.compiled import CompiledWorkflow
    from molab.workspace.run import Run

__all__ = [
    "WorkflowRecoverer",
    "WorkflowRecoveryError",
    "can_recover_workflow",
    "compiled_workflow_for_run",
    "get_workflow_recoverer",
    "set_workflow_recoverer",
]


class WorkflowRecoveryError(WorkflowError):
    """Raised when a run carries no recoverable workflow identity.

    The error names both persisted shapes and what the run actually carries,
    so a run that is simply missing its generator is distinguishable from one
    whose carried shape is broken.
    """


@runtime_checkable
class WorkflowRecoverer(Protocol):
    """Reconstructs a compiled workflow from a run's own generated source.

    ``can_recover`` must be cheap — callers use it as an executability
    precondition (the server checks it before dispatching a run to a
    scheduler) and must not pay for a full compile to get the answer.
    """

    def can_recover(self, run: Run) -> bool:
        """True if *run* carries this recoverer's persisted shape."""
        ...

    def recover(self, run: Run) -> CompiledWorkflow | None:
        """Compile *run*'s generated workflow, or ``None`` if absent."""
        ...


_recoverer: WorkflowRecoverer | None = None


def set_workflow_recoverer(recoverer: WorkflowRecoverer | None) -> None:
    """Register the generated-source recoverer, or ``None`` to unwind it.

    Called at import time by whichever package owns the generated format.
    """
    global _recoverer
    _recoverer = recoverer


def get_workflow_recoverer() -> WorkflowRecoverer | None:
    """Return the registered recoverer, or ``None`` if the seam is unwired."""
    return _recoverer


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

    Cheap by contract: neither branch loads or compiles the workflow.
    """
    if _recoverer is not None and _recoverer.can_recover(run):
        return True
    return _entrypoint_of(run) is not None


def compiled_workflow_for_run(run: Run) -> CompiledWorkflow:
    """Rebuild the compiled workflow a persisted *run* was declared with.

    Args:
        run: The workspace Run whose workflow identity is reconstructed.

    Returns:
        The compiled workflow, ready for :func:`molab.workflow.execute_run`.

    Raises:
        WorkflowRecoveryError: The run carries neither persisted shape, or a
            carried shape is unloadable (broken source / dead entrypoint).
    """
    if _recoverer is not None:
        compiled = _recoverer.recover(run)
        if compiled is not None:
            return compiled

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
        "Experiment.define/sweep/run) and no generated workflow source is "
        "registered for it. Re-declare the experiment by running its script, "
        "or regenerate it with `molab plan`."
    )
