# ruff: noqa: RUF001, RUF003 — the CJK text and full-width characters below are the
# fixtures under test; "fixing" them to ASCII would delete the test.
"""CJK-aware tokenization + BM25F ranking.

The load-bearing case is a natural-language question that shares **no substring**
with the document that answers it — which is the normal case in Chinese, and the
reason substring search was not good enough.
"""

from __future__ import annotations

from pathlib import Path

from molab.knowledge import Bundle, Note
from molab.knowledge.retrieval import bm25f_rank, tokenize


class TestTokenize:
    """Terms, not substrings — and CJK without a segmenter."""

    def test_latin_runs_become_one_token_each(self) -> None:
        assert tokenize("Tg DSC 10k r_min") == ["tg", "dsc", "10k", "r_min"]

    def test_case_and_width_are_folded(self) -> None:
        # The full-width characters here are the fixture, not a typo: NFKC must
        # fold them onto ASCII so a paper pasted from a PDF still matches.
        full_width = "\uff34\uff47"  # Ｔｇ
        assert tokenize(full_width) == tokenize("TG") == ["tg"]

    def test_cjk_emits_unigrams_and_bigrams(self) -> None:
        assert tokenize("降温速率") == ["降", "温", "速", "率", "降温", "温速", "速率"]

    def test_mixed_script_splits_at_the_boundary(self) -> None:
        assert tokenize("计算Tg") == ["计", "算", "计算", "tg"]

    def test_punctuation_separates_rather_than_joins(self) -> None:
        assert tokenize("a, b; c") == ["a", "b", "c"]

    def test_empty_and_symbol_only_text_yield_no_terms(self) -> None:
        assert tokenize("") == []
        assert tokenize("—— !!! ") == []

    def test_a_query_shares_bigrams_with_a_differently_worded_title(self) -> None:
        # "升降温" vs "降温速率" share the "降温" bigram — this single fact is
        # what makes the Chinese golden case below work.
        assert set(tokenize("升降温")) & set(tokenize("降温速率")) >= {"降温"}


class TestBm25fRank:
    """Scoring behaviour that callers depend on."""

    def test_ranks_the_document_containing_more_query_terms_first(self) -> None:
        docs = {
            "a": {"body": "alpha beta gamma"},
            "b": {"body": "alpha delta"},
        }
        ranked = bm25f_rank("alpha beta", docs)
        assert next(d.key for d in ranked) == "a"

    def test_title_boost_outranks_body(self) -> None:
        docs = {
            "in-title": {"title": "diffusion", "body": "unrelated prose"},
            "in-body": {"title": "unrelated", "body": "diffusion mentioned once"},
        }
        ranked = bm25f_rank("diffusion", docs)
        assert [d.key for d in ranked] == ["in-title", "in-body"]

    def test_documents_with_no_query_term_are_omitted(self) -> None:
        docs = {"a": {"body": "alpha"}, "b": {"body": "zeta"}}
        assert [d.key for d in bm25f_rank("alpha", docs)] == ["a"]

    def test_matched_fields_report_where_the_terms_were(self) -> None:
        docs = {"a": {"title": "alpha", "body": "beta", "tags": ["gamma"]}}
        ranked = bm25f_rank("alpha gamma", docs)
        assert ranked[0].matched_fields == ("tags", "title")

    def test_a_term_in_every_document_cannot_demote(self) -> None:
        # IDF is floored at zero: a universal term adds nothing, but must never
        # subtract — a negative weight would rank a document *below* one that
        # lacks the term it matched on.
        docs = {"a": {"body": "common alpha"}, "b": {"body": "common"}}
        ranked = bm25f_rank("common alpha", docs)
        assert next(d.key for d in ranked) == "a"
        assert all(d.score >= 0.0 for d in ranked)

    def test_ties_break_deterministically_by_key(self) -> None:
        docs = {"b": {"body": "alpha"}, "a": {"body": "alpha"}}
        assert [d.key for d in bm25f_rank("alpha", docs)] == ["a", "b"]

    def test_tags_are_tokenized_not_taken_whole(self) -> None:
        # A CJK tag must match a query naming only part of it.
        docs = {"a": {"tags": ["玻璃化转变"]}, "b": {"tags": ["其他"]}}
        assert [d.key for d in bm25f_rank("玻璃化", docs)] == ["a"]

    def test_empty_query_or_corpus_ranks_nothing(self) -> None:
        assert bm25f_rank("", {"a": {"body": "alpha"}}) == []
        assert bm25f_rank("alpha", {}) == []

    def test_limit_caps_the_result(self) -> None:
        docs = {k: {"body": "alpha"} for k in ("a", "b", "c")}
        assert len(bm25f_rank("alpha", docs, limit=2)) == 2


def _note(root: Path, name: str, body: str, tags: list[str] | None = None) -> Note:
    note = Note(root / name)
    note.write_meta({"tags": tags or []})
    note.set_body(body)
    return note


class TestChineseGoldenCase:
    """The question this whole feature exists to answer.

    A researcher asks "计算Tg的时候升降温怎么选择". The note that answers it is
    titled "玻璃化转变温度 Tg 的模拟流程" and its relevant heading is
    "降温速率的选择". **No substring of the question appears in that note** — the
    old substring search returned nothing at all.
    """

    QUESTION = "计算Tg的时候升降温怎么选择"

    def _wiki(self, tmp_path: Path) -> Bundle:
        _note(
            tmp_path,
            "tg-protocol",
            "# 玻璃化转变温度 Tg 的模拟流程\n\n"
            "## 降温速率的选择\n"
            "本组约定采用三段式：先在 600 K 平衡 5 ns，再以 1 K/ns 降温至 200 K，"
            "最后分段线性拟合比容-温度曲线取交点。降温速率过快会系统性高估 Tg。\n",
            tags=["Tg", "玻璃化转变", "退火"],
        )
        _note(
            tmp_path,
            "rdf-analysis",
            "# 径向分布函数分析\n\n计算 RDF 时的积分区间与归一化约定。\n",
            tags=["RDF"],
        )
        _note(tmp_path, "cluster-usage", "# 集群使用说明\n\n提交作业的排队规则。\n")
        return Bundle(tmp_path)

    def test_the_question_finds_the_protocol_note_first(self, tmp_path: Path) -> None:
        hits = self._wiki(tmp_path).search(self.QUESTION).hits
        assert hits, "the question must not come back empty"
        assert hits[0].entry.path == "tg-protocol"

    def test_the_snippet_lands_on_the_passage_that_answers_it(self, tmp_path: Path) -> None:
        hits = self._wiki(tmp_path).search(self.QUESTION).hits
        assert hits[0].snippet is not None
        assert "降温速率" in hits[0].snippet

    def test_the_answer_outranks_the_merely_related_note(self, tmp_path: Path) -> None:
        # "计算" appears in the RDF note too; the Tg note must still win.
        hits = self._wiki(tmp_path).search(self.QUESTION).hits
        by_path = {h.entry.path: h.score for h in hits}
        assert by_path["tg-protocol"] > by_path.get("rdf-analysis", 0.0)

    def test_an_unrelated_note_is_not_returned_at_all(self, tmp_path: Path) -> None:
        hits = self._wiki(tmp_path).search("降温速率").hits
        assert "cluster-usage" not in {h.entry.path for h in hits}

    def test_the_whole_markdown_is_reachable_from_a_hit(self, tmp_path: Path) -> None:
        # Not RAG: retrieval's job ends at handing over the document itself.
        wiki = self._wiki(tmp_path)
        hit = wiki.search(self.QUESTION).hits[0]
        concept = wiki.get(hit.entry.path)
        assert "1 K/ns 降温至 200 K" in concept.body()
        assert (concept.path / "index.md").is_file()


class TestSearchReadsEachBodyOnce:
    """Indexing and ranking share one read per Concept per query.

    Both halves want the same text — the title is the body's H1, the edges are
    its markdown links, and the ranking is over its words. Reading it more than
    once is pure waste on a local disk and a second network round trip on a
    remote one.
    """

    def test_one_read_per_concept(self, tmp_path: Path) -> None:
        from collections import Counter

        from molab.fs.local import LocalFileSystem
        from molab.knowledge import Bundle

        reads: list[str] = []

        class CountingFileSystem(LocalFileSystem):
            def read_text(self, path, encoding: str = "utf-8") -> str:  # type: ignore[override]
                if str(path).endswith("index.md"):
                    reads.append(str(path))
                return super().read_text(path, encoding)

        fs = CountingFileSystem()
        for i in range(4):
            note = Note(tmp_path / f"n{i}", fs=fs)
            note.write_meta()
            note.set_body(f"# Note {i}\n\nbody about diffusion {i}\n")

        reads.clear()
        Bundle(tmp_path, fs=fs).search("diffusion")

        per_file = Counter(reads)
        assert per_file, "the search must have read the bodies at all"
        assert max(per_file.values()) == 1, per_file
