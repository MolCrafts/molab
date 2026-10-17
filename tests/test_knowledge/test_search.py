"""In-memory ranker (``molab.knowledge.search``)."""

from __future__ import annotations

import pytest

from molab.knowledge.retrieval import Bm25fCorpus
from molab.knowledge.search import (
    MAX_BODY_SEARCH_BYTES,
    ConceptIndexEntry,
    best_body_line,
    capped_body,
    passes_filters,
    ranking_corpus,
    search_index,
)


def _entry(
    path: str, *, type: str = "Note", title: str = "", tags: tuple[str, ...] = ()
) -> ConceptIndexEntry:
    return ConceptIndexEntry(path=path, type=type, title=title, tags=tags)


def _index(*entries: ConceptIndexEntry) -> tuple[ConceptIndexEntry, ...]:
    return entries


class TestSearchIndex:
    def test_body_query_ranks_the_matching_document_first(self) -> None:
        index = _index(
            _entry("a", title="a"),
            _entry("b", title="b"),
            _entry("c", title="c"),
        )
        result = search_index(index, {"b": "alpha beta"}, "beta")

        assert result.hits[0].entry.path == "b"
        assert result.hits[0].snippet == "alpha beta"
        assert "body" in result.hits[0].matched_fields

    def test_text_none_keeps_index_order_and_zero_scores(self) -> None:
        index = _index(_entry("a"), _entry("b"), _entry("c"))

        result = search_index(index, {"b": "alpha beta"}, None)

        assert [hit.entry.path for hit in result.hits] == ["a", "b", "c"]
        assert [hit.score for hit in result.hits] == [0.0, 0.0, 0.0]

    def test_limit_one_reports_truncated(self) -> None:
        index = _index(_entry("a"), _entry("b"), _entry("c"))

        result = search_index(index, {}, None, limit=1)

        assert len(result.hits) == 1
        assert result.truncated is True

    def test_include_body_false_drops_the_body_match(self) -> None:
        index = _index(_entry("a", title="a"), _entry("b", title="b"))

        result = search_index(index, {"b": "alpha beta"}, "beta", include_body=False)

        assert [hit.entry.path for hit in result.hits] == []

    def test_concept_type_keeps_only_notes(self) -> None:
        index = _index(_entry("a", type="Note"), _entry("b", type="Finding"))

        result = search_index(index, {}, None, concept_type="Note")

        assert [hit.entry.path for hit in result.hits] == ["a"]


class TestRankingCorpus:
    def test_path_slashes_become_spaces_and_tags_pass_through(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: dict[str, dict[str, object]] = {}
        real = Bm25fCorpus

        def capture(documents: dict[str, dict[str, object]]) -> Bm25fCorpus:
            seen.update(documents)
            return real(documents)

        import molab.knowledge.search as search_mod

        monkeypatch.setattr(search_mod, "Bm25fCorpus", capture)  # type: ignore[attr-defined]
        entry = _entry("projects/p/x.md", title="T", tags=("Tg", "glass"))

        ranking_corpus(_index(entry), {})

        assert seen[entry.path]["path"] == "projects p x.md"
        assert seen[entry.path]["tags"] == ["Tg", "glass"]


class TestPassesFilters:
    def test_scope_is_a_path_prefix(self) -> None:
        inside = _entry("projects/p/x.md")
        sibling = _entry("projects/pp/x.md")

        assert passes_filters(inside, concept_type=None, tag=None, scope="projects/p") is True
        assert passes_filters(sibling, concept_type=None, tag=None, scope="projects/p") is False

    def test_a_missing_tag_rejects(self) -> None:
        entry = _entry("a", tags=("glass",))

        assert passes_filters(entry, concept_type=None, tag="Tg", scope=None) is False


class TestCappedBody:
    def test_over_the_cap_becomes_empty(self) -> None:
        assert capped_body("x" * (MAX_BODY_SEARCH_BYTES + 1)) == ""

    def test_a_short_body_is_kept(self) -> None:
        assert capped_body("short") == "short"


class TestBestBodyLine:
    def test_the_line_with_the_query_is_chosen(self) -> None:
        body = "# 标题\n降温速率的选择\n无关"

        assert best_body_line(body, "降温速率") == "降温速率的选择"

    def test_no_overlap_is_none(self) -> None:
        assert best_body_line("alpha\nbeta", "gamma") is None

    def test_a_long_line_is_cut_to_160_characters(self) -> None:
        line = "beta " + ("x" * 200)

        snippet = best_body_line(line, "beta")

        assert snippet is not None
        assert len(snippet) == 160


class TestSearchModels:
    def test_the_public_hit_is_the_search_module_hit(self) -> None:
        import molab.knowledge
        from molab.knowledge.search import SearchHit

        assert molab.knowledge.SearchHit is SearchHit

    def test_an_empty_result_is_not_truncated(self) -> None:
        from molab.knowledge.search import SearchResult

        result = SearchResult()

        assert result.hits == ()
        assert result.truncated is False

    def test_an_entry_defaults_title_and_tags_empty(self) -> None:
        entry = ConceptIndexEntry(path="knowledges/a.md", type="Note")

        assert entry.title == ""
        assert entry.tags == ()


class TestExtractTitle:
    @pytest.mark.parametrize(
        ("text", "title"),
        [
            ("# Cooling rate\n\nbody", "Cooling rate"),
            ("no heading", None),
            ("# 玻璃化转变\n", "玻璃化转变"),
            ("text\n#  Spaced  \n", "Spaced"),
        ],
    )
    def test_the_first_heading_is_the_title(self, text: str, title: str | None) -> None:
        from molab.knowledge.search import extract_title

        assert extract_title(text) == title


class TestSearchImportWeight:
    def test_module_imports_stay_in_stdlib_pydantic_and_retrieval(self) -> None:
        import ast
        import sys
        from pathlib import Path

        tree = ast.parse(Path("src/molab/knowledge/search.py").read_text(encoding="utf-8"))
        modules: set[str] = set()
        for node in tree.body:
            if isinstance(node, ast.Import):
                modules.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                name = node.module.lstrip(".")
                modules.add(name.split(".", 1)[0])
        allowed = set(sys.stdlib_module_names) | {"__future__", "pydantic", "retrieval"}
        assert modules <= allowed
