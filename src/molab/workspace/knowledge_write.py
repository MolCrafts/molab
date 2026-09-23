"""``write_knowledge`` — the single sourced-Knowledge writer.

Places a ``molab.knowledge`` product at ``<host>/knowledges/<slug>/`` via
``write``. Not Folder CRUD.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path

from molab.fs import PathArg
from molab.knowledge import Finding, Knowledge, Observation, Plan, Report, SourceRef
from molab.knowledge.concept import append_link as knowledge_append_link

from .edges import EdgeRole
from .folder import Folder
from .knowledge import knowledge_dir

__all__ = ["write_knowledge"]

_LOG = logging.getLogger(__name__)


def _workspace_root(folder: Folder) -> Path:
    cur = Path(str(folder.resolve()))
    while True:
        if (cur / "workspace.json").is_file():
            return cur
        if cur.parent == cur:
            return Path(str(folder.resolve()))
        cur = cur.parent


def write_knowledge(
    host: Folder,
    *,
    name: str,
    of: type[Knowledge],
    sources: list[SourceRef],
    created_by: str,
    text: str,
    cite: Sequence[tuple[Folder | Knowledge | PathArg, EdgeRole]] = (),
    title: str = "",
) -> Knowledge:
    """Write sourced :class:`~molab.knowledge.Knowledge` under *host* (idempotent on *name*).

    Args:
        host: Parent (a Project or Experiment).
        name: Directory slug.
        of: Knowledge subclass — this **is** the category (``Plan``, ``Finding``).
        sources: Non-empty source list for sourced classes.
        created_by: Author (person or ``agent:…`` / ``PlanOrchestrator/…``).
        text: Narrative for the document.
        cite: Optional ``(Folder, EdgeRole)`` pairs.
        title: Display title accepted by callers; identity is *name*.
    """
    _ = title
    dest = knowledge_dir(host, name)
    fs = host._disk()
    if of is Finding or of is Report or of is Plan or of is Observation:
        item = of(dest, sources=list(sources), fs=fs)
    else:
        item = of(dest, fs=fs)
    item.write(text, {"created_by": created_by, "name": name})
    root = _workspace_root(host)
    for source, role in cite:
        try:
            from molab.knowledge.concept import Concept as KnowledgeConcept

            from .doc_embed import resolve_embed_target

            if isinstance(source, Folder):
                dst = resolve_embed_target(source, root=root)
                target = dst.resolve()
            elif isinstance(source, KnowledgeConcept):
                target = source.path
            else:
                target = source
            knowledge_append_link(item, target, role=role)
        except Exception:
            _LOG.warning(
                "write_knowledge: cite failed for %s role=%s",
                getattr(source, "name", source),
                role,
                exc_info=True,
            )
    return item
