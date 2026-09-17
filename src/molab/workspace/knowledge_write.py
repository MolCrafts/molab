"""``write_knowledge`` — the single sourced-Knowledge writer.

Shared by :func:`harvest_run`, plan-record writers, and agent session harvest.
The **class** is the category (``Plan``, ``Finding``, …); it is not stored as a
``kind`` string. Reconstruction is the entity filename.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime

from .edges import EdgeRole
from .folder import Folder
from .knowledge import Knowledge, SourceRef

__all__ = ["write_knowledge"]

_LOG = logging.getLogger(__name__)


def write_knowledge(
    host: Folder,
    *,
    name: str,
    cls: type[Knowledge],
    sources: list[SourceRef],
    created_by: str,
    body: str,
    cite: Sequence[tuple[Folder, EdgeRole]] = (),
    title: str = "",
) -> Knowledge:
    """Write sourced :class:`Knowledge` under *host* (idempotent on *name*).

    Args:
        host: Parent (a Project or Experiment).
        name: Directory slug.
        cls: Knowledge subclass — this **is** the category (``Plan``, ``Finding``).
        sources: Non-empty source list.
        created_by: Author (person or ``agent:…`` / ``PlanOrchestrator/…``).
        body: Markdown for ``index.md``.
        cite: Optional ``(Folder, EdgeRole)`` pairs.
        title: Display title accepted by callers; identity is *name*.
    """
    _ = title
    existed = host.has_folder(name, cls=Knowledge)
    if existed:
        item = host.get_folder(name, cls=Knowledge)
        if type(item) is not cls:
            host.remove_folder(name, cls=Knowledge)
            existed = False
    if not existed:
        item = host.add_folder(
            cls(
                parent=host,
                name=name,
                sources=sources,
                created_by=created_by,
            )
        )
    else:
        item._entity_metadata = item.metadata.model_copy(
            update={
                "sources": list(sources),
                "created_by": created_by,
                "created_at": datetime.now(UTC),
            }
        )
        item.save()
    item.set_body(body)
    for source, role in cite:
        try:
            item.cite(source, role=role)
        except Exception:
            _LOG.warning(
                "write_knowledge: cite failed for %s role=%s",
                getattr(source, "name", source),
                role,
                exc_info=True,
            )
    return item
