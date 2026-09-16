"""Re-export shim — ``KnowledgeItem`` moved to :mod:`molexp.knowledge.knowledge_item`."""

from molexp.knowledge.knowledge_item import (
    KNOWLEDGE_ITEM_KIND,
    KNOWLEDGE_KINDS,
    KnowledgeItem,
    KnowledgeKind,
    KnowledgeMeta,
    SourceKind,
    SourceRef,
    parse_knowledge_kind,
)

__all__ = [
    "KNOWLEDGE_ITEM_KIND",
    "KNOWLEDGE_KINDS",
    "KnowledgeItem",
    "KnowledgeKind",
    "KnowledgeMeta",
    "SourceKind",
    "SourceRef",
    "parse_knowledge_kind",
]
