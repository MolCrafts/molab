"""Generic ``scandir`` / ``read_range`` for in-memory test filesystems.

The real implementations answer these in one syscall or one round-trip, which
is the whole point of putting them on the Protocol. A test fake has no such
constraint, so it can satisfy the Protocol by composing the per-path calls it
already implements.

These live under ``tests/`` on purpose: shipping a fallback in ``src/`` would
be a code path with no production caller, and worse, it would let a real
filesystem silently keep the N+1 behaviour the bulk ops exist to remove.

Usage in a fake::

    from tests.support.fs_fallbacks import default_read_range, default_scandir


    class _FakeFS:
        ...

        def scandir(self, path, *, with_stat=True):
            return default_scandir(self, path, with_stat=with_stat)

        def read_range(self, path, offset, length):
            return default_read_range(self, path, offset, length)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from molexp.fs import DirEntry

if TYPE_CHECKING:
    from molexp.fs import PathArg


def default_scandir(fs: Any, path: PathArg, *, with_stat: bool = True) -> list[DirEntry]:
    """Compose ``listdir`` + per-entry ``is_dir`` / ``stat`` into a listing."""
    target = str(path)
    if not fs.is_dir(target):
        if fs.exists(target):
            raise NotADirectoryError(target)
        raise FileNotFoundError(target)
    entries: list[DirEntry] = []
    for name in fs.listdir(target):
        full = fs.join(target, name)
        is_dir = fs.is_dir(full)
        is_file = not is_dir and fs.exists(full)
        size = 0
        mtime = 0.0
        if with_stat:
            try:
                st = fs.stat(full)
                size, mtime = st.size, st.mtime
                is_dir, is_file = st.is_dir, st.is_file
            except (FileNotFoundError, OSError):
                pass
        entries.append(DirEntry(name=name, is_dir=is_dir, is_file=is_file, size=size, mtime=mtime))
    return entries


def default_read_range(fs: Any, path: PathArg, offset: int, length: int) -> bytes:
    """Slice ``read_bytes`` — correct for a fake, wasteful for anything real."""
    if offset < 0 or length < 0:
        raise ValueError(f"read_range needs non-negative offset/length, got {offset}/{length}")
    if length == 0:
        return b""
    return fs.read_bytes(str(path))[offset : offset + length]


__all__ = ["default_read_range", "default_scandir"]
