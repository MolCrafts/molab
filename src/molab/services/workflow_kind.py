"""Legacy workflow-kind classification.

One rule, shared by ``molab migrate workflow-kind`` and the server writers'
409 gate. Read-only: nothing here writes an experiment. This module reads
``workflow_entrypoint``, ``plan_run_id``, and ``workflow.ir.json``. A
non-empty locator wins first; ``plan_run_id`` is not a kind.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from molab.workspace import Experiment, WorkflowKind

__all__ = [
    "LegacyWorkflowClassification",
    "classify_legacy_workflow",
    "needs_workflow_kind_migration",
]


class LegacyWorkflowClassification(BaseModel):
    """How a pre-``workflow_kind`` experiment would be bound, if at all."""

    model_config = ConfigDict(frozen=True)

    kind: WorkflowKind | None = None
    entrypoint: str | None = None
    document: dict[str, Any] | None = None
    note: str | None = None


def _classify_ir(document: dict[str, Any]) -> LegacyWorkflowClassification:
    """Split a JSON object into a document binding, a code snapshot, or noise."""
    if "task_configs" in document:
        return LegacyWorkflowClassification(kind="document", document=document)
    if "tasks" in document:
        return LegacyWorkflowClassification(
            kind="code",
            document=document,
            note="memo-only: re-run its defining script",
        )
    return LegacyWorkflowClassification(note="not a recognised workflow IR")


def classify_legacy_workflow(experiment: Experiment) -> LegacyWorkflowClassification:
    """Classify *experiment* from its legacy fields. Read-only; first match wins.

    A non-empty ``workflow_entrypoint`` is code, and ``plan_run_id`` is not
    consulted for that decision. Otherwise a plan id is unrecoverable. An IR
    object is taken only from :attr:`Experiment.workflow_document`
    (``workflow.ir.json``). ``task_configs`` is the document kind; ``tasks``
    is a code snapshot with no locator. Anything else is left unbound.

    Args:
        experiment: Experiment to inspect. Not modified.

    Returns:
        The classification. ``kind is None`` means migration will not bind it.
    """
    meta = experiment.metadata
    entrypoint = meta.workflow_entrypoint
    if entrypoint:
        return LegacyWorkflowClassification(
            kind="code",
            entrypoint=entrypoint,
            document=experiment.workflow_document,
        )
    if meta.plan_run_id:
        return LegacyWorkflowClassification(note="unrecoverable (legacy plan run)")

    document = experiment.workflow_document
    if document is not None:
        return _classify_ir(document)
    return LegacyWorkflowClassification()


def needs_workflow_kind_migration(experiment: Experiment) -> bool:
    """Return whether migration would bind *experiment*.

    True only when ``workflow_kind`` is unset and
    :func:`classify_legacy_workflow` names a kind. The two cannot diverge:
    this is exactly "migration would write a binding".

    Args:
        experiment: Experiment to inspect. Not modified.
    """
    return (
        experiment.workflow_kind is None and classify_legacy_workflow(experiment).kind is not None
    )
