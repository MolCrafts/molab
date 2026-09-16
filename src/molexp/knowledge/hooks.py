"""Inversion seam: let a host layer observe Concept creation without being imported.

``molexp.knowledge`` is the bottom OKF library — it must not import
``molexp.workspace``. But when a bundle *is* a molexp workspace, a newly created
Concept should land on the workspace event spine as ``knowledge.created``.

So the dependency is inverted, exactly like ``workspace.set_run_executor``: the
host registers a hook at import time and ``Bundle`` calls it if one is present.
A standalone group wiki registers nothing and emits nothing — correct, since an
event spine is a workspace concern, not an OKF one.

The hook is best-effort by contract: the Concept is already durable on disk when
it runs, so a raising hook must never fail the write.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from pathlib import Path

    from .concept import Concept


class ConceptCreatedHook(Protocol):
    """Called once per newly materialized Concept."""

    def __call__(self, *, root: Path, concept: Concept, title: str) -> None: ...


_HOOK: ConceptCreatedHook | None = None


def set_concept_created_hook(hook: ConceptCreatedHook | None) -> None:
    """Register (or clear, with ``None``) the Concept-created observer."""
    global _HOOK
    _HOOK = hook


def notify_concept_created(*, root: Path, concept: Concept, title: str) -> None:
    """Invoke the registered hook, swallowing its failures.

    Best-effort: the Concept write is already durable, so an observer that
    raises (a locked event DB, a read-only mount) must not turn a successful
    create into an error.
    """
    if _HOOK is None:
        return
    with contextlib.suppress(Exception):  # observation must never break the write
        _HOOK(root=root, concept=concept, title=title)


__all__ = ["ConceptCreatedHook", "notify_concept_created", "set_concept_created_hook"]
