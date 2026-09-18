"""Re-export shim — the derived index models moved to :mod:`molab.knowledge.bundle_index`."""

from molab.knowledge.bundle_index import (
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
