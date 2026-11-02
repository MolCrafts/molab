"""Unified folder abstraction for workspace storage.

Introduces ``Folder``: a plain Python class providing the contract every
directory under a workspace satisfies — lazy mkdir, atomic JSON, id /
name / kind validation, parent pointer, generic five-verb CRUD
(``add_folder`` / ``get_folder`` / ``has_folder`` / ``list_folders`` /
``remove_folder``), the directory tree as the only child index, lifecycle
metadata, and delete / move operations.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path as _StdPath
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, ClassVar, Literal, TypeVar, cast, overload

from molab._typing import JSONValue
from molab.path import Path

from .base import _reconstruct
from .entity_record import (
    INDEX_FILENAME,
    RESERVED_INDEX_KEYS,
    EntityRecord,
    UnmigratedLayoutError,
    read_body,
    read_record,
    read_type,
    update_record,
    write_record,
)
from .errors import FolderMoveCollisionError
from .fs import DirEntry, FileSystem, PathArg
from .fs_local import LocalFS
from .models import FolderMetadata
from .naming import SCRATCH_CONTAINER
from .utils import slugify

if TYPE_CHECKING:
    from .file_store import FileStore

F = TypeVar("F", bound="Folder")

WORKSPACE_ROOT_KIND = "workspace.root"
WORKSPACE_PROJECT_KIND = "workspace.project"
WORKSPACE_EXPERIMENT_KIND = "workspace.experiment"
WORKSPACE_RUN_KIND = "workspace.run"

_KIND_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*(?:\.[a-z0-9][a-z0-9_-]*)*$")

_FORBIDDEN_FILE_NAMES = {".", ".."}
_CAMEL_TO_SNAKE = re.compile(r"(?<!^)(?=[A-Z])")

# ── OKF: one index.md per Folder (D88) ────────────────────────────────────────
# Every Folder keeps its record in the YAML frontmatter of its own ``index.md``
# (``type`` → class registry), a derived ``index:`` block that nests the next
# level (D89), and the narrative as the body. ``entity_record`` owns the file;
# ``INDEX_FILENAME`` is re-exported from there.

#: A section key another layer may ask the owner to write under ``index:``.
_SECTION_KEY = re.compile(r"^[a-z][a-z0-9_]*$")


def _parse_iso_datetime(raw: object, *, default: datetime) -> datetime:
    if isinstance(raw, datetime):
        return raw
    if isinstance(raw, str) and raw:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return default
    return default


def _folder_metadata_from_marker(
    child_dir: PathArg,
    marker: Mapping[str, object],
) -> FolderMetadata:
    """Build in-memory :class:`FolderMetadata` from a generic record + dir name.

    Path basename is identity — a record ``id`` is ignored when present (legacy).
    """
    slug = PurePosixPath(str(child_dir)).name
    kind = str(marker.get("type") or "").strip() or "concept"
    now = datetime.now(UTC)
    created = _parse_iso_datetime(marker.get("created_at"), default=now)
    updated = _parse_iso_datetime(marker.get("updated_at"), default=created)
    extra_raw = marker.get("extra")
    extra: dict[str, JSONValue] = (
        cast("dict[str, JSONValue]", extra_raw) if isinstance(extra_raw, dict) else {}
    )
    return FolderMetadata(
        id=slug,
        name=slug,
        kind=kind,
        created_at=created,
        updated_at=updated,
        extra=extra,
    )


#: Record ``type`` → Folder subclass, filled by :func:`register_entity_class`.
#: A directory says what it is through the ``type`` in its ``index.md`` head.
_ENTITY_TYPE_TO_CLS: dict[str, type[Folder]] = {}


def register_entity_class(cls: type[F]) -> type[F]:  # noqa: UP047
    """Register *cls* for reconstruction from its record ``type``.

    *cls* declares the type it writes as ``_entity_kind``. :func:`concept_from_dir`
    reads a directory's ``type`` and hands the directory to ``cls.from_disk``.
    """
    _ENTITY_TYPE_TO_CLS[cls._entity_kind] = cls
    return cls


def class_for_entity_type(kind: str) -> type[Folder] | None:
    """Return the Folder subclass registered for record ``type`` *kind*, if any."""
    return _ENTITY_TYPE_TO_CLS.get(kind)


def _validate_kind(kind: str) -> None:
    if not isinstance(kind, str) or not kind:
        raise ValueError("folder kind must be a non-empty string")
    if not _KIND_PATTERN.fullmatch(kind):
        raise ValueError(
            f"invalid folder kind {kind!r}: must be dotted lowercase ASCII "
            "(e.g. 'workspace.project'); no path separators, leading dots, "
            "uppercase, or whitespace"
        )


def _validate_file_name(name: str) -> None:
    if not isinstance(name, str) or not name:
        raise ValueError("folder file name must be a non-empty string")
    if name in _FORBIDDEN_FILE_NAMES or "/" in name or "\\" in name:
        raise ValueError(f"invalid folder file name {name!r}")


def _validate_name_to_id(name: str) -> str:
    if not isinstance(name, str) or not name:
        raise ValueError("folder name must be a non-empty string")
    if not _KIND_PATTERN.fullmatch(name):
        raise ValueError(
            f"invalid folder name {name!r}: must be dotted lowercase ASCII "
            "(e.g. 'my-project'); no path separators, leading dots, "
            "uppercase, or whitespace"
        )
    derived = slugify(name)
    if not derived or not _KIND_PATTERN.fullmatch(derived):
        raise ValueError(f"folder name {name!r} produced invalid id {derived!r}")
    return derived


def _registered_targets(node: object) -> tuple[object, ...]:
    """Compute targets visible from *node*, walking real parents.

    A served project or experiment keeps its on-disk parent when one exists.
    The registry still lives on that workspace. An empty registry does not
    stop the walk. A parentless mount has nowhere to look and returns ().
    """
    current: object | None = node
    seen = 0
    while current is not None and seen < 8:
        metadata = getattr(current, "metadata", None)
        found = getattr(metadata, "targets", None) or ()
        if found:
            return tuple(found)
        current = getattr(current, "_parent", None)
        seen += 1
    return ()


def _validate_target_registered(workspace: object, target: str | None) -> None:
    """Reject a *target* that is not in the workspace's compute-target registry.

    No-op when *target* is ``None`` or the registry is empty (a registry-less
    workspace keeps accepting free-form target strings — back-compat). Once a
    workspace registers any target, references must name a registered one
    (models.py: ``RunMetadata.target`` is "validated against
    WorkspaceMetadata.targets at write time").
    """
    if target is None:
        return
    registered = _registered_targets(workspace)
    if registered and not any(getattr(t, "name", None) == target for t in registered):
        names = sorted(str(getattr(t, "name", "?")) for t in registered)
        raise ValueError(
            f"unknown compute target {target!r}: not in the workspace target "
            f"registry {names}; register it first (e.g. `molab target add`)."
        )


class Folder:
    """A location on a workspace disk.

    The disk itself is :attr:`Folder.fs` (a :class:`FileSystem`: local,
    remote, or cached). A Folder does not own a disk — it resolves I/O
    by walking to the root Folder. User byte writes go through
    :attr:`files` (a :class:`FileStore` rooted here).

    Carries a ``parent`` pointer, lazy materialization, atomic JSON IO,
    children listing, lifecycle metadata, delete / move operations, and
    the generic ``attach`` / ``create_child`` / ``get_child`` triplet.
    """

    _exists_error_cls: ClassVar[type[Exception]] = ValueError
    _not_found_error_cls: ClassVar[type[Exception]] = LookupError
    #: The record ``type`` a registered subclass writes (``workspace.project``).
    _entity_kind: ClassVar[str] = ""

    def __init__(
        self,
        *,
        parent: Folder | None = None,
        name: str,
        kind: str,
        root_path: PathArg | None = None,
        fs: FileSystem | None = None,
    ) -> None:
        if parent is not None and root_path is not None:
            raise ValueError(
                "Folder: parent and root_path are mutually exclusive — "
                "non-root folders inherit their parent's path"
            )
        _validate_kind(kind)
        derived_id = _validate_name_to_id(name)
        self._parent = parent
        self._name = derived_id
        self._kind = kind
        self._root_path: Path | None = Path(os.fspath(root_path)) if root_path is not None else None
        if fs is not None:
            self._disk_backend = fs
        elif parent is None:
            self._disk_backend = LocalFS()
        else:
            self._disk_backend = None
        self._metadata = FolderMetadata(id=derived_id, name=name, kind=kind)
        self._children_cache: dict[str, Folder] = {}
        self._serve_boundary = False

    # ── Properties ───────────────────────────────────────────────────────

    @property
    def parent(self) -> Folder | None:
        return self._parent

    @property
    def name(self) -> str:
        return self._name

    @property
    def kind(self) -> str:
        return self._kind

    @property
    def metadata(self) -> FolderMetadata:
        return self._metadata

    @property
    def folder_metadata(self) -> FolderMetadata:
        return self._metadata

    def _disk(self) -> FileSystem:
        """The disk this location lives on (walks to the workspace root)."""
        node: Folder | None = self
        while node is not None:
            backend = getattr(node, "_disk_backend", None)
            if backend is not None:
                return backend
            node = node._parent
        return LocalFS()

    @property
    def fs(self) -> FileSystem:
        """The disk this location lives on; resolved by walking to the root Folder; the Folder does not own it.

        Read-only: assigning to ``fs`` raises ``AttributeError``.

        Returns:
            The same filesystem object :meth:`_disk` returns.
        """
        return self._disk()

    @overload
    def ls(
        self,
        path: str = ".",
        *,
        a: bool = False,
        A: bool = False,
        l: Literal[True],  # noqa: E741
    ) -> list[DirEntry]: ...

    @overload
    def ls(
        self,
        path: str = ".",
        *,
        a: bool = False,
        A: bool = False,
        l: Literal[False] = False,  # noqa: E741
    ) -> list[str]: ...

    def ls(
        self,
        path: str = ".",
        *,
        a: bool = False,
        A: bool = False,
        l: bool = False,  # noqa: E741
    ) -> list[str] | list[DirEntry]:
        """List *path* on this folder's disk. ``.`` is the folder itself.

        Flags match :meth:`FileSystem.ls`: plain ``ls()`` hides dotfiles,
        ``A=True`` is ``ls -A``, ``a=True`` is ``ls -a``, ``l=True`` is ``ls -l``.
        A local folder and a remote folder take the same call.
        """
        disk = self._disk()
        root = str(self.resolve())
        raw = (path or ".").strip() or "."
        if raw in {".", ""}:
            target = root
        elif disk.is_absolute(raw):
            target = raw
        else:
            target = disk.join(root, raw)
        return disk.ls(target, a=a, A=A, l=l)

    @property
    def files(self) -> FileStore:
        """Byte-exit rooted at this folder. Does not own the disk."""
        from .file_store import FileStore

        return FileStore(self.path, fs=self._disk())

    # ── Path resolution ──────────────────────────────────────────────────
    #
    # ``resolve`` returns :class:`molab.Path` (pure POSIX math; I/O goes
    # through :meth:`_disk`). ``path`` is a :class:`pathlib.Path` for local
    # joins like ``run.path / "index.md"``.

    @property
    def path(self) -> _StdPath:
        """On-disk directory as :class:`pathlib.Path`.

        Creates the directory if missing (lazy, idempotent). Pure path math
        without mkdir is :meth:`resolve`.
        """
        target = self.resolve()
        if not self._disk().is_dir(target):
            self._disk().mkdir(target, parents=True, exist_ok=True)
        return _StdPath(str(target))

    def resolve(self) -> Path:
        """Walk the parent chain without triggering lazy mkdir."""
        if self._parent is None:
            if self._root_path is None:
                raise RuntimeError(
                    f"folder {self._name!r} (kind={self._kind!r}) is unmounted — "
                    "construct via parent.add_folder(child) or pass root_path="
                )
            # A parentless serve root IS the directory it was opened from.
            # Nested folders still join ``_root_path / name``.
            if getattr(self, "_serve_boundary", False):
                return Path(self._root_path)
            return Path(self._disk().join(self._root_path, self._name))
        return Path(self._disk().join(self._parent.resolve(), self._name))

    def scope_top(self) -> Folder:
        """Nearest serve boundary, or the parentless root when none is set.

        Children stay mounted on their real parents. The boundary is the
        directory ``molab serve`` opened; ancestors above it are not part of
        the application.
        """
        node: Folder = self
        while node._parent is not None and not getattr(node, "_serve_boundary", False):
            node = node._parent
        return node

    def scope_root_path(self) -> Path:
        """Directory that bounds navigation and relative API paths."""
        return Path(self.scope_top().resolve())

    def asset_host(self) -> Folder:
        """Disk root for asset and history writes.

        Walks through a serve boundary so a project opened inside a real
        workspace still records history on that workspace. A parentless mount
        is its own host.
        """
        node: Folder = self
        while node._parent is not None:
            node = node._parent
        return node

    def ancestor(self, kind: str) -> Folder | None:
        """The folder of *kind* at or above ``self``, stopping above the serve boundary."""
        node: Folder | None = self
        while node is not None:
            if node.kind == kind:
                return node
            if getattr(node, "_serve_boundary", False):
                return None
            node = node._parent
        return None

    def ancestor_id(self, kind: str) -> str:
        """Id of :meth:`ancestor`, or ``""`` when that level is outside the serve root."""
        found = self.ancestor(kind)
        if found is None:
            return ""
        ident = getattr(found, "id", None)
        return str(ident) if ident else found.metadata.id

    # ── Index filename ───────────────────────────────────────────────────
    #
    # ── Atomic JSON IO ───────────────────────────────────────────────────

    def read_json(self, name: str) -> dict[str, JSONValue]:
        _validate_file_name(name)
        fpath = self._disk().join(self.path, name)
        with self._disk().open(fpath) as fh:
            raw: object = json.load(fh)
        if not isinstance(raw, dict):
            raise ValueError(f"{fpath} top-level JSON must be an object, got {type(raw).__name__}")
        return cast("dict[str, JSONValue]", raw)

    def write_json(self, name: str, data: object) -> str:
        _validate_file_name(name)
        fpath = self._disk().join(self.path, name)
        self._disk().atomic_write_json(fpath, data)
        return fpath

    # ── OKF record: index.md frontmatter (D88) ──

    def _lock_root(self) -> Path:
        """Workspace root whose ``.molab/locks`` guards this record's writes."""
        return self.asset_host().resolve()

    def _canonical_record(self) -> dict[str, JSONValue]:
        """The canonical zone this Folder writes. Subclasses with a model override it.

        * required ``type`` — registered concept kind (path basename = id)
        * ``created_at`` / ``updated_at`` — lifecycle of a generic :class:`Folder`
        * optional ``extra`` — free-form map
        """
        data: dict[str, JSONValue] = {
            "type": self._kind,
            "created_at": self._metadata.created_at.isoformat(),
            "updated_at": self._metadata.updated_at.isoformat(),
        }
        if self._metadata.extra:
            data["extra"] = self._metadata.extra
        return data

    def _write_record(self, canonical: dict[str, JSONValue]) -> str:
        """Replace the canonical zone of ``index.md``; keep the index and body."""
        write_record(self._disk(), self.path, canonical=canonical, lock_root=self._lock_root())
        return self._disk().join(self.resolve(), INDEX_FILENAME)

    def _record_written(self) -> None:
        """Refresh the derived ``index:`` here and in the parent after a canonical write.

        A parent batching child creation (:meth:`_batched_index`) refreshes
        itself once at the end instead of once per child.
        """
        from .index_projection import refresh_index

        parent = self._parent
        deferred = parent is not None and getattr(parent, "_index_deferred", False)
        refresh_index(self, parent=not deferred)

    def _parent_index_paths(self) -> tuple[str, ...]:
        """The parent's ``index.md``, for a history commit that follows a child write."""
        if self._parent is None:
            return ()
        return (self._disk().join(self._parent.resolve(), INDEX_FILENAME),)

    @contextmanager
    def _batched_index(self) -> Generator[None]:
        """Defer this Folder's index refresh to the end of a batch of child writes."""
        from .index_projection import refresh_index

        outer = getattr(self, "_index_deferred", False)
        self._index_deferred = True
        try:
            yield
        finally:
            self._index_deferred = outer
            if not outer:
                refresh_index(self, parent=False)

    def write_meta(self) -> str:
        """Write this Folder's canonical record into ``index.md``; return its path.

        Subclasses with a typed model override :meth:`_canonical_record`.
        """
        path = self._write_record(self._canonical_record())
        self._record_written()
        return path

    def read_meta(self) -> dict[str, JSONValue]:
        """The canonical zone of ``index.md``, or ``{}`` when there is no record."""
        record = read_record(self._disk(), self.resolve())
        return dict(record.canonical) if record is not None else {}

    def set_index_section(self, key: str, rows: list[dict[str, JSONValue]]) -> None:
        """Ask the owner to write ``index.<key>`` in this Folder's ``index.md``.

        The key is opaque to workspace: another layer names its own section
        and keeps it current. A refresh of the reserved keys keeps the
        section verbatim. :meth:`index_section` reads it back.

        Raises:
            ValueError: *key* is not ``^[a-z][a-z0-9_]*$`` or is a reserved key
                the owner derives from the tree.
        """
        if not _SECTION_KEY.fullmatch(key):
            raise ValueError(f"index section key {key!r} must match ^[a-z][a-z0-9_]*$")
        if key in RESERVED_INDEX_KEYS:
            raise ValueError(f"index section key {key!r} is reserved")
        section = [dict(row) for row in rows]

        def change(current: EntityRecord) -> EntityRecord:
            index = dict(current.index)
            index[key] = cast("JSONValue", section)
            return EntityRecord(canonical=current.canonical, index=index, body=current.body)

        update_record(self._disk(), self.path, change, lock_root=self._lock_root())

    def index_section(self, key: str) -> list[dict[str, JSONValue]] | None:
        """The rows of ``index.<key>`` a layer asked for, or ``None`` when absent.

        The reader beside :meth:`set_index_section`: the same opaque key, the
        rows as written. A record with no such section (or no record at all)
        returns ``None``, which a caller may treat as "never written".

        Raises:
            ValueError: *key* is not ``^[a-z][a-z0-9_]*$`` or is a reserved key.
        """
        if not _SECTION_KEY.fullmatch(key):
            raise ValueError(f"index section key {key!r} must match ^[a-z][a-z0-9_]*$")
        if key in RESERVED_INDEX_KEYS:
            raise ValueError(f"index section key {key!r} is reserved")
        record = read_record(self._disk(), self.resolve())
        if record is None:
            return None
        rows = record.index.get(key)
        if not isinstance(rows, list):
            return None
        return [dict(row) for row in rows if isinstance(row, dict)]

    # ── OKF narrative ─────────────────────────────────────────────────────

    def read_index(self) -> str:
        """Return the narrative body of ``index.md`` (no frontmatter), or ``""``."""
        return read_body(self._disk(), self.resolve())

    def write_index(self, text: str) -> str:
        """Atomically replace the narrative body of ``index.md``; keep its frontmatter."""
        write_record(self._disk(), self.path, body=text, lock_root=self._lock_root())
        return self._disk().join(self.resolve(), INDEX_FILENAME)

    # ── Lifecycle ────────────────────────────────────────────────────────

    def materialize(self) -> None:
        """Persist the record in ``index.md`` (creating the dir lazily)."""
        self._metadata = self._metadata.model_copy(update={"updated_at": datetime.now()})
        self.write_meta()

    def save(self) -> None:
        """Bump ``updated_at`` and rewrite the record."""
        self._metadata = self._metadata.model_copy(update={"updated_at": datetime.now()})
        self.write_meta()

    # ── Children ─────────────────────────────────────────────────────────

    def _try_child_folder_metadata(self, entry_path: PathArg) -> FolderMetadata | None:
        """Load in-memory FolderMetadata from the child's ``index.md`` record."""
        record = read_record(self._disk(), entry_path)
        if record is None:
            return None
        return _folder_metadata_from_marker(entry_path, record.canonical)

    def children(self, kind: str | None = None) -> list[Folder]:
        self_path = self.resolve()
        if not self._disk().is_dir(self_path):
            return []
        result: list[Folder] = []
        for entry in self._disk().ls(self_path, A=True, l=True):
            # ``scratch/`` is a disposable tier, never a child (D90).
            entry_name = entry.name
            if entry_name in _FORBIDDEN_FILE_NAMES or entry_name == SCRATCH_CONTAINER:
                continue
            if not entry.is_dir:
                continue
            entry_path = self._disk().join(self_path, entry_name)
            child_meta = self._try_child_folder_metadata(entry_path)
            if child_meta is None:
                continue
            if kind is not None and child_meta.kind != kind:
                continue
            child = _reconstruct(
                Folder,
                {
                    "_parent": self,
                    "_name": child_meta.id,
                    "_kind": child_meta.kind,
                    "_root_path": None,
                    "_metadata": child_meta,
                    "_children_cache": {},
                },
            )
            result.append(child)
        return result

    # ── Subclass hook contract ────────────────────────────────────────────
    #
    # ``resolve``, ``child_dir`` and ``from_disk`` are **framework hooks** —
    # public protocol surface that the Folder CRUD machinery (``add_folder``,
    # ``get_folder``, ``has_folder``, …) reaches into across class boundaries
    # to wire children to disk. Subclasses override them.
    #
    # Invariants every override MUST hold (failure modes have bitten us in
    # the past, see git history for ``fs``-drop bugs at every level):
    #
    #   * Never store a FileSystem on the child — the disk lives on
    #     Workspace and :meth:`_disk` walks to it. Use
    #     :meth:`base_from_disk_attrs` instead of hand-rolling the attrs
    #     dict — it bakes the invariants in.
    #   * Carry ``FolderMetadata`` (kind, id, *human* name, timestamps)
    #     into ``_metadata`` — don't substitute id for name.
    #   * ``resolve()`` is the side-effect-free path computation; ``path()``
    #     is its mkdir-ing twin. Don't trigger I/O in ``resolve``.
    #   * ``child_dir`` returns the absolute path of a child with this
    #     class's *layout* (e.g. ``projects/<id>``, ``experiments/<id>``).
    #
    # **Return type**: every Folder subclass returns :class:`molab.Path`
    # (a :class:`pathlib.PurePosixPath` subclass).  Pure POSIX path
    # arithmetic is available (``/`` operator, ``.parent``, ``.name``);
    # I/O methods are deliberately absent so a remote-backed folder cannot
    # silently short-circuit to the local filesystem.  All I/O routes
    # through ``self._disk()``, so every subclass inherits remote-compat
    # for free.
    #
    # Subclasses with their own entity metadata (Project / Experiment / Run)
    # override ``from_disk`` to load their entity model from a different
    # filename, but must call :meth:`base_from_disk_attrs` to seed the
    # common keys.
    # ──────────────────────────────────────────────────────────────────────

    @classmethod
    def child_dir(cls, parent: Folder, derived_id: str) -> Path:
        """Where a child with *derived_id* lives under *parent*. Override per subclass layout.

        Must use :meth:`resolve` (not :meth:`path`) — this is pure path math
        and must not trigger lazy mkdir on the parent (remote workspaces would
        otherwise attempt writes during list/get).
        """
        return Path(parent._disk().join(parent.resolve(), derived_id))

    @classmethod
    def base_from_disk_attrs(
        cls,
        parent: Folder,
        meta: FolderMetadata,
        *,
        slug: str | None = None,
    ) -> dict[str, object]:
        """Common attrs dict for ``_reconstruct`` — call this from every
        subclass ``from_disk`` to guarantee the parent link (and thus the disk).

        ``slug`` is the child's directory basename, which is what mounts it
        under its parent. Identity (``meta.id``) is a field inside the entity
        file, never the path.
        """
        return {
            "_parent": parent,
            "_name": slug if slug is not None else meta.id,
            "_kind": meta.kind,
            "_root_path": None,
            "_metadata": meta,
            "_children_cache": {},
        }

    @classmethod
    def _require_record(cls, child_dir: PathArg, parent: Folder) -> EntityRecord:
        """*child_dir*'s record, which must carry this class's ``type``.

        Raises:
            FileNotFoundError: No ``index.md`` record.
            ValueError: The record names another type.
            UnmigratedLayoutError: Only a legacy JSON record is present.
        """
        fs = parent._disk()
        record = read_record(fs, child_dir)
        if record is None:
            raise FileNotFoundError(fs.join(child_dir, INDEX_FILENAME))
        if cls._entity_kind and record.type != cls._entity_kind:
            raise ValueError(f"{child_dir} is a {record.type!r} record, not {cls._entity_kind!r}")
        return record

    @classmethod
    def from_disk(cls, child_dir: PathArg, parent: Folder) -> Folder:
        """Generic loader: reconstruct *child_dir* from its ``index.md`` record.

        Concept identity is the record's ``type`` (→ kind; dir name → id).
        A dir with no record is not a Folder: ``FileNotFoundError``.
        """
        record = cls._require_record(child_dir, parent)
        child_meta = _folder_metadata_from_marker(child_dir, record.canonical)
        return _reconstruct(
            cls,
            cls.base_from_disk_attrs(parent, child_meta, slug=parent._disk().basename(child_dir)),
        )

    # ── Generic five-verb CRUD ───────────────────────────────────────────

    def _construct_child(self, cls: type[F], name: str, **kwargs: object) -> F:
        """Build a typed child folder parented at ``self`` (not yet on disk).

        The single construction hook the typed ``add_*`` sugar
        (:meth:`Workspace.add_project`, :meth:`Project.add_experiment`,
        :meth:`Experiment.add_run`) uses before handing the child to
        :meth:`add_folder`. Entity constructors require a parent, so the child
        is built self-parented; :meth:`add_folder` accepts a self-parented
        child and performs the idempotent mount (cache / on-disk hit / create).
        """
        # Heterogeneous entity constructors (Run/Experiment/Project) all accept
        # ``parent`` + ``name`` plus their own typed kwargs; the dynamic forward
        # is sound at the call sites but not statically checkable here.
        return cls(parent=self, name=name, **kwargs)  # ty: ignore[invalid-argument-type]

    def add_folder(self, child: F) -> F:
        # Accept an unmounted child, or one already parented at ``self`` (the
        # typed ``add_*`` sugar builds self-parented children via
        # ``_construct_child``). Reject a child mounted elsewhere or a root.
        if child._root_path is not None or (
            child._parent is not None and child._parent is not self
        ):
            raise ValueError(
                f"folder {child._name!r} (kind={child._kind!r}) is already mounted; "
                "add_folder() accepts only unmounted or self-parented folders"
            )
        target_cls = type(child)
        slug = child._name
        cached = self._children_cache.get(slug)
        if cached is not None and cached._kind == child._kind:
            # Cache/disk hits reconstruct through type(child), so the narrow
            # return type is truthful (add_folder is generic like get_folder).
            return cast("F", cached)
        child_dir = target_cls.child_dir(self, slug)
        if self._disk().is_dir(child_dir):
            existing = target_cls.from_disk(child_dir, self)
            self._children_cache[slug] = existing
            return cast("F", existing)
        child._parent = self
        child._root_path = None
        if getattr(child, "_disk_backend", None) is not None:
            del child._disk_backend
        child.materialize()  # writes the index.md record and refreshes the index
        if read_type(self._disk(), child.resolve()) is None:
            child.write_meta()
        self._children_cache[slug] = child
        return child

    def get_folder(self, name: str, *, cls: type[F]) -> F:
        """Resolve a child by its directory name, its display name, or its id.

        The directory name is the primary handle — that is what a person types.
        A UUIDv7 identity still resolves, because references between entities
        cite ids, not paths.
        """
        found = self._find_folder(name, cls)
        if found is None:
            raise cls._not_found_error_cls(name)
        return found

    def has_folder(self, name: str, *, cls: type[Folder]) -> bool:
        return self._find_folder(name, cls) is not None

    def _find_folder(self, name: str, cls: type[F]) -> F | None:
        for candidate in (name, slugify(name)):
            if not candidate:
                continue
            cached = self._children_cache.get(candidate)
            if isinstance(cached, cls):
                return cached
            child_dir = cls.child_dir(self, candidate)
            if self._disk().is_dir(child_dir):
                loaded = cls.from_disk(child_dir, self)
                if isinstance(loaded, cls):
                    self._children_cache[loaded._name] = loaded
                    return loaded
        return self._child_by_id(name, cls=cls)

    def _child_by_id(self, entity_id: str, *, cls: type[F]) -> F | None:
        """The child of type *cls* whose entity id is *entity_id*, if any.

        The one id lookup inside the workspace layer. Directory names and
        display names stay on :meth:`_find_folder`.
        """
        for child in self.list_folders(cls=cls):
            if child.metadata.id == entity_id:
                return child
        return None

    def list_folders(self, *, cls: type[F] | None = None) -> list[F]:
        """List children by scanning disk — the tree *is* the index."""
        if cls is None:
            return cast("list[F]", self.children())
        container = cls._container_dir(self)
        if not self._disk().is_dir(container):
            return []
        out: list[F] = []
        for entry in self._disk().ls(container, A=True, l=True):
            # A generic Folder's container is its own directory, where an
            # experiment keeps ``scratch/``; it is never a child (D90).
            entry_name = entry.name
            if entry_name in _FORBIDDEN_FILE_NAMES or entry_name == SCRATCH_CONTAINER:
                continue
            if not entry.is_dir:
                continue
            cached = self._children_cache.get(entry_name)
            if isinstance(cached, cls):
                out.append(cached)
                continue
            entry_path = self._disk().join(container, entry_name)
            try:
                loaded = cls.from_disk(entry_path, self)
            except UnmigratedLayoutError:
                raise
            except (FileNotFoundError, OSError, ValueError):
                continue
            if isinstance(loaded, cls):
                self._children_cache[loaded._name] = loaded
                out.append(loaded)
        return out

    def remove_folder(self, name: str, *, cls: type[Folder]) -> None:
        found = self._find_folder(name, cls)
        if found is not None:
            name = found._name
        for candidate in (name, slugify(name)):
            if not candidate:
                continue
            child_dir = cls.child_dir(self, candidate)
            if self._disk().is_dir(child_dir):
                self._disk().rm(child_dir, recursive=True)
                self._children_cache.pop(candidate, None)
                self._refresh_own_index()
                return
            cached = self._children_cache.get(candidate)
            if isinstance(cached, cls):
                self._children_cache.pop(candidate, None)
                return
        raise cls._not_found_error_cls(name)

    # ── Container dir + index helpers ────────────────────────────────────

    @classmethod
    def _container_dir(cls, parent: Folder) -> Path:
        return Path(parent._disk().dirname(cls.child_dir(parent, "_probe_")))

    # ── Delete + move ────────────────────────────────────────────────────

    def _refresh_own_index(self) -> None:
        from .index_projection import refresh_index

        refresh_index(self, parent=False)

    def delete(self) -> None:
        target = self.resolve()
        if self._disk().exists(target):
            self._disk().rm(target, recursive=True)
        if self._parent is not None:
            self._parent._children_cache.pop(self._name, None)
            self._parent._refresh_own_index()

    def _sync_entity_identity(self) -> None:
        """Hook — subclasses with entity metadata mirror the folder identity.

        Called by :meth:`move_to` after the folder identity is updated and
        before any :meth:`resolve`-dependent write: entity subclasses resolve
        their directory from the entity id, so a stale entity id would land
        :meth:`write_meta` in a freshly created old-id dir and key the in-memory
        child cache by the old id. Default: no entity metadata, no-op.
        """

    def _move_target_id(self, new_name: str | None) -> str:
        """Directory basename for the move target.

        Default (generic Folder): a rename slugs to a new id. Entity
        subclasses (Project / Experiment / Run) override this to keep their
        stable UUID id — ``new_name`` then changes only the human name.
        """
        return self._name if new_name is None else _validate_name_to_id(new_name)

    def move_to(
        self,
        new_parent: Folder,
        *,
        new_name: str | None = None,
    ) -> None:
        # move_to uses OS-level ``shutil.move`` (local paths only). On a
        # remote-backed folder that would silently operate on the wrong (local)
        # path, so refuse it with a clear error instead.
        if not isinstance(self._disk(), LocalFS) or not isinstance(new_parent._disk(), LocalFS):
            raise NotImplementedError(
                "move_to is only supported for local-filesystem folders "
                "(it uses OS-level shutil.move); remote-backed folders cannot be moved."
            )
        target_id = self._move_target_id(new_name)
        # Honor the child class's container layout (``runs/<slug>``,
        # ``projects/<slug>``, …) via the same ``child_dir`` hook that mounting
        # uses — a naive ``new_parent.path()/id`` join would strand the moved
        # folder outside its container and hide it from ``list_folders``.
        target_dir = Path(type(self).child_dir(new_parent, target_id))
        if new_parent._disk().exists(target_dir):
            raise FolderMoveCollisionError(str(self.resolve()), str(target_dir))
        src = self.resolve()
        old_parent = self._parent
        # ``shutil.move`` only creates the final path component, so ensure the
        # container dir (``runs/``, ``projects/``, …) exists under the new parent.
        new_parent._disk().mkdir(
            new_parent._disk().dirname(target_dir), parents=True, exist_ok=True
        )
        shutil.move(str(src), str(target_dir))
        if old_parent is not None:
            old_parent._children_cache.pop(self._name, None)
        self._parent = new_parent
        self._root_path = None
        if getattr(self, "_disk_backend", None) is not None:
            del self._disk_backend
        self._name = target_id
        self._metadata = self._metadata.model_copy(
            update={
                "id": target_id,
                "name": new_name if new_name is not None else self._metadata.name,
                "updated_at": datetime.now(),
            }
        )
        # Before any resolve()-dependent write — entity subclasses derive their
        # directory from the entity id, so this must land ahead of write_meta().
        self._sync_entity_identity()
        new_parent._children_cache[target_id] = self
        self.write_meta()  # refreshes this record's index and the new parent's
        if old_parent is not None and old_parent is not new_parent:
            old_parent._refresh_own_index()


def concept_from_dir(child_dir: PathArg, parent: Folder) -> Folder:
    """Reconstruct *child_dir* as its Folder subclass, from its record ``type``.

    A ``type`` that :func:`class_for_entity_type` knows (the four tree levels,
    each registered by its own module) picks the subclass; any other record
    rebuilds as the bare :class:`Folder`. A directory with no record at all is
    not a Folder and raises ``TypeError``.
    """
    fs = parent._disk()
    kind = read_type(fs, child_dir)
    if kind is None:
        read_record(fs, child_dir)  # raises UnmigratedLayoutError on a legacy dir
        raise TypeError(f"{child_dir} is not a Folder: no {INDEX_FILENAME} record")
    mapped = class_for_entity_type(kind)
    if mapped is not None:
        return mapped.from_disk(child_dir, parent)
    return Folder.from_disk(child_dir, parent)


__all__ = [
    "INDEX_FILENAME",
    "WORKSPACE_EXPERIMENT_KIND",
    "WORKSPACE_PROJECT_KIND",
    "WORKSPACE_ROOT_KIND",
    "WORKSPACE_RUN_KIND",
    "Folder",
    "class_for_entity_type",
    "concept_from_dir",
    "register_entity_class",
]
