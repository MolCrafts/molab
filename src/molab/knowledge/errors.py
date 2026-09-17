"""Typed exceptions for OKF bundle operations.

``ConceptNotFoundError`` subclasses :class:`LookupError`, matching the workspace
``*NotFoundError`` family so the server's "a LookupError is a 404" mapping keeps
working after the OKF library moved out of ``molab.workspace``. It is
re-exported from ``molab.workspace.errors`` as the *same class object*, so
existing ``except ConceptNotFoundError`` sites catch it either way.
"""

from __future__ import annotations


class ConceptNotFoundError(LookupError):
    """Raised by ``Bundle.get(rel_path)`` when no Concept lives at that path.

    A *Concept* is a directory that directly holds ``meta.json`` (the OKF
    marker). A path that does not exist, or that exists but lacks ``meta.json``,
    is not a Concept and raises this error. The bundle-relative path is carried
    in the message so callers need not re-resolve it.
    """

    _entity_kind = "concept"

    def __init__(self, entity_id: str) -> None:
        super().__init__(f"{self._entity_kind} {entity_id!r} not found")
        self.entity_id = entity_id


__all__ = ["ConceptNotFoundError"]
