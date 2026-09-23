"""Inversion seam: let a host layer observe Concept creation without being imported.

``molab.knowledge`` never imports a layer *above* it at module scope. But when
a bundle *is* a molab workspace, a newly created Concept should land on the
workspace event spine as ``knowledge.created`` — so the dependency is inverted,
exactly like ``workspace.set_run_executor``: the host registers a hook and
``Bundle`` calls it if one is present. A standalone group wiki registers nothing
and emits nothing — correct, since an event spine is a workspace concern, not an
OKF one.

The knowledge layer also ships its **own** emitter
(:func:`_emit_knowledge_created`) and registers it at import, so a workspace
that has not imported anything of its own still records the event. That emitter
reaches ``molab.workspace`` only from inside a function body, which keeps
``import molab.knowledge`` acyclic.

The hook is best-effort by contract: the Concept is already durable on disk when
it runs, so a raising hook must never fail the write.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
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


def _emit_knowledge_created(*, root: Path, concept: Concept, title: str) -> None:
    """Record a newly created Concept in the workspace's git history.

    Best-effort: the Concept is already durable on disk when this runs, so a
    history backend that is unavailable (no git, a root that is not a repo) must
    not turn a successful write into an error — ``GitHistory.record`` returning
    ``None`` on a non-repo root is the accepted no-op.
    """
    from contextlib import suppress

    from molab.workspace.history import EntityRef, GitHistory

    rel = Path(str(concept.path)).relative_to(root).as_posix()
    with suppress(Exception):
        GitHistory(str(root)).record(
            "knowledge.created",
            subject=EntityRef(id=rel, type=concept.type()),
            summary=title,
            paths=(Path(str(concept.path)),),
        )


set_knowledge_created_hook = set_concept_created_hook

# The knowledge side installs its own emitter: a freshly created Concept records
# the event with no workspace-side registration (a later host registration simply
# replaces it — the slot is single).
set_concept_created_hook(_emit_knowledge_created)

__all__ = [
    "ConceptCreatedHook",
    "notify_concept_created",
    "set_concept_created_hook",
    "set_knowledge_created_hook",
]
