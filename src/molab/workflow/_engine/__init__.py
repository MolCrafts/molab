"""Workflow engine internals — lowering, structural scheduler, persistence.

This private subpackage is the molab-owned execution engine
(historically named ``_pydantic_graph/`` when it shimmed that library;
the dependency has been removed entirely and nothing under ``src/`` may
import ``pydantic_graph`` — enforced by
``tests/test_workflow/test_engine_boundary.py``). The compiler lowers
the topology to an :class:`~.plan.ExecutionPlan` and :mod:`.engine`
runs it with values-on-edges semantics (inputs delivered from upstream
outputs, structural deadlock detection, no timing constants). The
``End`` sentinel is molab-owned and lives in
:mod:`molab.workflow.types`.
"""

from .compiler import WorkflowGraphCompiler
from .runtime import WorkflowRuntime

__all__ = [
    "WorkflowGraphCompiler",
    "WorkflowRuntime",
]
