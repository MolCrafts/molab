"""``Concept`` — a knowledge document whose **path is its identity**.

A product document is one markdown file, ``knowledges/<name>.md``. YAML
frontmatter names the class; the narrative's markdown links are the graph.
A bare :class:`Concept` is only a root handle for ``walk`` / ``search`` /
``open`` / ``import_zotero``.

**Path is identity.** A ``Concept`` holds an absolute path and a
:class:`~molab.fs.FileSystem`. It has no parent pointer and composes no path
from a hierarchy, so the same handle opens a group wiki or a subtree of a
workspace.

The workspace :class:`~molab.workspace.folder.Folder` family is a separate
base: its ``resolve()`` replays ``projects/`` / ``experiments/`` / ``runs/``.
"""

from __future__ import annotations

import os
import posixpath
import re
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, ClassVar, NamedTuple

from molab.fs import FileSystem, LocalFileSystem, PathArg

from .edges import (
    DEFAULT_EDGE_ROLE,
    Edge,
    EdgeRole,
    encode_label,
    link_line,
    parse_role,
    validate_role,
)

if TYPE_CHECKING:
    from .concepts import Literature
    from .edges import Backlink
    from .search import SearchResult

#: ``[label](target)`` — both halves captured; the label carries the edge role.
_MD_LINK = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")

#: Declared type of a bare root handle.
FALLBACK_CONCEPT_TYPE = "concept"


class LinkScan(NamedTuple):
    """Resolved out-links of a Concept's narrative.

    Attributes:
        concepts: Existing in-tree paths. :meth:`Concept.out_edges` reports these.
        external: ``http(s)://`` links.
        other: Schemes and anchors that are not refs and not relative paths.
        typed_concepts: Typed edges, including refs and missing paths.
        refs: ``molab:`` targets, verbatim.
        missing: Relative paths that do not exist, as absolute paths.
    """

    concepts: list[str]
    external: list[str]
    other: list[str]
    typed_concepts: list[Edge]
    refs: list[str]
    missing: list[str]


class Concept:
    """An OKF Concept.

    A bare ``Knowledge`` is a root handle: it walks, searches and opens
    documents, and it is not a document itself. Product subclasses are one
    markdown file, ``knowledges/<name>.md``, whose YAML frontmatter names
    the class.
    """

    #: Declared type of a bare root handle. A file document uses its own.
    DEFAULT_TYPE: ClassVar[str] = FALLBACK_CONCEPT_TYPE
    #: Product documents are markdown files, not directories.
    FILE_DOCUMENT: ClassVar[bool] = False

    def __init__(
        self,
        path: PathArg,
        name: str | None = None,
        *,
        type: str | None = None,
        fs: FileSystem | None = None,
    ) -> None:
        """Bind this Concept to *path*, or to *path* (a host) plus *name*.

        Args:
            path: This handle's path. A file document's path is its markdown
                file. With *name* given, *path* is instead the **host**: a
                ``str`` / :class:`os.PathLike` directory used as given, or a
                workspace ``Folder``.
            name: A human document name. When given, the path is derived by
                :func:`~molab.knowledge.location.folder` as
                ``folder(path, name, self.__class__)``. A document class lands
                at ``<host>/knowledges/<slug>.md``. Nothing touches disk; the
                first :meth:`write` / :meth:`ref` lands the bytes.
            type: Declared type; defaults to :attr:`DEFAULT_TYPE`.
            fs: The filesystem to read and write through; defaults to the
                host's own disk (never the local one) in the *name* form, and
                to :class:`~molab.fs.LocalFileSystem` otherwise.

        Raises:
            TypeError: If *name* is given and *path* is not a recognised host —
                a path or a workspace Folder. An object with ``resolve()``
                that is not a Folder is rejected.
        """
        if name is not None:
            from .location import _host_fs, folder

            # ``self.__class__``, not ``type(self)``: the *type* kwarg below
            # shadows the builtin.
            raw = str(folder(path, name, self.__class__))
            disk = fs if fs is not None else _host_fs(path)
        else:
            raw = str(path)
            if self.__class__.FILE_DOCUMENT:
                from .naming import as_knowledge_file

                raw = as_knowledge_file(raw)
            disk = fs if fs is not None else LocalFileSystem()
        self._fs: FileSystem = disk
        self._path = raw
        self._type = type if type is not None else self.DEFAULT_TYPE

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self._path!r}, type={self._type!r})"

    def __eq__(self, other: object) -> bool:
        """Two Concepts are equal when they address the same directory.

        Path *is* identity, so this is the only sound definition — the declared
        type is metadata about that directory, not a second identity axis.
        """
        if not isinstance(other, Concept):
            return NotImplemented
        return self._norm(self._path) == self._norm(other._path)

    def __hash__(self) -> int:
        return hash(self._norm(self._path))

    @staticmethod
    def _norm(path: PathArg) -> str:
        """Canonical POSIX spelling of *path*, for identity comparison."""
        return str(PurePosixPath(os.path.normpath(str(path))))

    # ── identity ─────────────────────────────────────────────────────────

    @property
    def path(self) -> Path:
        """This Concept's directory — its identity."""
        return Path(self._path)

    @property
    def name(self) -> str:
        """Directory name, or markdown stem for a file document."""
        name = PurePosixPath(self._path).name
        lower = name.lower()
        if lower.endswith(".md"):
            return name[:-3]
        if lower.endswith(".mdx"):
            return name[:-4]
        return name

    @property
    def fs(self) -> FileSystem:
        """The filesystem this Concept reads and writes through."""
        return self._fs

    def resolve(self) -> Path:
        """This Concept's directory.

        Present so a Concept can stand in wherever a workspace ``Folder``'s
        ``resolve()`` is called for its path alone. For a Concept it is simply
        :attr:`path` — there is no parent chain to walk.
        """
        return self.path

    def exists(self) -> bool:
        """Whether this document is on disk."""
        if self.__class__.FILE_DOCUMENT:
            return self._fs.is_file(self._path)
        return self._fs.is_dir(self._path)

    def _require_document(self, verb: str) -> None:
        """Refuse a document verb on a bare root handle."""
        if not type(self).FILE_DOCUMENT:
            raise TypeError(
                "a Knowledge root handle is not a document; open one with "
                f"Knowledge.open(path) or use Note/Literature/… ({verb})"
            )

    @classmethod
    def open(
        cls,
        directory: PathArg,
        *,
        fs: FileSystem | None = None,
    ) -> Concept:
        """Open the markdown document at *directory*.

        A ``.md`` / ``.mdx`` path is opened as written. A suffix-less path is
        the same file with ``.md`` appended. A directory is not a document.

        Raises:
            KnowledgeNotFoundError: The file is absent.
        """
        from .errors import KnowledgeNotFoundError
        from .naming import as_knowledge_file, is_knowledge_file

        disk = fs if fs is not None else LocalFileSystem()
        raw = str(directory)
        if is_knowledge_file(raw):
            return cls._open_markdown(raw, disk)
        md = as_knowledge_file(raw)
        if disk.is_file(md):
            return cls._open_markdown(md, disk)
        raise KnowledgeNotFoundError(str(directory))

    @classmethod
    def _open_markdown(cls, path: str, disk: FileSystem) -> Concept:
        """Open a ``.md`` / ``.mdx`` Knowledge file from its frontmatter ``class``."""
        from .concepts import _PRODUCTS, Note, _SourcedKnowledge
        from .errors import KnowledgeNotFoundError
        from .frontmatter import split_frontmatter

        text = read_text_or_none(path, fs=disk)
        if text is None:
            raise KnowledgeNotFoundError(path)
        meta, _body = split_frontmatter(text)
        class_name = str(meta.get("class") or "Note")
        klass = _PRODUCTS.get(class_name, Note)
        if issubclass(klass, _SourcedKnowledge):
            return klass._from_disk(path, fs=disk)
        return klass(path, fs=disk)

    def _document_paths(self) -> Iterator[str]:
        """Yield each markdown file this handle walks, in listing order.

        A directory that is itself a workspace root lists ``knowledges/*.md``
        on the root and on every project, experiment and run. Any other
        directory is itself the container. Both lookups keep this handle's
        spelling and ignore the CLI root override.

        Yields:
            Absolute paths of markdown files, spelled from this handle's path.
        """
        from molab.workspace import Workspace

        from .location import is_workspace_root
        from .naming import KNOWLEDGE_CONTAINER, is_knowledge_file

        if is_workspace_root(self._path, fs=self._fs):
            containers = [
                self._fs.join(str(host), KNOWLEDGE_CONTAINER)
                for host in Workspace.list_hosts(self._path, fs=self._fs)
            ]
        else:
            containers = [self._path]
        for container in containers:
            try:
                entries = self._fs.scandir(container, with_stat=False)
            except (OSError, ValueError):
                continue
            files = sorted(
                (entry for entry in entries if entry.is_file and is_knowledge_file(entry.name)),
                key=lambda entry: entry.name,
            )
            for entry in files:
                yield self._fs.join(container, entry.name)

    def walk(self) -> Iterator[Concept]:
        """Yield each Knowledge document under this handle.

        When this path is a workspace root, the documents are the
        ``knowledges/*.md`` files of the root and of every project, experiment
        and run. Any other directory is itself the container: its own markdown
        files, not a subdirectory. A missing directory yields nothing. The
        walk stays on the path the caller named.

        Yields:
            One opened document per markdown file. A file that cannot be
            opened is skipped.
        """
        from .errors import KnowledgeNotFoundError

        for path in self._document_paths():
            try:
                yield type(self).open(path, fs=self._fs)
            except KnowledgeNotFoundError:
                continue

    def search(
        self,
        text: str | None = None,
        of: object | None = None,
        *,
        tag: str | None = None,
        limit: int = 50,
        include_text: bool = True,
    ) -> SearchResult:
        """Search the documents :meth:`walk` would yield.

        Each file is read once. *of*, when a class, keeps that class and its
        subclasses. *tag* keeps documents whose frontmatter lists that tag.
        Ranking goes through :func:`molab.knowledge.search.search_index`.

        Args:
            text: The query. ``None`` or empty keeps index order.
            of: A Knowledge subclass to keep, or ``None`` for every class.
            tag: A frontmatter tag that must be present.
            limit: Maximum hits. A cut result reports ``truncated``.
            include_text: ``False`` ranks on title, tags and path only.

        Returns:
            The ranked hits. Each entry path is relative to this handle and
            keeps the ``.md`` suffix. ``type`` is the Knowledge class name.
        """
        from .concepts import _PRODUCTS, Note
        from .frontmatter import split_frontmatter
        from .search import ConceptIndexEntry, extract_title, search_index

        entries: list[ConceptIndexEntry] = []
        bodies: dict[str, str] = {}
        for path in self._document_paths():
            raw = read_text_or_none(path, fs=self._fs)
            if raw is None:
                continue
            meta, body = split_frontmatter(raw)
            class_name = str(meta.get("class") or "Note")
            klass = _PRODUCTS.get(class_name, Note)
            if isinstance(of, type) and not issubclass(klass, of):
                continue
            tags_raw = meta.get("tags")
            tags = tuple(str(item) for item in tags_raw) if isinstance(tags_raw, list) else ()
            if tag is not None and tag not in tags:
                continue
            title = extract_title(body) or PurePosixPath(path).stem
            rel = PurePosixPath(os.path.relpath(path, self._path)).as_posix()
            bodies[rel] = body if include_text else ""
            entries.append(
                ConceptIndexEntry(
                    path=rel,
                    type=klass.__name__,
                    title=title,
                    tags=tags,
                )
            )
        return search_index(
            tuple(entries),
            bodies,
            text,
            limit=limit,
            include_body=include_text,
        )

    def type(self) -> str:
        """This handle's declared type. A file document does not read disk."""
        return self._type

    def tags(self) -> list[str]:
        """Categorical labels from frontmatter."""
        self._require_document("tags")
        raw = self.frontmatter().get("tags")
        return [str(t) for t in raw] if isinstance(raw, list) else []

    def frontmatter(self) -> dict[str, object]:
        """YAML frontmatter of this file document."""
        from .frontmatter import split_frontmatter

        self._require_document("frontmatter")
        text = read_text_or_none(self._path, fs=self._fs)
        if text is None:
            return {}
        meta, _body = split_frontmatter(text)
        return meta

    def read(self) -> str:
        """This document's narrative (markdown body, frontmatter stripped)."""
        from .frontmatter import split_frontmatter

        self._require_document("read")
        text = read_text_or_none(self._path, fs=self._fs)
        if text is None:
            return ""
        _meta, body = split_frontmatter(text)
        return body

    def ref(
        self,
        ref: object,
        *,
        text: str | None = None,
        role: EdgeRole = DEFAULT_EDGE_ROLE,
    ) -> None:
        """Cross-reference another Knowledge document — the strict spelling of :meth:`cite`.

        *ref* must denote a Knowledge: a :class:`Concept` subclass instance
        other than the bare base class, or a path :meth:`Concept.open` locates
        such a subclass at.
        A workspace ``Folder``, an ``Asset``, a bare coordinate or any other
        object is a programming error, never an edge.

        Args:
            ref: The target Knowledge, or the path locating it.
            text: Optional link label; defaults to the target's name.
            role: The declared :class:`~molab.knowledge.edges.EdgeRole`.

        Raises:
            TypeError: If *ref* denotes no Knowledge. A path that locates no
                document chains the underlying
                :class:`~molab.knowledge.errors.KnowledgeNotFoundError`.
            ValueError: If *role* is not a known ``EdgeRole`` — validated by
                :func:`append_link` before any write.
        """
        target = _knowledge_target(ref, fs=self._fs)
        append_link(self, target, text=text, role=role)

    def cite(
        self,
        ref: Concept | PathArg,
        *,
        text: str | None = None,
        role: EdgeRole = DEFAULT_EDGE_ROLE,
    ) -> None:
        """Cite *ref* — append a typed markdown link.

        The loose spelling of :meth:`ref`: a Knowledge target is delegated to
        it, while a bare directory (a run, an experiment) is still linked as
        given, so knowledge never imports the workspace layer. All six
        knowledge classes share this verb.
        """
        try:
            target = _knowledge_target(ref, fs=self._fs)
        except TypeError:
            append_link(self, ref, text=text, role=role)
            return
        self.ref(target, text=text, role=role)

    def backlinks(self, *, within: Concept | PathArg | None = None) -> list[Backlink]:
        """Documents under *within* whose links point at this one.

        A self-edge is not a backlink. Computed by walking; nothing is indexed.

        Args:
            within: Tree to scan. ``None`` scans the enclosing workspace when
                this document lives in a ``knowledges/`` directory.

        Returns:
            One :class:`~molab.knowledge.edges.Backlink` per inbound edge.

        Raises:
            ValueError: If *within* is omitted and this document is not a host
                document inside a workspace.
        """
        root = self._scan_root(within)
        target = self._norm(self.path)
        return [
            link
            for link in backlinks_to([str(self.path)], within=root.path, fs=self._fs)
            if self._norm(link.source.path) != target
        ]

    def rename(self, new_name: str, *, within: Concept | PathArg | None = None) -> None:
        """Rename this document in place and rewrite inbound links.

        Args:
            new_name: The new human name.
            within: Tree whose inbound links are rewritten.

        Raises:
            FileExistsError: If the destination already exists.
            ValueError: If *within* is omitted and cannot be derived.
        """
        from .location import document_slug

        self._require_document("rename")
        slug = document_slug(new_name)
        if type(self).FILE_DOCUMENT:
            slug = f"{slug}{PurePosixPath(self._path).suffix}"
        dst = self._fs.join(self._fs.dirname(self._path), slug)
        if self._norm(dst) == self._norm(self._path):
            return
        if self._fs.exists(dst):
            raise FileExistsError(f"cannot rename {self._path!r} to {dst!r}: destination exists")
        inbound = self.backlinks(within=within)
        old = self._path
        self._fs.rename(old, dst)
        self._path = dst
        _rewrite_inbound(inbound, old, dst)

    def move_to(
        self,
        host: object,
        *,
        stem: str | None = None,
        relink: bool = True,
        within: Concept | PathArg | None = None,
    ) -> None:
        """Move this document onto *host* and rewrite relative links.

        Args:
            host: A Folder, a path, or a bare Knowledge handle.
            stem: Filename stem kept exactly as ``<stem>.md``, with no slug.
                ``None`` keeps the slug derived from this document's name.
            relink: When false, move the bytes and update this handle only.
                Outbound and inbound links stay as they were.
            within: Tree whose inbound links are rewritten.

        Raises:
            FileExistsError: If the destination already exists.
            TypeError: If *host* is a document instance.
            ValueError: If *stem* is empty, contains ``/``, or is ``.`` / ``..``,
                or *within* is omitted and cannot be derived.
        """
        from .location import folder

        if stem is not None and (stem == "" or "/" in stem or stem in {".", ".."}):
            raise ValueError(f"stem {stem!r} is not a single path segment")
        planned = str(folder(host, self.name, type(self)))  # ty: ignore[invalid-argument-type]
        dst = planned if stem is None else self._fs.join(self._fs.dirname(planned), f"{stem}.md")
        if self._norm(dst) == self._norm(self._path):
            return
        if self._fs.exists(dst):
            raise FileExistsError(f"cannot move {self._path!r} to {dst!r}: destination exists")
        old = self._path
        inbound = None
        old_dir = ""
        if relink:
            inbound = self.backlinks(within=within)
            old_dir = _link_base(self)
        self._fs.mkdir(self._fs.dirname(dst), parents=True, exist_ok=True)
        self._fs.rename(old, dst)
        self._path = dst
        if relink and inbound is not None:
            new_dir = _link_base(self)
            _retarget_links(self, lambda target: _rehome_link(target, old_dir, new_dir))
            _rewrite_inbound(inbound, old, dst)

    def delete(self) -> None:
        """Remove this document. Inbound links are left dangling."""
        self._require_document("delete")
        self._fs.remove(self._path)

    def export(self) -> str:
        """This document's narrative, without frontmatter."""
        return self.read()

    def _scan_root(self, within: Concept | PathArg | None) -> Concept:
        """The tree *within* names, or the enclosing workspace for a host document."""
        if within is not None:
            if isinstance(within, Concept):
                return within
            return Knowledge(within, fs=self._fs)
        from .location import enclosing_workspace_root
        from .naming import KNOWLEDGE_CONTAINER

        if PurePosixPath(self._path).parent.name == KNOWLEDGE_CONTAINER:
            root = enclosing_workspace_root(self.path, fs=self._fs)
            if root is not None:
                return Knowledge(root, fs=self._fs)
        raise ValueError(f"{self.path} is not inside a workspace; pass within= explicitly")

    @classmethod
    def create(
        cls,
        host: object,
        name: str,
        *,
        sources: list[object] | None = None,
        created_by: str,
        text: str,
        cite: Sequence[tuple[object, str]] = (),
        title: str = "",
    ) -> Concept:
        """Write this class under *host* (idempotent on *name*).

        Args:
            host: Parent folder (a Project or Experiment).
            name: Document name; slugified to the landed filename.
            sources: Source list. Required for Finding, Report, Plan, Observation.
            created_by: Author (a person or tool identifier).
            text: Narrative for the document.
            cite: Optional ``(target, role)`` pairs.
            title: History summary for ``knowledge.created``. Falls back to *name*.

        Returns:
            The written document.
        """
        from .write import write_knowledge

        return write_knowledge(
            host,  # ty: ignore[invalid-argument-type]
            name=name,
            of=cls,
            sources=list(sources or ()),
            created_by=created_by,
            text=text,
            cite=cite,  # ty: ignore[invalid-argument-type]
            title=title,
        )

    def write(
        self,
        text: str | object | None = None,
        data: object | None = None,
        *,
        tags: list[str] | None = None,
        status: str | None = None,
        replace: bool = False,
    ) -> None:
        """Write this document.

        A string is the narrative, or a full markdown document with YAML
        frontmatter. Structured records (``ReferenceMeta``, sources, tags)
        fold into the frontmatter. One file: ``knowledges/<name>.md``.

        With ``replace=True``, *text* is the whole file. It is persisted
        verbatim: no frontmatter merge and no source rendering. Equal bytes
        are left untouched.

        Args:
            text: Narrative, a full markdown document, or a structured record
                when *data* is omitted.
            data: Structured record folded into the frontmatter.
            tags: Frontmatter tags. ``None`` leaves stored tags alone.
            status: Frontmatter status. ``None`` leaves stored status alone.
            replace: Persist *text* as the whole file.

        Raises:
            TypeError: ``replace=True`` and *text* is not a ``str``.
            ValueError: ``replace=True`` and the frontmatter ``class`` is not
                this document's class.
        """
        from .frontmatter import dump_frontmatter, split_frontmatter
        from .naming import as_knowledge_file

        self._require_document("write")
        if replace:
            if not isinstance(text, str):
                raise TypeError(
                    f"replace=True requires the whole document as str, got {type(text).__name__}"
                )
            meta, _body = split_frontmatter(text)
            declared = meta.get("class")
            if declared != type(self).__name__:
                raise ValueError(
                    f"frontmatter class {declared!r} does not match {type(self).__name__}"
                )
            if self._fs.is_file(self._path) and self._fs.read_text(self._path) == text:
                return
            self._fs.mkdir(self._fs.dirname(self._path), parents=True, exist_ok=True)
            self._fs.atomic_write_text(self._path, text)
            return

        if self.__class__.FILE_DOCUMENT:
            self._path = as_knowledge_file(self._path)
        record = data
        narrative: str | None
        incoming_fm: dict[str, object] = {}
        if text is None:
            narrative = None
        elif isinstance(text, str):
            incoming_fm, body = split_frontmatter(text)
            if incoming_fm:
                narrative = body
            else:
                narrative = text
        else:
            record = text if record is None else record
            narrative = None
        extra: dict[str, object] = dict(incoming_fm)
        if tags is not None:
            extra["tags"] = list(tags)
        if status is not None:
            extra["status"] = status
        if record is not None:
            dumped = _record_as_dict(record)
            extra = {**dumped, **extra}
        extra["class"] = type(self).__name__
        extra.pop("type", None)
        extra.pop("kind", None)
        extra.pop("id", None)
        sources = list(getattr(self, "_sources", None) or [])
        existing_fm = self.frontmatter()
        merged = {**existing_fm, **extra}
        if narrative is None:
            narrative = self.read()
        parent = str(PurePosixPath(self._path).parent)
        self._fs.mkdir(parent, parents=True, exist_ok=True)
        body, _appended = append_source_links(narrative or "", sources, base_dir=parent)
        self._fs.atomic_write_text(self._path, dump_frontmatter(merged, body))

    @classmethod
    def write_document(
        cls,
        path: PathArg,
        text: str,
        *,
        fs: FileSystem | None = None,
    ) -> Concept:
        """Offline migration writer: persists a composed document verbatim, with no source invariant; ``write_knowledge`` is the create path.

        The class comes from *text*'s frontmatter ``class``. A sourced class
        is opened through its disk constructor, so legacy ``sources:`` rows
        are never passed to a constructor that requires them.

        Args:
            path: The markdown file to persist.
            text: The whole file, including frontmatter.
            fs: Filesystem to write through. Defaults to the local one.

        Returns:
            The document handle for *path*.

        Raises:
            ValueError: Frontmatter has no ``class``, or the name is unknown.
            TypeError: *text* is not a ``str``.
        """
        from .concepts import parse_class
        from .frontmatter import split_frontmatter

        meta, _body = split_frontmatter(text)
        class_name = meta.get("class")
        if not isinstance(class_name, str) or class_name == "":
            raise ValueError("knowledge document requires a frontmatter class")
        klass = parse_class(class_name)
        disk = fs if fs is not None else LocalFileSystem()
        opener = getattr(klass, "_from_disk", None)
        handle = opener(str(path), fs=disk) if opener is not None else klass(path, fs=disk)
        handle.write(text, replace=True)
        return handle

    def links(self) -> list[Edge]:
        """The documents this one cites — typed markdown links in the narrative."""
        return self.scan_links(self.read()).typed_concepts

    def scan_links(self, body: str) -> LinkScan:
        """Classify the markdown links in *body* as if it were this Concept's.

        The same scan as :meth:`links`, against the narrative the caller
        already holds, so a title read does not read the file a second time
        for its edges.

        Args:
            body: The narrative to scan.
        """
        from molab.workspace.refs import is_ref

        base = PurePosixPath(self._path)
        if self.__class__.FILE_DOCUMENT:
            base = base.parent
        concepts: list[str] = []
        external: list[str] = []
        other: list[str] = []
        typed_concepts: list[Edge] = []
        refs: list[str] = []
        missing: list[str] = []
        for raw_label, target in _MD_LINK.findall(body):
            role, _human = parse_role(raw_label)
            if target.startswith(("http://", "https://")):
                external.append(target)
                if role in {"cites", "derived_from"}:
                    typed_concepts.append(Edge(target=target, role=role))
                continue
            if is_ref(target):
                refs.append(target)
                typed_concepts.append(Edge(target=target, role=role))
                continue
            head = target.split("/", 1)[0]
            if target.startswith("#") or ":" in head:
                other.append(target)
                continue
            path_part, sep, fragment = target.partition("#")
            norm = PurePosixPath(os.path.normpath(str(base / path_part)))
            resolved = str(norm)
            edge_target = f"{resolved}#{fragment}" if sep else resolved
            if self._fs.is_dir(resolved) or self._fs.is_file(resolved):
                concepts.append(resolved)
            else:
                missing.append(resolved)
            typed_concepts.append(Edge(target=edge_target, role=role))
        return LinkScan(
            concepts=concepts,
            external=external,
            other=other,
            typed_concepts=typed_concepts,
            refs=refs,
            missing=missing,
        )

    def out_edges(self) -> list[str]:
        """In-tree link targets (paths only)."""
        return self.scan_links(self.read()).concepts

    def import_zotero(
        self,
        path: PathArg,
        *,
        under: object | None = None,
        now: object | None = None,
    ) -> list[Literature]:
        """Import a local Zotero library as Literature markdown files.

        Each item is written through :func:`~molab.knowledge.write.write_knowledge`.
        With *under* omitted, this handle is the host: a workspace root lands
        in ``knowledges/``, a plain wiki in its own directory. A repeat import
        merges frontmatter and does not create a second file. PDFs are pointed
        at, never copied.

        Args:
            path: The ``zotero.sqlite`` to read (opened read-only).
            under: Host to write under. ``None`` uses this handle.
            now: Unused; accepted so callers matching the old signature keep working.

        Returns:
            The :class:`Literature` records created or updated.
        """
        from .concepts import Literature
        from .reference_meta import ReferenceMeta
        from .write import write_knowledge
        from .zotero import read_zotero

        _ = now
        host: object = self if under is None else under
        refs: list[Literature] = []
        for item in read_zotero(path):
            written = write_knowledge(
                host,  # ty: ignore[invalid-argument-type]
                name=item.key,
                of=Literature,
                created_by="zotero",
                text="",
                record=ReferenceMeta(
                    title=item.title,
                    authors=item.authors,
                    year=item.year,
                    doi=item.doi,
                    url=item.url,
                    pdf_path=item.pdf_path,
                    source="zotero",
                    source_key=item.key,
                ),
                fs=self._fs,
            )
            refs.append(written)  # ty: ignore[invalid-argument-type]
        return refs


def _knowledge_target(ref: object, *, fs: FileSystem) -> Concept:
    """The Knowledge *ref* denotes, or ``TypeError`` — the one strictness rule.

    Shared by :meth:`Concept.ref` (which propagates the error) and
    :meth:`Concept.cite` (which falls back to its loose path branch): an object
    denotes a Knowledge when its class is a :class:`Concept` subclass other than
    the bare base class, and a path denotes one when :meth:`Concept.open`
    locates such a subclass there. A run / project / experiment directory fails
    both — ``Concept.open`` finds no markdown document there.

    Args:
        ref: The candidate — a Concept, a path, or anything else.
        fs: The filesystem to locate a path through (the caller's own).

    Returns:
        The Knowledge *ref* denotes.

    Raises:
        TypeError: If *ref* denotes no Knowledge, chaining the
            :class:`~molab.knowledge.errors.KnowledgeNotFoundError` a path
            lookup raised.
    """
    if isinstance(ref, Concept):
        if type(ref) is Concept:
            raise TypeError(
                "the bare Concept base class is not a Knowledge: a run / project / "
                "experiment directory reconstructs to it — cross-reference the document "
                "it holds instead"
            )
        return ref
    if isinstance(ref, (str, os.PathLike)):
        from .errors import KnowledgeNotFoundError

        path = str(ref)
        try:
            located = Concept.open(path, fs=fs)
        except KnowledgeNotFoundError as exc:
            raise TypeError(f"{path!r} locates no Knowledge document") from exc
        if type(located) is Concept:
            raise TypeError(f"{path!r} locates a bare Concept, not a Knowledge")
        return located
    raise TypeError(
        f"cross-reference target must be a Knowledge document, got {type(ref).__name__}; "
        "pass the Knowledge, or the path locating one"
    )


def _record_as_dict(record: object) -> dict[str, object]:
    """Flatten a write() record into frontmatter keys (no type/kind/id)."""
    from .concept_meta import ConceptMeta

    if isinstance(record, ConceptMeta):
        payload = dict(record.model_dump(mode="json"))
    elif isinstance(record, Mapping):
        payload = {str(key): value for key, value in record.items()}
    else:
        payload = {}
    payload.pop("type", None)
    payload.pop("kind", None)
    payload.pop("id", None)
    return payload


def _skip_link(target: str) -> bool:
    """Whether *target* is an external, schemed, anchor, or molab reference.

    A reference, including a ``#span`` suffix, is canonical text. Rewriting it
    as a relative path would drop the only provenance record on a disk-opened
    document.
    """
    from molab.workspace.refs import is_ref

    return target.startswith(("#", "http://", "https://")) or "://" in target or is_ref(target)


def _link_base(doc: Concept) -> str:
    """The directory relative links in *doc* are resolved against."""
    if type(doc).FILE_DOCUMENT:
        return str(PurePosixPath(doc.path).parent)
    return str(doc.path)


def _rehome_link(target: str, old_dir: str, new_dir: str) -> str | None:
    """Re-express a relative *target* from *old_dir* against *new_dir*."""
    if _skip_link(target):
        return None
    absolute = os.path.normpath(str(PurePosixPath(old_dir) / target))
    return PurePosixPath(os.path.relpath(absolute, new_dir)).as_posix()


def _rewrite_inbound(inbound: Sequence[Backlink], old: str, new: str) -> None:
    """Point inbound edges that named *old* at *new*."""

    def _rewrite(doc: Concept, target: str) -> str | None:
        if _skip_link(target):
            return None
        resolved = os.path.normpath(str(PurePosixPath(_link_base(doc)) / target))
        if Concept._norm(resolved) != Concept._norm(old):
            return None
        return PurePosixPath(os.path.relpath(new, _link_base(doc))).as_posix()

    for link in inbound:
        doc = link.source
        _retarget_links(doc, lambda target, doc=doc: _rewrite(doc, target))


def retarget_links(
    text: str,
    rewrite: Callable[[str, bool], str | None],
) -> tuple[str, int]:
    """Replace markdown link targets in *text*. Pure: no I/O.

    *rewrite* receives ``(target, image)``. ``image`` is true when the match
    is preceded by ``!``. ``None`` or the same target keeps the link. A
    different string replaces only the target; the label stays byte-for-byte.
    The same grammar as :meth:`Concept.scan_links`, including links inside
    fenced code.

    Args:
        text: Markdown to scan.
        rewrite: Maps ``(target, image)`` to a new target, or ``None`` to keep it.

    Returns:
        The new text and how many targets actually changed.
    """
    count = 0

    def _sub(match: re.Match[str]) -> str:
        nonlocal count
        label, target = match.group(1), match.group(2)
        image = match.start() > 0 and text[match.start() - 1] == "!"
        updated = rewrite(target, image)
        if updated is None or updated == target:
            return match.group(0)
        count += 1
        return f"[{label}]({updated})"

    return _MD_LINK.sub(_sub, text), count


def _retarget_links(doc: Concept, rewrite: Callable[[str], str | None]) -> bool:
    """Rewrite markdown link targets in *doc*, keeping labels.

    Args:
        doc: The document to rewrite.
        rewrite: Maps a raw target to its replacement, or ``None`` to keep it.

    Returns:
        Whether the narrative changed.
    """
    new, count = retarget_links(doc.read(), lambda target, _image: rewrite(target))
    if count > 0:
        doc.write(new)
    return count > 0


def append_source_links(
    body: str,
    sources: Sequence[object],
    *,
    base_dir: str,
) -> tuple[str, int]:
    """Append each source's link line once.

    A source whose ``(role, posixpath.normpath(target))`` is already a link
    in *body*, or was already appended in this call, is skipped. Each line
    comes from ``SourceRef.link_line``; this function renders none itself.

    Args:
        body: Narrative to extend.
        sources: Source rows. Each must provide ``link_target``, ``link_role``
            and ``link_line``.
        base_dir: Directory ``link_target`` relativizes file paths against.

    Returns:
        The new body and how many lines were appended.

    Raises:
        ValueError: A source's ``link_target`` rejects its ref (a bare entity id).
    """
    if not sources:
        return body, 0
    have = {
        (parse_role(label)[0], posixpath.normpath(target))
        for label, target in _MD_LINK.findall(body)
    }
    lines: list[str] = []
    for source in sources:
        target = source.link_target(base_dir)  # ty: ignore[unresolved-attribute]
        role = source.link_role  # ty: ignore[unresolved-attribute]
        key = (role, posixpath.normpath(target))
        if key in have:
            continue
        have.add(key)
        lines.append(source.link_line(base_dir))  # ty: ignore[unresolved-attribute]
    if not lines:
        return body, 0
    text = body
    if text and not text.endswith("\n"):
        text += "\n"
    return text + "\n".join(lines) + "\n", len(lines)


def remove_legacy_files(
    directory: PathArg,
    names: Sequence[str],
    *,
    fs: FileSystem,
) -> list[str]:
    """Delete named plain files in *directory*, then remove it when empty.

    Never recursive, and never touches an entry that was not named. A name
    that is a subdirectory is left in place and reported.

    Args:
        directory: Directory holding the legacy files.
        names: Plain file names to delete when they are files.
        fs: Filesystem the directory lives on.

    Returns:
        Sorted names that remain after the named files are gone. Empty when
        the directory itself was removed.

    Raises:
        ValueError: A name contains ``/`` or is ``.`` / ``..``.
    """
    for name in names:
        if "/" in name or name in {".", ".."}:
            raise ValueError(f"legacy name {name!r} is not a single file name")
    if not fs.is_dir(directory):
        return []
    for name in names:
        path = fs.join(directory, name)
        if fs.is_file(path):
            fs.remove(path)
    remaining = fs.listdir(directory)
    if not remaining:
        Path(os.fspath(directory)).rmdir()
        return []
    return sorted(remaining)


def backlinks_to(
    targets: Iterable[str],
    *,
    within: PathArg,
    fs: FileSystem,
) -> list[Backlink]:
    """Documents under *within* that link any of *targets*.

    A path matches by normalized spelling. A ``molab:`` ref matches the
    canonical string. Self-edges are included; :meth:`Concept.backlinks`
    drops those.

    Not part of :data:`molab.knowledge.__all__`. The server imports it from
    this module.
    """
    from molab.workspace.refs import is_ref

    from .edges import Backlink

    wanted_refs: list[str] = []
    wanted_paths: list[str] = []
    for target in targets:
        if is_ref(target):
            wanted_refs.append(target.split("#", 1)[0])
        else:
            wanted_paths.append(Concept._norm(target))
    found: list[Backlink] = []
    for source in Knowledge(within, fs=fs).walk():
        for edge in source.links():
            if is_ref(edge.target):
                hit = edge.target.split("#", 1)[0] in wanted_refs
            else:
                hit = Concept._norm(edge.target.split("#", 1)[0]) in wanted_paths
            if hit:
                found.append(Backlink(source=source, role=edge.role))
    return found


def append_link(
    src: Concept,
    dst: Concept | PathArg,
    *,
    text: str | None = None,
    role: EdgeRole = DEFAULT_EDGE_ROLE,
) -> None:
    """Append a typed relative markdown link ``src → dst`` to ``src``'s body.

    The single markdown-edge writer, and the sole role-writing chokepoint:
    ``Note.cite`` delegates here,
    so the on-disk edge format cannot drift. The graph lives in the markdown
    body. The default role encodes to the bare label, so pre-role
    output stays byte-identical. Appends unconditionally; link dedup remains a
    future enhancement.

    **A link target is a path, not a class.** *dst* may be a ``Concept`` or a
    bare directory path, so a Concept can cite something outside its own family
    — a workspace ``Run``, an asset record dir — without ``molab.knowledge``
    importing the layer that owns it.

    Args:
        src: The Concept the edge originates from.
        dst: The Concept, or directory path, the edge points to.
        text: Optional link label; defaults to *dst*'s directory name.
        role: The declared :class:`~molab.knowledge.edges.EdgeRole`.

    Raises:
        ValueError: If *role* is not a known ``EdgeRole`` — validated before any
            write, so an invalid role leaves the document body untouched.
        TypeError: If *dst* is neither a ``Concept`` nor a path.
    """
    validate_role(role)
    from molab.workspace.refs import MolabRef, is_ref

    if isinstance(dst, MolabRef) or (isinstance(dst, str) and is_ref(dst)):
        target = str(dst)
        label = text if text is not None else target.rstrip("/").rsplit("/", 1)[-1]
        encoded = encode_label(role, label)
        existing = src.read()
        prefix = existing if not existing or existing.endswith("\n") else existing + "\n"
        src.write(prefix + link_line(encoded, target) + "\n")
        return
    if isinstance(dst, Concept):
        dst_path = str(dst.path)
    elif isinstance(dst, (str, os.PathLike)):
        dst_path = str(dst)
    else:
        # Never ``str()`` an arbitrary object into a link: that would write a
        # repr as the target and produce a silently broken edge. A caller
        # holding a foreign-family object (a workspace ``Folder``) passes its
        # directory.
        raise TypeError(
            f"edge target must be a Concept or a path, got {type(dst).__name__}; "
            "pass its directory (e.g. folder.resolve())"
        )
    src_base = str(Path(src.path).parent) if type(src).FILE_DOCUMENT else str(src.path)
    rel = os.path.relpath(dst_path, src_base)
    rel_posix = PurePosixPath(rel).as_posix()
    label = text if text is not None else PurePosixPath(dst_path).name
    encoded = encode_label(role, label)
    existing = src.read()
    prefix = existing if not existing or existing.endswith("\n") else existing + "\n"
    src.write(prefix + link_line(encoded, rel_posix) + "\n")


def read_text_or_none(path: PathArg, *, fs: FileSystem) -> str | None:
    """Read *path* as text, or ``None`` when there is no such file.

    The try-read idiom: one filesystem call instead of ``exists`` + read. A
    missing file, or a path whose parent is a file rather than a directory,
    is the negative answer; any other error (permissions, I/O) propagates.
    """
    try:
        return fs.read_text(path)
    except (FileNotFoundError, NotADirectoryError):
        return None


Knowledge = Concept


__all__ = [
    "FALLBACK_CONCEPT_TYPE",
    "Concept",
    "Knowledge",
    "LinkScan",
    "append_link",
    "append_source_links",
    "read_text_or_none",
    "remove_legacy_files",
    "retarget_links",
]
