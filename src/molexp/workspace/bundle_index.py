"""Re-export shim — the derived index models moved to :mod:`molexp.knowledge.bundle_index`."""

from molexp.knowledge.bundle_index import (
    INDEX_JSON_FILENAME,
    INDEX_MD_FILENAME,
    BundleIndex,
    ConceptIndexEntry,
    SearchHit,
    SearchResult,
    extract_title,
)

__all__ = [
    "INDEX_JSON_FILENAME",
    "INDEX_MD_FILENAME",
    "BundleIndex",
    "ConceptIndexEntry",
    "SearchHit",
    "SearchResult",
    "extract_title",
]
