"""Keyword retrieval over an OKF bundle — CJK-aware tokenization + BM25F.

Substring matching cannot answer a real question. A researcher asks "计算 Tg 的
时候升降温怎么选择", and the note that answers it is titled "降温速率的选择" —
no substring of the question appears in it. Ranking by *terms* does answer it.

This is deliberately **not** RAG: no embeddings, no vector store, no chunking, no
LLM re-ranking. Stdlib only. The job is to put the right document first and hand
the whole thing to whoever asked — a person, or a model with the file in context.

**Tokenization.** Latin/alphanumeric runs become one token each (``tg``, ``dsc``,
``10k``). CJK has no word delimiters, so each CJK run emits **both** its single
characters and its adjacent character bigrams: ``计算Tg`` → ``计``, ``算``,
``计算``, ``tg``.

Emitting both is the whole trick, and it is self-balancing rather than tuned.
Bigrams alone lose single-character recall (``温``); unigrams alone destroy
precision (``计`` matches everything). Emitting both lets IDF sort it out: ``计算``
is far rarer in a corpus than ``计``, so it earns a much higher weight and
dominates the score on its own. No dictionary, no segmenter, no 20 MB model —
which is what keeps this module stdlib-only.

**Scoring.** Okapi BM25F — per *field*, not per document. Title, tags, path and
body each get their own length normalization and boost, combined into one
weighted pseudo-``tf`` *before* the saturation function. The naive alternative
(repeating a title's terms N times at index time) inflates document length and
corrupts the ``b`` normalization it is trying to exploit.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

__all__ = [
    "BM25_B",
    "BM25_K1",
    "FIELD_BOOSTS",
    "Bm25fCorpus",
    "ScoredDoc",
    "bm25f_rank",
    "tokenize",
]

# ── tokenization ──────────────────────────────────────────────────────────

#: One Latin/alphanumeric run (identifiers like ``tg``, ``10k``, ``r_min``).
_LATIN_RUN = re.compile(r"[0-9a-z_]+")

#: One run of CJK ideographs, kana or hangul — scripts written without spaces.
#: Spelled with explicit code-point escapes: the literal characters are
#: indistinguishable from ASCII lookalikes in a diff.
_CJK_RUN = re.compile(
    "[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]+"
)

#: Either kind of run; anything else (punctuation, spaces) is a separator.
_TOKEN_RUN = re.compile(f"{_LATIN_RUN.pattern}|{_CJK_RUN.pattern}")


def tokenize(text: str) -> list[str]:
    """Split *text* into match terms, handling CJK without a segmenter.

    Normalizes NFKC and case-folds first, so full-width and ASCII spellings of a
    symbol (and upper/lower case) both
    reach the same term. Then each Latin/alphanumeric run yields one token, and each CJK
    run yields its unigrams **and** its adjacent bigrams (see the module
    docstring for why both).

    Args:
        text: Raw text — a query, a title, a markdown body.

    Returns:
        The terms, in order, with duplicates retained (term frequency matters).
    """
    folded = unicodedata.normalize("NFKC", text).casefold()
    tokens: list[str] = []
    for match in _TOKEN_RUN.finditer(folded):
        run = match.group()
        if _CJK_RUN.fullmatch(run):
            tokens.extend(run)  # unigrams
            tokens.extend(run[i : i + 2] for i in range(len(run) - 1))  # bigrams
        else:
            tokens.append(run)
    return tokens


# ── BM25F ─────────────────────────────────────────────────────────────────

BM25_K1 = 1.2
"""Term-frequency saturation. Standard Okapi value."""

BM25_B = 0.75
"""Length-normalization strength. Standard Okapi value."""

FIELD_BOOSTS: dict[str, float] = {
    "title": 3.0,
    "tags": 2.0,
    "path": 1.5,
    "body": 1.0,
}
"""Per-field weights. A term in a title says far more about what a document *is*
about than the same term buried in its body; a tag is a deliberate, curated
claim about the document, so it ranks close behind."""


class ScoredDoc:
    """One ranked document: its key, its BM25F score, and which fields matched.

    A plain class rather than a pydantic model: this is an inner-loop scratch
    value built once per candidate per query, never persisted or validated.
    """

    __slots__ = ("key", "matched_fields", "score")

    def __init__(self, key: str, score: float, matched_fields: tuple[str, ...]) -> None:
        self.key = key
        self.score = score
        self.matched_fields = matched_fields

    def __repr__(self) -> str:
        return f"ScoredDoc({self.key!r}, score={self.score:.4f}, fields={self.matched_fields})"


def _idf(n_docs: int, df: int) -> float:
    """Robertson/Sparck-Jones IDF with the standard +0.5 smoothing.

    Floored at zero: a term present in nearly every document carries no signal,
    and a negative weight would let a common term *demote* a document that
    contains it, which is never what a reader means.
    """
    return max(0.0, math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5)))


class Bm25fCorpus:
    """A tokenized document set, ready to rank any number of queries.

    Everything that depends only on the *documents* — per-field term counts
    and lengths, average field lengths, document frequencies — is computed
    once here; :meth:`rank` then costs one pass over the query terms per
    document. A host that scans a bundle once and answers many queries keeps
    one of these next to its index instead of re-tokenizing the corpus per
    keystroke. A plain class: it holds derived counters, never persisted.
    """

    __slots__ = ("_avg_len", "_df", "_lengths", "_n_docs", "_tokenized")

    def __init__(self, documents: Mapping[str, Mapping[str, str | Sequence[str]]]) -> None:
        """Tokenize *documents* (``{key: {field: text-or-terms}}``) once.

        A field value may be a string (tokenized) or an already-split sequence
        of terms (tags). Unknown fields are kept and later scored with weight
        1.0 rather than dropped.
        """
        tokenized: dict[str, dict[str, Counter[str]]] = {}
        lengths: dict[str, dict[str, int]] = {}
        for key, fields in documents.items():
            per_field: dict[str, Counter[str]] = {}
            per_len: dict[str, int] = {}
            for field, value in fields.items():
                field_terms = _field_terms(value)
                per_field[field] = Counter(field_terms)
                per_len[field] = len(field_terms)
            tokenized[key] = per_field
            lengths[key] = per_len

        field_names = {f for per in lengths.values() for f in per}
        avg_len = {
            field: (sum(per.get(field, 0) for per in lengths.values()) / len(lengths)) or 1.0
            for field in field_names
        }

        # Document frequency is counted per *document*, across all its fields: a
        # term in both the title and the body is still one document containing it.
        df: Counter[str] = Counter()
        for per_field in tokenized.values():
            present = {t for counts in per_field.values() for t in counts}
            for term in present:
                df[term] += 1

        self._tokenized = tokenized
        self._lengths = lengths
        self._avg_len = avg_len
        self._df = df
        self._n_docs = len(documents)

    def __len__(self) -> int:
        return self._n_docs

    def __contains__(self, key: object) -> bool:
        return key in self._tokenized

    def rank(
        self,
        query: str,
        *,
        limit: int | None = None,
        boosts: Mapping[str, float] | None = None,
    ) -> list[ScoredDoc]:
        """Rank this corpus against *query* with BM25F, best first.

        Args:
            query: The raw query text; tokenized with :func:`tokenize`.
            limit: Keep at most this many hits; ``None`` keeps all.
            boosts: Per-field weights; defaults to :data:`FIELD_BOOSTS`.

        Returns:
            The documents that matched at least one query term, ordered by
            score descending and then by key ascending, so ties are
            deterministic.
        """
        weights = dict(FIELD_BOOSTS if boosts is None else boosts)
        terms = tokenize(query)
        if not terms or not self._n_docs:
            return []

        unique_terms = set(terms)
        results: list[ScoredDoc] = []
        for key, per_field in self._tokenized.items():
            score = 0.0
            matched: set[str] = set()
            doc_lengths = self._lengths[key]
            for term in unique_terms:
                doc_freq = self._df.get(term, 0)
                if doc_freq == 0:
                    continue
                # BM25F: combine the length-normalized per-field frequencies into a
                # single pseudo-tf, THEN saturate. Normalizing after saturation would
                # let a long body outweigh a precise title match.
                pseudo_tf = 0.0
                for field, counts in per_field.items():
                    tf = counts.get(term, 0)
                    if not tf:
                        continue
                    matched.add(field)
                    length = doc_lengths.get(field, 0)
                    norm = 1.0 - BM25_B + BM25_B * (length / self._avg_len.get(field, 1.0))
                    pseudo_tf += weights.get(field, 1.0) * tf / (norm or 1.0)
                if pseudo_tf <= 0.0:
                    continue
                score += _idf(self._n_docs, doc_freq) * pseudo_tf / (BM25_K1 + pseudo_tf)
            if score > 0.0:
                results.append(ScoredDoc(key, score, tuple(sorted(matched))))

        results.sort(key=lambda d: (-d.score, d.key))
        return results if limit is None else results[:limit]


def bm25f_rank(
    query: str,
    documents: Mapping[str, Mapping[str, str | Sequence[str]]],
    *,
    limit: int | None = None,
    boosts: Mapping[str, float] | None = None,
) -> list[ScoredDoc]:
    """Rank *documents* against *query* with BM25F, best first.

    The one-shot form of :class:`Bm25fCorpus` — tokenizes *documents* and
    ranks once. Identical results to ``Bm25fCorpus(documents).rank(query)``.

    Args:
        query: The raw query text; tokenized with :func:`tokenize`.
        documents: ``{key: {field: text-or-terms}}``. A field value may be a
            string (tokenized) or an already-split sequence of terms (tags).
            Unknown fields are scored with weight 1.0 rather than dropped.
        limit: Keep at most this many hits; ``None`` keeps all.
        boosts: Per-field weights; defaults to :data:`FIELD_BOOSTS`.

    Returns:
        The documents that matched at least one query term, ordered by score
        descending and then by key ascending, so ties are deterministic.
    """
    if not documents:
        return []
    return Bm25fCorpus(documents).rank(query, limit=limit, boosts=boosts)


def _field_terms(value: str | Sequence[str] | Iterable[str]) -> list[str]:
    """Terms for one field value — a string is tokenized, a sequence is joined.

    Tag lists arrive already split by the author; tokenizing each tag (rather
    than taking it whole) means a CJK tag still matches a query that names only
    part of it.
    """
    if isinstance(value, str):
        return tokenize(value)
    terms: list[str] = []
    for item in value:
        terms.extend(tokenize(str(item)))
    return terms
