"""A Folder's record: the YAML frontmatter of its own ``index.md`` (D88).

Every level of the tree (workspace, project, experiment, run, and a generic
:class:`~molab.workspace.folder.Folder`) keeps one file, ``index.md``. Its
frontmatter holds two zones and the markdown after it is the narrative:

* the **canonical** zone — the fields the level's metadata model writes
  (``type``, ``id``, ``name``, …, ``schema_version``). This is the record.
* the **derived** zone, under the ``index:`` key (D89) — rewritten by the
  owner from the tree (``index_projection``), and never read by molab to
  decide anything. It lets an agent walk down from the root ``index.md``.
* the **body** — the narrative; its markdown links are the cross-reference graph.

This module is the single read/write path for that file. A write replaces any
zone it is given and keeps the others, atomically, under a per-directory
advisory lock in the workspace's ``.molab/locks``.
"""

from __future__ import annotations

import contextlib
import hashlib
from collections.abc import Callable, Generator
from pathlib import Path as _LocalPath
from typing import Final, NamedTuple, cast

from molab import frontmatter
from molab._typing import JSONValue

from .errors import UnmigratedLayoutError
from .fs import FileSystem, PathArg
from .fs_local import LocalFileSystem

#: The one file that holds a Folder's record, index and narrative.
ENTITY_FILENAME: Final = "index.md"
INDEX_FILENAME: Final = ENTITY_FILENAME

#: Frontmatter key of the derived zone.
INDEX_KEY: Final = "index"

#: Derived keys the owner rewrites on refresh. Any other key under ``index:``
#: is a section another layer asked for (``Folder.set_index_section``) and
#: is kept verbatim.
RESERVED_INDEX_KEYS: Final = frozenset(
    {"parent", "children", "entrypoint", "scratch", "executions", "latest_status"}
)

#: Record files of the JSON layout this replaced. Only the
#: :class:`UnmigratedLayoutError` detector names them; nothing reads them.
LEGACY_RECORD_FILES: Final = (
    "workspace.json",
    "project.json",
    "experiment.json",
    "run.json",
    "meta.json",
)


class _Keep:
    """Sentinel type: leave this zone as it is on disk."""

    def __repr__(self) -> str:
        return "KEEP"


KEEP: Final = _Keep()


class EntityRecord(NamedTuple):
    """One ``index.md``: ``(canonical, index, body)``.

    ``canonical`` is the record proper, ``index`` the derived ``index:`` zone,
    ``body`` the narrative after the frontmatter.
    """

    canonical: dict[str, JSONValue]
    index: dict[str, JSONValue]
    body: str

    @property
    def type(self) -> str:
        return str(self.canonical.get("type") or "")


def _record_path(fs: FileSystem, directory: PathArg) -> str:
    return fs.join(directory, ENTITY_FILENAME)


def legacy_record_files(fs: FileSystem, directory: PathArg) -> tuple[str, ...]:
    """The legacy JSON record files present in *directory* (one listing)."""
    try:
        names = {entry.name for entry in fs.scandir(directory, with_stat=False)}
    except OSError:
        return ()
    return tuple(name for name in LEGACY_RECORD_FILES if name in names)


def _raise_if_legacy(fs: FileSystem, directory: PathArg) -> None:
    legacy = legacy_record_files(fs, directory)
    if legacy:
        raise UnmigratedLayoutError(str(directory), legacy)


def _from_meta(meta: dict[str, object], body: str) -> EntityRecord:
    # The YAML loader yields JSON values only (no timestamps, no tags).
    raw_index = meta.get(INDEX_KEY)
    index = cast("dict[str, JSONValue]", dict(raw_index) if isinstance(raw_index, dict) else {})
    canonical = cast(
        "dict[str, JSONValue]",
        {key: value for key, value in meta.items() if key != INDEX_KEY},
    )
    return EntityRecord(canonical=canonical, index=index, body=body)


def _read_text(fs: FileSystem, directory: PathArg) -> str | None:
    try:
        return fs.read_text(_record_path(fs, directory))
    except (FileNotFoundError, IsADirectoryError, NotADirectoryError):
        return None


def read_record(fs: FileSystem, directory: PathArg) -> EntityRecord | None:
    """Read *directory*'s record, or ``None`` when it has none.

    ``None`` means ``index.md`` is absent or its frontmatter carries no
    ``type`` (a plain narrative file is not a record).

    Raises:
        UnmigratedLayoutError: There is no record but a legacy JSON record
            file is still in *directory*.
    """
    text = _read_text(fs, directory)
    if text is not None:
        meta, body = frontmatter.split(text)
        if meta.get("type"):
            return _from_meta(meta, body)
    _raise_if_legacy(fs, directory)
    return None


def read_type(fs: FileSystem, directory: PathArg) -> str | None:
    """The record's ``type``, from the head only; ``None`` when there is no record.

    The discovery probe: it does not read the body and never raises for a
    legacy directory (the validator reports that instead).
    """
    head = frontmatter.read_head(fs, _record_path(fs, directory))
    if not head:
        return None
    found = head.get("type")
    return str(found) if found else None


def read_body(fs: FileSystem, directory: PathArg) -> str:
    """The narrative of *directory*'s ``index.md``; ``""`` when absent.

    A file with no frontmatter is all body.
    """
    text = _read_text(fs, directory)
    if text is None:
        return ""
    return frontmatter.split(text)[1]


def _lock_backend(fs: FileSystem) -> str:
    return "flock" if isinstance(fs, LocalFileSystem) else "none"


@contextlib.contextmanager
def _record_lock(fs: FileSystem, directory: PathArg, lock_root: PathArg | None) -> Generator[None]:
    """Advisory lock for one directory's ``index.md`` read-modify-write.

    The lock file lives under ``<lock_root>/.molab/locks`` (the same helper and
    directory the run and execution locks use). Without a *lock_root* there
    is nowhere machine state may go, so the write runs unlocked.
    """
    if lock_root is None or _lock_backend(fs) == "none":
        yield
        return
    from molab.atomicio import file_lock

    from .history import MOLAB_DIR

    digest = hashlib.sha256(str(directory).encode("utf-8")).hexdigest()[:20]
    lock = _LocalPath(str(lock_root)) / MOLAB_DIR / "locks" / f"index-{digest}.lock"
    with file_lock(lock):
        yield


def _current(fs: FileSystem, directory: PathArg) -> EntityRecord:
    """What is on disk now, tolerant of a missing or plain-narrative file."""
    text = _read_text(fs, directory)
    if text is None:
        return EntityRecord(canonical={}, index={}, body="")
    meta, body = frontmatter.split(text)
    return _from_meta(meta, body)


def _render(record: EntityRecord) -> str:
    meta: dict[str, object] = dict(record.canonical)
    if record.index:
        meta[INDEX_KEY] = record.index
    return frontmatter.dump(meta, record.body)


def update_record(
    fs: FileSystem,
    directory: PathArg,
    change: Callable[[EntityRecord], EntityRecord],
    *,
    lock_root: PathArg | None = None,
) -> EntityRecord:
    """Read-modify-write *directory*'s ``index.md`` under its lock.

    *change* receives what is on disk (an empty record when nothing is) and
    returns the record to write. Nothing is written when it returns the same
    record, so a no-op refresh leaves the file's mtime alone.

    Returns:
        The record as it now stands on disk.
    """
    with _record_lock(fs, directory, lock_root):
        current = _current(fs, directory)
        updated = change(current)
        if updated != current:
            fs.mkdir(directory, parents=True, exist_ok=True)
            fs.atomic_write_text(_record_path(fs, directory), _render(updated))
        return updated


def write_record(
    fs: FileSystem,
    directory: PathArg,
    *,
    canonical: dict[str, JSONValue] | _Keep = KEEP,
    index: dict[str, JSONValue] | _Keep = KEEP,
    body: str | _Keep = KEEP,
    lock_root: PathArg | None = None,
) -> EntityRecord:
    """Replace the given zones of *directory*'s record; keep the others.

    Args:
        fs: The disk.
        directory: The Folder's directory.
        canonical: The new canonical zone (``model_dump(mode="json")`` plus
            ``type`` / ``schema_version``), or :data:`KEEP`.
        index: The whole new ``index:`` zone, or :data:`KEEP`.
        body: The new narrative, or :data:`KEEP`.
        lock_root: Workspace root whose ``.molab/locks`` holds the lock.

    Returns:
        The record as written.
    """

    def change(current: EntityRecord) -> EntityRecord:
        return EntityRecord(
            canonical=current.canonical if isinstance(canonical, _Keep) else dict(canonical),
            index=current.index if isinstance(index, _Keep) else dict(index),
            body=current.body if isinstance(body, _Keep) else body,
        )

    return update_record(fs, directory, change, lock_root=lock_root)


__all__ = [
    "ENTITY_FILENAME",
    "INDEX_FILENAME",
    "INDEX_KEY",
    "KEEP",
    "LEGACY_RECORD_FILES",
    "RESERVED_INDEX_KEYS",
    "EntityRecord",
    "UnmigratedLayoutError",
    "legacy_record_files",
    "read_body",
    "read_record",
    "read_type",
    "update_record",
    "write_record",
]
