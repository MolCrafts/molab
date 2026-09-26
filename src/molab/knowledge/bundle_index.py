"""Derived bundle index models (OKF rollup, in memory only).

:meth:`molab.knowledge.bundle.Bundle.scan_index` walks the whole Concept tree
and rolls each Concept's identity (path / type / id / tags / title / out-edges)
into a :class:`BundleIndex`. It is built in memory per query from the
authoritative ``meta.json`` + ``index.md`` graph and never persisted — never a
source of truth (the workspace "one source of truth" law).

``BundleIndex`` is an index *of every Concept in a directory subtree*.
"""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel

# First markdown H1 (``# Title``) line, if any.
_H1 = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)


def extract_title(index_md: str) -> str | None:
    """Return the first markdown H1 in *index_md*, or ``None`` if absent.

    Args:
        index_md: The raw ``index.md`` narrative text.

    Returns:
        The H1 title (without the leading ``#``), or ``None`` when there is no
        H1 heading.
    """
    match = _H1.search(index_md)
    return match.group(1).strip() if match else None


class ConceptIndexEntry(BaseModel, frozen=True):
    """One Concept's row in the derived bundle index.

    Attributes:
        path: Bundle-relative POSIX path — the Concept's identity.
        type: The Concept's ``meta.json`` type.
        id: Optional stable id from ``meta.json``.
        title: The ``index.md`` H1 if present, else the Concept name.
        tags: Categorical labels from ``meta.json``.
        links: Out-edges (in-tree Concept targets) as bundle-relative paths.
    """

    path: str
    type: str
    id: str | None = None
    title: str = ""
    tags: tuple[str, ...] = ()
    links: tuple[str, ...] = ()


class SearchHit(BaseModel, frozen=True):
    """One ``Bundle.search`` match.

    Attributes:
        entry: The matching Concept's index row.
        snippet: The best-matching body line (trimmed to ≤160 chars) when the
            hit matched on body text; ``None`` for index-only matches.
        matched_fields: Which fields matched, a subset of
            ``("path", "title", "tag", "body")`` — empty for pure filter
            queries (``text=None``).
        score: The BM25F relevance score. ``0.0`` for a filter-only query, where
            nothing was ranked and hits keep index order.
    """

    entry: ConceptIndexEntry
    snippet: str | None = None
    matched_fields: tuple[str, ...] = ()
    score: float = 0.0


class SearchResult(BaseModel, frozen=True):
    """The structured outcome of one ``Bundle.search`` call.

    Attributes:
        hits: The matches. Ranked queries come back score-descending (ties broken
            by path ascending, so the order is deterministic); a filter-only
            query keeps path-ascending index order.
        truncated: ``True`` iff ``limit`` cut real matches — a capped result
            always says so (no silent caps).
    """

    hits: tuple[SearchHit, ...] = ()
    truncated: bool = False


class BundleIndex(BaseModel, frozen=True):
    """The derived rollup of a bundle's Concept tree.

    Attributes:
        generated_at: Aware-UTC build timestamp, or ``None`` if unset.
        entries: One :class:`ConceptIndexEntry` per Concept, in walk order.
    """

    generated_at: datetime | None = None
    entries: tuple[ConceptIndexEntry, ...] = ()


__all__ = [
    "BundleIndex",
    "ConceptIndexEntry",
    "SearchHit",
    "SearchResult",
    "extract_title",
]
