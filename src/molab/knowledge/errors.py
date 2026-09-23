"""Typed exceptions for OKF bundle operations.

``ConceptNotFoundError`` subclasses :class:`LookupError`, matching the workspace
``*NotFoundError`` family so the server's "a LookupError is a 404" mapping keeps
working after the OKF library moved out of ``molab.workspace``. It is
re-exported from ``molab.workspace.errors`` as the *same class object*, so
existing ``except ConceptNotFoundError`` sites catch it either way.
"""

from __future__ import annotations


class KnowledgeNotFoundError(LookupError):
    """Raised when no Knowledge lives at that path.

    A Knowledge directory holds one of the six class-named JSON heads
    (``note.json`` / …). The path is carried in the message so callers need
    not re-resolve it.
    """

    _entity_kind = "knowledge"

    def __init__(self, entity_id: str) -> None:
        super().__init__(f"{self._entity_kind} {entity_id!r} not found")
        self.entity_id = entity_id


ConceptNotFoundError = KnowledgeNotFoundError

__all__ = ["ConceptNotFoundError", "KnowledgeNotFoundError"]
