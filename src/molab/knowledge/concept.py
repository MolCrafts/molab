"""``Concept`` — an OKF Concept: a directory whose **path is its identity**.

In the Open Knowledge Format a Concept is a plain directory holding two files:

- ``meta.json`` — the typed head. Its one required field, ``type``, is the key
  into the concept-type registry (:mod:`molab.knowledge.types`), so a directory
  says what it is and :func:`concept_from_dir` rebuilds the right subclass.
- ``index.md`` — the human narrative. Its markdown links **are** the knowledge
  graph: every in-tree link that resolves to a directory is a typed out-edge
  (:meth:`Concept.typed_out_edges`), with the role riding in the ``[label]``
  channel.

**Path is identity, and that is the whole design.** A ``Concept`` holds an
absolute path and a :class:`~molab.fs.FileSystem`; it has no parent pointer and
composes no path from a hierarchy. That is what lets an OKF bundle open *any*
directory — a group wiki, a git repo, a subtree of a molab workspace — without
a workspace, and it is why reading a Concept never depends on knowing what
contains it.

Contrast the workspace :class:`~molab.workspace.folder.Folder` family, whose
``resolve()`` deliberately *does* chain through parents to replay the frozen
layout (``projects/`` / ``experiments/`` / ``runs/run-``). The two families are
independent by design and share only the concept-type registry, which keeps them
apart via ``resolve_concept_type(..., base=...)``.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterator, Mapping
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, ClassVar, NamedTuple

from molab.fs import FileSystem, LocalFileSystem, PathArg

from .concept_meta import ConceptMeta
from .edges import DEFAULT_EDGE_ROLE, Edge, EdgeRole, encode_label, parse_role, validate_role
from .types import resolve_concept_type

if TYPE_CHECKING:
    from molab._typing import JSONValue

    from .bundle_index import SearchResult
    from .concepts import Literature

INDEX_FILENAME = "index.md"
META_JSON_FILENAME = "meta.json"

#: OKF operational sidecar — hot machine state, never knowledge. Skipped by walks.
OPS_DIR = "_ops"

#: Directories a Knowledge walk never enters. Run output and machine state
#: cannot hold a product document; visiting them on a workspace is the hang.
_KNOWLEDGE_WALK_PRUNE: frozenset[str] = frozenset(
    {
        OPS_DIR,
        "executions",
        "out",
        "artifacts",
        "jobs",
        "work",
        "checkpoints",
        "cache",
        "logs",
        "source",
        # legacy on-disk name: written by runs before D86 removed the agent layer; tolerated on read
        "harness",
        "node_modules",
        "__pycache__",
        "dist",
        "assets",
    }
)

#: Layout containers whose children are entity folders (or ``knowledges/``).
#: Everywhere else the walk only descends into these names — so ``pinn-src/``,
#: ``campaign/``, ``ic/`` and similar bulk trees are never scanned.
_KNOWLEDGE_WALK_CONTAINERS: frozenset[str] = frozenset(
    {"knowledges", "projects", "experiments", "runs"}
)

#: ``[label](target)`` — both halves captured; the label carries the edge role.
_MD_LINK = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")

#: Fallback ``type`` for a directory whose ``meta.json`` declares none.
FALLBACK_CONCEPT_TYPE = "concept"


class LinkScan(NamedTuple):
    """Resolved out-links of a Concept's ``index.md``.

    Attributes:
        concepts: Targets resolving to an existing in-tree dir — the
            knowledge-graph out-edges (path-only).
        external: ``http(s)://`` links.
        other: In-tree targets that don't resolve to a dir.
        typed_concepts: The same edges as :attr:`concepts`, each paired with the
            :class:`~molab.knowledge.edges.EdgeRole` recovered from the
            markdown ``[label]`` channel.
    """

    concepts: list[str]
    external: list[str]
    other: list[str]
    typed_concepts: list[Edge]


class Concept:
    """An OKF Concept — a directory addressed by its absolute path.

    Product Knowledge subclasses (``FILE_DOCUMENT``) are instead a
    ``knowledges/<name>.md`` file whose YAML frontmatter names the class.
    """

    #: The ``meta.json`` ``type`` a bare construction of this class declares.
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
            path: The Concept's directory — its identity (already-absolute in
                every production call path). With *name* given it is instead
                the **host**: a ``str`` / :class:`os.PathLike` directory used
                as given, or a ``Folder``-family object carrying ``_disk()``.
            name: A human document name. When given, the path is derived by
                :func:`~molab.knowledge.location.folder` as
                ``folder(path, name, self.__class__)`` — a ``FILE_DOCUMENT``
                class lands at ``<host>/knowledges/<slug>.md``, a
                directory-form class at ``<host>/knowledges/<slug>/`` — and
                nothing touches disk; the first :meth:`write` / :meth:`ref`
                lands the bytes.
            type: The ``type`` :meth:`write_meta` stamps; defaults to
                :attr:`DEFAULT_TYPE`.
            fs: The filesystem to read and write through; defaults to the
                host's own disk (never the local one) in the *name* form, and
                to :class:`~molab.fs.LocalFileSystem` otherwise.

        Raises:
            TypeError: If *name* is given and *path* is not a recognised host —
                an object with ``resolve()`` but no ``_disk()`` included.
        """
        if name is not None:
            from .location import _host_disk, folder

            # ``self.__class__``, not ``type(self)``: the *type* kwarg below
            # shadows the builtin.
            raw = str(folder(path, name, self.__class__))
            disk = fs if fs is not None else _host_disk(path)
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

    # ── meta.json (the typed head) ───────────────────────────────────────

    def read_meta(self) -> dict[str, JSONValue]:
        """This Concept's ``meta.json`` as a plain dict (``{}`` when absent).

        One filesystem call: the file is read directly and an absent marker is
        the ``FileNotFoundError`` it raises — never an ``exists`` probe first
        (two round trips on a remote filesystem for one answer).
        """
        return read_meta_dict(self._path, fs=self._fs) or {}

    def write_meta(self, meta: ConceptMeta | Mapping[str, object] | None = None) -> None:
        """Atomically write this Concept's ``meta.json``, creating the dir.

        The on-disk ``type`` and ``id`` are always stamped to this Concept's own
        type and directory name, so :func:`concept_from_dir` reconstructs the
        same class and identity stays path-derived no matter what *meta* says.

        Args:
            meta: The typed head to write; ``None`` writes the bare
                ``{type, id}`` marker.
        """
        if meta is None:
            payload: dict[str, object] = {}
        elif isinstance(meta, ConceptMeta):
            payload = meta.model_dump(mode="json")
        else:
            payload = dict(meta)
        payload["type"] = self._type
        payload["id"] = self.name
        self._fs.mkdir(self._path, parents=True, exist_ok=True)
        self._fs.atomic_write_text(
            self._fs.join(self._path, META_JSON_FILENAME),
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        )

    def _persist(self, data: object | None = None) -> None:
        """Persist the class-named JSON — never ``meta.json``, never ``type``/``kind``."""
        from .naming import knowledge_filename

        payload: dict[str, object]
        if data is None:
            payload = {}
        elif isinstance(data, ConceptMeta):
            payload = dict(data.model_dump(mode="json"))
        elif isinstance(data, Mapping):
            payload = {str(key): value for key, value in data.items()}
        else:
            payload = {}
        payload.pop("type", None)
        payload.pop("kind", None)
        payload.pop("id", None)
        sources = getattr(self, "_sources", None)
        if sources:
            payload["sources"] = [
                s.model_dump(mode="json") if hasattr(s, "model_dump") else s for s in sources
            ]
        self._fs.mkdir(self._path, parents=True, exist_ok=True)
        self._fs.atomic_write_text(
            self._fs.join(self._path, knowledge_filename(type(self))),
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        )

    @classmethod
    def open(
        cls,
        directory: PathArg,
        *,
        fs: FileSystem | None = None,
    ) -> Concept:
        """Open the document at *directory*, choosing the subclass from the class-named json."""
        from .errors import KnowledgeNotFoundError
        from .naming import knowledge_filename

        disk = fs if fs is not None else LocalFileSystem()
        from .concepts import Finding, Literature, Note, Observation, Plan, Report
        from .naming import is_knowledge_file

        raw = str(directory)
        if is_knowledge_file(raw):
            return cls._open_markdown(raw, disk)
        from .naming import as_knowledge_file

        md = as_knowledge_file(raw)
        if disk.is_file(md):
            return cls._open_markdown(md, disk)

        mapping = {
            knowledge_filename(Note): Note,
            knowledge_filename(Literature): Literature,
            knowledge_filename(Report): Report,
            knowledge_filename(Finding): Finding,
            knowledge_filename(Plan): Plan,
            knowledge_filename(Observation): Observation,
        }
        for name, klass in mapping.items():
            text = read_text_or_none(disk.join(str(directory), name), fs=disk)
            if text is None:
                continue
            payload: dict[str, object] = {}
            if text.strip():
                raw = json.loads(text)
                if isinstance(raw, dict):
                    payload = raw
            if klass in (Finding, Report, Plan, Observation):
                from .knowledge_item import SourceRef

                sources_raw = payload.get("sources") or []
                if not isinstance(sources_raw, list):
                    sources_raw = []
                sources = [
                    SourceRef.model_validate(row) if not isinstance(row, SourceRef) else row
                    for row in sources_raw
                ]
                if klass is Finding:
                    return Finding(directory, sources=sources, fs=disk)
                if klass is Report:
                    return Report(directory, sources=sources, fs=disk)
                if klass is Plan:
                    return Plan(directory, sources=sources, fs=disk)
                return Observation(directory, sources=sources, fs=disk)
            return klass(directory, fs=disk)
        raise KnowledgeNotFoundError(str(directory))

    @classmethod
    def _open_markdown(cls, path: str, disk: FileSystem) -> Concept:
        """Open a ``.md`` / ``.mdx`` Knowledge file from its frontmatter ``class``."""
        from .concepts import Finding, Literature, Note, Observation, Plan, Report
        from .errors import KnowledgeNotFoundError
        from .frontmatter import split_frontmatter
        from .knowledge_item import SourceRef

        text = read_text_or_none(path, fs=disk)
        if text is None:
            raise KnowledgeNotFoundError(path)
        meta, _body = split_frontmatter(text)
        class_name = str(meta.get("class") or "Note")
        mapping = {
            "Note": Note,
            "Literature": Literature,
            "Report": Report,
            "Finding": Finding,
            "Plan": Plan,
            "Observation": Observation,
        }
        klass = mapping.get(class_name, Note)
        sources_raw = meta.get("sources") or []
        if not isinstance(sources_raw, list):
            sources_raw = []
        sources = []
        for row in sources_raw:
            if isinstance(row, SourceRef):
                sources.append(row)
                continue
            if isinstance(row, dict):
                row = dict(row)
                if row.get("span") is not None:
                    row["span"] = str(row["span"])
            sources.append(SourceRef.model_validate(row))
        if klass in (Finding, Report, Plan, Observation):
            if not sources:
                sources = [SourceRef(kind="file", ref=PurePosixPath(path).name)]
            return klass(path, sources=sources, fs=disk)
        return klass(path, fs=disk)

    def walk(self) -> Iterator[Concept]:
        """Yield Knowledge subclasses under this handle that hold a class-named head.

        Only descends ``knowledges/``, ``projects/``, ``experiments/``, and
        ``runs/`` (plus each entity folder those containers hold). Bulk trees
        next to them (``pinn-src/``, ``campaign/``, ``ic/``, …) are skipped.
        """
        yield from self._walk_knowledge(self._path)

    def _walk_knowledge(self, directory: str) -> Iterator[Concept]:
        from .errors import KnowledgeNotFoundError
        from .naming import KNOWLEDGE_CONTAINER, is_knowledge_file

        try:
            entries = self._fs.scandir(directory, with_stat=False)
        except (OSError, ValueError):
            return
        dirname = PurePosixPath(directory).name
        if dirname == KNOWLEDGE_CONTAINER:
            for entry in entries:
                if not entry.is_file or not is_knowledge_file(entry.name):
                    continue
                child = self._fs.join(directory, entry.name)
                try:
                    yield type(self).open(child, fs=self._fs)
                except KnowledgeNotFoundError:
                    continue
            return
        # ``projects/`` / ``experiments/`` / ``runs/`` hold entity folders —
        # enter every child. Everywhere else, only layout containers.
        descend_all = dirname in {"projects", "experiments", "runs"}
        for entry in entries:
            if not entry.is_dir or entry.name in _KNOWLEDGE_WALK_PRUNE:
                continue
            if entry.name.startswith("."):
                continue
            if not descend_all and entry.name not in _KNOWLEDGE_WALK_CONTAINERS:
                continue
            yield from self._walk_knowledge(self._fs.join(directory, entry.name))

    def search(
        self,
        text: str | None = None,
        of: object | None = None,
        *,
        tag: str | None = None,
        limit: int = 50,
        include_text: bool = True,
    ) -> SearchResult:
        """Search documents under this handle. *of* is a subclass to keep (e.g. ``Note``)."""
        from .bundle import Bundle
        from .bundle_index import BundleIndex, ConceptIndexEntry, extract_title

        root = Path(self._path)
        entries = []
        bodies: dict[str, str] = {}
        for item in self.walk():
            if isinstance(of, type) and not isinstance(item, of):
                continue
            if tag is not None and tag not in item.tags():
                continue
            rel = Path(str(item.path)).relative_to(root).as_posix()
            body = item.read() if include_text else ""
            bodies[rel] = body
            entries.append(
                ConceptIndexEntry(
                    path=rel,
                    type=type(item).__name__,
                    title=extract_title(body) or item.name,
                    tags=tuple(item.tags()),
                )
            )
        return Bundle(self.path, fs=self._fs).search(
            text,
            tag=None,
            limit=limit,
            include_body=include_text,
            index=BundleIndex(entries=tuple(entries)),
            bodies=bodies,
        )

    def type(self) -> str:
        """The ``meta.json`` ``type``, falling back to this Concept's declared type."""
        raw = self.read_meta().get("type")
        return str(raw) if raw else self._type

    def tags(self) -> list[str]:
        """Categorical labels from frontmatter (file) or ``meta.json`` (directory)."""
        if self.__class__.FILE_DOCUMENT:
            raw = self.frontmatter().get("tags")
            return [str(t) for t in raw] if isinstance(raw, list) else []
        raw = self.read_meta().get("tags")
        return [str(t) for t in raw] if isinstance(raw, list) else []

    # ── index.md (the narrative, and the graph) ──────────────────────────

    def read_index(self) -> str:
        """This Concept's ``index.md`` (``""`` when absent) — one read, no probe."""
        text = read_text_or_none(self._fs.join(self._path, INDEX_FILENAME), fs=self._fs)
        return "" if text is None else text

    def write_index(self, text: str) -> None:
        """Atomically write this Concept's ``index.md``, creating the dir."""
        self._fs.mkdir(self._path, parents=True, exist_ok=True)
        self._fs.atomic_write_text(self._fs.join(self._path, INDEX_FILENAME), text)

    def frontmatter(self) -> dict[str, object]:
        """YAML frontmatter of a file document (``{}`` when absent or a directory)."""
        from .frontmatter import split_frontmatter

        if not self.__class__.FILE_DOCUMENT:
            return {}
        text = read_text_or_none(self._path, fs=self._fs)
        if text is None:
            return {}
        meta, _body = split_frontmatter(text)
        return meta

    def read(self) -> str:
        """This document's narrative (markdown body, frontmatter stripped)."""
        from .frontmatter import split_frontmatter
        from .naming import is_knowledge_file

        if type(self).FILE_DOCUMENT or is_knowledge_file(self._path):
            text = read_text_or_none(self._path, fs=self._fs)
            if text is None:
                return ""
            _meta, body = split_frontmatter(text)
            return body
        return self.read_index()

    def ref(
        self,
        ref: object,
        *,
        text: str | None = None,
        role: EdgeRole = DEFAULT_EDGE_ROLE,
    ) -> None:
        """Cross-reference another Knowledge document — the strict spelling of :meth:`cite`.

        *ref* must denote a Knowledge: a :class:`Concept` subclass instance
        other than the bare base class (the object :func:`concept_from_dir`
        hands back for a workspace entity, i.e. a run / project / experiment
        directory), or a path :meth:`Concept.open` locates such a subclass at.
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

    def write(
        self,
        text: str | object | None = None,
        data: object | None = None,
        *,
        tags: list[str] | None = None,
        status: str | None = None,
    ) -> None:
        """Write this document.

        A string is the narrative, or a full markdown document with YAML
        frontmatter. Structured records (``ReferenceMeta``, sources, tags)
        fold into the frontmatter. One file: ``knowledges/<name>.md``.
        """
        from .frontmatter import dump_frontmatter, split_frontmatter
        from .naming import as_knowledge_file

        if not self.__class__.FILE_DOCUMENT:
            record = data
            narrative: str | None
            if text is None:
                narrative = None
            elif isinstance(text, str):
                narrative = text
            else:
                record = text if record is None else record
                narrative = None
            extra: dict[str, object] = {}
            if tags is not None:
                extra["tags"] = list(tags)
            if status is not None:
                extra["status"] = status
            if extra:
                if record is None:
                    record = extra
                elif isinstance(record, Mapping):
                    record = {**{str(k): v for k, v in record.items()}, **extra}
            self._persist(record)
            if narrative is not None:
                self.write_index(narrative)
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
        sources = getattr(self, "_sources", None)
        if sources and "sources" not in extra:
            extra["sources"] = [
                s.model_dump(mode="json") if hasattr(s, "model_dump") else s for s in sources
            ]
        existing_fm = self.frontmatter()
        merged = {**existing_fm, **extra}
        if narrative is None:
            narrative = self.read()
        parent = str(PurePosixPath(self._path).parent)
        self._fs.mkdir(parent, parents=True, exist_ok=True)
        self._fs.atomic_write_text(self._path, dump_frontmatter(merged, narrative or ""))
        srcs = merged.get("sources")
        if isinstance(srcs, list) and srcs:
            from .knowledge_item import SourceRef

            self._sources = [  # type: ignore[attr-defined]
                SourceRef.model_validate(row) if not isinstance(row, SourceRef) else row
                for row in srcs
            ]

    def links(self) -> list[Edge]:
        """The documents this one cites — typed markdown links in the narrative."""
        return self.scan_links(self.read()).typed_concepts

    def scan_links(self, body: str) -> LinkScan:
        """Classify the markdown links in *body* as if it were this Concept's.

        The same scan as :meth:`links`, against text the caller already holds.
        Indexing reads every ``index.md`` for its title and then wants its
        edges; without this the file would be read a second time to answer a
        question the first read already contained.

        Args:
            body: The ``index.md`` text to scan.
        """
        base = PurePosixPath(self._path)
        if self.__class__.FILE_DOCUMENT:
            base = base.parent
        concepts: list[str] = []
        external: list[str] = []
        other: list[str] = []
        typed_concepts: list[Edge] = []
        for raw_label, target in _MD_LINK.findall(body):
            if target.startswith(("http://", "https://")):
                external.append(target)
                continue
            norm = PurePosixPath(os.path.normpath(base / target))
            concept_dir = norm.parent if norm.name == INDEX_FILENAME else norm
            if self._fs.is_dir(str(concept_dir)) or self._fs.is_file(str(concept_dir)):
                concepts.append(str(concept_dir))
                role, _human = parse_role(raw_label)
                typed_concepts.append(Edge(target=str(concept_dir), role=role))
            else:
                other.append(target)
        return LinkScan(
            concepts=concepts,
            external=external,
            other=other,
            typed_concepts=typed_concepts,
        )

    def out_edges(self) -> list[str]:
        """In-tree link targets (paths only)."""
        return self.scan_links(self.read()).concepts

    def typed_out_edges(self) -> list[Edge]:
        """Same as :meth:`links` — kept for Folder-shaped call sites."""
        return self.links()

    def import_zotero(
        self,
        path: PathArg,
        *,
        under: PathArg | None = None,
        now: object | None = None,
    ) -> list[Literature]:
        """Link a local Zotero library as :class:`Literature` directories.

        Each item becomes ``literature.json`` + ``index.md`` under *under*
        (default: ``references/`` at this handle). PDFs are pointed at, never
        copied. Idempotent on the slugified Zotero key.

        Args:
            path: The ``zotero.sqlite`` to read (opened read-only).
            under: Directory to mount literature beneath.
            now: Unused; accepted so callers matching the old signature keep working.

        Returns:
            The :class:`Literature` records created or updated.
        """
        from molab.ids import slugify

        from .concepts import Literature
        from .reference_meta import ReferenceMeta
        from .zotero import read_zotero_items

        _ = now
        host = Path(str(under)) if under is not None else Path(self._path) / "references"
        items = read_zotero_items(path)
        refs: list[Literature] = []
        for item in items:
            slug = slugify(item.key) or item.key
            lit = Literature(self._fs.join(str(host), slug), fs=self._fs)
            lit.write(
                ReferenceMeta(
                    title=item.title,
                    authors=item.authors,
                    year=item.year,
                    doi=item.doi,
                    url=item.url,
                    pdf_path=item.pdf_path,
                    source="zotero",
                    source_key=item.key,
                )
            )
            refs.append(lit)
        return refs


def _knowledge_target(ref: object, *, fs: FileSystem) -> Concept:
    """The Knowledge *ref* denotes, or ``TypeError`` — the one strictness rule.

    Shared by :meth:`Concept.ref` (which propagates the error) and
    :meth:`Concept.cite` (which falls back to its loose path branch): an object
    denotes a Knowledge when its class is a :class:`Concept` subclass other than
    the bare base class, and a path denotes one when :meth:`Concept.open`
    locates such a subclass there. A run / project / experiment directory fails
    both — :func:`concept_from_dir` reconstructs it as the bare base class, and
    ``Concept.open`` finds no class-named head in it.

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


def append_link(
    src: Concept,
    dst: Concept | PathArg,
    *,
    text: str | None = None,
    role: EdgeRole = DEFAULT_EDGE_ROLE,
) -> None:
    """Append a typed relative markdown link ``src → dst`` to ``src``'s ``index.md``.

    The single markdown-edge writer, and the sole role-writing chokepoint:
    ``Bundle.link``, ``Note.cite`` and ``KnowledgeItem.cite`` all delegate here,
    so the on-disk edge format cannot drift. The graph lives in markdown, never
    in ``meta.json``. The default role encodes to the bare label, so pre-role
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
            write, so an invalid role leaves ``index.md`` untouched.
        TypeError: If *dst* is neither a ``Concept`` nor a path.
    """
    validate_role(role)
    if isinstance(dst, Concept):
        dst_path = str(dst.path)
    elif isinstance(dst, (str, os.PathLike)):
        dst_path = str(dst)
    else:
        # Never ``str()`` an arbitrary object into a link: that would write a
        # repr as the target and produce a silently broken edge. A caller
        # holding a foreign-family object (a workspace ``Folder``) passes its
        # directory; ``Bundle`` does that coercion at its own boundary.
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
    src.write(f"{prefix}- [{encoded}]({rel_posix})\n")


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


def parse_meta_text(text: str) -> dict[str, JSONValue]:
    """Parse a ``meta.json`` document into a dict (``{}`` for empty / non-mapping)."""
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


#: Extra filenames a host layer has declared to be Concept markers, tried in
#: registration order after ``meta.json``. See :func:`register_marker_filenames`.
_EXTRA_MARKER_FILENAMES: tuple[str, ...] = ()

#: Whether :func:`register_host_markers` has already run this process.
_HOST_MARKERS_REGISTERED = False


def register_marker_filenames(*names: str) -> None:
    """Declare that *names* also mark a directory as a Concept.

    A host layer may already write a typed record per directory and have no
    reason to write a second one: a molab workspace's ``run.json`` /
    ``project.json`` *is* that run's or project's identity, and it carries the
    same ``type`` key ``meta.json`` would. Registering those filenames lets a
    bundle walk the workspace tree without either layer importing the other, and
    without duplicating the record — the one-source-of-truth law applies across
    this seam too.

    Idempotent, and order-preserving: ``meta.json`` is always tried first, so a
    directory that carries both reads as its own Concept head.
    """
    global _EXTRA_MARKER_FILENAMES
    _EXTRA_MARKER_FILENAMES += tuple(n for n in names if n not in _EXTRA_MARKER_FILENAMES)


def register_host_markers() -> None:
    """Declare the host layer's own entity filenames as Concept markers.

    A molab workspace marks each entity directory with its own class-named
    record (``workspace.json`` / ``project.json`` / ``experiment.json`` /
    ``run.json``) and writes no second ``meta.json``, so those directories are
    only Concepts because the host declares them. The host owns that list
    (:func:`molab.workspace.folder.entity_json_names`) and this is the one place
    knowledge asks for it — imported **inside the function body**, the only form
    the layer firewall allows, because ``molab.workspace`` eagerly loads this
    package the other way. Runs once per process; :func:`marker_filenames`
    triggers it, so every reader sees the host's names without registering them
    itself.
    """
    global _HOST_MARKERS_REGISTERED
    if _HOST_MARKERS_REGISTERED:
        return
    from molab.workspace.folder import entity_json_names

    register_marker_filenames(*entity_json_names())
    _HOST_MARKERS_REGISTERED = True


def marker_filenames() -> tuple[str, ...]:
    """Every filename that marks a Concept directory, in read order."""
    register_host_markers()
    return (META_JSON_FILENAME, *_EXTRA_MARKER_FILENAMES)


def read_meta_dict(directory: PathArg, *, fs: FileSystem) -> dict[str, JSONValue] | None:
    """The parsed Concept head at *directory*, or ``None`` when there is none.

    ``None`` means "not a Concept directory" (no marker file at all); an empty
    or non-mapping marker parses to ``{}``. One read per candidate, no probe —
    the single primitive the bundle walk uses to decide concept-ness *and* type
    together. Candidates are ``meta.json`` then whatever the host registered
    (:func:`register_marker_filenames`), first hit wins.
    """
    for name in marker_filenames():
        text = read_text_or_none(fs.join(directory, name), fs=fs)
        if text is None:
            continue
        meta = parse_meta_text(text)
        # A host's record may name the type by its *filename* instead of a
        # ``type`` key — a molab workspace reconstructs its knowledge family
        # that way (``observation.json`` → ``observation``). Fill it in so every
        # reader downstream sees one typed head, without the record growing a
        # second spelling of what its own name already says.
        if name != META_JSON_FILENAME and "type" not in meta:
            meta["type"] = name.removesuffix(".json")
        return meta
    return None


def meta_type(meta: Mapping[str, object] | None) -> str:
    """The ``type`` string carried by a parsed ``meta.json`` (``""`` when absent)."""
    if not meta:
        return ""
    raw = meta.get("type", "")
    return str(raw) if raw else ""


def concept_type_of(directory: PathArg, *, fs: FileSystem) -> str:
    """The ``meta.json`` ``type`` declared at *directory* (``""`` when absent)."""
    return meta_type(read_meta_dict(directory, fs=fs))


def concept_from_dir(
    directory: PathArg,
    *,
    fs: FileSystem,
    type_str: str | None = None,
) -> Concept:
    """Reconstruct *directory* as its registered :class:`Concept` subclass.

    Reads the OKF ``meta.json`` ``type`` and resolves it through the shared
    concept-type registry, filtered to the ``Concept`` family
    (``base=Concept``) so a workspace ``Folder`` subclass registered under the
    same registry is never handed back here. An unknown, foreign or absent type
    yields a base :class:`Concept` carrying the declared type string — the walk
    stays total over a heterogeneous tree instead of raising.

    Args:
        directory: The Concept directory to reconstruct.
        fs: The filesystem to read through.
        type_str: The already-read ``meta.json`` ``type`` (``""`` for a
            marker without one). A walker that has just parsed the marker
            passes it so the file is read exactly once; ``None`` reads it here.
    """
    from .errors import KnowledgeNotFoundError

    try:
        return Concept.open(directory, fs=fs)
    except KnowledgeNotFoundError:
        pass
    if type_str is None:
        type_str = concept_type_of(directory, fs=fs)
    cls = resolve_concept_type(type_str, Concept, base=Concept)
    return cls(directory, type=type_str or None, fs=fs)


Knowledge = Concept


__all__ = [
    "FALLBACK_CONCEPT_TYPE",
    "INDEX_FILENAME",
    "META_JSON_FILENAME",
    "OPS_DIR",
    "Concept",
    "Knowledge",
    "LinkScan",
    "append_link",
    "concept_from_dir",
    "concept_type_of",
    "marker_filenames",
    "meta_type",
    "parse_meta_text",
    "read_meta_dict",
    "read_text_or_none",
    "register_host_markers",
    "register_marker_filenames",
]
