"""The user-facing byte-exit under one directory root.

A :class:`FileStore` is *files in a place*. It does not own a disk: the
:class:`~molexp.workspace.fs.FileSystem` (the disk) is injected, usually
from :attr:`Workspace.fs`. Relative paths only; escape is rejected.

``put`` is atomic (temp + rename on the local disk; the FileSystem
atomic helpers on a remote). Catalog registration is orthogonal.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterable
from os import PathLike, fspath
from pathlib import Path, PurePosixPath

from molexp.atomicio import atomic_write_bytes, atomic_write_json, atomic_write_text

from .fs import FileSystem
from .fs_local import LocalFileSystem


def _unshare(target: Path) -> None:
    """Break a hard link before appending, so only this file grows.

    A hard-linked file is the *same* file under two names, so appending to it
    inside a workspace also appends to whatever else points at that inode —
    which is exactly how an archive built with hard links (``molexp migrate``)
    stops being a snapshot of its source. Replacing the file with a private
    copy first costs one copy the first time and nothing after.
    """
    try:
        if not target.is_file() or target.stat().st_nlink < 2:
            return
    except OSError:
        return
    private = target.with_name(f"{target.name}.unshare.{os.getpid()}")
    try:
        shutil.copy2(target, private)
        private.replace(target)
    except OSError:
        private.unlink(missing_ok=True)


_PutData = Path | bytes | bytearray | dict | list | str


class FileStore:
    """Write files under *root* on *fs*. Relative paths only."""

    def __init__(
        self,
        root: str | PathLike[str],
        *,
        fs: FileSystem | None = None,
    ) -> None:
        self._root = fspath(root)
        self._fs: FileSystem = fs if fs is not None else LocalFileSystem()

    @property
    def root(self) -> str:
        return self._root

    def resolve(self, relpath: str | Path) -> Path:
        """Return ``root/relpath`` if it stays inside *root*."""
        rel = PurePosixPath(fspath(relpath))
        if rel.is_absolute():
            raise ValueError(f"FileStore: path must be relative, got {relpath!r}")
        if ".." in rel.parts:
            raise ValueError(f"FileStore: path {relpath!r} escapes root {self._root}")
        return Path(self._fs.join(self._root, str(rel)))

    def mkdir(self, relpath: str | Path) -> Path:
        """Create *relpath* under the root and return a local :class:`~pathlib.Path`."""
        target = self.resolve(relpath)
        self._fs.mkdir(str(target), parents=True, exist_ok=True)
        return target

    def put(self, relpath: str | Path, data: _PutData) -> Path:
        """Atomically write *data* at *relpath*. Returns the destination path."""
        target = self.resolve(relpath)
        if isinstance(self._fs, LocalFileSystem):
            if isinstance(data, (bytes, bytearray)):
                atomic_write_bytes(target, bytes(data))
            elif isinstance(data, Path):
                src = Path(data)
                try:
                    already = target.exists() and src.resolve().samefile(target.resolve())
                except OSError:
                    already = False
                if not already:
                    atomic_write_bytes(target, src.read_bytes())
            elif isinstance(data, (dict, list)):
                atomic_write_json(target, data)
            else:
                atomic_write_text(target, str(data))
            return target
        self._put_via_fs(str(target), data)
        return target

    def _put_via_fs(self, target: str, data: _PutData) -> None:
        disk = self._fs
        parent = disk.dirname(target)
        if parent:
            disk.mkdir(parent, parents=True, exist_ok=True)
        if isinstance(data, (bytes, bytearray)):
            disk.write_bytes(target, bytes(data))
        elif isinstance(data, Path):
            disk.write_bytes(target, data.read_bytes())
        elif isinstance(data, (dict, list)):
            disk.atomic_write_json(target, data)
        else:
            disk.atomic_write_text(target, str(data))

    def append_many(self, relpath: str | Path, lines: Iterable[str]) -> Path:
        """Append every line in one open — the bulk path, unshared once."""
        target = self.resolve(relpath)
        if isinstance(self._fs, LocalFileSystem):
            target.parent.mkdir(parents=True, exist_ok=True)
            _unshare(target)
            with target.open("a", encoding="utf-8") as fh:
                for line in lines:
                    fh.write(line if line.endswith("\n") else line + "\n")
            return target
        for line in lines:
            self.append(relpath, line)
        return target

    def append(self, relpath: str | Path, line: str) -> Path:
        """Append *line* (a trailing newline is added if missing)."""
        target = self.resolve(relpath)
        payload = line if line.endswith("\n") else line + "\n"
        if isinstance(self._fs, LocalFileSystem):
            target.parent.mkdir(parents=True, exist_ok=True)
            _unshare(target)
            with target.open("a", encoding="utf-8") as fh:
                fh.write(payload)
            return target
        dest = str(target)
        existing = self._fs.read_text(dest) if self._fs.exists(dest) else ""
        self._fs.atomic_write_text(dest, existing + payload)
        return target
