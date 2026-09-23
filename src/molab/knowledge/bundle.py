"""``Bundle`` — the OKF bundle façade over a Concept-directory tree.

A *bundle* is a directory subtree whose Concept dirs (dirs that directly hold
``meta.json``) form a knowledge graph via ``index.md`` markdown links. A
:class:`Bundle` wraps a *bundle root* and exposes the whole subtree — at any
depth — as one management entry point: :meth:`walk` (depth-first Concept
enumeration), :meth:`get` (path-as-identity resolution), :meth:`put`
(idempotent materialization), :meth:`link` (a semantic edge written as a
markdown link, round-tripping through :meth:`Concept.out_edges`), plus a derived
rollup :meth:`build_index` (→ ``index.json`` machine + ``INDEX.md`` human/agent),
queried by :meth:`search` (body-aware retrieval returning :class:`SearchResult`).

**The root is just a directory.** A bundle needs no workspace: a group wiki, a
git repo of protocol notes, or a subtree of a molab workspace all open the same
way. Because a :class:`~molab.knowledge.concept.Concept` is addressed by its
absolute path, mounting one at any depth is arithmetic-free — there is no parent
chain to re-anchor and no container segment to replay.

It is a thin runtime container (explicit ``__init__``, no pydantic): it records
the root path + filesystem and does **no** disk I/O on construction.
"""

from __future__ import annotations

import contextlib
import json
import os
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from pathlib import Path as _StdPath
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, NamedTuple, Protocol, runtime_checkable

from molab._typing import JSONValue
from molab.fs import FileSystem, LocalFileSystem, PathArg
from molab.gitignore import GITIGNORE_FILENAME
from molab.ids import slugify

from .bundle_index import (
    INDEX_JSON_FILENAME,
    INDEX_MD_FILENAME,
    BundleIndex,
    ConceptIndexEntry,
    SearchHit,
    SearchResult,
    extract_title,
)
from .concept import (
    INDEX_FILENAME,
    META_JSON_FILENAME,
    OPS_DIR,
    Concept,
    append_link,
    concept_from_dir,
    meta_type,
    read_meta_dict,
    read_text_or_none,
)
from .concepts import Literature, Note
from .edges import DEFAULT_EDGE_ROLE, EdgeRole
from .errors import ConceptNotFoundError
from .hooks import notify_concept_created
from .knowledge_item import KnowledgeItem
from .reference_meta import ReferenceMeta
from .retrieval import Bm25fCorpus, tokenize
from .types import non_concept_subdirs
from .zotero import read_zotero_items

if TYPE_CHECKING:
    from molab.gitignore import GitIgnoreMatcher

__all__ = ["Backlink", "Bundle", "BundleScan", "ConceptMetaDict", "ConceptPartition"]

#: Body-search size cap — mirrors the agent file-tools read cap so one
#: pathological ``index.md`` cannot stall retrieval.
_MAX_BODY_SEARCH_BYTES = 512 * 1024

REFERENCES_GROUP = "references"
REFERENCES_GROUP_TYPE = "bundle.references"
SOURCES_FILENAME = "sources.json"


class Backlink(NamedTuple):
    """One resolved reverse edge, as returned by :meth:`Bundle.backlinks`.

    A ``NamedTuple`` wrapper — **not** a bare Concept: it pairs the *source*
    Concept whose ``index.md`` holds the link with the edge's declared *role*
    (the inverse of a :meth:`Concept.typed_out_edges` :class:`Edge`). Unpack it
    as ``source, role = backlink`` or read the fields by name.

    Attributes:
        source: The Concept whose ``index.md`` holds the edge pointing at the
            queried target.
        role: The declared :class:`~molab.knowledge.edges.EdgeRole` of that
            edge (``"references"`` for untyped legacy links).
    """

    source: Concept
    role: EdgeRole


@runtime_checkable
class NamesDirectory(Protocol):
    """Anything that names a directory by answering ``resolve()``.

    The structural half of the workspace ``Folder`` contract, declared here so
    the path-only bundle verbs can *say* they accept one without a module-level
    import of the storage family above it (``molab.workspace`` is reachable only
    lazily, from inside a function body). Duck-typing was already the runtime
    behaviour (see :func:`_dir_of`); this makes it checkable.
    """

    def resolve(self) -> object: ...


#: What the path-only verbs address: a Concept, a bare path, or a Folder-like.
DirTarget = Concept | PathArg | NamesDirectory


def _dir_of(target: DirTarget) -> str:
    """The directory *target* addresses, for the path-only bundle verbs.

    Some verbs (:meth:`Bundle.rel_path`, :meth:`Bundle.backlinks`) need nothing
    but a directory, and are legitimately called with a workspace ``Folder`` — a
    different storage family this layer imports only lazily, inside a function
    body. Rather than force callers to unwrap, accept anything that *names* a
    directory: a ``Concept``, a path, or an object exposing ``resolve()`` (the
    ``Folder`` contract).

    A ``str`` / ``PathLike`` is taken as-is **before** the duck-typed branch, so
    a ``pathlib.Path`` is never silently symlink-resolved by its own
    ``resolve()``.
    """
    if isinstance(target, Concept):
        return str(target.path)
    if isinstance(target, (str, os.PathLike)):
        return str(target)
    resolve = getattr(target, "resolve", None)
    if callable(resolve):
        return str(resolve())
    raise TypeError(f"expected a Concept, a path, or a Folder-like object, got {target!r}")


def _utcnow() -> datetime:
    """Return the current time as an aware-UTC ``datetime``."""
    return datetime.now(UTC)


def _is_concept_dir(path: PathArg, fs: FileSystem) -> bool:
    """Return ``True`` iff *path* is a dir that directly holds ``meta.json``.

    One filesystem call: ``is_file`` on the marker answers both halves (a
    marker cannot be a file inside something that is not a directory).
    """
    try:
        return fs.is_file(fs.join(path, META_JSON_FILENAME))
    except OSError:
        # Broken / cycle symlinks or path-too-long entries are not concepts.
        return False


#: A parsed ``meta.json`` as the walk hands it back alongside its Concept.
ConceptMetaDict = dict[str, JSONValue]


class ConceptPartition(NamedTuple):
    """The typed knowledge views of one bundle walk (see :meth:`Bundle.partition`).

    Attributes:
        notes: Every :class:`Note`, in walk (depth-first preorder) order.
        references: Every :class:`Literature`.
        items: Every :class:`KnowledgeItem`.
        metas: Each yielded Concept's parsed ``meta.json``, keyed by
            bundle-relative path — read once during the walk, so a caller
            summarizing tags / status / bib fields need not read it again.
    """

    notes: list[Note]
    references: list[Literature]
    items: list[KnowledgeItem]
    metas: dict[str, ConceptMetaDict]


class BundleScan(NamedTuple):
    """Everything one bundle walk can produce (see :meth:`Bundle.scan_all`).

    Attributes:
        index: The derived :class:`~molab.knowledge.bundle_index.BundleIndex`.
        bodies: Each Concept's ``index.md`` text, keyed by bundle-relative path.
        metas: Each Concept's parsed ``meta.json``, keyed the same way.
        notes / references / items: The typed views, in walk order.
    """

    index: BundleIndex
    bodies: dict[str, str]
    metas: dict[str, ConceptMetaDict]
    notes: list[Note]
    references: list[Literature]
    items: list[KnowledgeItem]


class Bundle:
    """A management façade over an OKF bundle (a Concept-directory tree)."""

    def __init__(
        self,
        root: PathArg,
        *,
        fs: FileSystem | None = None,
        prune_dirs: frozenset[str] = frozenset(),
    ) -> None:
        """Record the bundle *root* + filesystem; perform no disk I/O (lazy).

        Args:
            root: The bundle root directory. Any directory will do — a workspace
                root, a group wiki, a git repo of notes.
            fs: The filesystem backing this bundle's I/O (default: local).
            prune_dirs: Directory *names* the walk never descends into, at any
                depth, regardless of position (the ``_ops/`` sidecar is always
                pruned). Use this only for names that can never hold a Concept
                *anywhere* in the tree; a layout-specific subtree belongs on
                the owning Concept type's ``NON_CONCEPT_SUBDIRS`` instead (see
                :func:`~molab.knowledge.types.non_concept_subdirs`), which
                scopes the skip to that type's own children. The OKF library
                itself prunes nothing beyond ``_ops``: it does not know what a
                directory means.
        """
        self._root = _StdPath(os.fspath(root))
        self._fs: FileSystem = fs if fs is not None else LocalFileSystem()
        self._prune_dirs: frozenset[str] = frozenset(prune_dirs) | {OPS_DIR}
        # Built lazily on first walk — keeps construction free of I/O.
        self._ignore: GitIgnoreMatcher | None = None

    @property
    def prune_dirs(self) -> frozenset[str]:
        """Directory names :meth:`walk` never descends into (always incl. ``_ops``)."""
        return self._prune_dirs

    @property
    def root(self) -> _StdPath:
        """The bundle root directory."""
        return self._root

    @property
    def fs(self) -> FileSystem:
        """The filesystem backing this bundle's I/O."""
        return self._fs

    # ── identity helpers ─────────────────────────────────────────────────

    def rel_path(self, concept: DirTarget) -> str:
        """Return *concept*'s identity: its POSIX path relative to the root.

        Accepts anything that names a directory (see :func:`_dir_of`), so a
        caller holding a workspace ``Folder`` need not unwrap it first.
        """
        return _StdPath(_dir_of(concept)).relative_to(self._root).as_posix()

    @staticmethod
    def _norm(path: PathArg) -> str:
        """Normalize *path* to a canonical POSIX string for identity comparison."""
        return str(PurePosixPath(os.path.normpath(str(path))))

    def _concept_at(self, directory: PathArg, *, type_str: str | None = None) -> Concept:
        """The typed Concept whose identity is the directory *directory*.

        One line, because path is identity: there is no ancestor to reconstruct,
        no thin parent to pin, and no container segment to un-double. A caller
        that has already parsed the marker passes *type_str* so ``meta.json``
        is not read a second time.
        """
        return concept_from_dir(directory, fs=self._fs, type_str=type_str)

    def _emit_created(self, concept: Concept, *, title: str) -> None:
        """Best-effort ``knowledge.created`` notification through the host hook.

        Emitted only for NEWLY materialized Concepts (the create verbs are
        idempotent — a repeat call is not a creation). Routed through
        :mod:`molab.knowledge.hooks` so a workspace can put it on its event
        spine while a standalone wiki simply has no observer.
        """
        notify_concept_created(root=self._root, concept=concept, title=title)

    # ── walk / get / put / link ──────────────────────────────────────────

    def _ignore_matcher(self) -> GitIgnoreMatcher:
        """Lazy :class:`~molab.gitignore.GitIgnoreMatcher` for this root."""
        if self._ignore is None:
            from molab.gitignore import load_gitignore_matcher

            self._ignore = load_gitignore_matcher(self._root, fs=self._fs)
        return self._ignore

    def walk(self) -> Iterator[Concept]:
        """Yield every Concept under the root, depth-first (preorder).

        A dir is yielded iff it holds ``meta.json``. The ``_ops/`` sidecar (and
        everything beneath it) is skipped, as is every :attr:`prune_dirs` name;
        paths matching the ``.gitignore`` cascade (plus a safety-floor denylist
        for ``node_modules`` / ``.git`` / venvs) are skipped entirely; symlink
        cycles are cut by tracking resolved paths. Non-Concept organizational
        dirs are descended into but not yielded; loose files are inherently
        skipped.
        """
        for concept, _meta in self.walk_with_meta():
            yield concept

    def walk_with_meta(self) -> Iterator[tuple[Concept, ConceptMetaDict]]:
        """:meth:`walk`, handing back each Concept's parsed ``meta.json`` too.

        The walk has to read the marker to know a directory *is* a Concept and
        which class it is; returning what it read means an indexer, a lister
        or a context assembler never reads the same small file a second time.
        """
        root = str(self._root)
        yield from self._walk_dir(root, parent_type=self._type_at(root))

    def _type_at(self, directory: str) -> str | None:
        """The Concept ``type`` of *directory*, or ``None`` if it has no marker."""
        try:
            meta = read_meta_dict(directory, fs=self._fs)
        except OSError:
            return None
        return meta_type(meta) if meta is not None else None

    def _walk_dir(
        self,
        directory: str,
        *,
        parent_type: str | None = None,
        _visited: set[str] | None = None,
        _real: str | None = None,
        _root_resolved: str | None = None,
        _ignore: GitIgnoreMatcher | None = None,
    ) -> Iterator[tuple[Concept, ConceptMetaDict]]:
        """One ``scandir`` per directory; children's types come from the listing.

        The per-entry ``is_dir`` probe is gone — ``scandir`` reports each
        child's type in the same pass that names it. So is the per-entry
        ``resolve``: a child that is not a symlink sits at ``<parent real
        path>/<name>`` by construction, so only a symlink (the sole way a
        child's real path can diverge, and the only cycle risk) still pays one.
        ``_real`` / ``_root_resolved`` / ``_ignore`` are threaded down rather
        than recomputed per level for the same reason.
        """
        visited = _visited if _visited is not None else set()
        ignore = _ignore if _ignore is not None else self._ignore_matcher()
        if _root_resolved is None:
            try:
                _root_resolved = self._fs.resolve(str(self._root))
            except OSError:
                return
        root_resolved = _root_resolved
        if _real is None:
            try:
                _real = self._fs.resolve(directory)
            except OSError:
                return
        real = _real
        if real in visited:
            return
        visited.add(real)

        try:
            entries = self._fs.scandir(directory, with_stat=False)
        except (OSError, ValueError):
            # Not a directory, vanished, or unreadable — nothing to walk.
            return

        # The listing just answered "does this directory have a .gitignore?",
        # so the matcher never has to probe for one.
        if not any(e.name == GITIGNORE_FILENAME for e in entries):
            with contextlib.suppress(ValueError):  # outside root: nothing to mark
                ignore.mark_absent(_StdPath(real).relative_to(root_resolved).as_posix())

        # Position-aware pruning: the parent's own type decides which of ITS
        # children are job output. A bare name is never enough — a directory
        # called ``logs`` is a run's output under a run, and may be somebody's
        # Note anywhere else.
        pruned = self._prune_dirs | non_concept_subdirs(parent_type)

        for entry in sorted(entries, key=lambda e: e.name):
            name = entry.name
            if name in pruned or not entry.is_dir:
                continue
            child = self._fs.join(directory, name)
            if entry.is_symlink:
                # Only a symlink can point somewhere other than <real>/<name>,
                # so only a symlink needs the syscall that detects cycles.
                try:
                    entry_real = self._fs.resolve(child)
                except OSError:
                    continue
            else:
                entry_real = self._fs.join(real, name)
            # Root-relative path for gitignore matching.
            try:
                rel_s = _StdPath(entry_real).relative_to(root_resolved).as_posix()
            except ValueError:
                # Outside root (symlink escape) — skip rather than walk forever.
                continue
            if ignore.is_ignored(rel_s, is_dir=True):
                continue
            # One read decides concept-ness AND type: a missing marker is the
            # negative answer, never a separate ``exists`` probe.
            try:
                meta = read_meta_dict(child, fs=self._fs)
            except OSError:
                meta = None
            child_type = meta_type(meta) if meta is not None else None
            if meta is not None:
                yield self._concept_at(child, type_str=child_type), meta
            yield from self._walk_dir(
                child,
                parent_type=child_type,
                _visited=visited,
                _real=entry_real,
                _root_resolved=root_resolved,
                _ignore=ignore,
            )

    def get(self, rel_path: PathArg) -> Concept:
        """Resolve a bundle-relative path to its typed :class:`Concept`.

        Args:
            rel_path: A bundle-relative POSIX path (the Concept's identity).

        Returns:
            The typed :class:`Concept` at *rel_path*.

        Raises:
            ConceptNotFoundError: if *rel_path* is not a Concept dir.
        """
        rel = PurePosixPath(os.fspath(rel_path))
        target = self._fs.join(str(self._root), *rel.parts)
        try:
            meta = read_meta_dict(target, fs=self._fs)
        except OSError:
            meta = None
        if meta is None:
            raise ConceptNotFoundError(str(rel_path))
        return self._concept_at(target, type_str=meta_type(meta))

    def put(self, concept: Concept) -> Concept:
        """Idempotently materialize *concept* (write ``meta.json`` if absent).

        Args:
            concept: The Concept to materialize.

        Returns:
            The same *concept* (now backed by a ``meta.json`` on disk).
        """
        if not _is_concept_dir(concept.path, self._fs):
            concept.write_meta()
        return concept

    def link(
        self,
        src: Concept,
        dst: Concept | PathArg,
        *,
        text: str | None = None,
        role: EdgeRole = DEFAULT_EDGE_ROLE,
    ) -> None:
        """Record a typed semantic edge ``src → dst`` as a markdown link in *src*.

        Appends a real markdown link (relative to *src*) to ``src/index.md`` so
        :meth:`Concept.out_edges` resolves it back to *dst* and
        :meth:`Concept.typed_out_edges` recovers *role*. The graph lives in
        markdown, never in ``meta.json``. A thin delegator over the single
        :func:`~molab.knowledge.concept.append_link` writer.

        Args:
            src: The Concept the edge originates from.
            dst: The edge target — a Concept, a path, or a workspace ``Folder``
                (only its directory is used).
            text: Optional link label; defaults to *dst*'s directory name.
            role: The declared :class:`~molab.knowledge.edges.EdgeRole`.
        """
        # Coerce at the bundle boundary: a Bundle may be handed a foreign-family
        # target (a workspace Folder), but ``append_link`` stays strict.
        append_link(src, _dir_of(dst), text=text, role=role)

    # ── document CRUD verbs ──────────────────────────────────────────────
    #
    # The shared document surface: CLI and server both call these same ``Bundle``
    # verbs, so the CRUD logic lives in one place and is never re-implemented at
    # the HTTP boundary (the Python==UI invariant).

    def _child_dir(self, name: str, parent: Concept | PathArg | None) -> _StdPath:
        """Absolute dir for a child document *name* under *parent* (root if None).

        *parent* goes through :func:`_dir_of`, so a workspace ``Folder`` is
        resolved to its directory rather than stringified into a name — the
        difference between mounting a note under an experiment and creating a
        directory called ``<molab.workspace.experiment.Experiment object …>``.

        A *parent* that is a **file document** (a ``FILE_DOCUMENT`` Concept, whose
        path is a ``.md`` file) contributes its own directory: a file has no
        interior, so nesting under a document nests beside it.
        """
        if parent is None:
            base = str(self._root)
        elif isinstance(parent, Concept) and type(parent).FILE_DOCUMENT:
            base = self._fs.dirname(str(parent.path))
        else:
            base = _dir_of(parent)
        return _StdPath(self._fs.join(base, name))

    def create_note(
        self,
        name: str,
        *,
        parent: Concept | PathArg | None = None,
        body: str = "",
    ) -> Note:
        """Idempotently create (or fetch) a :class:`Note` document.

        *name* is slugified to the document's filename (path is identity). With
        *parent* ``None`` the note mounts at the bundle root; otherwise it mounts
        under *parent*, which may be a Concept or a bare directory path — so a
        note nests under another note, or under a workspace ``Experiment``, by
        the same call. Repeat calls on the same slug return the existing Concept
        — no duplicate document.

        A :class:`Note` is a ``FILE_DOCUMENT``: it lands as a single markdown
        file (``<dir>/<slug>.md``) carrying its head as frontmatter, so this verb
        never writes a ``meta.json`` — writing one would mean ``mkdir``-ing a
        *directory* at the document's own ``.md`` path.

        Args:
            name: Human name; slugified to the document's filename.
            parent: Concept or directory to nest under; ``None`` for the root.
            body: Initial narrative. Written on the creating call; a repeat call
                never truncates an existing body.

        Returns:
            The mounted :class:`Note` (the existing one on a repeat call).
        """
        slug = slugify(name) or name
        note = Note(self._child_dir(slug, parent), fs=self._fs)
        created = not note.exists()
        if body or created:
            note.write(body)
        if created:
            self._emit_created(note, title=name)
        return note

    def rename_note(self, concept: Concept, new_name: str) -> None:
        """Rename *concept* in place (same parent dir), preserving body + children.

        One move, so the whole document travels as one and the Concept resolves
        at its new identity path. A file document keeps its ``.md`` suffix (the
        suffix is how the layout marks a document, not part of the name).

        Args:
            concept: The Concept to rename.
            new_name: The new human name; slugified to the new document name.

        Raises:
            FileExistsError: If the destination already exists.
        """
        slug = slugify(new_name) or new_name
        if type(concept).FILE_DOCUMENT:
            slug = f"{slug}{_StdPath(concept.path).suffix}"
        dst = _StdPath(self._fs.join(self._fs.dirname(str(concept.path)), slug))
        self._move_dir(concept.path, dst)

    def move_note(self, concept: Concept, new_parent: Concept | PathArg) -> None:
        """Move *concept* under *new_parent*, preserving body + child docs.

        Existing relative links inside the moved document travel verbatim (they
        are not rewritten) — a derived :meth:`backlinks` recompute reflects the
        Concept's new identity. A file document keeps its ``.md`` suffix.

        Args:
            concept: The Concept to move.
            new_parent: The Concept, or directory, to mount it under.

        Raises:
            FileExistsError: If the destination already exists.
        """
        name = concept.name
        if type(concept).FILE_DOCUMENT:
            name = f"{name}{_StdPath(concept.path).suffix}"
        self._move_dir(concept.path, self._child_dir(name, new_parent))

    def _move_dir(self, src: PathArg, dst: PathArg) -> None:
        """Move a Concept directory, refusing to clobber an existing one."""
        if self._norm(src) == self._norm(dst):
            return
        if self._fs.exists(str(dst)):
            raise FileExistsError(f"cannot move {str(src)!r} to {str(dst)!r}: destination exists")
        self._fs.mkdir(self._fs.dirname(str(dst)), parents=True, exist_ok=True)
        self._fs.rename(str(src), str(dst))

    def delete_note(self, concept: Concept) -> None:
        """Delete *concept* — remove its directory subtree.

        After deletion :meth:`walk` no longer yields the Concept.

        Args:
            concept: The Concept to delete.
        """
        self._fs.remove(str(concept.path), recursive=True)

    def backlinks(self, concept: DirTarget) -> list[Backlink]:
        """Return the :class:`Backlink` rows whose edge points at *concept*.

        Each result is a ``Backlink(source, role)`` wrapper — not the bare
        source Concept: ``source`` is the Concept whose ``index.md`` holds the
        edge, ``role`` its declared :class:`~molab.knowledge.edges.EdgeRole`
        (the default ``references`` role is included, never dropped). Computed
        by walking the bundle and reading each Concept's
        :meth:`Concept.typed_out_edges` — a rebuildable derived view; no reverse
        index is persisted (one-source-of-truth law).

        Args:
            concept: The link target to find backlinks for — a Concept, a path,
                or a workspace ``Folder`` (only its directory is used).

        Returns:
            One :class:`Backlink` per edge resolving to *concept*.
        """
        target = self._norm(_dir_of(concept))
        result: list[Backlink] = []
        for source in self.walk():
            if self._norm(source.path) == target:
                continue  # a self-edge is not a backlink
            for edge in source.links():
                if self._norm(edge.target) == target:
                    result.append(Backlink(source=source, role=edge.role))
        return result

    def export_markdown(self, concept: Concept, *, include_children: bool = True) -> str:
        """Return *concept*'s ``index.md`` as portable Markdown (optionally folding children).

        With *include_children* the descendant :class:`Note` bodies are appended
        depth-first in document order, each under a ``## <bundle-relative-path>``
        header. Read-only — writes nothing.

        Args:
            concept: The Concept whose Markdown to export.
            include_children: Fold descendant ``Note`` bodies in (default ``True``).

        Returns:
            A single portable Markdown string.
        """
        parts = [concept.read_index()]
        if include_children:
            root = str(concept.path)
            for descendant, _meta in self._walk_dir(root, parent_type=self._type_at(root)):
                if isinstance(descendant, Note):
                    parts.append(f"\n\n## {self.rel_path(descendant)}\n\n{descendant.read_index()}")
        return "".join(parts)

    # ── typed filtered views + Zotero import ─────────────────────────────

    def partition(self) -> ConceptPartition:
        """Every knowledge Concept, split by kind, from **one** walk.

        The typed views (:meth:`notes` / :meth:`references` / :meth:`items`)
        each answer one question; a caller that needs two of them — the
        knowledge list endpoint wants notes *and* references — pays one walk
        here instead of one per view, and gets each Concept's already-parsed
        ``meta.json`` alongside (see :class:`ConceptPartition`).
        """
        notes: list[Note] = []
        references: list[Literature] = []
        items: list[KnowledgeItem] = []
        metas: dict[str, ConceptMetaDict] = {}
        for concept, meta in self.walk_with_meta():
            if isinstance(concept, Note):
                notes.append(concept)
            elif isinstance(concept, Literature):
                references.append(concept)
            elif isinstance(concept, KnowledgeItem):
                items.append(concept)
            else:
                continue
            metas[self.rel_path(concept)] = meta
        return ConceptPartition(notes=notes, references=references, items=items, metas=metas)

    def scan_all(self, *, now: datetime | None = None) -> BundleScan:
        """The index, bodies, metas **and** typed partition — from one walk.

        :meth:`scan_index` and :meth:`partition` each walk the tree; a host
        that wants both (a server read model caching one scan to answer list
        *and* search requests) would otherwise pay two. This yields everything
        in a single pass and writes nothing.

        Args:
            now: Index timestamp; defaults to aware-UTC ``datetime.now``.

        Returns:
            A :class:`BundleScan`.
        """
        entries: list[ConceptIndexEntry] = []
        bodies: dict[str, str] = {}
        metas: dict[str, ConceptMetaDict] = {}
        notes: list[Note] = []
        references: list[Literature] = []
        items: list[KnowledgeItem] = []
        for concept, meta in self.walk_with_meta():
            entry, body = self._entry_and_body(concept, meta=meta)
            entries.append(entry)
            bodies[entry.path] = body
            metas[entry.path] = meta
            if isinstance(concept, Note):
                notes.append(concept)
            elif isinstance(concept, Literature):
                references.append(concept)
            elif isinstance(concept, KnowledgeItem):
                items.append(concept)
        return BundleScan(
            index=BundleIndex(generated_at=now or _utcnow(), entries=tuple(entries)),
            bodies=bodies,
            metas=metas,
            notes=notes,
            references=references,
            items=items,
        )

    def concepts_by_type(self) -> dict[str, list[Concept]]:
        """Every Concept grouped by its ``meta.json`` ``type`` string — one walk.

        The untyped companion of :meth:`partition`: entity folders
        (``workspace.run`` …) and foreign markers are included, keyed exactly as
        declared on disk (``""`` for a marker without a ``type``).
        """
        grouped: dict[str, list[Concept]] = {}
        for concept, meta in self.walk_with_meta():
            grouped.setdefault(meta_type(meta), []).append(concept)
        return grouped

    def references(self) -> list[Literature]:
        """Every OKF ``Reference`` Concept in the bundle (typed view of walk)."""
        return self.partition().references

    def notes(self) -> list[Note]:
        """Every OKF ``Note`` Concept in the bundle (typed view of walk)."""
        return self.partition().notes

    def items(self) -> list[KnowledgeItem]:
        """Every OKF ``KnowledgeItem`` Concept in the bundle (typed view of walk)."""
        return self.partition().items

    def import_zotero(
        self,
        path: PathArg,
        *,
        under: Concept | PathArg | None = None,
        now: datetime | None = None,
    ) -> list[Literature]:
        """Link a local Zotero library (read-only) as ``Reference`` Concepts.

        Each Zotero item becomes a :class:`Literature` under *under*
        (default: a ``references/`` group at the bundle root); its PDF is
        *pointed at* via ``ReferenceMeta.pdf_path`` — no bytes are copied.
        Idempotent on ``source_key``: re-importing an item updates its
        ``meta.json`` in place (the slugified Zotero key is the dir name)
        rather than duplicating it. Records the link in ``sources.json``.

        Args:
            path: The ``zotero.sqlite`` to read (opened read-only).
            under: The Concept or directory to mount references beneath
                (default: a ``references/`` group at the bundle root).
            now: Import timestamp; defaults to aware-UTC ``datetime.now``.

        Returns:
            The :class:`Literature` records created or updated.
        """
        host = under if under is not None else self._references_group()
        items = read_zotero_items(path)
        refs: list[Literature] = []
        for item in items:
            slug = slugify(item.key) or item.key
            directory = self._child_dir(slug, host)
            created = not _is_concept_dir(directory, self._fs)
            ref = Literature(directory, fs=self._fs)
            ref.write(
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
            if created:
                # After write — the document is bib-complete when the event lands.
                self._emit_created(ref, title=item.title or slug)
            refs.append(ref)
        self._record_source("zotero", str(path), len(items), now=now)
        return refs

    def _references_group(self) -> Concept:
        """Materialize (idempotently) the default ``references/`` host Concept."""
        group = Concept(
            self._fs.join(str(self._root), REFERENCES_GROUP),
            type=REFERENCES_GROUP_TYPE,
            fs=self._fs,
        )
        if not self._fs.is_dir(str(group.path)):
            group.write_meta()
        return group

    def _record_source(self, source: str, path: str, count: int, *, now: datetime | None) -> None:
        """Append (dedup on source+path) a linked-source row into ``sources.json``."""
        sources_path = self._fs.join(str(self._root), SOURCES_FILENAME)
        existing: list[dict[str, object]] = []
        if self._fs.is_file(sources_path):
            raw = json.loads(self._fs.read_text(sources_path))
            if isinstance(raw, list):
                existing = [e for e in raw if isinstance(e, dict)]
        existing = [
            e for e in existing if not (e.get("source") == source and e.get("path") == path)
        ]
        existing.append(
            {
                "source": source,
                "path": path,
                "count": count,
                "imported_at": (now or _utcnow()).isoformat(),
            }
        )
        self._fs.atomic_write_json(sources_path, existing)

    # ── derived index + search ───────────────────────────────────────────

    def _entry_and_body(
        self, concept: Concept, *, meta: ConceptMetaDict | None = None
    ) -> tuple[ConceptIndexEntry, str]:
        """Build *concept*'s index row and return the body it was read from.

        Indexing already reads every ``index.md`` (the title is its H1), and
        ranking needs the same text. Returning it means one read per Concept per
        query instead of two — the body never crosses the filesystem twice. The
        same goes for *meta*: the walk that found the Concept has already parsed
        its marker, so it is passed in rather than read again.
        """
        if meta is None:
            meta = concept.read_meta()
        raw_type = meta.get("type")
        raw_id = meta.get("id")
        raw_tags = meta.get("tags")
        body = concept.read_index()
        links = tuple(
            _StdPath(str(target)).relative_to(self._root).as_posix()
            for target in concept.scan_links(body).concepts
        )
        tags = tuple(str(t) for t in raw_tags) if isinstance(raw_tags, list) else ()
        entry = ConceptIndexEntry(
            path=self.rel_path(concept),
            type=str(raw_type) if raw_type is not None else "",
            id=str(raw_id) if raw_id is not None else None,
            title=extract_title(body) or concept.name,
            tags=tags,
            links=links,
        )
        return entry, body

    def _entry_for(self, concept: Concept) -> ConceptIndexEntry:
        """Just the index row for *concept* (see :meth:`_entry_and_body`)."""
        return self._entry_and_body(concept)[0]

    def scan_index(
        self, *, now: datetime | None = None
    ) -> tuple[BundleIndex, dict[str, str], dict[str, ConceptMetaDict]]:
        """Walk the bundle into an in-memory :class:`BundleIndex` — **no writes**.

        The read half of :meth:`build_index`: every Concept becomes one
        :class:`ConceptIndexEntry`, and the ``index.md`` bodies and parsed
        ``meta.json`` heads read along the way come back with it (keyed by
        bundle-relative path) so a ranker or lister never re-reads them. A
        query is a read; only the explicit :meth:`build_index` verb touches
        the disk.

        Args:
            now: Index timestamp; defaults to aware-UTC ``datetime.now``.

        Returns:
            ``(index, bodies, metas)``.
        """
        rows: list[tuple[ConceptIndexEntry, str, ConceptMetaDict]] = [
            (*self._entry_and_body(concept, meta=meta), meta)
            for concept, meta in self.walk_with_meta()
        ]
        index = BundleIndex(
            generated_at=now or _utcnow(),
            entries=tuple(entry for entry, _body, _meta in rows),
        )
        return (
            index,
            {entry.path: body for entry, body, _meta in rows},
            {entry.path: meta for entry, _body, meta in rows},
        )

    def build_index(self, *, now: datetime | None = None) -> BundleIndex:
        """Rebuild the derived bundle index and write its two sibling files.

        Walks every Concept, rolls its identity into a :class:`BundleIndex`, and
        atomically writes ``index.json`` (machine) + ``INDEX.md`` (human/agent)
        at the bundle root. Always a fresh, full rebuild — never authoritative
        (``meta.json`` + ``index.md`` remain the source of truth). This is the
        **only** bundle verb that writes those files; :meth:`search` never does.

        Args:
            now: Build timestamp; defaults to aware-UTC ``datetime.now``.

        Returns:
            The freshly built :class:`BundleIndex`.
        """
        index, _bodies, _metas = self.scan_index(now=now)
        self._fs.atomic_write_json(
            self._fs.join(str(self._root), INDEX_JSON_FILENAME),
            index.model_dump(mode="json"),
        )
        self._fs.atomic_write_text(
            self._fs.join(str(self._root), INDEX_MD_FILENAME),
            index.to_markdown(),
        )
        return index

    def _load_index(self) -> tuple[BundleIndex, dict[str, str]]:
        """The last written ``index.json``, or a fresh in-memory scan if absent.

        A read path: when no index has been built yet this scans instead of
        writing one — a query never leaves derived files behind.
        """
        text = read_text_or_none(self._fs.join(str(self._root), INDEX_JSON_FILENAME), fs=self._fs)
        if text is None:
            index, bodies, _metas = self.scan_index()
            return index, bodies
        return BundleIndex.model_validate(json.loads(text)), {}

    def search(
        self,
        text: str | None = None,
        *,
        concept_type: str | None = None,
        tag: str | None = None,
        scope: str | None = None,
        limit: int = 50,
        include_body: bool = True,
        rebuild: bool = True,
        index: BundleIndex | None = None,
        bodies: Mapping[str, str] | None = None,
        corpus: Bm25fCorpus | None = None,
    ) -> SearchResult:
        """Keyword retrieval over the Concept tree — BM25F-ranked.

        *text* is tokenized and scored against every Concept's title, tags,
        path and — when *include_body* — its ``index.md`` body (see
        :mod:`molab.knowledge.retrieval`). Because matching is by term rather
        than substring, a natural-language question finds the document that
        answers it even when no phrase is shared, and CJK works without a
        segmenter. Filters (*concept_type* / *tag* / *scope*) are AND semantics
        and narrow the **ranked** list: term weights (IDF) are always those of
        the whole bundle, so one ranking corpus serves every filter and a
        document's score does not change with the filter it was found under.

        Hits come back **score-descending**, ties broken by path ascending. A
        filter-only query (*text* ``None`` or empty) is not ranked at all and
        keeps path-ascending index order, with ``score == 0.0``.

        A body larger than ``_MAX_BODY_SEARCH_BYTES`` (or undecodable) is
        skipped for body matching, but the entry still ranks on its index
        fields. **A search never writes** — the index is scanned in memory;
        only :meth:`build_index` persists it.

        Args:
            text: The query; ``None`` **or empty** means filter-only.
            concept_type: Exact ``type`` to match.
            tag: A tag that must be present on the Concept.
            scope: Bundle-relative path prefix — restricts hits to that subtree.
            limit: Maximum hits returned; a cut result reports
                ``truncated=True`` (never a silent cap).
            include_body: ``False`` skips all body I/O, ranking on the index
                fields alone.
            rebuild: Rescan the tree first (default); otherwise reuse the last
                written ``index.json`` (scanned in memory if absent).
            index: A prebuilt index to rank against — supply it (with *bodies*
                and ideally *corpus*) and the query does **no I/O at all**.
                This is how a host that caches one scan, such as the server's
                read model, answers many queries per walk instead of one.
            bodies: ``index.md`` text per bundle-relative path, as returned
                beside *index* by :meth:`scan_index`.
            corpus: A :class:`~molab.knowledge.retrieval.Bm25fCorpus` already
                built over *index* + *bodies* (see :meth:`ranking_corpus`), so
                the tokenization is not redone per query.

        Returns:
            A :class:`SearchResult` of :class:`SearchHit` rows.
        """
        if index is not None:
            read_bodies = dict(bodies or {})
        elif rebuild:
            index, read_bodies, _metas = self.scan_index()
        else:
            index, read_bodies = self._load_index()
        if not text:
            # Filter-only: nothing to rank, so keep deterministic index order.
            candidates = [
                entry
                for entry in index.entries
                if self._passes_filters(entry, concept_type=concept_type, tag=tag, scope=scope)
            ]
            hits = tuple(SearchHit(entry=entry) for entry in candidates[:limit])
            return SearchResult(hits=hits, truncated=len(candidates) > limit)

        ranking_bodies = {
            entry.path: (self._ranking_body(entry.path, read_bodies) if include_body else "")
            for entry in index.entries
        }
        if corpus is None:
            corpus = self.ranking_corpus(index, ranking_bodies)
        return self._rank(
            corpus,
            index,
            ranking_bodies,
            text,
            concept_type=concept_type,
            tag=tag,
            scope=scope,
            limit=limit,
        )

    @staticmethod
    def ranking_corpus(index: BundleIndex, bodies: Mapping[str, str]) -> Bm25fCorpus:
        """The BM25F corpus over the **whole** *index* (bodies keyed by path).

        Public so a host that caches the scan (a server read model) can keep
        the tokenized corpus alongside it and answer many queries from one
        walk; :meth:`search` builds it per call.
        """
        documents = {
            entry.path: {
                "title": entry.title,
                "tags": list(entry.tags),
                "path": entry.path.replace("/", " "),
                "body": bodies.get(entry.path, ""),
            }
            for entry in index.entries
        }
        return Bm25fCorpus(documents)

    def _rank(
        self,
        corpus: Bm25fCorpus,
        index: BundleIndex,
        bodies: Mapping[str, str],
        text: str,
        *,
        concept_type: str | None,
        tag: str | None,
        scope: str | None,
        limit: int,
    ) -> SearchResult:
        """Rank *text* over *corpus*, then narrow by the filters (see :meth:`search`)."""
        by_path = {entry.path: entry for entry in index.entries}
        ranked = [
            doc
            for doc in corpus.rank(text)
            if self._passes_filters(
                by_path[doc.key], concept_type=concept_type, tag=tag, scope=scope
            )
        ]
        hits = tuple(
            SearchHit(
                entry=by_path[doc.key],
                snippet=(
                    self._best_body_line(bodies.get(doc.key, ""), text)
                    if "body" in doc.matched_fields
                    else None
                ),
                # Report the caller-facing field names ("tag", not "tags").
                matched_fields=tuple("tag" if f == "tags" else f for f in doc.matched_fields),
                score=doc.score,
            )
            for doc in ranked[:limit]
        )
        return SearchResult(hits=hits, truncated=len(ranked) > limit)

    @staticmethod
    def _passes_filters(
        entry: ConceptIndexEntry,
        *,
        concept_type: str | None,
        tag: str | None,
        scope: str | None,
    ) -> bool:
        """Whether *entry* survives the pre-ranking filters (AND semantics)."""
        if concept_type is not None and entry.type != concept_type:
            return False
        if tag is not None and tag not in entry.tags:
            return False
        if scope is not None:
            prefix = scope.rstrip("/")
            if entry.path != prefix and not entry.path.startswith(prefix + "/"):
                return False
        return True

    def _ranking_body(self, entry_path: str, already_read: dict[str, str]) -> str:
        """The body to rank *entry_path* on, honouring the size cap.

        Indexing has usually just read this file, so prefer that copy over a
        second trip to disk. The cap still applies to it: it exists so one
        pathological ``index.md`` cannot stall retrieval, and that is just as
        true when the bytes are already in hand.
        """
        cached = already_read.get(entry_path)
        if cached is None:
            return self._read_body(entry_path)
        return "" if len(cached.encode("utf-8")) > _MAX_BODY_SEARCH_BYTES else cached

    def _read_body(self, entry_path: str) -> str:
        """Read a Concept's ``index.md`` for ranking, or ``""`` if unreadable.

        Size-capped at ``_MAX_BODY_SEARCH_BYTES``; an absent, oversized or
        undecodable body never raises — it just cannot contribute body terms.
        """
        body_path = self._fs.join(str(self._root), entry_path, INDEX_FILENAME)
        try:
            # stat BEFORE read: the cap must prevent the transfer (one round
            # trip on a remote filesystem), not merely discard it afterwards.
            st = self._fs.stat(body_path)
            if not st.is_file or st.size > _MAX_BODY_SEARCH_BYTES:
                return ""
            return self._fs.read_text(body_path)
        except (OSError, UnicodeDecodeError, ValueError):
            return ""

    @staticmethod
    def _best_body_line(body: str, query: str) -> str | None:
        """The body line sharing the most query terms, trimmed to ≤160 chars.

        Ranking picked the document; this picks the line to show for it. Scoring
        lines by shared terms (rather than taking the first that matches
        anything) means the snippet lands on the passage that earned the hit —
        for "升降温怎么选择" that is the cooling-rate paragraph, not the title.
        """
        wanted = set(tokenize(query))
        if not wanted:
            return None
        best: tuple[int, str] | None = None
        for line in body.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            overlap = len(wanted & set(tokenize(stripped)))
            if overlap and (best is None or overlap > best[0]):
                best = (overlap, stripped)
        return best[1][:160] if best is not None else None
