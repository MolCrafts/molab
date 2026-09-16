"""The workspace's ``Bundle`` — the OKF façade, opened with the layout it knows.

The OKF ``Bundle`` lives in :mod:`molexp.knowledge.bundle`: a bundle is a
Concept-directory tree and never needed a workspace, so a standalone group wiki
uses the same class. This module owns the two things only the workspace knows:

- **Which subtrees can hold no Concept.** Every workspace ``Folder`` writes a
  ``meta.yaml`` marker, so a walk over the tree visits every project,
  experiment and run — and, unpruned, every run's ``executions/`` /
  ``artifacts/`` / ``logs/`` beneath it, which is where the bulk of a
  ten-thousand-run workspace's directories live. Knowledge is only ever
  mounted *directly* under a Folder (:mod:`molexp.workspace.knowledge_mount`
  → ``<host>/<slug>/``), never inside those job-output dirs, so
  :data:`WORKSPACE_PRUNE_DIRS` names them and this :class:`Bundle` subclass
  passes them by default. The knowledge library itself prunes nothing: it does
  not know what a directory means.
- **The event seam.** ``molexp.knowledge`` must not import ``molexp.workspace``,
  so a newly created Concept reaches the workspace event spine through a hook
  the knowledge layer calls if one is registered (:mod:`molexp.knowledge.hooks`).
  Registering it here keeps the dependency pointing downward, and a bundle
  opened over a plain wiki simply has no observer.
"""

from __future__ import annotations

from pathlib import Path

from molexp.knowledge.bundle import (
    REFERENCES_GROUP,
    SOURCES_FILENAME,
    Backlink,
    ConceptPartition,
)
from molexp.knowledge.bundle import Bundle as _KnowledgeBundle
from molexp.knowledge.concept import Concept
from molexp.knowledge.hooks import set_concept_created_hook

from .run import Run

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
#: Owned by :class:`~molexp.workspace.run.Run` as its ``NON_CONCEPT_SUBDIRS`` and
#: re-exported here under its historical name. It is **not** a global denylist:
#: the walk skips these names only among a *Run's own* children, so a Note in a
#: directory called ``logs`` or ``source`` anywhere else stays visible.
WORKSPACE_PRUNE_DIRS: frozenset[str] = Run.NON_CONCEPT_SUBDIRS


class Bundle(_KnowledgeBundle):
    """The OKF ``Bundle`` opened over a workspace, pruned to its layout.

    Behaviourally identical to :class:`molexp.knowledge.bundle.Bundle` — the
    layout pruning it used to configure now travels through the concept-type
    registry instead. Every walk (listing, indexing, searching, backlinks,
    context assembly) skips a run's output subtrees because
    :class:`~molexp.workspace.run.Run` declares them in
    ``NON_CONCEPT_SUBDIRS``, which
    :func:`~molexp.knowledge.types.non_concept_subdirs` reads when the walk is
    standing *in* a run. Pruning is therefore scoped by position rather than by
    bare name, which is what keeps a user's Note in a directory called ``logs``
    from disappearing.

    This subclass survives as the workspace's named entry point (and the home
    of the event seam below); constructing it is the same as constructing the
    knowledge ``Bundle`` over the same root.
    """


def _emit_knowledge_created(*, root: Path, concept: Concept, title: str) -> None:
    """Put a newly created Concept on the workspace event spine.

    Best-effort by ``emit_workspace_event``'s contract — the Concept is already
    durable on disk when this runs.
    """
    from .events import emit_workspace_event

    emit_workspace_event(
        root,
        "knowledge.created",
        "bundle",
        payload={"type": concept.type(), "title": title},
        refs=[Path(str(concept.path)).relative_to(root).as_posix()],
    )


set_concept_created_hook(_emit_knowledge_created)
