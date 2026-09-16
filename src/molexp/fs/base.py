"""FileSystem abstraction — the workspace layer speaks this, never raw pathlib.

Two implementations: LocalFileSystem (wraps pathlib/os/shutil) and
RemoteFileSystem (wraps molq Transport + shell commands for missing ops).

All path arguments are interpreted on this filesystem.  ``str`` and any
:class:`os.PathLike[str]` (notably :class:`molexp.Path` /
:class:`pathlib.PurePosixPath`) are accepted; implementations normalize
to ``str`` internally before doing string operations or shelling out.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import IO, Any, Protocol, runtime_checkable

PathArg = str | os.PathLike[str]
"""Anything that ``os.fspath()`` can turn into a POSIX path string.

Includes plain ``str``, :class:`molexp.Path`, :class:`pathlib.PurePosixPath`,
and any third-party object implementing ``__fspath__() -> str``.
"""


@dataclass(frozen=True)
class StatResult:
    """Cross-platform stat result. Fields match the subset workspace needs."""

    size: int
    mtime: float
    is_dir: bool
    is_file: bool


@dataclass(frozen=True, slots=True)
class DirEntry:
    """One child of a directory, as returned by :meth:`FileSystem.scandir`.

    The bulk counterpart to ``listdir`` + per-entry ``is_dir`` / ``stat``.
    One local ``os.scandir`` pass — or one remote round-trip — answers what
    the per-path Protocol needs N+1 calls for.

    ``is_dir`` / ``is_file`` follow symlinks (``os.DirEntry`` semantics), so a
    symlink to a directory reports ``is_dir=True, is_symlink=True``; a broken
    or looping link reports both False with ``is_symlink=True``. ``size`` and
    ``mtime`` describe the *target* and are ``0`` / ``0.0`` when the listing
    was taken with ``with_stat=False``.
    """

    name: str
    is_dir: bool
    is_file: bool
    is_symlink: bool = False
    size: int = 0
    mtime: float = 0.0


@runtime_checkable
class FileSystem(Protocol):
    """Where files and directories actually live.

    Implementations: LocalFileSystem (stdlib), RemoteFileSystem (SSH via molq Transport).
    Third-party plugins may implement this Protocol without importing workspace internals.
    """

    # ── Path operations ──────────────────────────────────────────────────

    def join(self, *parts: PathArg) -> str: ...
    def dirname(self, path: PathArg) -> str: ...
    def basename(self, path: PathArg) -> str: ...
    def resolve(self, path: PathArg) -> str: ...
    def is_absolute(self, path: PathArg) -> bool: ...

    # ── Existence / type ─────────────────────────────────────────────────

    def exists(self, path: PathArg) -> bool: ...
    def is_dir(self, path: PathArg) -> bool: ...
    def is_file(self, path: PathArg) -> bool: ...

    # ── Directory operations ─────────────────────────────────────────────

    def mkdir(self, path: PathArg, *, parents: bool = True, exist_ok: bool = True) -> None: ...
    def listdir(self, path: PathArg) -> list[str]: ...
    def glob(self, path: PathArg, pattern: str) -> Iterable[str]: ...
    def rglob(self, path: PathArg, pattern: str) -> Iterable[str]: ...

    def scandir(self, path: PathArg, *, with_stat: bool = True) -> list[DirEntry]:
        """List *path*'s children with their type (and size/mtime) in one pass.

        A ``list``, not an iterator: the remote implementation has to fetch the
        whole listing anyway, and the cached layer pins it. Order is
        unspecified — callers that need determinism sort by ``name``. ``.`` and
        ``..`` are never included.

        ``with_stat=False`` lets an implementation skip per-entry metadata
        (``size``/``mtime`` come back zeroed) while still reporting ``is_dir``
        and ``is_file`` exactly; implementations for which metadata is free
        (one remote listing carries it) may ignore the flag.

        Raises:
            FileNotFoundError: *path* does not exist.
            NotADirectoryError: *path* exists but is not a directory.
        """
        ...

    def read_range(self, path: PathArg, offset: int, length: int) -> bytes:
        """Read bytes ``[offset, offset + length)`` without loading the file.

        The primitive behind log tails and windowed file views: a multi-GB
        artifact must never be slurped to show its last screenful. Returns
        fewer than *length* bytes at EOF, and ``b""`` when *offset* is at or
        past the end. Never allocates more than *length* bytes.

        Raises:
            ValueError: *offset* or *length* is negative.
            FileNotFoundError: *path* does not exist.
            IsADirectoryError: *path* is a directory.
        """
        ...

    # ── Read ─────────────────────────────────────────────────────────────

    def read_text(self, path: PathArg, encoding: str = "utf-8") -> str: ...
    def read_bytes(self, path: PathArg) -> bytes: ...
    def open(self, path: PathArg, mode: str = "r", encoding: str = "utf-8") -> IO[Any]: ...

    # ── Write ────────────────────────────────────────────────────────────

    def write_text(self, path: PathArg, content: str, *, mode: int = 0o600) -> None: ...
    def write_bytes(self, path: PathArg, content: bytes, *, mode: int = 0o600) -> None: ...

    # ── Mutations ────────────────────────────────────────────────────────

    def rename(self, src: PathArg, dst: PathArg) -> None: ...
    def remove(self, path: PathArg, *, recursive: bool = False) -> None: ...
    def copy(self, src: PathArg, dst: PathArg) -> None: ...
    def copytree(self, src: PathArg, dst: PathArg, *, dirs_exist_ok: bool = False) -> None: ...

    # ── Metadata ─────────────────────────────────────────────────────────

    def stat(self, path: PathArg) -> StatResult: ...
    def lstat(self, path: PathArg) -> StatResult: ...
    def touch(self, path: PathArg) -> None: ...
    def chmod(self, path: PathArg, mode: int) -> None: ...
    def getsize(self, path: PathArg) -> int: ...

    # ── Symlinks ─────────────────────────────────────────────────────────

    def symlink(self, src: PathArg, dst: PathArg) -> None: ...

    # ── Atomic I/O ───────────────────────────────────────────────────────

    def atomic_write_json(self, path: PathArg, data: object) -> None: ...
    def atomic_write_text(
        self, path: PathArg, content: str, *, encoding: str = "utf-8"
    ) -> None: ...


@contextlib.contextmanager
def bulk(fs: FileSystem) -> Iterator[None]:
    """Group many operations on *fs* into one batch, when it supports batching.

    ``CachedRemoteFileSystem`` re-serializes its whole index sidecar on every
    recorded entry; a walk that touches N paths therefore writes O(N²) bytes
    unless it runs inside that class's ``batched()`` context. Wrapping a walker
    in ``bulk(fs)`` gets that batching where it exists and costs nothing where
    it does not, so walkers do not have to know which filesystem they are on.

    Args:
        fs: Any filesystem; one without a ``batched()`` method is a no-op.
    """
    batched = getattr(fs, "batched", None)
    if batched is None:
        yield
        return
    with batched():
        yield
