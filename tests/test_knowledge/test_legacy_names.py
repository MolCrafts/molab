"""Deleted knowledge product names must not import from molab.knowledge."""

from __future__ import annotations

import molab.knowledge as knowledge


class TestLegacyNames:
    def test_bundle_is_not_public(self) -> None:
        import molab.workspace as workspace

        assert "Bundle" not in knowledge.__all__
        assert not hasattr(knowledge, "Bundle")
        assert "Bundle" not in workspace.__all__
        assert not hasattr(workspace, "Bundle")

    def test_index_types_are_not_public(self) -> None:
        import molab.workspace as workspace

        for name in ("Backlink", "BundleIndex", "ConceptIndexEntry", "ConceptNotFoundError"):
            assert name not in knowledge.__all__
            assert name not in workspace.__all__
            assert not hasattr(workspace, name)

    def test_reference_concept_is_not_public(self) -> None:
        assert "ReferenceConcept" not in knowledge.__all__
        assert not hasattr(knowledge, "ReferenceConcept")

    def test_has_knowledge_is_gone(self) -> None:
        import molab.workspace.knowledge as ws_knowledge

        assert "HasKnowledge" not in ws_knowledge.__all__
        assert not hasattr(ws_knowledge, "HasKnowledge")

    def test_failure_analysis_is_gone(self) -> None:
        import molab.workspace.knowledge as ws_knowledge

        assert not hasattr(ws_knowledge, "FailureAnalysis")
        assert not hasattr(ws_knowledge, "ProtocolNote")
        assert not hasattr(ws_knowledge, "Decision")
