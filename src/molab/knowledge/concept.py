"""``Concept`` — a knowledge document whose **path is its identity**.

A product document is one file, ``knowledges/<name>.md`` (YAML frontmatter +
markdown) or ``knowledges/<name>.html`` (the frontmatter as JSON in
``<script id="molab-record">``, a body of ``<molab-markdown>`` blocks and
``<molab-…>`` elements). The frontmatter names the class and carries the
fields that class declares (:attr:`Concept.FIELDS`); the narrative's markdown
links are the graph.
A bare :class:`Concept` is only a root handle for ``walk`` / ``search`` /
``import_zotero``. It does not construct a subclass.

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

from pydantic import BaseModel

from molab.fs import FileSystem, LocalFS, PathArg
from molab.texdoc import link_text

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
    from molab.workspace.domain import Asset
    from molab.workspace.folder import Folder
    from molab.workspace.refs import MolabRef

    from .concepts import Literature
    from .edges import Backlink
    from .naming import KnowledgeFormat
    from .search import SearchResult

#: ``[label](target)`` — both halves captured; the label carries the edge role.
_MD_LINK = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
_CODE_FENCE = re.compile(
    r"^(?P<fence>`{3,}|~{3,})[^\n]*\n.*?^(?P=fence)[ \t]*$", re.MULTILINE | re.DOTALL
)
_CODE_SPAN = re.compile(r"(?<!`)(?P<ticks>`+)(?!`).+?(?<!`)(?P=ticks)(?!`)", re.DOTALL)


def _blank(match: re.Match[str]) -> str:
    """The matched text with every character but newlines turned into spaces."""
    return re.sub(r"[^\n]", " ", match.group(0))


def _mask_code(text: str) -> str:
    """*text* with code blocks and inline code blanked, every offset kept.

    Markdown does not read links inside code, so neither does molab: a SMILES
    such as ``[N+](C)`` in backticks is chemistry, not a link.
    """
    return _CODE_SPAN.sub(_blank, _CODE_FENCE.sub(_blank, text))


def markdown_links(text: str, *, path: object = None) -> list[re.Match[str]]:
    """Every markdown link in *text* outside code, as matches against *text*.

    *text* is the body of the document at *path*. A TeX body carries links
    only in whole-line ``%`` comments (:func:`molab.texdoc.link_text`): a
    bracket followed by a parenthesis in LaTeX is mathematics, not a link.
    """
    from .naming import is_tex_document

    masked = link_text(text) if path is not None and is_tex_document(path) else _mask_code(text)
    return [
        match
        for match in _MD_LINK.finditer(text)
        if masked[match.start() : match.end()] == match.group(0)
    ]


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
    file, ``knowledges/<name>.md`` or ``knowledges/<name>.html``, whose
    frontmatter names the class.
    """

    #: Product documents are markdown files, not directories.
    FILE_DOCUMENT: ClassVar[bool] = False
    #: The storage formats this class's documents may take, the default first
    #: (:data:`~molab.knowledge.naming.KnowledgeFormat`). A write in another
    #: format is refused, and ``molab validate`` reports a file in one.
    FORMATS: ClassVar[tuple[KnowledgeFormat, ...]] = ("md", "html")
    #: The frontmatter fields this class owns beyond the keys every document
    #: carries (:data:`~molab.knowledge.fields.COMMON_KEYS`): a pydantic model
    #: that refuses an unknown key. ``None`` owns none, so no other key is
    #: written. A subclass that adds fields extends its parent's model.
    FIELDS: ClassVar[type[BaseModel] | None] = None

    def __init__(
        self,
        path: PathArg,
        name: str | None = None,
        *,
        fs: FileSystem | None = None,
    ) -> None:
        """Bind this Concept to *path*, or to *path* (a host) plus *name*.

        Args:
            path: This handle's path. A file document's path is its markdown
                file. With *name* given, *path* is instead the **host**: a
                ``str`` / :class:`os.PathLike` directory used as given, or a
                workspace ``Folder``.
            name: A human document name. When given, the path is
                ``Note(path, name).path``: a document class lands at
                ``<host>/knowledges/<slug>.md``. Nothing touches disk; the first
                :meth:`write` / :meth:`ref` lands the bytes. A bare
                :class:`Concept` is not a document and raises ``TypeError``.
            fs: The filesystem to read and write through; defaults to the
                host's own disk (never the local one) in the *name* form, and
                to :class:`~molab.fs.LocalFS` otherwise.

        Raises:
            TypeError: If *name* is given and *path* is not a recognised host —
                a path or a workspace Folder. An object with ``resolve()``
                that is not a Folder is rejected.
        """
        if name is not None:
            from .location import _folder, _host_fs

            raw = str(_folder(path, name, type(self)))
            disk = fs if fs is not None else _host_fs(path)
        else:
            raw = str(path)
            if self.__class__.FILE_DOCUMENT:
                from .naming import as_knowledge_file

                raw = as_knowledge_file(raw)
            disk = fs if fs is not None else LocalFS()
        self._fs: FileSystem = disk
        self._path = raw

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self._path!r})"

    def __eq__(self, other: object) -> bool:
        """Two Concepts are equal when they address the same directory.

        Path *is* identity, so this is the only sound definition — the class
        is what the file declares, not a second identity axis.
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
        """This document's path. For a file document that path is the ``.md`` file."""
        return Path(self._path)

    @property
    def name(self) -> str:
        """Directory name, or the file stem (no ``.md`` / ``.html``) for a file document."""
        from .naming import knowledge_stem

        return knowledge_stem(PurePosixPath(self._path).name)

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
                "a Knowledge root handle is not a document; construct one with "
                f"Note(path) or Note(host, name) ({verb})"
            )

    def _document_paths(self) -> Iterator[str]:
        """Yield each markdown file this handle walks, in listing order.

        A directory that is itself a workspace root, or a project, experiment
        or run directory (a served node), lists ``knowledges/*.md`` on it and
        on every host below it. Any other
        directory is itself the container. Both lookups keep this handle's
        spelling and ignore the CLI root override.

        Yields:
            Absolute paths of markdown files, spelled from this handle's path.
        """
        from molab.workspace import Workspace

        from .location import is_workspace_root
        from .naming import KNOWLEDGE_CONTAINER, is_knowledge_file

        if is_workspace_root(self._path, fs=self._fs) or Workspace.is_node_dir(
            self._path, fs=self._fs
        ):
            containers = [
                self._fs.join(str(host), KNOWLEDGE_CONTAINER)
                for host in Workspace.list_hosts(self._path, fs=self._fs)
            ]
        else:
            containers = [self._path]
        for container in containers:
            try:
                entries = self._fs.ls(container, A=True, l=True)
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
            One opened document per document file. A file whose frontmatter
            names no knowledge class is not a document and is skipped.
        """
        from .concepts import _open_document
        from .errors import KnowledgeNotFoundError

        for path in self._document_paths():
            try:
                yield _open_document(path, fs=self._fs)
            except (KnowledgeNotFoundError, ValueError):
                # No class, or a path that is not a document. One bad file
                # does not hide the rest of the tree.
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
            keeps its ``.md`` / ``.html`` suffix. ``cls`` is the Knowledge
            class name; the title is :meth:`title`'s rule. An HTML document is
            ranked on its text without tags.
        """
        from .concepts import class_of
        from .frontmatter import document_text, split_frontmatter
        from .index_section import document_title
        from .search import ConceptIndexEntry, search_index

        entries: list[ConceptIndexEntry] = []
        bodies: dict[str, str] = {}
        for path in self._document_paths():
            raw = read_text_or_none(path, fs=self._fs)
            if raw is None:
                continue
            meta, body = split_frontmatter(raw, path=path)
            klass = class_of(meta)
            if klass is None:
                continue
            title = document_title(meta, body, PurePosixPath(path).stem)
            if isinstance(of, type) and not issubclass(klass, of):
                continue
            tags_raw = meta.get("tags")
            tags = tuple(str(item) for item in tags_raw) if isinstance(tags_raw, list) else ()
            if tag is not None and tag not in tags:
                continue
            body = document_text(body, path=path)
            rel = PurePosixPath(os.path.relpath(path, self._path)).as_posix()
            bodies[rel] = body if include_text else ""
            entries.append(
                ConceptIndexEntry(
                    path=rel,
                    cls=klass.__name__,
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
        meta, _body = split_frontmatter(text, path=self._path)
        return meta

    def fields(self) -> BaseModel | None:
        """This document's :attr:`FIELDS`, read from its frontmatter; ``None`` without.

        A key the class does not declare is not read (``molab validate``
        reports it); a declared value the model rejects raises ``ValueError``.
        """
        model = type(self).FIELDS
        return None if model is None else self._fields_of(model)

    def _fields_of[M: BaseModel](self, model: type[M]) -> M:
        """*model* built from this document's frontmatter keys that it declares."""
        meta = self.frontmatter()
        return model.model_validate({key: meta[key] for key in model.model_fields if key in meta})

    def title(self) -> str:
        """The display title: frontmatter ``title``, else the first H1, else ``name``, else the stem.

        The one rule, :func:`~molab.knowledge.index_section.document_title`.
        """
        from .frontmatter import split_frontmatter
        from .index_section import document_title

        self._require_document("title")
        meta, body = split_frontmatter(
            read_text_or_none(self._path, fs=self._fs) or "", path=self._path
        )
        return document_title(meta, body, self.name)

    def read(self) -> str:
        """This document's narrative: the markdown body, or the HTML ``<body>`` content."""
        from .frontmatter import split_frontmatter

        self._require_document("read")
        text = read_text_or_none(self._path, fs=self._fs)
        if text is None:
            return ""
        _meta, body = split_frontmatter(text, path=self._path)
        return body

    def ref(
        self,
        ref: object,
        *,
        text: str | None = None,
        role: EdgeRole = DEFAULT_EDGE_ROLE,
    ) -> None:
        """Cross-reference another Knowledge document.

        *ref* must denote a Knowledge: a :class:`Concept` subclass instance
        other than the bare base class, or a path whose markdown file names one.
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

        The host's ``index.knowledges`` section is rebuilt afterwards.

        Args:
            new_name: The new human name.
            within: Tree whose inbound links are rewritten.

        Raises:
            FileExistsError: If the destination already exists.
            ValueError: If *within* is omitted and cannot be derived.

        Runs under the document's lock and records one ``knowledge.moved``
        history commit (:func:`~molab.knowledge.mutation.mutation`).
        """
        from .location import document_slug
        from .mutation import mutation

        self._require_document("rename")
        slug = f"{document_slug(new_name)}{PurePosixPath(self._path).suffix}"
        dst = self._fs.join(self._fs.dirname(self._path), slug)
        if self._norm(dst) == self._norm(self._path):
            return
        with mutation(self, "knowledge.moved", f"rename {self.name} to {new_name}") as change:
            if self._fs.exists(dst):
                raise FileExistsError(
                    f"cannot rename {self._path!r} to {dst!r}: destination exists"
                )
            inbound = self.backlinks(within=within)
            old = self._path
            self._fs.mv(old, dst)
            self._path = dst
            _rewrite_inbound(inbound, old, dst)
            _refresh_sections(self._fs, dst)
            change.touched.extend(str(link.source.path) for link in inbound)

    def move_to(
        self,
        host: object,
        *,
        stem: str | None = None,
        relink: bool = True,
        within: Concept | PathArg | None = None,
    ) -> None:
        """Move this document onto *host* and rewrite relative links.

        The ``index.knowledges`` sections of the old and the new host are
        rebuilt afterwards.

        Args:
            host: A Folder, a path, or a bare Knowledge handle.
            stem: Filename stem kept exactly as ``<stem>.md`` (or ``.html``,
                this document's own suffix), with no slug. ``None`` keeps the
                slug derived from this document's name.
            relink: When false, move the bytes and update this handle only.
                Outbound and inbound links stay as they were.
            within: Tree whose inbound links are rewritten.

        Raises:
            FileExistsError: If the destination already exists.
            TypeError: If *host* is a document instance.
            ValueError: If *stem* is empty, contains ``/``, or is ``.`` / ``..``,
                or *within* is omitted and cannot be derived.

        Runs under the document's lock and records one ``knowledge.moved``
        history commit (:func:`~molab.knowledge.mutation.mutation`).
        """
        if stem is not None and (stem == "" or "/" in stem or stem in {".", ".."}):
            raise ValueError(f"stem {stem!r} is not a single path segment")
        from .location import _folder
        from .mutation import mutation
        from .naming import document_format

        fmt = document_format(self._path)
        planned = str(_folder(host, self.name, type(self), format=fmt))  # ty: ignore[invalid-argument-type]
        suffix = PurePosixPath(planned).suffix
        dst = planned if stem is None else self._fs.join(self._fs.dirname(planned), stem + suffix)
        if self._norm(dst) == self._norm(self._path):
            return
        with mutation(self, "knowledge.moved", f"move {self.name}") as change:
            if self._fs.exists(dst):
                raise FileExistsError(f"cannot move {self._path!r} to {dst!r}: destination exists")
            old = self._path
            inbound = None
            old_dir = ""
            if relink:
                inbound = self.backlinks(within=within)
                old_dir = _link_base(self)
            self._fs.mkdir(self._fs.dirname(dst), parents=True, exist_ok=True)
            self._fs.mv(old, dst)
            self._path = dst
            if relink and inbound is not None:
                new_dir = _link_base(self)
                _retarget_links(self, lambda target: _rehome_link(target, old_dir, new_dir))
                _rewrite_inbound(inbound, old, dst)
                change.touched.extend(str(link.source.path) for link in inbound)
            _refresh_sections(self._fs, old, dst)

    def delete(self) -> None:
        """Remove this document. Inbound links are left dangling.

        The host's ``index.knowledges`` section is rebuilt afterwards. Runs
        under the document's lock and records one ``knowledge.deleted`` history
        commit (:func:`~molab.knowledge.mutation.mutation`).
        """
        from .mutation import mutation

        self._require_document("delete")
        with mutation(self, "knowledge.deleted", f"delete {self.name}"):
            self._fs.rm(self._path)
            _refresh_sections(self._fs, self._path)

    def supersede_with(
        self, successor: Concept, *, within: Concept | PathArg | None = None
    ) -> list[str]:
        """Delete this document and point every inbound link at *successor*.

        Returns:
            The documents whose links were rewritten.
        """
        self._require_document("supersede")
        inbound = [
            link
            for link in self.backlinks(within=within)
            if self._norm(link.source.path) != self._norm(successor.path)
        ]
        old = self._path
        self._fs.rm(old)
        _rewrite_inbound(inbound, old, str(successor.path))
        _refresh_sections(self._fs, old)
        return sorted({str(link.source.path) for link in inbound})

    def export(self) -> str:
        """This document as a file to hand out.

        A markdown document exports its narrative, without frontmatter, and a
        TeX document its LaTeX, without the record block. An HTML document
        exports the whole file: it is already a standalone page, and its
        frontmatter is an inert script element.
        """
        from .naming import is_html_document

        if is_html_document(self._path):
            self._require_document("export")
            return read_text_or_none(self._path, fs=self._fs) or ""
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

    def write(
        self,
        text: str | None = None,
        fields: Mapping[str, object] | None = None,
        *,
        tags: list[str] | None = None,
        replace: bool = False,
    ) -> None:
        """Write this document.

        A string is the narrative, or a full document whose frontmatter is
        merged over the stored one. One file: ``knowledges/<name>.md``, or
        ``.html`` for an HTML document (the frontmatter and body in that
        format).

        With ``replace=True``, *text* is the whole file. It is persisted
        verbatim: no frontmatter merge and no source rendering. Equal bytes
        are left untouched.

        Args:
            text: Narrative, or a full document. ``None`` keeps the narrative.
            fields: Frontmatter keys to set, merged over the stored ones: the
                class's own :attr:`FIELDS`, or a key every document carries.
            tags: Frontmatter tags. ``None`` leaves stored tags alone.
            replace: Persist *text* as the whole file.

        Runs under the document's lock and records one history commit,
        ``knowledge.meta_changed`` when the narrative is kept and
        ``knowledge.edited`` otherwise
        (:func:`~molab.knowledge.mutation.mutation`).

        Raises:
            TypeError: ``replace=True`` and *text* is not a ``str``.
            ValueError: The frontmatter ``class`` is not this document's
                class.
            ContentRuleError: The document the write would leave breaks an
                error-level content rule, its class's fields among them
                (:func:`~molab.knowledge.content_rules.error_issues`). Nothing
                is written.
        """
        from .content_rules import refuse_errors
        from .frontmatter import dump_frontmatter, split_frontmatter
        from .mutation import mutation

        self._require_document("write")
        if text is None and not replace:
            event = "knowledge.meta_changed"
            summary = f"{self.name}: tags" if fields is None else f"{self.name}: fields"
        else:
            event, summary = "knowledge.edited", f"edit {self.name}"
        with mutation(self, event, summary):
            if replace:
                if not isinstance(text, str):
                    raise TypeError(
                        f"replace=True requires the whole document as str, got {type(text).__name__}"
                    )
                meta, body = split_frontmatter(text, path=self._path)
                declared = meta.get("class")
                if declared != type(self).__name__:
                    raise ValueError(
                        f"frontmatter class {declared!r} does not match {type(self).__name__}"
                    )
                if self._fs.is_file(self._path) and self._fs.read_text(self._path) == text:
                    return
                self._refuse_other_class()
                refuse_errors(type(self), str(self._path), meta, body)
                self._fs.mkdir(self._fs.dirname(self._path), parents=True, exist_ok=True)
                self._fs.atomic_write_text(self._path, text)
                return

            head: dict[str, object] = {}
            narrative = text
            if text is not None:
                incoming, body = split_frontmatter(text, path=self._path)
                if incoming:
                    head.update(incoming)
                    narrative = body
            if fields is not None:
                head.update(fields)
            if tags is not None:
                head["tags"] = list(tags)
            head["class"] = type(self).__name__
            sources = list(getattr(self, "_sources", None) or [])
            merged = {**self.frontmatter(), **head}
            self._refuse_other_class()
            if narrative is None:
                narrative = self.read()
            parent = str(PurePosixPath(self._path).parent)
            body, _appended = append_source_links(
                narrative or "", sources, base_dir=parent, path=self._path
            )
            refuse_errors(type(self), str(self._path), merged, body)
            self._fs.mkdir(parent, parents=True, exist_ok=True)
            self._fs.atomic_write_text(self._path, dump_frontmatter(merged, body, path=self._path))

    def _refuse_other_class(self) -> None:
        """Refuse to write over a file that holds another class. Nothing is written yet."""
        stored = self.frontmatter() if self.exists() else {}
        if stored and stored.get("class") != type(self).__name__:
            raise ValueError(
                f"{self.path} already holds a {stored.get('class')}, not a {type(self).__name__}"
            )

    def _follow_moved(self, old: str, new: str) -> None:
        """Re-point an edge this document holds outside its markdown links at *new*.

        :func:`_rewrite_inbound` calls it on each document that linked the
        moved document at *old*, after the markdown links are rewritten. A
        class whose edges are all markdown links holds no other kind.
        """

    def _store_relinked(self, body: str) -> None:
        """Store *body*, in which only link targets changed, under the stored frontmatter.

        Moving a document rewrites the links that point at it. Relinking
        changes no content rule's verdict, so it skips :meth:`write`'s gate: a
        document that already breaks a rule does not block the move.
        """
        from .frontmatter import dump_frontmatter
        from .mutation import mutation

        with mutation(self, "knowledge.edited", f"relink {self.name}"):
            self._fs.atomic_write_text(
                self._path, dump_frontmatter(self.frontmatter(), body, path=self._path)
            )

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
        return self._classify_links(markdown_links(body, path=self._path))

    def _classify_links(self, links: Iterable[re.Match[str]]) -> LinkScan:
        """Resolve each matched markdown link against this document's directory."""
        from molab.workspace.refs import is_ref

        base = PurePosixPath(self._path).parent
        concepts: list[str] = []
        external: list[str] = []
        other: list[str] = []
        typed_concepts: list[Edge] = []
        refs: list[str] = []
        missing: list[str] = []
        for link in links:
            raw_label, target = link.group(1), link.group(2)
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
        from .write import write_knowledge
        from .zotero import ZoteroLibrary

        _ = now
        host: object = self if under is None else under
        refs: list[Literature] = []
        for item in ZoteroLibrary(path).items():
            written = write_knowledge(
                host,  # ty: ignore[invalid-argument-type]
                name=str(item.source_key),
                of=Literature,
                created_by="zotero",
                text="",
                fields=item.model_dump(mode="json", exclude_unset=True),
                fs=self._fs,
            )
            refs.append(written)  # ty: ignore[invalid-argument-type]
        return refs


def _knowledge_target(ref: object, *, fs: FileSystem) -> Concept:
    """The Knowledge *ref* denotes, or ``TypeError`` — the one strictness rule.

    Used by :meth:`Concept.ref`: an object
    denotes a Knowledge when its class is a :class:`Concept` subclass other than
    the bare base class, and a path denotes one when the markdown file there
    names a subclass. A run / project / experiment directory fails both — it
    is not a markdown document.

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
        from .concepts import _open_document
        from .errors import KnowledgeNotFoundError

        path = str(ref)
        try:
            located = _open_document(path, fs=fs)
        except KnowledgeNotFoundError as exc:
            raise TypeError(f"{path!r} locates no Knowledge document") from exc
        if type(located) is Concept:
            raise TypeError(f"{path!r} locates a bare Concept, not a Knowledge")
        return located
    raise TypeError(
        f"cross-reference target must be a Knowledge document, got {type(ref).__name__}; "
        "pass the Knowledge, or the path locating one"
    )


def _refresh_sections(fs: FileSystem, *document_paths: str) -> None:
    """Rebuild the ``index.knowledges`` section of each host these paths sit under.

    Two paths on one host (a rename) rebuild it once. Never raises.
    """
    from .index_section import refresh_section
    from .location import host_of

    seen: set[str] = set()
    for path in document_paths:
        host = str(host_of(path))
        if host in seen:
            continue
        seen.add(host)
        refresh_section(path, fs=fs)


def _skip_link(target: str) -> bool:
    """Whether *target* is an external, schemed, anchor, or molab reference.

    A reference, including a ``#span`` suffix, is canonical text. Rewriting it
    as a relative path would drop the only provenance record on a disk-opened
    document.
    """
    from molab.workspace.refs import is_ref

    return target.startswith(("#", "http://", "https://")) or "://" in target or is_ref(target)


def _link_base(doc: Concept) -> str:
    """The directory relative links in document *doc* are resolved against."""
    return str(PurePosixPath(doc.path).parent)


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
        doc._follow_moved(old, new)


def retarget_links(
    text: str,
    rewrite: Callable[[str, bool], str | None],
    *,
    path: object = None,
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
        path: The document *text* belongs to (:func:`markdown_links`).

    Returns:
        The new text and how many targets actually changed.
    """
    count = 0
    pieces: list[str] = []
    cursor = 0
    for match in markdown_links(text, path=path):
        label, target = match.group(1), match.group(2)
        image = match.start() > 0 and text[match.start() - 1] == "!"
        updated = rewrite(target, image)
        if updated is None or updated == target:
            continue
        count += 1
        pieces.append(text[cursor : match.start()])
        pieces.append(f"[{label}]({updated})")
        cursor = match.end()
    pieces.append(text[cursor:])
    return "".join(pieces), count


def _retarget_links(doc: Concept, rewrite: Callable[[str], str | None]) -> bool:
    """Rewrite markdown link targets in *doc*, keeping labels.

    Args:
        doc: The document to rewrite.
        rewrite: Maps a raw target to its replacement, or ``None`` to keep it.

    Returns:
        Whether the narrative changed.
    """
    new, count = retarget_links(doc.read(), lambda target, _image: rewrite(target), path=doc.path)
    if count > 0:
        doc._store_relinked(new)
    return count > 0


def append_source_links(
    body: str,
    sources: Sequence[object],
    *,
    base_dir: str,
    path: PathArg | None = None,
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
        path: The document *body* belongs to. An HTML document gets the
            lines as one ``<molab-markdown>`` block.

    Returns:
        The new body and how many lines were appended.

    Raises:
        ValueError: A source's ``link_target`` rejects its ref (a bare entity id).
    """
    if not sources:
        return body, 0
    have = {
        (parse_role(label)[0], posixpath.normpath(target))
        for label, target in (link.groups() for link in markdown_links(body, path=path))
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
    from .frontmatter import append_markdown

    return append_markdown(body, "\n".join(lines) + "\n", path=path), len(lines)


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


def link_target(dst: Concept | Folder | Asset | MolabRef | PathArg) -> str:
    """The target an edge to *dst* names, before it is made relative.

    The one resolver for every link writer. A workspace project, experiment,
    run or asset is its ``molab:`` reference. A reference, or a string that is
    one, is itself. A document is its path, any other workspace folder its
    directory, and a path is itself.

    Raises:
        TypeError: *dst* is none of those. An arbitrary object is never
            ``str()``-ed into a link: its repr would be a silently broken edge.
    """
    from molab.workspace.domain import Asset
    from molab.workspace.experiment import Experiment
    from molab.workspace.folder import Folder
    from molab.workspace.project import Project
    from molab.workspace.refs import MolabRef, ref_of
    from molab.workspace.run import Run

    if isinstance(dst, (Project, Experiment, Run, Asset)):
        return str(ref_of(dst))
    if isinstance(dst, Concept):
        return str(dst.path)
    if isinstance(dst, Folder):
        return str(dst.resolve())
    if isinstance(dst, (MolabRef, str, os.PathLike)):
        return str(dst)
    raise TypeError(
        f"edge target must be a document, a workspace entity, a molab reference or a "
        f"path, got {type(dst).__name__}"
    )


def append_link(
    src: Concept,
    dst: Concept | Folder | Asset | MolabRef | PathArg,
    *,
    text: str | None = None,
    role: EdgeRole = DEFAULT_EDGE_ROLE,
) -> None:
    """Append a typed markdown link ``src → dst`` to ``src``'s body.

    The single markdown-edge writer, and the sole role-writing chokepoint, so
    the on-disk edge format cannot drift. The graph lives in the markdown
    body. The default role encodes to the bare label. Appends
    unconditionally.

    *dst* resolves through :func:`link_target`: a ``molab:`` reference is
    written verbatim, and a path is written relative to *src*.

    Args:
        src: The Concept the edge originates from.
        dst: What the edge points to (see :func:`link_target`).
        text: Optional link label; defaults to the target's last segment.
        role: The declared :class:`~molab.knowledge.edges.EdgeRole`.

    Runs under *src*'s lock and records one ``knowledge.linked`` history
    commit (:func:`~molab.knowledge.mutation.mutation`).

    Raises:
        ValueError: If *role* is not a known ``EdgeRole`` — validated before any
            write, so an invalid role leaves the document body untouched.
        TypeError: If *dst* names nothing :func:`link_target` accepts.
    """
    validate_role(role)
    from molab.workspace.refs import is_ref

    from .mutation import mutation

    target = link_target(dst)
    if is_ref(target):
        label = text if text is not None else target.rstrip("/").rsplit("/", 1)[-1]
        with mutation(src, "knowledge.linked", f"@{role} {target} from {src.name}"):
            _append_line(src, link_line(encode_label(role, label), target))
        return
    src_base = str(Path(src.path).parent)
    rel_posix = PurePosixPath(os.path.relpath(target, src_base)).as_posix()
    label = text if text is not None else PurePosixPath(target).name
    with mutation(src, "knowledge.linked", f"@{role} {rel_posix} from {src.name}"):
        _append_line(src, link_line(encode_label(role, label), rel_posix))


def _append_line(src: Concept, line: str) -> None:
    """Append one markdown *line* to *src*'s narrative, in its own format."""
    from .frontmatter import append_markdown

    src.write(append_markdown(src.read(), line + "\n", path=src.path))


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
    "Concept",
    "Knowledge",
    "LinkScan",
    "append_link",
    "append_source_links",
    "link_target",
    "read_text_or_none",
    "retarget_links",
]
