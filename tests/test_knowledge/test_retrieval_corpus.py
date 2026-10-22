"""``Bm25fCorpus`` — the reusable, pre-tokenized form of ``bm25f_rank``.

The corpus exists so a host can tokenize a bundle once and rank many queries
against it. Its whole contract is *identical results*: for every query and
option, ``Bm25fCorpus(docs).rank(q)`` must equal ``bm25f_rank(q, docs)``.
"""

from __future__ import annotations

import pytest

from molab.knowledge.retrieval import Bm25fCorpus, ScoredDoc, bm25f_rank

DOCS = {
    "tg-protocol": {
        "title": "降温速率的选择",
        "tags": ["tg", "protocol"],
        "path": "protocols tg",
        "body": "计算 Tg 时以 1 K/ns 降温至 200 K, 取拐点。",
    },
    "rdf-analysis": {
        "title": "RDF analysis",
        "tags": ["analysis"],
        "path": "analysis rdf",
        "body": "计算径向分布函数 g(r) 的步骤。",
    },
    "cluster-usage": {
        "title": "Cluster usage",
        "tags": [],
        "path": "ops cluster",
        "body": "how to submit jobs to the scheduler",
    },
    "empty": {"title": "", "tags": [], "path": "empty", "body": ""},
}

QUERIES = ["计算 Tg 的时候升降温怎么选择", "rdf", "scheduler jobs", "降温速率", "zzz-no-match", ""]


def _as_tuples(ranked: list[ScoredDoc]) -> list[tuple[str, float, tuple[str, ...]]]:
    return [(d.key, round(d.score, 12), d.matched_fields) for d in ranked]


class TestCorpusMatchesOneShotRanking:
    @pytest.mark.parametrize("query", QUERIES)
    def test_identical_keys_scores_and_fields(self, query: str) -> None:
        corpus = Bm25fCorpus(DOCS)
        assert _as_tuples(corpus.rank(query)) == _as_tuples(bm25f_rank(query, DOCS))

    def test_one_corpus_answers_many_queries(self) -> None:
        corpus = Bm25fCorpus(DOCS)
        for query in QUERIES:
            assert _as_tuples(corpus.rank(query)) == _as_tuples(bm25f_rank(query, DOCS))

    def test_limit_and_boosts_pass_through(self) -> None:
        corpus = Bm25fCorpus(DOCS)
        boosts = {"title": 10.0, "body": 0.1}
        assert _as_tuples(corpus.rank("计算", limit=1, boosts=boosts)) == _as_tuples(
            bm25f_rank("计算", DOCS, limit=1, boosts=boosts)
        )
        assert len(corpus.rank("计算", limit=1)) == 1

    def test_the_question_still_finds_the_protocol_note_first(self) -> None:
        ranked = Bm25fCorpus(DOCS).rank("计算 Tg 的时候升降温怎么选择")
        assert ranked[0].key == "tg-protocol"


class TestCorpusEdges:
    def test_empty_corpus_ranks_nothing(self) -> None:
        corpus = Bm25fCorpus({})
        assert len(corpus) == 0
        assert corpus.rank("anything") == []
        assert bm25f_rank("anything", {}) == []

    def test_empty_query_ranks_nothing(self) -> None:
        assert Bm25fCorpus(DOCS).rank("") == []
        assert Bm25fCorpus(DOCS).rank("   ") == []

    def test_len_and_contains(self) -> None:
        corpus = Bm25fCorpus(DOCS)
        assert len(corpus) == len(DOCS)
        assert "tg-protocol" in corpus
        assert "nope" not in corpus

    def test_ranking_is_deterministic_on_ties(self) -> None:
        docs = {"b": {"title": "same words"}, "a": {"title": "same words"}}
        assert [d.key for d in Bm25fCorpus(docs).rank("same")] == ["a", "b"]
