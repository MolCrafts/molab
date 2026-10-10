"""In-memory BM25F ranking over an already-built index.

No I/O. Callers pass the index rows and the bodies they have already read.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from pydantic import BaseModel

from .retrieval import Bm25fCorpus, tokenize

_H1 = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)


def extract_title(index_md: str) -> str | None:
    """Return the first markdown H1 in *index_md*, or ``None`` if absent.

    Args:
        index_md: The document narrative.

    Returns:
        The H1 title without the leading ``#``, or ``None`` when there is no H1.
    """
    match = _H1.search(index_md)
    return match.group(1).strip() if match else None


class ConceptIndexEntry(BaseModel, frozen=True):
    """One document's row in a search index.

    Attributes:
        path: POSIX path relative to the searched root.
        type: The Knowledge class name.
        id: Optional stable id.
        title: The H1 if present, else the document name.
        tags: Frontmatter tags.
        links: Out-edge targets.
    """

    path: str
    type: str
    id: str | None = None
    title: str = ""
    tags: tuple[str, ...] = ()
    links: tuple[str, ...] = ()


class SearchHit(BaseModel, frozen=True):
    """One search match.

    Attributes:
        entry: The matching row.
        snippet: The best-matching body line, trimmed to 160 characters.
        matched_fields: Which fields matched. Empty for a filter-only query.
        score: The BM25F score. ``0.0`` when nothing was ranked.
    """

    entry: ConceptIndexEntry
    snippet: str | None = None
    matched_fields: tuple[str, ...] = ()
    score: float = 0.0


class SearchResult(BaseModel, frozen=True):
    """The outcome of one search.

    Attributes:
        hits: Ranked queries come back score-descending. A filter-only query
            keeps index order.
        truncated: ``True`` when ``limit`` cut real matches.
    """

    hits: tuple[SearchHit, ...] = ()
    truncated: bool = False


MAX_BODY_SEARCH_BYTES = 512 * 1024
"""Body-search size cap so one pathological document cannot stall retrieval."""

__all__ = [
    "MAX_BODY_SEARCH_BYTES",
    "ConceptIndexEntry",
    "SearchHit",
    "SearchResult",
    "best_body_line",
    "capped_body",
    "extract_title",
    "passes_filters",
    "ranking_corpus",
    "search_index",
]


def ranking_corpus(entries: Sequence[ConceptIndexEntry], bodies: Mapping[str, str]) -> Bm25fCorpus:
    """Build the BM25F corpus over the whole *index*.

    Bodies are keyed by entry path. The path field replaces ``/`` with a
    space so each segment is its own term. Tags are the entry's tags.

    Args:
        index: The in-memory index to rank.
        bodies: Body text per entry path. A missing path ranks as empty.

    Returns:
        A corpus a caller can reuse across queries.
    """
    documents = {
        entry.path: {
            "title": entry.title,
            "tags": list(entry.tags),
            "path": entry.path.replace("/", " "),
            "body": bodies.get(entry.path, ""),
        }
        for entry in entries
    }
    return Bm25fCorpus(documents)


def passes_filters(
    entry: ConceptIndexEntry,
    *,
    concept_type: str | None,
    tag: str | None,
    scope: str | None,
) -> bool:
    """Return whether *entry* survives the pre-ranking filters.

    The filters are AND. *scope* is a path prefix: ``projects/p`` accepts
    ``projects/p/x.md`` and rejects ``projects/pp/x.md``.

    Args:
        entry: One index row.
        concept_type: Exact type to keep, or ``None``.
        tag: A tag that must be present, or ``None``.
        scope: Path prefix, or ``None``.

    Returns:
        ``True`` when every given filter matches.
    """
    if concept_type is not None and entry.type != concept_type:
        return False
    if tag is not None and tag not in entry.tags:
        return False
    if scope is not None:
        prefix = scope.rstrip("/")
        if entry.path != prefix and not entry.path.startswith(prefix + "/"):
            return False
    return True


def capped_body(text: str) -> str:
    """Return *text*, or ``""`` when its UTF-8 size exceeds the body cap.

    Args:
        text: A document body already in memory.

    Returns:
        *text* when it is within :data:`MAX_BODY_SEARCH_BYTES`, else ``""``.
    """
    if len(text.encode("utf-8")) > MAX_BODY_SEARCH_BYTES:
        return ""
    return text


def best_body_line(body: str, query: str) -> str | None:
    """Return the body line sharing the most query terms, trimmed to 160 characters.

    Ranking picked the document; this picks the line to show for it. Scoring
    lines by shared terms means the snippet lands on the passage that earned
    the hit.

    Args:
        body: The document body.
        query: The query whose terms select the line.

    Returns:
        The best line, or ``None`` when no line shares a query term.
    """
    wanted = set(tokenize(query))
    if not wanted:
        return None
    best: tuple[int, str] | None = None
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        overlap = len(wanted & set(tokenize(stripped)))
        if overlap and (best is None or overlap > best[0]):
            best = (overlap, stripped)
    return best[1][:160] if best is not None else None


def search_index(
    entries: Sequence[ConceptIndexEntry],
    bodies: Mapping[str, str],
    text: str | None,
    *,
    concept_type: str | None = None,
    tag: str | None = None,
    scope: str | None = None,
    limit: int = 50,
    include_body: bool = True,
    corpus: Bm25fCorpus | None = None,
) -> SearchResult:
    """Rank *text* over *index*, or keep index order when there is nothing to rank.

    A missing or empty *text* is filter-only: hits stay in index order and
    every score is ``0.0``. Otherwise hits come back score-descending. A body
    over the size cap is dropped from body matching. ``include_body=False``
    ranks on the index fields alone.

    Args:
        index: The in-memory index.
        bodies: Body text per entry path.
        text: The query. ``None`` or empty means filter-only.
        concept_type: Exact type to keep.
        tag: A tag that must be present.
        scope: Path prefix to keep.
        limit: Maximum hits. A cut result reports ``truncated=True``.
        include_body: ``False`` skips body matching.
        corpus: A corpus already built over *index* and the ranking bodies.

    Returns:
        The hits, and whether *limit* cut real matches.
    """
    ranking_bodies = {
        entry.path: (capped_body(bodies.get(entry.path, "")) if include_body else "")
        for entry in entries
    }
    if not text:
        candidates = [
            entry
            for entry in entries
            if passes_filters(entry, concept_type=concept_type, tag=tag, scope=scope)
        ]
        hits = tuple(SearchHit(entry=entry) for entry in candidates[:limit])
        return SearchResult(hits=hits, truncated=len(candidates) > limit)
    if corpus is None:
        corpus = ranking_corpus(entries, ranking_bodies)
    return _rank(
        corpus,
        entries,
        ranking_bodies,
        text,
        concept_type=concept_type,
        tag=tag,
        scope=scope,
        limit=limit,
    )


def _rank(
    corpus: Bm25fCorpus,
    entries: Sequence[ConceptIndexEntry],
    bodies: Mapping[str, str],
    text: str,
    *,
    concept_type: str | None,
    tag: str | None,
    scope: str | None,
    limit: int,
) -> SearchResult:
    """Rank *text* over *corpus*, then narrow by the filters."""
    by_path = {entry.path: entry for entry in entries}
    ranked = [
        doc
        for doc in corpus.rank(text)
        if passes_filters(by_path[doc.key], concept_type=concept_type, tag=tag, scope=scope)
    ]
    hits = tuple(
        SearchHit(
            entry=by_path[doc.key],
            snippet=(
                best_body_line(bodies.get(doc.key, ""), text)
                if "body" in doc.matched_fields
                else None
            ),
            matched_fields=tuple(
                "tag" if field == "tags" else field for field in doc.matched_fields
            ),
            score=doc.score,
        )
        for doc in ranked[:limit]
    )
    return SearchResult(hits=hits, truncated=len(ranked) > limit)
