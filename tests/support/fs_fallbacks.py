"""Generic ``ls`` / ``read_range`` for in-memory test filesystems.

The real implementations answer a long listing in one pass, which is the whole
point of putting ``ls`` on the Protocol. A test fake has no such constraint, so
it can satisfy the Protocol by composing the per-path calls it already
implements. Call it on the *inner* filesystem, not on the fake whose ``ls``
delegates here — otherwise the call recurses.

These live under ``tests/`` on purpose: shipping a fallback in ``src/`` would
be a code path with no production caller, and worse, it would let a real
filesystem silently keep the N+1 behaviour the bulk ops exist to remove.

Usage in a fake::

    from tests.support.fs_fallbacks import default_ls, default_read_range


    class _FakeFS:
        ...

        def ls(self, path, *, a=False, A=False, l=False):
            return default_ls(self._real, path, a=a, A=A, l=l)

        def read_range(self, path, offset, length):
            return default_read_range(self, path, offset, length)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from molab.fs import DirEntry
from molab.fs.base import select_ls_entries, select_ls_names

if TYPE_CHECKING:
    from molab.fs import PathArg


def default_ls(
    fs: Any,
    path: PathArg,
    *,
    a: bool = False,
    A: bool = False,
    l: bool = False,  # noqa: E741
) -> list[str] | list[DirEntry]:
    """Compose ``ls -A`` plus per-entry ``stat`` into a listing.

    *fs* must already implement ``ls``. This helper applies the caller's flags
    on top of that real-child set, and stats each child only when ``l`` is set.
    """
    target = str(path)
    if not fs.is_dir(target):
        if fs.exists(target):
            raise NotADirectoryError(target)
        raise FileNotFoundError(target)
    names = fs.ls(target, A=True)
    if not l:
        return select_ls_names(names, a=a, A=A)
    entries: list[DirEntry] = []
    for name in names:
        full = fs.join(target, name)
        try:
            st = fs.stat(full)
        except (FileNotFoundError, OSError):
            entries.append(DirEntry(name=name, is_dir=False, is_file=False))
            continue
        entries.append(
            DirEntry(
                name=name,
                is_dir=st.is_dir,
                is_file=st.is_file,
                size=st.size,
                mtime=st.mtime,
            )
        )
    dot = dotdot = None
    if a:
        here = fs.stat(target)
        dot = DirEntry(
            name=".", is_dir=here.is_dir, is_file=here.is_file, size=here.size, mtime=here.mtime
        )
        parent = fs.dirname(target)
        above = fs.stat(target if parent in {"", "."} else parent)
        dotdot = DirEntry(
            name="..",
            is_dir=above.is_dir,
            is_file=above.is_file,
            size=above.size,
            mtime=above.mtime,
        )
    return select_ls_entries(entries, a=a, A=A, dot=dot, dotdot=dotdot)


def default_read_range(fs: Any, path: PathArg, offset: int, length: int) -> bytes:
    """Slice ``read_bytes`` — correct for a fake, wasteful for anything real."""
    if offset < 0 or length < 0:
        raise ValueError(f"read_range needs non-negative offset/length, got {offset}/{length}")
    if length == 0:
        return b""
    return fs.read_bytes(str(path))[offset : offset + length]


__all__ = ["default_ls", "default_read_range"]
