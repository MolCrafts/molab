"""``molab.knowledge.concepts.parse_class`` — the class-name entry point.

The six Knowledge class names are the vocabulary a config, a CLI flag or an
agent-tool payload already spells; the mapping lives once, on the knowledge
side, and an unknown name fails loudly with the candidates listed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from molab.knowledge import Finding, Literature, Note, Observation, Plan, Report
from molab.knowledge.concepts import parse_class

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
        assert parse_class(name) is expected

    def test_an_unknown_name_is_refused_with_the_candidates(self) -> None:
        with pytest.raises(ValueError) as excinfo:
            parse_class("Chart")

        message = str(excinfo.value)
        assert "unknown knowledge class 'Chart'" in message
        assert "Finding, Literature, Note, Observation, Plan, Report" in message


class TestSourcedKnowledgeSources:
    def test_a_reopened_doc_reads_the_run_edge(self, tmp_path: Path) -> None:
        from molab.knowledge import Knowledge
        from molab.knowledge.knowledge_item import SourceRef

        finding = Finding(
            tmp_path / "f",
            sources=[SourceRef(kind="run", ref="molab:experiment/E1/run/R1")],
        )
        finding.write("# F\n")

        reopened = Knowledge.open(finding.path)

        assert reopened.sources == [SourceRef(kind="run", ref="molab:experiment/E1/run/R1")]

    def test_a_sourceless_legacy_finding_opens_empty(self, tmp_path: Path) -> None:
        from molab.knowledge import Knowledge

        path = tmp_path / "old.md"
        path.write_text("---\nclass: Finding\n---\n\n# Old\n")

        opened = Knowledge.open(path)

        assert isinstance(opened, Finding)
        assert opened.sources == []

    def test_an_edge_precedes_the_legacy_row(self, tmp_path: Path) -> None:
        from molab.knowledge import Knowledge
        from molab.knowledge.knowledge_item import SourceRef

        path = tmp_path / "mix.md"
        path.write_text(
            "---\nclass: Finding\nsources:\n- kind: file\n  ref: legacy.txt\n---\n\n"
            "# M\n- [@derived_from R1](molab:experiment/E1/run/R1)\n"
        )

        opened = Knowledge.open(path)

        assert opened.sources == [
            SourceRef(kind="run", ref="molab:experiment/E1/run/R1"),
        ]

    def test_a_references_edge_is_not_a_source(self, tmp_path: Path) -> None:
        from molab.knowledge import Knowledge

        path = tmp_path / "r.md"
        path.write_text("---\nclass: Finding\n---\n\n- [R1](molab:experiment/E1/run/R1)\n")

        assert Knowledge.open(path).sources == []

    def test_frontmatter_sources_are_not_a_record(self) -> None:
        from molab.knowledge.concepts import _SourcedKnowledge

        assert not hasattr(_SourcedKnowledge, "_legacy_frontmatter_sources")

    def test_a_frontmatter_row_alone_is_ignored(self, tmp_path: Path) -> None:
        from molab.knowledge import Knowledge

        path = tmp_path / "fa.md"
        text = "---\nclass: Finding\nsources:\n- kind: run\n  ref: molab:experiment/E1/run/R1\n---\n\n# A\n"
        path.write_text(text, encoding="utf-8")
        before = path.read_bytes()

        opened = Knowledge.open(path)

        assert isinstance(opened, Finding)
        assert opened.sources == []
        assert path.read_bytes() == before

    def test_a_link_is_the_only_source(self, tmp_path: Path) -> None:
        from molab.knowledge import Knowledge
        from molab.knowledge.knowledge_item import SourceRef

        path = tmp_path / "fb.md"
        path.write_text(
            "---\nclass: Finding\nsources:\n- kind: run\n  ref: molab:experiment/E1/run/R1\n---\n\n"
            "# B\n- [@derived_from R1](molab:experiment/E1/run/R1)\n",
            encoding="utf-8",
        )

        opened = Knowledge.open(path)

        assert opened.sources == [SourceRef(kind="run", ref="molab:experiment/E1/run/R1")]

    def test_writing_tags_keeps_the_frontmatter_sources_value(self, tmp_path: Path) -> None:
        from molab.knowledge import Knowledge

        path = tmp_path / "fa.md"
        path.write_text(
            "---\nclass: Finding\nsources:\n- kind: file\n  ref: legacy.txt\n---\n\n# A\n",
            encoding="utf-8",
        )
        opened = Knowledge.open(path)
        stored = opened.frontmatter()["sources"]

        opened.write(tags=["t"])

        assert opened.frontmatter()["sources"] == stored
        assert opened.sources == []
        assert opened.tags() == ["t"]


class TestHarvestTargets:
    def test_the_view_is_finding_observation_report(self) -> None:
        from molab.knowledge.concepts import _PRODUCTS, HARVEST_TARGETS

        assert tuple(HARVEST_TARGETS) == ("Finding", "Observation", "Report")
        for key in HARVEST_TARGETS:
            assert HARVEST_TARGETS[key] is _PRODUCTS[key]

    def test_item_assignment_is_refused(self) -> None:
        from molab.knowledge.concepts import HARVEST_TARGETS

        with pytest.raises(TypeError):
            HARVEST_TARGETS["Note"] = Note  # type: ignore[index]


class TestNoteFrontmatterOnly:
    def test_missing_tags_and_status_use_the_defaults(self, tmp_path: Path) -> None:
        note = Note(tmp_path / "n.md")
        note.write("# N\n")

        assert note.tags() == []
        assert note.status() == "active"

    def test_tags_and_status_come_from_frontmatter(self, tmp_path: Path) -> None:
        path = tmp_path / "n.md"
        path.write_text(
            "---\nclass: Note\ntags:\n- tg\nstatus: draft\n---\n\n# N\n",
            encoding="utf-8",
        )
        note = Note(path)

        assert note.tags() == ["tg"]
        assert note.status() == "draft"
