"""AssembleKnowledgeContext walks Knowledge(root) in six-class order."""

from __future__ import annotations

import inspect

from molab.harness.stages.assemble_knowledge_context import (
    _CLASS_ORDER,
    AssembleKnowledgeContext,
)
from molab.knowledge import Finding, Literature, Note, Observation, Plan, Report


class TestAssembleKnowledgeContext:
    def test_class_order_starts_with_report_then_finding(self) -> None:
        assert _CLASS_ORDER[:2] == (Report, Finding)
        assert (Report, Finding, Plan, Observation, Note, Literature) == _CLASS_ORDER

    def test_render_uses_knowledge_walk(self) -> None:
        src = inspect.getsource(AssembleKnowledgeContext._render_digest)
        assert "Knowledge(root).walk()" in src
        assert "get_folder" not in src
        assert "FailureAnalysis" not in src
