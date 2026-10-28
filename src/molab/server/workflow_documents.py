"""Shared workflow-document checks for the server writers.

Routes that bind a document compile it here. The function does not write.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from molab.workflow import CompiledWorkflow, default_codec

__all__ = [
    "compile_workflow_document",
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
