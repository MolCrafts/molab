"""Content-addressed payload storage, separate from provenance identity."""

from __future__ import annotations

import hashlib
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict

from molexp.ids import generate_uuid7

from .fs import FileSystem, PathArg
from .fs_local import LocalFileSystem


class ContentRef(BaseModel):
    """Location-independent identity and shape of stored bytes."""

    model_config = ConfigDict(frozen=True)

    digest: str
    size: int
    kind: Literal["file", "directory"]


class ContentStore:
    """SHA-256 CAS supporting both local files and directory packages."""

    def __init__(self, root: PathArg, *, fs: FileSystem | None = None) -> None:
        self.root = str(root)
        self.fs = fs or LocalFileSystem()

    def _object_dir(self, digest: str) -> str:
        bare = digest.removeprefix("sha256:")
        return self.fs.join(self.root, "content", "sha256", bare[:2], bare)

    def _hash_file(self, path: str) -> tuple[str, int]:
        hasher = hashlib.sha256()
        size = 0
        with self.fs.open(path, "rb") as handle:
            while chunk := handle.read(1024 * 1024):
                hasher.update(chunk)
                size += len(chunk)
        return f"sha256:{hasher.hexdigest()}", size

    def _hash_directory(self, path: str) -> tuple[str, int]:
        hasher = hashlib.sha256()
        size = 0
        entries = sorted(item for item in self.fs.rglob(path, "*") if self.fs.is_file(item))
        prefix = path.rstrip("/") + "/"
        for entry in entries:
            rel = entry[len(prefix) :] if entry.startswith(prefix) else self.fs.basename(entry)
            rel_bytes = PurePosixPath(rel).as_posix().encode("utf-8")
            hasher.update(rel_bytes + b"\0")
            with self.fs.open(entry, "rb") as handle:
                while chunk := handle.read(1024 * 1024):
                    hasher.update(chunk)
                    size += len(chunk)
            hasher.update(b"\0")
        return f"sha256:{hasher.hexdigest()}", size

    def put(self, source: PathArg) -> ContentRef:
        source_path = str(source)
        if not self.fs.exists(source_path):
            raise FileNotFoundError(source_path)
        is_dir = self.fs.is_dir(source_path)
        digest, size = self._hash_directory(source_path) if is_dir else self._hash_file(source_path)
        kind: Literal["file", "directory"] = "directory" if is_dir else "file"
        final_dir = self._object_dir(digest)
        payload = self.fs.join(final_dir, "tree" if is_dir else "payload")
        if not self.fs.exists(payload):
            staging = self.fs.join(self.root, "content", ".staging", generate_uuid7())
            self.fs.mkdir(staging, parents=True, exist_ok=False)
            staged_payload = self.fs.join(staging, "tree" if is_dir else "payload")
            try:
                if is_dir:
                    self.fs.copytree(source_path, staged_payload)
                else:
                    self.fs.copy(source_path, staged_payload)
                self.fs.atomic_write_json(
                    self.fs.join(staging, "content.json"),
                    {"schema_version": 2, "digest": digest, "size": size, "kind": kind},
                )
                if self.fs.exists(final_dir):
                    self.fs.remove(staging, recursive=True)
                else:
                    self.fs.mkdir(self.fs.dirname(final_dir), parents=True, exist_ok=True)
                    self.fs.rename(staging, final_dir)
            except BaseException:
                if self.fs.exists(staging):
                    self.fs.remove(staging, recursive=True)
                raise
        ref = ContentRef(digest=digest, size=size, kind=kind)
        if not self.verify(ref):
            raise OSError(f"content verification failed after put: {digest}")
        return ref

    def payload_path(self, ref: ContentRef) -> str:
        return self.fs.join(
            self._object_dir(ref.digest), "tree" if ref.kind == "directory" else "payload"
        )

    def verify(self, ref: ContentRef) -> bool:
        payload = self.payload_path(ref)
        if not self.fs.exists(payload):
            return False
        digest, size = (
            self._hash_directory(payload) if ref.kind == "directory" else self._hash_file(payload)
        )
        return digest == ref.digest and size == ref.size


__all__ = ["ContentRef", "ContentStore"]
