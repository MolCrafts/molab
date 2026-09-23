"""``ChangeProposal`` binds knowledge's own ``SourceRef`` — no mirror type."""

from __future__ import annotations

import inspect

import molab.knowledge
from molab.harness.schemas import change_proposal


class TestChangeProposalSchema:
    def test_sourceref_is_the_knowledge_object(self) -> None:
        assert change_proposal.SourceRef is molab.knowledge.SourceRef

    def test_knowledge_field_annotates_the_knowledge_sourceref_list(self) -> None:
        annotation = change_proposal.ChangeProposal.model_fields["knowledge"].annotation
        assert annotation == list[molab.knowledge.SourceRef]

    def test_sourceref_is_imported_from_molab_knowledge(self) -> None:
        src = inspect.getsource(change_proposal)
        assert "from molab.knowledge import SourceRef" in src
        assert "molab.workspace" not in src
