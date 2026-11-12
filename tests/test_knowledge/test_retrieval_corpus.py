"""``Bm25fCorpus`` — tokenize a bundle once, rank many queries against it."""

from __future__ import annotations

from molab.knowledge.retrieval import Bm25fCorpus

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


class TestCorpusRanking:
    def test_a_limit_keeps_that_many(self) -> None:
        assert len(Bm25fCorpus(DOCS).rank("计算", limit=1)) == 1

    def test_the_question_still_finds_the_protocol_note_first(self) -> None:
        ranked = Bm25fCorpus(DOCS).rank("计算 Tg 的时候升降温怎么选择")
        assert ranked[0].key == "tg-protocol"


class TestCorpusEdges:
    def test_empty_corpus_ranks_nothing(self) -> None:
        corpus = Bm25fCorpus({})
        assert len(corpus) == 0
        assert corpus.rank("anything") == []

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
