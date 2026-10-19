"""FileSystem contract adapter over molq's public, scoped file APIs."""

from __future__ import annotations

import base64
import io
import os
import posixpath
from collections.abc import Iterable, Sequence
from pathlib import PurePosixPath
from typing import IO, Any

from molq import Molq, MolqError, Path

from .fs import DirEntry, PathArg, StatResult


class RemoteFileSystem:
    """A destination-bound filesystem; molq owns transport and native operations."""

    def __init__(self, client: Molq, cluster_id: str, root: str) -> None:
        self._client = client
        self.cluster_id = cluster_id
        self.root = root

    def _path(self, path: PathArg) -> Path:
        return Path(f"{self.cluster_id}:{os.fspath(path)}", molq=self._client, root=self.root)

    @staticmethod
    def join(*parts: PathArg) -> str:
        return posixpath.join(*(os.fspath(p) for p in parts if p)) if parts else ""

    @staticmethod
    def dirname(path: PathArg) -> str:
        return posixpath.dirname(os.fspath(path)) or "."

    @staticmethod
    def basename(path: PathArg) -> str:
        return posixpath.basename(os.fspath(path))

    def resolve(self, path: PathArg) -> str:
        if ".." in PurePosixPath(os.fspath(path)).parts:
            raise PermissionError("Path traversal is outside the workspace access contract")
        return posixpath.normpath(os.fspath(path))

    @staticmethod
    def is_absolute(path: PathArg) -> bool:
        return os.fspath(path).startswith(("/", "~/"))

    def exists(self, path: PathArg) -> bool:
        return self._path(path).exists()

    def is_dir(self, path: PathArg) -> bool:
        return self._path(path).is_dir()

    def is_file(self, path: PathArg) -> bool:
        return self._path(path).is_file()

    def mkdir(self, path: PathArg, *, parents: bool = True, exist_ok: bool = True) -> None:
        self._path(path).mkdir(parents=parents, exist_ok=exist_ok)

    def scandir(self, path: PathArg, *, with_stat: bool = True) -> list[DirEntry]:
        entries: list[DirEntry] = []
        after = None
        while True:
            page = self._path(path).list_page(with_stat=with_stat, after=after)
            entries.extend(
                DirEntry(
                    name=e["name"],
                    is_dir=e["kind"] == "directory",
                    is_file=e["kind"] == "file",
                    is_symlink=e["is_symlink"],
                    size=e.get("size", 0),
                    mtime=e.get("mtime", 0.0),
                )
                for e in page["entries"]
            )
            after = page.get("next_after")
            if after is None:
                return entries

    def listdir(self, path: PathArg) -> list[str]:
        return [e.name for e in self.scandir(path, with_stat=False)]

    def glob(self, path: PathArg, pattern: str) -> Iterable[str]:
        return (p.as_posix() for p in self._path(path).glob(pattern))

    def rglob(self, path: PathArg, pattern: str) -> Iterable[str]:
        return (p.as_posix() for p in self._path(path).rglob(pattern))

    def read_text(self, path: PathArg, encoding: str = "utf-8") -> str:
        return self._path(path).read_text(encoding=encoding)

    def read_bytes(self, path: PathArg) -> bytes:
        return self._path(path).read_bytes()

    def read_range(self, path: PathArg, offset: int, length: int) -> bytes:
        return self._path(path).read_range(offset, length)

    def read_many(
        self, paths: Sequence[str], *, max_bytes: int = 262144
    ) -> dict[str, bytes | Exception]:
        result: dict[str, bytes | Exception] = {}
        pending = [list(paths[start : start + 128]) for start in range(0, len(paths), 128)]
        while pending:
            requested = pending.pop(0)
            if not requested:
                continue
            batch = self._path(self.root).read_many(requested, max_bytes=max_bytes)
            limited: list[str] = []
            for item in batch["items"]:
                if "data" in item:
                    result[item["path"]] = base64.b64decode(item["data"])
                else:
                    error = item["error"]
                    reason = error["context"].get("reason")
                    if reason == "limit" and len(requested) > 1:
                        limited.append(item["path"])
                    elif reason == "not_found":
                        result[item["path"]] = FileNotFoundError(item["path"])
                    elif reason == "outside_root":
                        result[item["path"]] = PermissionError(item["path"])
                    else:
                        result[item["path"]] = MolqError.from_wire(error)
            if limited:
                # Only explicit capacity failures are split; transport failures propagate.
                width = max(1, len(requested) // 2)
                pending.extend(
                    limited[start : start + width] for start in range(0, len(limited), width)
                )
        return result

    def open(self, path: PathArg, mode: str = "r", encoding: str = "utf-8") -> IO[Any]:
        if mode not in {"r", "rt", "rb"}:
            raise ValueError("Remote open supports read-only buffers")
        return (
            io.BytesIO(self.read_bytes(path))
            if mode == "rb"
            else io.StringIO(self.read_text(path, encoding))
        )

    def write_text(self, path: PathArg, content: str, *, mode: int = 0o600) -> None:
        self.write_bytes(path, content.encode("utf-8"), mode=mode)

    def write_bytes(self, path: PathArg, content: bytes, *, mode: int = 0o600) -> None:
        target = self._path(path)
        target.write_bytes(content)
        target.chmod(mode)

    def rename(self, src: PathArg, dst: PathArg) -> None:
        self._path(src).rename(self._path(dst))

    def remove(self, path: PathArg, *, recursive: bool = False) -> None:
        target = self._path(path)
        if recursive:
            target.remove(recursive=True)
        elif target.is_dir() and not target.is_symlink():
            target.rmdir()
        else:
            target.unlink(missing_ok=True)

    def copy(self, src: PathArg, dst: PathArg) -> None:
        self._path(src).transfer(self._path(dst), "-aL", timeout=3600)

    def copytree(self, src: PathArg, dst: PathArg, *, dirs_exist_ok: bool = False) -> None:
        if not dirs_exist_ok and self.exists(dst):
            raise FileExistsError(os.fspath(dst))
        self._path(src).transfer(self._path(dst), "-aL", timeout=3600)

    def stat(self, path: PathArg) -> StatResult:
        s = self._path(path).stat()
        import stat

        return StatResult(
            size=s.st_size,
            mtime=s.st_mtime,
            is_dir=stat.S_ISDIR(s.st_mode),
            is_file=stat.S_ISREG(s.st_mode),
        )

    def lstat(self, path: PathArg) -> StatResult:
        return self.stat(path)

    def getsize(self, path: PathArg) -> int:
        return self.stat(path).size

    def touch(self, path: PathArg) -> None:
        self._path(path).touch()

    def chmod(self, path: PathArg, mode: int) -> None:
        self._path(path).chmod(mode)

    def symlink(self, src: PathArg, dst: PathArg) -> None:
        self._path(dst).symlink_to(self._path(src))

    def atomic_write_json(self, path: PathArg, data: object) -> None:
        import json

        self.atomic_write_text(
            path, json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        )

    def atomic_write_text(self, path: PathArg, content: str, *, encoding: str = "utf-8") -> None:
        self._path(path).write_text(content, encoding=encoding)

    def upload(
        self,
        local: str,
        remote: str,
        *,
        recursive: bool = False,
        exclude: Sequence[str] = (),
        delete: bool = False,
        dry_run: bool = False,
    ) -> None:
        source = Path(local, molq=self._client)
        if source.is_dir() and not recursive:
            raise IsADirectoryError(local)
        options = ["-a", *(f"--exclude={p}" for p in exclude)]
        if delete:
            options.append("--delete")
        if dry_run:
            options.append("--dry-run")
        source.transfer(self._path(remote), *options, timeout=3600)

    def download(
        self,
        remote: str,
        local: str,
        *,
        recursive: bool = False,
        exclude: Sequence[str] = (),
        delete: bool = False,
        dry_run: bool = False,
    ) -> None:
        source = self._path(remote)
        if source.is_dir() and not recursive:
            raise IsADirectoryError(remote)
        options = ["-a", *(f"--exclude={p}" for p in exclude)]
        if delete:
            options.append("--delete")
        if dry_run:
            options.append("--dry-run")
        source.transfer(Path(local, molq=self._client), *options, timeout=3600)
