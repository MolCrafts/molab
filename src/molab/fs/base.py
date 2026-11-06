"""FileSystem abstraction — the workspace layer speaks this, never raw pathlib.

Two implementations: LocalFS (wraps pathlib/os/shutil) and
RemoteFS (uses the public molq file and transfer APIs).

All path arguments are interpreted on this filesystem.  ``str`` and any
:class:`os.PathLike[str]` (notably :class:`molab.Path` /
:class:`pathlib.PurePosixPath`) are accepted; implementations normalize
to ``str`` internally before doing string operations or shelling out.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Generator, Iterable
from dataclasses import dataclass
from typing import IO, Any, Literal, Protocol, overload, runtime_checkable

PathArg = str | os.PathLike[str]
"""Anything that ``os.fspath()`` can turn into a POSIX path string.

Includes plain ``str``, :class:`molab.Path`, :class:`pathlib.PurePosixPath`,
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
    """One row of ``ls -l`` (:meth:`FileSystem.ls` with ``l=True``).

    ``is_dir`` / ``is_file`` follow symlinks (``os.DirEntry`` semantics), so a
    symlink to a directory reports ``is_dir=True, is_symlink=True``. A broken
    or looping link reports both False with ``is_symlink=True``, and ``size``
    / ``mtime`` stay ``0`` / ``0.0``. ``size`` and ``mtime`` describe the target.
    """

    name: str
    is_dir: bool
    is_file: bool
    is_symlink: bool = False
    size: int = 0
    mtime: float = 0.0


def select_ls_names(names: Iterable[str], *, a: bool, A: bool) -> list[str]:
    """Apply ``ls`` / ``ls -a`` / ``ls -A`` to real child names.

    *names* is the directory's children. ``.`` and ``..`` are not children;
    ``a=True`` adds them. ``A=True`` keeps other hidden names. ``a`` wins when
    both are set, matching GNU ``ls``.
    """
    show_hidden = a or A
    out = [
        name
        for name in names
        if name not in {".", ".."} and (show_hidden or not name.startswith("."))
    ]
    if a:
        out.extend((".", ".."))
    return sorted(out)


def select_ls_entries(
    entries: Iterable[DirEntry],
    *,
    a: bool,
    A: bool,
    dot: DirEntry | None = None,
    dotdot: DirEntry | None = None,
) -> list[DirEntry]:
    """Apply ``ls -l`` flags to real child entries. ``a=True`` appends *dot* and *dotdot*."""
    show_hidden = a or A
    out = [
        entry
        for entry in entries
        if entry.name not in {".", ".."} and (show_hidden or not entry.name.startswith("."))
    ]
    if a:
        out.append(dot if dot is not None else DirEntry(name=".", is_dir=True, is_file=False))
        out.append(
            dotdot if dotdot is not None else DirEntry(name="..", is_dir=True, is_file=False)
        )
    return sorted(out, key=lambda entry: entry.name)


@runtime_checkable
class FileSystem(Protocol):
    """Where files and directories actually live.

    Implementations: LocalFS (stdlib), RemoteFS (the public molq SDK).
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

    @overload
    def ls(
        self,
        path: PathArg,
        *,
        a: bool = False,
        A: bool = False,
        l: Literal[True],  # noqa: E741
    ) -> list[DirEntry]: ...

    @overload
    def ls(
        self,
        path: PathArg,
        *,
        a: bool = False,
        A: bool = False,
        l: Literal[False] = False,  # noqa: E741
    ) -> list[str]: ...

    def ls(
        self,
        path: PathArg,
        *,
        a: bool = False,
        A: bool = False,
        l: bool = False,  # noqa: E741
    ) -> list[str] | list[DirEntry]:
        """List *path* the way ``ls`` does.

        ``ls()`` returns sorted names and hides a name that starts with ``.``.
        ``a=True`` is ``ls -a``: hidden names, plus ``.`` and ``..``. ``A=True``
        is ``ls -A``: hidden names, without ``.`` and ``..``. When both are set,
        ``a`` wins. ``l=True`` is ``ls -l`` and returns :class:`DirEntry` rows
        (type, size, mtime) instead of names. A long listing is one pass: the
        remote implementation fetches the page once, and the cached layer pins it.

        A walk that used to call ``listdir`` and then ``is_dir`` on each child
        asks for ``A=True, l=True`` — every real child, with its type — and does
        not hide a dotfile the walk still has to reject itself.

        Raises:
            FileNotFoundError: *path* does not exist.
            NotADirectoryError: *path* exists but is not a directory.
        """
        ...

    def glob(self, path: PathArg, pattern: str) -> Iterable[str]: ...
    def rglob(self, path: PathArg, pattern: str) -> Iterable[str]: ...

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

    def mv(self, src: PathArg, dst: PathArg) -> None: ...

    def rm(self, path: PathArg, *, recursive: bool = False) -> None:
        """Remove *path*. ``recursive=True`` is ``rm -r``."""
        ...

    def cp(
        self, src: PathArg, dst: PathArg, *, recursive: bool = False, dirs_exist_ok: bool = False
    ) -> None:
        """Copy *src* to *dst*. A directory requires ``recursive=True`` (``cp -r``).

        Raises:
            IsADirectoryError: *src* is a directory and *recursive* is false.
            FileExistsError: *recursive* is true, *dst* exists, and *dirs_exist_ok* is false.
        """
        ...

    # ── Metadata ─────────────────────────────────────────────────────────

    def stat(self, path: PathArg) -> StatResult: ...
    def lstat(self, path: PathArg) -> StatResult: ...
    def touch(self, path: PathArg) -> None: ...
    def chmod(self, path: PathArg, mode: int) -> None: ...
    def getsize(self, path: PathArg) -> int: ...

    # ── Symlinks ─────────────────────────────────────────────────────────

    def ln(self, src: PathArg, dst: PathArg) -> None:
        """Create a symlink at *dst* pointing at *src* (``ln -s``)."""
        ...

    # ── Atomic I/O ───────────────────────────────────────────────────────

    def atomic_write_json(self, path: PathArg, data: object) -> None: ...
    def atomic_write_text(
        self, path: PathArg, content: str, *, encoding: str = "utf-8"
    ) -> None: ...


@contextlib.contextmanager
def bulk(fs: FileSystem) -> Generator[None]:
    """Group many operations on *fs* into one batch, when it supports batching.

    ``CachedRemoteFS`` re-serializes its whole index sidecar on every
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
