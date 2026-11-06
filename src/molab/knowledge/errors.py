"""Typed exceptions for knowledge documents.

``KnowledgeNotFoundError`` subclasses :class:`LookupError`, matching the workspace
``*NotFoundError`` family so the server's "a LookupError is a 404" mapping keeps
working. ``ConceptNotFoundError`` is the same class, defined here.
"""

from __future__ import annotations


class KnowledgeNotFoundError(LookupError):
    """Raised when no knowledge document lives at that path.

    A document is a markdown file under a host. The path is carried in the
    message so callers need not re-resolve it.
    """

    _entity_kind = "knowledge"

    def __init__(self, entity_id: str) -> None:
        super().__init__(f"{self._entity_kind} {entity_id!r} not found")
        self.entity_id = entity_id


ConceptNotFoundError = KnowledgeNotFoundError

__all__ = ["ConceptNotFoundError", "KnowledgeNotFoundError"]
