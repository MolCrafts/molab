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
    from .concepts import _SourcedKnowledge
    from .edges import EdgeRole
    from .naming import KnowledgeFormat

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
    replaces: Sequence[PathArg] = (),
    format: KnowledgeFormat | None = None,
) -> Concept:
    """Write one document under *host*. The single create path.

    *host* is a workspace root, any Project / Experiment / Run folder, a plain
    path, or a bare ``Knowledge`` tree handle. ``Note`` and ``Literature`` need
    no sources. A sourced class still rejects an empty source list. An existing
    document rewritten with ``text=""`` keeps its body and merges frontmatter.
    Every write inside a workspace is one history commit (``knowledge.created``
    or ``knowledge.rewritten``) that also carries the deletion of each
    *replaces* document, so a superseded document leaves the tree instead of
    piling up beside its successor. A new document is stamped ``created_at``
    (ISO-8601 UTC, seconds) unless *record* already carries one. A history failure never fails the write. The host's ``index.knowledges`` section (in its
    ``index.md``) is rebuilt after the write.

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
        replaces: Documents this one supersedes. Each is deleted after the
            write; git keeps its text.
        format: ``"md"`` (``<slug>.md``, YAML frontmatter + markdown) or
            ``"html"`` (``<slug>.html``). ``None`` keeps an existing
            document's format and writes markdown for a new one.

    Returns:
        The written document.

    Raises:
        TypeError: If *host* is not a recognised host.
        ValueError: If *of* requires sources and *sources* is empty, a
            *replaces* entry is not a knowledge document or is the written one,
            or the name already exists in the other *format*.
    """
    from contextlib import suppress

    from .index_section import refresh_section
    from .location import _host_fs, _lookup_path, enclosing_workspace_root, host_of

    disk = fs if fs is not None else _host_fs(host)
    from .concept import _record_as_dict
    from .planning import check_planning_record
    from .worker_report import check_worker_record

    preview = _record_as_dict(record) if record is not None else None
    path = _landed_path(host, name, of, format, disk)
    sourced = _sourced_class(of)
    if sourced is not None:
        # A dummy source lets an existing file answer ``exists`` before the
        # real source list is checked. It is never written.
        probe = sourced(path, sources=list(sources) or [object()], fs=disk)  # ty: ignore[invalid-argument-type]
    else:
        probe = of(path, fs=disk)
    existing = probe.frontmatter() if probe.exists() else None
    check_planning_record(of, preview, creating=existing is None)
    check_worker_record(of, preview, existing=existing)
    check_record = getattr(of, "check_record", None)
    if check_record is not None:
        check_record(preview, existing=existing)
    if sourced is not None and not sources:
        raise ValueError(f"{of.__name__} requires at least one SourceRef")
    item = probe
    created = not item.exists()
    retired = _replaced_paths(replaces, item.path, disk)
    payload = _merged_record(record, created_by=created_by, name=name, created=created)
    if item.exists() and text == "":
        item.write(None, payload)
    else:
        item.write(text, payload)
    root = enclosing_workspace_root(_lookup_path(host), fs=disk)
    _apply_cites(item, cite)
    relinked: list[str] = []
    for old in retired:
        from .concepts import _open_document

        relinked.extend(_open_document(old, fs=disk).supersede_with(item, within=root))
    refresh_section(item.path, fs=disk, root=root, known_root=True)
    if root is not None:
        with suppress(Exception):
            from molab.workspace.entity_record import INDEX_FILENAME
            from molab.workspace.history import EntityRef, GitHistory

            rel = Path(str(item.path)).relative_to(Path(str(root))).as_posix()
            touched = [item.path, *retired, *relinked]
            for path in (item.path, *retired):
                host_index = disk.join(str(host_of(path)), INDEX_FILENAME)
                if disk.is_file(host_index) and host_index not in touched:
                    touched.append(host_index)
            GitHistory(str(root)).record(
                "knowledge.created" if created else "knowledge.rewritten",
                subject=EntityRef(id=rel, type=type(item).__name__),
                summary=title or name,
                paths=tuple(touched),
            )
    return item


def _landed_path(
    host: Folder | Concept | PathArg,
    name: str,
    of: type[Concept],
    format: KnowledgeFormat | None,
    disk: FileSystem,
) -> str:
    """Where the *of* document *name* lands under *host*, in one format only.

    Raises:
        ValueError: *format* is given and the name exists in the other format.
    """
    from .location import _folder
    from .naming import KNOWLEDGE_FORMATS

    paths = {fmt: str(_folder(host, name, of, format=fmt)) for fmt in KNOWLEDGE_FORMATS}
    on_disk = [fmt for fmt in KNOWLEDGE_FORMATS if disk.is_file(paths[fmt])]
    if format is None:
        return paths[on_disk[0] if on_disk else "md"]
    clash = [fmt for fmt in on_disk if fmt != format]
    if clash:
        raise ValueError(
            f"{name!r} already exists as {paths[clash[0]]}; one document has one format"
        )
    return paths[format]


def _replaced_paths(replaces: Sequence[PathArg], written: PathArg, disk: FileSystem) -> list[str]:
    """The documents *replaces* names, checked before anything is written."""
    from .naming import is_knowledge_file

    retired: list[str] = []
    for raw in replaces:
        path = str(raw)
        if not disk.is_file(path) or not is_knowledge_file(disk.basename(path)):
            raise ValueError(f"--replaces {path!r} is not a knowledge document")
        if disk.resolve(path) == disk.resolve(str(written)):
            raise ValueError(f"--replaces {path!r} is the document being written")
        retired.append(path)
    return retired


def _sourced_class(of: type[Concept]) -> type[_SourcedKnowledge] | None:
    """*of* as a sourced class (one whose constructor takes ``sources``), or ``None``."""
    from .concepts import _SourcedKnowledge

    return of if issubclass(of, _SourcedKnowledge) else None


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


def _merged_record(
    record: object | None, *, created_by: str, name: str, created: bool
) -> dict[str, object]:
    """Frontmatter for a write: *record* under ``created_by``, ``name`` and, on create, ``created_at``."""
    from .concept import _record_as_dict

    payload = _record_as_dict(record) if record is not None else {}
    payload["created_by"] = created_by
    payload["name"] = name
    if created and not payload.get("created_at"):
        from molab.workspace.timestamps import utc_now

        payload["created_at"] = utc_now().replace(microsecond=0).isoformat()
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
