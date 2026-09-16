"""Folder directory → streamed zip.

The one workspace-layer zip archiver shared by agent export, server
``export_run``, and any future CLI. All I/O goes through ``folder._fs``
(local and remote backends). Consumers import this module directly
(``from molexp.workspace.archive import archive_folder_zip_iter``) — not
re-exported from ``molexp.workspace`` (same pattern as ``git_projection``).

:func:`archive_folder_zip_iter` is the only form: it yields compressed chunks
and never holds more than one file plus one chunk in memory, so exporting a run
with gigabytes of trajectories does not size the server's RAM to the run. There
is deliberately no buffered ``bytes`` variant — a caller that wants the whole
archive at once can ``b"".join`` it and own that decision explicitly.

Known debt (accepted):
* mode bits are not preserved (``ZipInfo.external_attr = 0``);
* symlink traversal follows the directory walk's semantics.
"""

from __future__ import annotations

import contextlib
import io
import time
import zipfile
from collections.abc import Iterator

from molexp.path import Path as MolexpPath

from .folder import Folder

__all__ = ["archive_folder_zip_iter", "archive_size"]

DEFAULT_CHUNK_BYTES = 1 << 20


class _ChunkSink(io.RawIOBase):
    """A non-seekable sink that hands each written block to a consumer.

    Passing an unseekable stream to :class:`zipfile.ZipFile` makes it emit data
    descriptors instead of rewinding to patch each header — which is exactly
    what lets the archive be produced incrementally.
    """

    def __init__(self) -> None:
        self._buf: list[bytes] = []

    def writable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return False

    def write(self, b, /) -> int:  # noqa: ANN001 - io.RawIOBase signature
        data = bytes(b)
        self._buf.append(data)
        return len(data)

    def pending(self) -> int:
        """Bytes buffered since the last drain."""
        return sum(len(b) for b in self._buf)

    def drain(self) -> bytes:
        """Take everything buffered since the last drain."""
        if not self._buf:
            return b""
        out = b"".join(self._buf)
        self._buf.clear()
        return out


def _walk_files(folder: Folder) -> list[tuple[str, str]]:
    """Every file under *folder* as ``(arcname, abspath)``, sorted by path parts."""
    fs = folder._fs
    root = str(folder.resolve())
    if not fs.is_dir(root):
        return []
    entries: list[tuple[tuple[str, ...], str, str]] = []
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            children = fs.scandir(current)
        except (FileNotFoundError, NotADirectoryError, OSError):
            continue
        for entry in children:
            full = fs.join(current, entry.name)
            if entry.is_dir:
                stack.append(full)
            elif entry.is_file:
                arcname = MolexpPath(full).relative_to(root).as_posix()
                entries.append((MolexpPath(arcname).parts, arcname, full))
    entries.sort(key=lambda t: t[0])
    return [(arcname, path) for _parts, arcname, path in entries]


def archive_size(folder: Folder) -> int:
    """Total uncompressed bytes under *folder* — the pre-flight size check.

    Lets a caller refuse (or warn about) an export before spending the time to
    build one. Cheap: the walk already carries each entry's size.
    """
    fs = folder._fs
    root = str(folder.resolve())
    if not fs.is_dir(root):
        return 0
    total = 0
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            children = fs.scandir(current)
        except (FileNotFoundError, NotADirectoryError, OSError):
            continue
        for entry in children:
            if entry.is_dir:
                stack.append(fs.join(current, entry.name))
            elif entry.is_file:
                total += entry.size
    return total


def archive_folder_zip_iter(
    folder: Folder, *, chunk_bytes: int = DEFAULT_CHUNK_BYTES
) -> Iterator[bytes]:
    """Yield the DEFLATED zip of *folder* in chunks, never buffering it whole.

    Args:
        folder: Any :class:`Folder` (Run, AgentSession, …). Uses
            :meth:`Folder.resolve` (no lazy mkdir) and ``folder._fs``.
        chunk_bytes: Both the read granularity per file and the minimum size
            of a yielded chunk.

    Yields:
        Successive byte blocks of a valid zip archive. A missing or
        non-directory root yields an empty but valid zip.
    """
    fs = folder._fs
    sink = _ChunkSink()
    with zipfile.ZipFile(sink, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for arcname, path in _walk_files(folder):
            info = zipfile.ZipInfo(filename=arcname)
            info.compress_type = zipfile.ZIP_DEFLATED
            with contextlib.suppress(Exception):
                info.date_time = time.localtime(fs.stat(path).mtime)[:6]
            with zf.open(info, mode="w") as dest:
                offset = 0
                while True:
                    block = fs.read_range(path, offset, chunk_bytes)
                    if not block:
                        break
                    dest.write(block)
                    offset += len(block)
                    if sink.pending() >= chunk_bytes:
                        yield sink.drain()
            flushed = sink.drain()
            if flushed:
                yield flushed
    tail = sink.drain()
    if tail:
        yield tail
