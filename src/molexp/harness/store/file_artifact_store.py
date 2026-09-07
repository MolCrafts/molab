"""Harness adapter over the canonical Execution Artifact repository.

Two projections share this class:

* **scratch** (``root=``) — content-addressed filesystem store for transient
  harness profiles with no Project/Run/Execution (one-shot chat, unit tests).
  ``put_*`` is idempotent per ``(kind, content)``: identical bytes under one
  kind reuse the ref (id unions in newly supplied ``parent_ids``), identical
  bytes under two kinds stay distinct.
* **execution** (:meth:`for_execution` / :meth:`open_execution`) — bound to one
  physical Execution. Each ``put_*`` is an ``ExecutionContext.emit_artifact``
  call and the returned id is the canonical Artifact UUID. Equal bytes may
  deduplicate in the Content Store while retaining distinct provenance
  identities.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from molexp.harness.errors import ArtifactNotFoundError
from molexp.harness.schemas import ArtifactKind, PlanArtifactRef
from molexp.ids import generate_uuid7
from molexp.workspace import atomic_write_json, atomic_write_text
from molexp.workspace.execution_dirs import WORK
from molexp.workspace.utils import compute_content_hash

if TYPE_CHECKING:
    from molexp.workspace.domain import Artifact
    from molexp.workspace.execution_context import ExecutionContext
    from molexp.workspace.run import Run

__all__ = ["FileArtifactStore"]

_ID_LEN = 16  # 64 bits of sha256 — collision-free at harness scale.


def _hash_path(path: Path) -> str:
    """Return bare-hex sha256 of an on-disk file/dir via the workspace helper."""
    return compute_content_hash(path).removeprefix("sha256:")


def _derive_id(kind: ArtifactKind, sha: str) -> str:
    """Derive a scratch artifact id from ``(kind, content_sha)``."""
    return hashlib.sha256(f"{kind}:{sha}".encode()).hexdigest()[:_ID_LEN]


class FileArtifactStore:
    """Compatibility projection of canonical Execution Artifacts."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)
        self._refs_dir = self._root / "_refs"
        self._index_dir = self._root / "_index"
        self._context: ExecutionContext | None = None
        self._run: Run | None = None
        self._execution_id: str | None = None
        self._workspace_root: str | None = None
        self._fs = None

    @classmethod
    def for_execution(cls, context: ExecutionContext) -> FileArtifactStore:
        """Create the writable adapter for one entered Execution."""
        store = cls(context.get_dir("work", "harness"))
        workspace = context.run.experiment.project.workspace
        store._context = context
        store._run = context.run
        store._execution_id = context.id
        store._workspace_root = str(workspace.root)
        store._fs = workspace.fs
        return store

    @classmethod
    def open_execution(cls, run: Run, execution_id: str) -> FileArtifactStore:
        """Open the read-only Artifact projection for an explicit Execution."""
        store = cls(Path(run.run_dir) / "executions" / execution_id / WORK.name / "harness")
        workspace = run.experiment.project.workspace
        store._run = run
        store._execution_id = execution_id
        store._workspace_root = str(workspace.root)
        store._fs = workspace.fs
        return store

    @property
    def execution_id(self) -> str | None:
        return self._execution_id

    def put_json(
        self,
        kind: ArtifactKind,
        obj: object,
        created_by: str,
        parent_ids: list[str],
    ) -> PlanArtifactRef:
        if self._context is not None:
            return self._emit(
                kind,
                obj,
                name=f"{kind}-{generate_uuid7()}.json",
                media_type="application/json",
                created_by=created_by,
                parent_ids=parent_ids,
            )
        return self._put_via_staging(
            kind=kind,
            suffix=".json",
            write_staged=lambda staged: atomic_write_json(staged, obj),
            created_by=created_by,
            parent_ids=parent_ids,
        )

    def put_text(
        self,
        kind: ArtifactKind,
        text: str,
        created_by: str,
        parent_ids: list[str],
    ) -> PlanArtifactRef:
        if self._context is not None:
            return self._emit(
                kind,
                text,
                name=f"{kind}-{generate_uuid7()}.txt",
                media_type="text/plain",
                created_by=created_by,
                parent_ids=parent_ids,
            )
        return self._put_via_staging(
            kind=kind,
            suffix=".txt",
            write_staged=lambda staged: atomic_write_text(staged, text),
            created_by=created_by,
            parent_ids=parent_ids,
        )

    def put_file(
        self,
        kind: ArtifactKind,
        path: Path,
        created_by: str,
        parent_ids: list[str],
    ) -> PlanArtifactRef:
        source = Path(path)
        if self._context is not None:
            destination = (
                self._context.get_dir("work", "harness", kind) / f"{generate_uuid7()}-{source.name}"
            )
            destination.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(source, destination)
            else:
                shutil.copy2(source, destination)
            return self._emit_path(
                kind,
                destination,
                created_by=created_by,
                parent_ids=parent_ids,
            )

        sha = _hash_path(source)
        existing = self._find_existing(kind, sha)
        if existing is not None:
            return self.merge_parent_ids(existing.id, parent_ids)

        artifact_id = _derive_id(kind, sha)
        dest_dir = self._root / kind
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{artifact_id}-{source.name}"
        if source.is_dir():
            shutil.copytree(source, dest)
        else:
            shutil.copy2(source, dest)
        return self._finalize(
            artifact_id=artifact_id,
            kind=kind,
            content_path=dest,
            sha=sha,
            created_by=created_by,
            parent_ids=parent_ids,
        )

    def _emit(
        self,
        kind: ArtifactKind,
        value: object,
        *,
        name: str,
        media_type: str,
        created_by: str,
        parent_ids: list[str],
    ) -> PlanArtifactRef:
        assert self._context is not None
        path = self._context.get_dir("work", "harness", kind) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(value, (bytes, bytearray)):
            path.write_bytes(bytes(value))
        elif isinstance(value, (dict, list)):
            path.write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")
        else:
            path.write_text(str(value), encoding="utf-8")
        artifact = self._context.emit_artifact(
            path,
            name=f"harness/{kind}/{name}",
            media_type=media_type,
            semantic_type=kind,
            metadata={"harness_created_by": created_by},
            consumed=parent_ids,
        )
        return self._project(artifact)

    def _emit_path(
        self,
        kind: ArtifactKind,
        path: Path,
        *,
        created_by: str,
        parent_ids: list[str],
    ) -> PlanArtifactRef:
        assert self._context is not None
        artifact = self._context.emit_artifact(
            path,
            semantic_type=kind,
            metadata={"harness_created_by": created_by},
            consumed=parent_ids,
        )
        return self._project(artifact)

    def get(self, artifact_id: str) -> bytes:
        if self._fs is not None and self._workspace_root is not None:
            artifact = self._lookup(artifact_id)
            path = self._fs.join(self._workspace_root, artifact.path)
            if self._fs.is_dir(path):
                raise IsADirectoryError(path)
            if not self._fs.is_file(path):
                raise ArtifactNotFoundError(f"artifact {artifact_id!r} content is missing")
            return self._fs.read_bytes(path)
        ref = self.get_ref(artifact_id)
        path = Path(ref.uri.removeprefix("file://"))
        if not path.exists():
            raise ArtifactNotFoundError(f"artifact {artifact_id!r} content is missing")
        return path.read_bytes()

    def get_ref(self, artifact_id: str) -> PlanArtifactRef:
        if self._run is not None and self._execution_id is not None:
            return self._project(self._lookup(artifact_id))
        path = self._refs_dir / f"{artifact_id}.json"
        if not path.exists():
            raise ArtifactNotFoundError(f"artifact {artifact_id!r} not found")
        return PlanArtifactRef.model_validate_json(path.read_text(encoding="utf-8"))

    def list_by_kind(self, kind: ArtifactKind) -> list[PlanArtifactRef]:
        if self._run is not None and self._execution_id is not None:
            return [ref for ref in self.list_refs() if ref.kind == kind]
        return [self.get_ref(aid) for aid in self._read_index(kind)]

    def latest_by_kind(self, kind: ArtifactKind) -> PlanArtifactRef | None:
        if self._run is not None and self._execution_id is not None:
            refs = self.list_by_kind(kind)
            if not refs:
                return None
            return max(refs, key=lambda item: (item.created_at, item.id))
        index = self._read_index(kind)
        if not index:
            return None
        return self.get_ref(index[-1])

    def list_refs(self) -> list[PlanArtifactRef]:
        if self._run is not None and self._execution_id is not None:
            return [
                self._project(item)
                for item in self._execution_artifacts()
                if item.semantic_type is not None
            ]
        if not self._refs_dir.exists():
            return []
        refs = [
            PlanArtifactRef.model_validate_json(path.read_text(encoding="utf-8"))
            for path in self._refs_dir.glob("*.json")
        ]
        return sorted(refs, key=lambda item: (item.created_at, item.id))

    def merge_parent_ids(self, artifact_id: str, parent_ids: list[str]) -> PlanArtifactRef:
        """Union *parent_ids* into a scratch ref; execution provenance is immutable."""
        if self._run is not None:
            ref = self.get_ref(artifact_id)
            missing = [value for value in parent_ids if value not in ref.parent_ids]
            if missing:
                raise RuntimeError(
                    "Artifact provenance is immutable; supply parent_ids when emitting the Artifact"
                )
            return ref
        existing = self.get_ref(artifact_id)
        merged: list[str] = list(existing.parent_ids)
        added = False
        for pid in parent_ids:
            if pid not in merged:
                merged.append(pid)
                added = True
        if not added:
            return existing
        updated = existing.model_copy(update={"parent_ids": merged})
        atomic_write_json(
            self._refs_dir / f"{existing.id}.json",
            json.loads(updated.model_dump_json()),
        )
        return updated

    def _execution_artifacts(self) -> list[Artifact]:
        """Products of this attempt, read from its own ``execution.json``."""
        if self._run is None or self._execution_id is None:
            return []
        for execution in self._run.executions:
            if execution.id == self._execution_id:
                return list(execution.artifacts)
        return []

    def _lookup(self, artifact_id: str) -> Artifact:
        for artifact in self._execution_artifacts():
            if artifact.id == artifact_id:
                return artifact
        raise ArtifactNotFoundError(f"artifact {artifact_id!r} not found")

    def _project(self, artifact: Artifact) -> PlanArtifactRef:
        return PlanArtifactRef(
            id=artifact.id,
            kind=artifact.semantic_type or "artifact",
            uri=f"molexp://{artifact.path}",
            sha256=artifact.content.digest.removeprefix("sha256:"),
            created_at=artifact.created_at,
            created_by=artifact.created_by.name or artifact.created_by.id,
            parent_ids=list(artifact.input_entity_ids),
            metadata=dict(artifact.metadata),
        )

    def _put_via_staging(
        self,
        *,
        kind: ArtifactKind,
        suffix: str,
        write_staged: Callable[[Path], None],
        created_by: str,
        parent_ids: list[str],
    ) -> PlanArtifactRef:
        kind_dir = self._root / kind
        kind_dir.mkdir(parents=True, exist_ok=True)
        fd, staged_str = tempfile.mkstemp(prefix=".staging_", suffix=suffix, dir=kind_dir)
        os.close(fd)
        staged = Path(staged_str)
        staged.unlink()
        try:
            write_staged(staged)
            sha = _hash_path(staged)
            existing = self._find_existing(kind, sha)
            if existing is not None:
                staged.unlink(missing_ok=True)
                return self.merge_parent_ids(existing.id, parent_ids)

            artifact_id = _derive_id(kind, sha)
            final = kind_dir / f"{artifact_id}{suffix}"
            staged.replace(final)
        except BaseException:
            staged.unlink(missing_ok=True)
            raise

        return self._finalize(
            artifact_id=artifact_id,
            kind=kind,
            content_path=final,
            sha=sha,
            created_by=created_by,
            parent_ids=parent_ids,
        )

    def _find_existing(self, kind: ArtifactKind, sha: str) -> PlanArtifactRef | None:
        artifact_id = _derive_id(kind, sha)
        ref_path = self._refs_dir / f"{artifact_id}.json"
        if not ref_path.exists():
            return None
        ref = PlanArtifactRef.model_validate_json(ref_path.read_text(encoding="utf-8"))
        if ref.kind != kind or ref.sha256 != sha:
            return None
        return ref

    def _finalize(
        self,
        *,
        artifact_id: str,
        kind: ArtifactKind,
        content_path: Path,
        sha: str,
        created_by: str,
        parent_ids: list[str],
    ) -> PlanArtifactRef:
        ref = PlanArtifactRef(
            id=artifact_id,
            kind=kind,
            uri=f"file://{content_path.resolve()}",
            sha256=sha,
            created_at=datetime.now(tz=UTC),
            created_by=created_by,
            parent_ids=list(parent_ids),
            metadata={},
        )
        atomic_write_json(self._refs_dir / f"{artifact_id}.json", json.loads(ref.model_dump_json()))
        self._append_to_index(kind, artifact_id)
        return ref

    def _read_index(self, kind: ArtifactKind) -> list[str]:
        index_path = self._index_dir / f"{kind}.json"
        if not index_path.exists():
            return []
        return json.loads(index_path.read_text(encoding="utf-8"))

    def _append_to_index(self, kind: ArtifactKind, artifact_id: str) -> None:
        index = self._read_index(kind)
        if artifact_id in index:
            return
        index.append(artifact_id)
        atomic_write_json(self._index_dir / f"{kind}.json", index)
