"""AssembleKnowledgeContext walks Knowledge(root) in six-class order."""

from __future__ import annotations

import inspect
from pathlib import Path

from molab.harness.stages.assemble_knowledge_context import (
    _CLASS_ORDER,
    AssembleKnowledgeContext,
)
from molab.knowledge import Finding, Literature, Note, Observation, Plan, Report, SourceRef
from molab.workspace import Workspace


class TestAssembleKnowledgeContext:
    def test_class_order_starts_with_report_then_finding(self) -> None:
        assert _CLASS_ORDER[:2] == (Report, Finding)
        assert (Report, Finding, Plan, Observation, Note, Literature) == _CLASS_ORDER

    def test_render_uses_knowledge_walk(self) -> None:
        src = inspect.getsource(AssembleKnowledgeContext._render_digest)
        assert "Knowledge(root).walk()" in src
        assert "get_folder" not in src
        assert "FailureAnalysis" not in src

    def test_report_heading_before_finding(self, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "ws", name="lab")
        ws.materialize()
        source = [SourceRef(kind="run", ref="r1")]
        finding = Finding(Path(str(ws.root)) / "finding-a", sources=source)
        finding.write("# Finding body\n")
        report = Report(Path(str(ws.root)) / "report-a", sources=source)
        report.write("# Report body\n")
        digest = AssembleKnowledgeContext()._render_digest(Path(str(ws.root)))
        assert digest.index("## [Report]") < digest.index("## [Finding]")
