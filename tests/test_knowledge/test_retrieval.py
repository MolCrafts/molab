# ruff: noqa: RUF003 — the CJK text and full-width characters below are the
# fixtures under test; "fixing" them to ASCII would delete the test.
"""CJK-aware tokenization + BM25F ranking.

The load-bearing case is a natural-language question that shares **no substring**
with the document that answers it — which is the normal case in Chinese, and the
reason substring search was not good enough.
"""

from __future__ import annotations

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
