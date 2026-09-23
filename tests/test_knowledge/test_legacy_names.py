"""Deleted knowledge product names must not import from molab.knowledge."""

from __future__ import annotations

import importlib

import pytest

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

    def test_workspace_knowledge_module_is_gone(self) -> None:
        # crossref-08: the workspace shed every knowledge verb — the module that
        # used to carry them is not merely shrunken, it does not exist.
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module("molab.workspace.knowledge")

    def test_workspace_knowledge_names_are_unreachable(self) -> None:
        import molab.workspace as workspace

        for name in ("HasKnowledge", "FailureAnalysis", "ProtocolNote", "Decision"):
            assert not hasattr(workspace, name)
