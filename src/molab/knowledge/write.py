"""Cite edges for :meth:`molab.knowledge.concept.Concept.create`.

The workspace ``Folder`` family is the host, and it is imported lazily.
``molab/__init__.py`` eagerly loads ``molab.workspace``, so a module-level
``from molab.workspace… import …`` would make ``import molab.knowledge`` a
cycle. Every such import therefore sits in a function body (or an
``if TYPE_CHECKING:`` block, which never executes at runtime).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from .concept import Knowledge, append_link
from .embed import resolve_embed_target

if TYPE_CHECKING:
    from molab.fs import FileSystem, PathArg
    from molab.workspace.folder import Folder

    from .concept import Concept
    from .edges import EdgeRole

_LOG = logging.getLogger(__name__)


def write_knowledge(
    host: Folder | Concept | PathArg,
    *,
    name: str,
    of: type[Concept],
    sources: Sequence[object] = (),
    created_by: str,
    text: str,
    cite: Sequence[tuple[Folder | Concept | PathArg, EdgeRole]] = (),
    title: str = "",
    record: object | None = None,
    fs: FileSystem | None = None,
) -> Concept:
    """Write one document under *host*. The single create path.

    *host* is a workspace root, any Project / Experiment / Run folder, a plain
    path, or a bare ``Knowledge`` tree handle. ``Note`` and ``Literature`` need
    no sources. A sourced class still rejects an empty source list. An existing
    document rewritten with ``text=""`` keeps its body and merges frontmatter.
    The first create inside a workspace records ``knowledge.created``; a history
    failure never fails the write.

    Args:
        host: Where the document lands.
        name: Human document name.
        of: The Knowledge class to write.
        sources: Source list. Required for Finding, Report, Plan, Observation.
        created_by: Author (a person or tool identifier).
        text: Narrative. ``""`` on an existing document leaves the body.
        cite: Optional ``(target, role)`` pairs.
        title: History summary. Falls back to *name*.
        record: Extra frontmatter, merged under ``created_by`` and ``name``.
        fs: Disk to write through. Defaults to the host's own disk.

    Returns:
        The written document.

    Raises:
        TypeError: If *host* is not a recognised host.
        ValueError: If *of* requires sources and *sources* is empty.
    """
    from contextlib import suppress

    from .location import _host_fs, _lookup_path, enclosing_workspace_root

    disk = fs if fs is not None else _host_fs(host)
    if getattr(of, "REQUIRES_SOURCES", False):
        item = of(host, name, sources=list(sources), fs=disk)  # ty: ignore[invalid-argument-type, unknown-argument]
    else:
        item = of(host, name, fs=disk)  # ty: ignore[invalid-argument-type]
    created = not item.exists()
    payload = _merged_record(record, created_by=created_by, name=name)
    if item.exists() and text == "":
        item.write(None, payload)
    else:
        item.write(text, payload)
    root = enclosing_workspace_root(_lookup_path(host), fs=disk)
    _apply_cites(item, cite)
    if created and root is not None:
        with suppress(Exception):
            from molab.workspace.history import EntityRef, GitHistory

            rel = Path(str(item.path)).relative_to(Path(str(root))).as_posix()
            GitHistory(str(root)).record(
                "knowledge.created",
                subject=EntityRef(id=rel, type=type(item).__name__),
                summary=title or name,
                paths=(item.path,),
            )
    return item


def normalize_sources(
    sources: Sequence[object] | None,
    *,
    default_host: object,
) -> list[object]:
    """Turn a free-form source list into :class:`SourceRef` rows.

    A folder becomes :meth:`SourceRef.of`. An empty request is the host
    itself. A DOI string becomes an https DOI reference.
    """
    from .knowledge_item import SourceRef

    return SourceRef.normalize(list(sources) if sources else None, default_host=default_host)  # ty: ignore[invalid-return-type]


def mount_note(host: Folder | Concept | PathArg, name: str, *, body: str = "") -> Concept:
    """Idempotently mount a ``Note`` under *host*.

    A repeat call, including ``body=""``, never truncates an existing body.
    """
    from .concepts import Note

    return write_knowledge(host, name=name, of=Note, created_by="", text=body)


def _merged_record(record: object | None, *, created_by: str, name: str) -> dict[str, object]:
    """Frontmatter for a write: *record* under ``created_by`` and ``name``."""
    from .concept import _record_as_dict

    payload = _record_as_dict(record) if record is not None else {}
    payload["created_by"] = created_by
    payload["name"] = name
    return payload


def _cite_target(_item: Knowledge, source: Folder | Concept | PathArg) -> str:
    """The string ``append_link`` would write for *source*."""
    from molab.workspace.domain import Asset
    from molab.workspace.folder import Folder

    if isinstance(source, (Folder, Asset)):
        return resolve_embed_target(source)
    if isinstance(source, Knowledge) and type(source) is not Knowledge:
        return str(source.path)
    return str(source)


def _apply_cites(
    item: Knowledge,
    cite: Sequence[tuple[Folder | Concept | PathArg, EdgeRole]],
) -> None:
    """Write each cite as a typed edge — best-effort, one try per target.

    A cite whose target and role are already on the document is skipped, so a
    source link and a cite of the same entity are not written twice. The
    document is already durable when an edge fails.
    """
    if not cite:
        return
    existing = {(edge.target, edge.role) for edge in item.links()}
    for source, role in cite:
        try:
            target = _cite_target(item, source)
            if (target, role) in existing:
                continue
            _cite(item, source, role=role)
            existing.add((target, role))
        except Exception:
            _LOG.warning(
                "cite failed for %s role=%s",
                getattr(source, "name", source),
                role,
                exc_info=True,
            )


def _cite(
    item: Knowledge,
    source: Folder | Concept | PathArg,
    *,
    role: EdgeRole,
) -> None:
    """Append one typed edge for *source*, in the branch its family demands.

    Three branches, and none of them silently drops an edge:

    - a ``Folder`` / ``Asset`` goes through
      :func:`~molab.knowledge.embed.resolve_embed_target` (the only resolver for
      those two families) and links the reference it returns;
    - a Knowledge document goes through :meth:`~molab.knowledge.concept.Concept.ref`;
    - anything else is taken as a bare path and linked verbatim — never handed
      to ``resolve_embed_target``, which would ``TypeError`` on it and lose the
      edge.
    """
    from molab.workspace.domain import Asset
    from molab.workspace.folder import Folder

    if isinstance(source, (Folder, Asset)):
        append_link(item, resolve_embed_target(source), role=role)
        return
    if isinstance(source, Knowledge) and type(source) is not Knowledge:
        item.ref(source, role=role)
        return
    append_link(item, source, role=role)
