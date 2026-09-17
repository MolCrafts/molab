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
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, ClassVar, NamedTuple

from molab.fs import FileSystem, LocalFileSystem, PathArg

from .concept_meta import ConceptMeta
from .edges import DEFAULT_EDGE_ROLE, Edge, EdgeRole, encode_label, parse_role, validate_role
from .types import resolve_concept_type

if TYPE_CHECKING:
    from molab._typing import JSONValue

INDEX_FILENAME = "index.md"
META_JSON_FILENAME = "meta.json"

#: OKF operational sidecar — hot machine state, never knowledge. Skipped by walks.
OPS_DIR = "_ops"

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

    Construction touches no disk: a ``Concept`` may name a directory that does
    not exist yet (:meth:`write_meta` / :meth:`set_body` create it), and reads
    of an absent ``meta.json`` / ``index.md`` return empty rather than raising,
    so a walk over a heterogeneous tree stays total.
    """

    #: The ``meta.json`` ``type`` a bare construction of this class declares.
    DEFAULT_TYPE: ClassVar[str] = FALLBACK_CONCEPT_TYPE

    def __init__(
        self,
        path: PathArg,
        *,
        type: str | None = None,
        fs: FileSystem | None = None,
    ) -> None:
        """Bind this Concept to *path* on *fs*.

        Args:
            path: The Concept's directory — its identity. Kept as given
                (already-absolute in every production call path).
            type: The ``type`` :meth:`write_meta` stamps; defaults to
                :attr:`DEFAULT_TYPE`.
            fs: The filesystem to read and write through; defaults to
                :class:`~molab.fs.LocalFileSystem`.
        """
        self._fs: FileSystem = fs if fs is not None else LocalFileSystem()
        self._path = str(path)
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
        """The directory name (the last path segment)."""
        return PurePosixPath(self._path).name

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
        """Whether this Concept's directory is on disk."""
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

    def type(self) -> str:
        """The ``meta.json`` ``type``, falling back to this Concept's declared type."""
        raw = self.read_meta().get("type")
        return str(raw) if raw else self._type

    def tags(self) -> list[str]:
        """Categorical labels from ``meta.json`` (``[]`` when untagged)."""
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

    def body(self) -> str:
        """The human narrative (its ``index.md``)."""
        return self.read_index()

    def set_body(self, text: str) -> None:
        """Set the human narrative (its ``index.md``)."""
        self.write_index(text)

    def links(self) -> LinkScan:
        """Parse ``index.md`` markdown links, classified (see :class:`LinkScan`).

        Targets resolve relative to this Concept's dir; a trailing ``index.md``
        is stripped to its containing dir. An in-tree target counts as a
        knowledge-graph edge when it resolves to an existing dir.
        """
        return self.scan_links(self.read_index())

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
            if self._fs.is_dir(str(concept_dir)):
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
        """In-tree link targets — the knowledge-graph out-edges (path-only)."""
        return self.links().concepts

    def typed_out_edges(self) -> list[Edge]:
        """In-tree out-edges paired with their declared ``EdgeRole``.

        A legacy untyped link defaults to
        :data:`~molab.knowledge.edges.DEFAULT_EDGE_ROLE` — defaulted, never
        dropped.
        """
        return self.links().typed_concepts


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
    rel = os.path.relpath(dst_path, str(src.path))
    rel_posix = PurePosixPath(rel).as_posix()
    label = text if text is not None else PurePosixPath(dst_path).name
    encoded = encode_label(role, label)
    existing = src.read_index()
    prefix = existing if not existing or existing.endswith("\n") else existing + "\n"
    src.write_index(f"{prefix}- [{encoded}]({rel_posix})\n")


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


def read_meta_dict(directory: PathArg, *, fs: FileSystem) -> dict[str, JSONValue] | None:
    """The parsed ``meta.json`` at *directory*, or ``None`` when there is none.

    ``None`` means "not a Concept directory" (no marker file at all); an empty
    or non-mapping marker parses to ``{}``. One read, no probe — the single
    primitive the bundle walk uses to decide concept-ness *and* type together.
    """
    text = read_text_or_none(fs.join(directory, META_JSON_FILENAME), fs=fs)
    return None if text is None else parse_meta_text(text)


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
    if type_str is None:
        type_str = concept_type_of(directory, fs=fs)
    cls = resolve_concept_type(type_str, Concept, base=Concept)
    return cls(directory, type=type_str or None, fs=fs)


__all__ = [
    "FALLBACK_CONCEPT_TYPE",
    "INDEX_FILENAME",
    "META_JSON_FILENAME",
    "OPS_DIR",
    "Concept",
    "LinkScan",
    "append_link",
    "concept_from_dir",
    "concept_type_of",
    "meta_type",
    "parse_meta_text",
    "read_meta_dict",
    "read_text_or_none",
]
