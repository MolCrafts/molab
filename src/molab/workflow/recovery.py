"""Kind-dispatched workflow resolution.

A run executed by id (``molab runs resume|rerun``, a molq worker, server
dispatch, ``Run.execute`` without a workflow argument) is resolved here and
only here. The experiment owns the association. Dispatch follows
``workflow_kind``:

- ``code`` and unbound (``None``) consult the in-process binding memo, then a
  code experiment loads its locator.
- ``document`` always decodes ``workflow.ir.json``. The memo is never
  consulted, because nothing can invalidate it across processes.

An experiment written before workflow kinds fails with
:class:`WorkflowRecoveryError` naming ``molab migrate workflow-kind``. This
module does not guess a kind and does not write the experiment.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from molab.workflow.types import WorkflowError

if TYPE_CHECKING:
    from molab.workflow.compiled import CompiledWorkflow
    from molab.workspace.experiment import Experiment
    from molab.workspace.run import Run

__all__ = [
    "WorkflowRecoveryError",
    "can_recover_workflow",
    "compiled_workflow_for_experiment",
    "compiled_workflow_for_run",
]


class WorkflowRecoveryError(WorkflowError):
    """Raised when an experiment's workflow cannot be resolved.

    The message names the experiment, the run when there is one, and the
    remedy for the kind that was actually stored.
    """


def _locator_of(experiment: Experiment) -> str | None:
    """The code locator, used only when ``workflow_kind`` is ``code``."""
    entrypoint = getattr(getattr(experiment, "metadata", None), "workflow_entrypoint", None)
    if isinstance(entrypoint, str) and entrypoint:
        return entrypoint
    return None


def _memo(experiment: Experiment) -> CompiledWorkflow | None:
    from molab.workflow.binding import default_binding_registry

    return default_binding_registry.for_experiment(experiment)


def can_recover_workflow(run: Run) -> bool:
    """True when another process can resolve *run* without this process's memo.

    Cheap by contract: no user import and no compile. A memo hit is not
    evidence a worker can recover the run.

    Args:
        run: The run whose experiment association is inspected.

    Returns:
        ``code`` with a locator, or ``document`` with a stored IR. Unbound
        experiments are not recoverable.
    """
    experiment = run.experiment
    kind = experiment.workflow_kind
    if kind == "code":
        return _locator_of(experiment) is not None
    if kind == "document":
        return experiment.workflow_document is not None
    return False


def compiled_workflow_for_run(run: Run) -> CompiledWorkflow:
    """Resolve the compiled workflow *run*'s experiment is bound to.

    Args:
        run: The workspace run. Resolution reads its parent experiment.

    Returns:
        The compiled workflow.

    Raises:
        WorkflowRecoveryError: The association is missing or cannot be loaded.
    """
    return _resolve(run.experiment, run)


def compiled_workflow_for_experiment(experiment: Experiment) -> CompiledWorkflow:
    """Resolve *experiment* the same way as :func:`compiled_workflow_for_run`.

    Args:
        experiment: The experiment whose association is read.

    Returns:
        The compiled workflow.

    Raises:
        WorkflowRecoveryError: The association is missing or cannot be loaded.
    """
    return _resolve(experiment, None)


def _resolve(experiment: Experiment, run: Run | None) -> CompiledWorkflow:
    kind = experiment.workflow_kind
    if kind == "document":
        return _resolve_document(experiment, run)
    if kind == "code":
        return _resolve_code(experiment, run)
    bound = _memo(experiment)
    if bound is not None:
        return bound
    root = experiment.project.workspace.root
    run_id = f" run {run.id}" if run is not None else ""
    raise WorkflowRecoveryError(
        f"no workflow bound to experiment {experiment.id}{run_id}: "
        f"workflow_kind=None. pass workflow=... to run it in-process, or run "
        f"`molab migrate workflow-kind {root}`"
    )


def _resolve_document(experiment: Experiment, run: Run | None) -> CompiledWorkflow:
    document = experiment.workflow_document
    who = _who(experiment, run)
    if not isinstance(document, dict):
        raise WorkflowRecoveryError(f"{who}: document workflow has no workflow.ir.json")
    from molab.workflow.codec import default_codec

    try:
        return default_codec.ir_to_spec(document)
    except Exception as exc:
        raise WorkflowRecoveryError(
            f"{who}: workflow document could not be decoded: {exc}"
        ) from exc


def _resolve_code(experiment: Experiment, run: Run | None) -> CompiledWorkflow:
    bound = _memo(experiment)
    if bound is not None:
        return bound
    locator = _locator_of(experiment)
    who = _who(experiment, run)
    if locator is None:
        raise WorkflowRecoveryError(
            f"{who}: code workflow has no locator and no in-process binding; "
            "re-run its defining script"
        )
    from molab.workflow.loader import load_workflow_from_entrypoint

    try:
        return load_workflow_from_entrypoint(locator)
    except Exception as exc:
        raise WorkflowRecoveryError(
            f"{who}: workflow entrypoint {locator!r} could not be loaded: {exc}"
        ) from exc


def _who(experiment: Experiment, run: Run | None) -> str:
    if run is None:
        return f"experiment {experiment.id}"
    return f"run {run.id}: experiment {experiment.id}"
