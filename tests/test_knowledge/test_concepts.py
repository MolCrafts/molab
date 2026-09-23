"""``molab.knowledge.concepts.parse_knowledge_class`` — the class-name entry point.

The six Knowledge class names are the vocabulary a config, a CLI flag or an
agent-tool payload already spells; the mapping lives once, on the knowledge
side, and an unknown name fails loudly with the candidates listed.
"""

from __future__ import annotations

import pytest

from molab.knowledge import Finding, Literature, Note, Observation, Plan, Report
from molab.knowledge.concepts import parse_knowledge_class

_EXPECTED: tuple[tuple[str, type], ...] = (
    ("Note", Note),
    ("Literature", Literature),
    ("Report", Report),
    ("Finding", Finding),
    ("Plan", Plan),
    ("Observation", Observation),
)


class TestParseKnowledgeClass:
    @pytest.mark.parametrize(("name", "expected"), _EXPECTED)
    def test_the_class_name_maps_to_its_subclass(self, name: str, expected: type) -> None:
        assert parse_knowledge_class(name) is expected

    def test_an_unknown_name_is_refused_with_the_candidates(self) -> None:
        with pytest.raises(ValueError) as excinfo:
            parse_knowledge_class("Chart")

        message = str(excinfo.value)
        assert "unknown knowledge class 'Chart'" in message
        assert "Finding, Literature, Note, Observation, Plan, Report" in message
