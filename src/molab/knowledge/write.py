"""The one knowledge create path, :func:`write_knowledge`.

The workspace ``Folder`` family is the host, and it is imported lazily.
``molab/__init__.py`` eagerly loads ``molab.workspace``, so a module-level
``from molab.workspace… import …`` would make ``import molab.knowledge`` a
cycle. Every such import therefore sits in a function body (or an
``if TYPE_CHECKING:`` block, which never executes at runtime).
"""

from __future__ import annotations

import os
import posixpath
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from .concept import Knowledge, append_link, link_target
from .edges import validate_role
from .knowledge_item import SourceRef

if TYPE_CHECKING:
    from molab.fs import FileSystem, PathArg
    from molab.workspace.domain import Asset
    from molab.workspace.folder import Folder
    from molab.workspace.refs import MolabRef

    from .concept import Concept
    from .concepts import _SourcedKnowledge
    from .edges import EdgeRole
    from .naming import KnowledgeFormat


def write_knowledge(
    host: Folder | Concept | PathArg,
    *,
    name: str,
    of: type[Concept],
    sources: Sequence[object] = (),
    created_by: str,
    text: str,
    cite: Sequence[tuple[Concept | Folder | Asset | MolabRef | PathArg, EdgeRole]] = (),
    title: str = "",
    fields: Mapping[str, object] | None = None,
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
    (ISO-8601 UTC, seconds). The host's ``index.knowledges`` section (in its ``index.md``) is
    rebuilt after the write. The write runs under the document's lock, and a
    history failure never fails it: it is logged by the history
    (:func:`~molab.knowledge.mutation.mutation`).

    Args:
        host: Where the document lands.
        name: Human document name.
        of: The Knowledge class to write.
        sources: Source list. Required for Finding, Report, Plan, Observation.
            A relative file path, here or in *cite*, is read from the
            workspace root (:func:`_relative_base`).
        created_by: Author (a person or tool identifier).
        text: Narrative. ``""`` on an existing document leaves the body.
        cite: ``(target, role)`` pairs, each written as one edge through
            :func:`~molab.knowledge.concept.append_link` unless the document
            already carries that edge (a source link, say). Every target and
            role is checked before anything is written.
        title: History summary. Falls back to *name*.
        fields: The fields *of* declares (:attr:`~molab.knowledge.concept.Concept.FIELDS`),
            merged over a rewritten document's. A key *of* does not declare
            is refused before anything is written.
        fs: Disk to write through. Defaults to the host's own disk.
        replaces: Documents this one supersedes. Each is deleted after the
            write; git keeps its text.
        format: ``"md"`` (``<slug>.md``, YAML frontmatter + markdown),
            ``"html"`` (``<slug>.html``) or ``"tex"`` (``<slug>.tex``), one of
            *of*'s :attr:`~molab.knowledge.concept.Concept.FORMATS`. ``None``
            keeps an existing document's format and writes a new one in the
            class's first format.

    Returns:
        The written document.

    Raises:
        TypeError: If *host* is not a recognised host, or a *cite* target
            names nothing :func:`~molab.knowledge.concept.link_target` accepts.
        ValueError: If a *cite* role is not an ``EdgeRole``, *of* requires sources and *sources* is empty, *fields*
            break *of*'s fields, a *replaces* entry is not a knowledge document
            or is the written one, the name already exists in another
            *format*, or *of* is not stored in *format*.
    """
    from .index_section import refresh_section
    from .location import _host_fs
    from .mutation import mutation

    disk = fs if fs is not None else _host_fs(host)
    path = _landed_path(host, name, of, format, disk)
    targets = [(link_target(target), validate_role(role)) for target, role in cite]
    relative = [t for t, _role in targets if _is_relative(t)] + [
        s.ref
        for s in sources
        if isinstance(s, SourceRef) and s.kind == "file" and _is_relative(s.ref)
    ]
    # The root walk is paid only when there is a relative path to read from it.
    base = _relative_base(path, disk) if relative else ""
    edges = [(_from_base(target, base), role) for target, role in targets]
    sources = [_rooted_source(source, base) for source in sources]
    sourced = _sourced_class(of)
    if sourced is not None:
        # A dummy source lets an existing file answer ``exists`` before the
        # real source list is checked. It is never written.
        probe = sourced(path, sources=list(sources) or [object()], fs=disk)  # ty: ignore[invalid-argument-type]
    else:
        probe = of(path, fs=disk)
    existing = probe.frontmatter() if probe.exists() else None
    if existing is not None:
        from .naming import knowledge_stem

        previous_name = existing.get("name")
        if previous_name and previous_name != name and name != knowledge_stem(disk.basename(path)):
            raise ValueError(
                f"{name!r} collides with existing document {previous_name!r} at {path}; "
                "choose a distinct name or explicitly replace the old document"
            )
    if sourced is not None and not sources:
        raise ValueError(f"{of.__name__} requires at least one SourceRef")
    item = probe
    created = not item.exists()
    retired = _replaced_paths(replaces, item.path, disk)
    head: dict[str, object] = {**(fields or {}), "created_by": created_by, "name": name}
    if created:
        from molab.workspace.timestamps import utc_now

        head["created_at"] = utc_now().replace(microsecond=0).isoformat()
    event = "knowledge.created" if created else "knowledge.rewritten"
    with mutation(item, event, title or name) as change:
        item.write(None if not created and text == "" else text, head)
        _append_new_edges(item, edges)
        for old in retired:
            from .concepts import _open_document

            relinked = _open_document(old, fs=disk).supersede_with(item, within=change.root)
            change.touched.extend([old, *relinked])
        refresh_section(item.path, fs=disk, root=change.root, known_root=True)
    return item


def _relative_base(path: str, disk: FileSystem) -> str:
    """What a relative path a writer is handed names a file from.

    The one rule for a relative source or cite target (``--source
    projects/p/knowledges/spec.md``): it is read from the root of the
    workspace the document lands in, wherever the document lands, so the
    same spelling works from a project, an experiment or a run. Outside a
    workspace it is read from the document's own directory. The writer turns
    it into a link relative to the document, which is how every reader and
    the ``knowledge.local_source`` check resolve a link.
    """
    from molab.workspace import Workspace

    root = Workspace.enclosing_root(path, fs=disk)
    return str(root) if root is not None else disk.dirname(path)


def _is_relative(target: str) -> bool:
    """Whether *target* is a relative local path (not a ref, a URL or an anchor)."""
    from .concept import _skip_link

    return not _skip_link(target) and not posixpath.isabs(target)


def _from_base(target: str, base: str) -> str:
    """*target* read from *base* when it is a relative local path; else itself."""
    if not _is_relative(target):
        return target
    return posixpath.normpath(posixpath.join(base, target))


def _rooted_source(source: object, base: str) -> object:
    """A relative ``file`` :class:`SourceRef` read from *base*; any other source as given."""
    if not isinstance(source, SourceRef) or source.kind != "file":
        return source
    return source.model_copy(update={"ref": _from_base(source.ref, base)})


def _landed_path(
    host: Folder | Concept | PathArg,
    name: str,
    of: type[Concept],
    format: KnowledgeFormat | None,
    disk: FileSystem,
) -> str:
    """Where the *of* document *name* lands under *host*, in one format only.

    Raises:
        ValueError: *of* is not stored in *format*, or *format* is given and
            the name exists in another format.
    """
    from .location import _folder
    from .naming import KNOWLEDGE_FORMATS

    if format is not None and format not in of.FORMATS:
        raise ValueError(f"a {of.__name__} is stored as {' or '.join(of.FORMATS)}, not {format}")
    paths = {fmt: str(_folder(host, name, of, format=fmt)) for fmt in KNOWLEDGE_FORMATS}
    on_disk = [fmt for fmt in KNOWLEDGE_FORMATS if disk.is_file(paths[fmt])]
    if not on_disk:
        # Keep the identity of a previously written mixed-language title.
        # Only an exact stored name may claim its old ASCII-only filename.
        from molab.ids import slugify

        from .frontmatter import split_frontmatter
        from .location import DOCUMENT_SLUG_MAX

        legacy = slugify(name, max_len=DOCUMENT_SLUG_MAX) or name
        for fmt in KNOWLEDGE_FORMATS:
            candidate = str(_folder(host, legacy, of, format=fmt))
            if (
                disk.is_file(candidate)
                and split_frontmatter(disk.read_text(candidate), path=candidate)[0].get("name")
                == name
            ):
                paths[fmt] = candidate
                on_disk.append(fmt)
    if format is None:
        return paths[on_disk[0] if on_disk else of.FORMATS[0]]
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
    sources: Sequence[object],
    *,
    default_host: object,
    of: type[Concept],
) -> list[SourceRef]:
    """*sources* as :class:`SourceRef` rows; a sourced class given none names its host.

    A folder becomes :meth:`SourceRef.of` and a string :meth:`SourceRef.parse`.
    ``Note`` and ``Literature`` given none get none.
    """

    if not sources and _sourced_class(of) is None:
        return []
    return SourceRef.normalize(list(sources) or None, default_host=default_host)


def _append_new_edges(item: Knowledge, edges: Sequence[tuple[str, EdgeRole]]) -> None:
    """Append each ``(target, role)`` edge *item* does not already carry."""
    from molab.workspace.refs import is_ref

    have = {(edge.target, edge.role) for edge in item.links()}
    for target, role in edges:
        key = target if is_ref(target) else os.path.normpath(target)
        if (key, role) in have:
            continue
        append_link(item, target, role=role)
        have.add((key, role))
