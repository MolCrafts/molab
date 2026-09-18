"""The workspace's ``Bundle`` — the OKF façade, opened with the layout it knows.

The OKF ``Bundle`` lives in :mod:`molab.knowledge.bundle`: a bundle is a
Concept-directory tree and never needed a workspace, so a standalone group wiki
uses the same class. This module owns the two things only the workspace knows:

- **Which subtrees can hold no Concept.** Every workspace ``Folder`` writes a
  ``meta.json`` marker, so a walk over the tree visits every project,
  experiment and run — and, unpruned, every run's ``executions/`` /
  ``artifacts/`` / ``logs/`` beneath it, which is where the bulk of a
  ten-thousand-run workspace's directories live. Knowledge is only ever
  mounted *directly* under a Folder (:mod:`molab.workspace.knowledge_mount`
  → ``<host>/<slug>/``), never inside those job-output dirs, so
  :data:`WORKSPACE_PRUNE_DIRS` names them and this :class:`Bundle` subclass
  passes them by default. The knowledge library itself prunes nothing: it does
  not know what a directory means.
- **The event seam.** ``molab.knowledge`` must not import ``molab.workspace``,
  so a newly created Concept reaches the workspace event spine through a hook
  the knowledge layer calls if one is registered (:mod:`molab.knowledge.hooks`).
  Registering it here keeps the dependency pointing downward, and a bundle
  opened over a plain wiki simply has no observer.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from molab.knowledge.bundle import (
    REFERENCES_GROUP,
    SOURCES_FILENAME,
    Backlink,
    ConceptPartition,
)
from molab.knowledge.bundle import Bundle as _KnowledgeBundle
from molab.knowledge.concept import Concept
from molab.knowledge.edges import EdgeRole
from molab.knowledge.hooks import set_concept_created_hook

from .doc_embed import EntitySummary
from .run import Run

if TYPE_CHECKING:
    from .assets.base import Asset
    from .folder import Folder

__all__ = [
    "REFERENCES_GROUP",
    "SOURCES_FILENAME",
    "WORKSPACE_PRUNE_DIRS",
    "Backlink",
    "Bundle",
    "ConceptPartition",
]

#: Run-internal subtrees that never hold a Concept (see the module docstring).
#: Job output, per-attempt state, caches, logs and the metrics stream — the
#: directories a run *produces*, as opposed to the knowledge mounted beside it.
#:
#: Owned by :class:`~molab.workspace.run.Run` as its ``NON_CONCEPT_SUBDIRS`` and
#: re-exported here under its historical name. It is **not** a global denylist:
#: the walk skips these names only among a *Run's own* children, so a Note in a
#: directory called ``logs`` or ``source`` anywhere else stays visible.
WORKSPACE_PRUNE_DIRS: frozenset[str] = Run.NON_CONCEPT_SUBDIRS


class Bundle(_KnowledgeBundle):
    """The OKF ``Bundle`` opened over a workspace, pruned to its layout.

    Behaviourally identical to :class:`molab.knowledge.bundle.Bundle` — the
    layout pruning it used to configure now travels through the concept-type
    registry instead. Every walk (listing, indexing, searching, backlinks,
    context assembly) skips a run's output subtrees because
    :class:`~molab.workspace.run.Run` declares them in
    ``NON_CONCEPT_SUBDIRS``, which
    :func:`~molab.knowledge.types.non_concept_subdirs` reads when the walk is
    standing *in* a run. Pruning is therefore scoped by position rather than by
    bare name, which is what keeps a user's Note in a directory called ``logs``
    from disappearing.

    It also carries the two verbs that need the *workspace* storage family —
    entity summaries and provenance embedding — which the OKF library cannot own
    without importing the layer above it. Both delegate to
    :mod:`molab.workspace.knowledge_mount`, the ``Folder`` ↔ ``Concept`` adapter.
    """

    def entity_summary(self, target: Concept | Folder | Asset) -> EntitySummary:
        """One-line identity card for *target* (a ``Concept``, ``Folder`` or ``Asset``)."""
        from . import knowledge_mount

        return knowledge_mount.entity_summary(target, root=self._root)

    def embed(
        self,
        note: Concept,
        target: Concept | Folder | Asset,
        *,
        role: EdgeRole | None = None,
    ) -> None:
        """Write ONE typed provenance edge from *note* to *target*."""
        from . import knowledge_mount

        knowledge_mount.embed(note, target, root=self._root, role=role)


def _emit_knowledge_created(*, root: Path, concept: Concept, title: str) -> None:
    """Record a newly created Concept in the workspace's git history.

    Best-effort: the Concept is already durable on disk when this runs, so a
    history backend that is unavailable (no git, a root that is not a repo) must
    not turn a successful write into an error.
    """
    from contextlib import suppress

    from .history import EntityRef, GitHistory

    rel = Path(str(concept.path)).relative_to(root).as_posix()
    with suppress(Exception):
        GitHistory(str(root)).record(
            "knowledge.created",
            subject=EntityRef(id=rel, type=concept.type()),
            summary=title,
            paths=(Path(str(concept.path)),),
        )


set_concept_created_hook(_emit_knowledge_created)
