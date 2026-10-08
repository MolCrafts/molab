"""Shared workflow-document checks for the server writers.

Routes that bind a document compile it here, and refuse an experiment that
still needs ``molab migrate workflow-kind``. Neither function writes.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from molab.services.workflow_kind import needs_workflow_kind_migration
from molab.workflow import CompiledWorkflow, default_codec
from molab.workspace import Experiment

from .exceptions import ConflictError

__all__ = [
    "compile_workflow_document",
    "require_migrated_workflow_binding",
]


def compile_workflow_document(
    document: Mapping[str, Any],
) -> tuple[CompiledWorkflow, dict[str, Any]]:
    """Validate *document* and return ``(spec, normalized IR)``.

    ``ir_to_spec`` checks the document; ``spec_to_ir`` is the shape writers
    persist. An unregistered ``task_type`` raises ``KeyError`` from the task
    registry; that becomes ``ValueError`` so the HTTP handlers map it to 400.
    ``WorkflowError`` and ``ValueError`` propagate unchanged.

    Args:
        document: Workflow IR object (codec wire shape).

    Returns:
        The compiled workflow and the normalized IR document.

    Raises:
        ValueError: The document is malformed, or names an unregistered task type.
        WorkflowError: The document is structurally invalid.
    """
    try:
        spec = default_codec.ir_to_spec(document)
    except KeyError as exc:
        detail = exc.args[0] if exc.args else "unregistered task_type"
        raise ValueError(detail) from exc
    return spec, dict(default_codec.spec_to_ir(spec))


def require_migrated_workflow_binding(experiment: Experiment) -> None:
    """Refuse a legacy experiment that ``migrate workflow-kind`` would bind.

    Read-only. Writers call this before any bind so a legacy experiment is
    409 instead of being guessed into a kind.

    Args:
        experiment: Experiment about to be written. Not modified.

    Raises:
        ConflictError: The experiment predates ``workflow_kind`` and migration
            would bind it.
    """
    if not needs_workflow_kind_migration(experiment):
        return
    root = experiment.project.workspace.root
    raise ConflictError(
        message=(
            f"experiment {experiment.id} predates workflow_kind; "
            f"run `molab migrate workflow-kind {root}` first"
        ),
        details={"workflow_kind": None, "remedy": "molab migrate workflow-kind"},
    )
