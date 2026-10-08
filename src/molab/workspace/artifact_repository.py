"""Execution Artifact emission and scope-level Asset promotion.

An Artifact is a *file that stayed*: emitting one copies it into the
attempt's ``artifacts/`` tier, hashes it, and attaches the record to the
Execution that produced it. ``locate`` is the only way back to those bytes.
There is no second copy in a content-addressed side store — the file is the
artifact, and git already deduplicates the small ones it tracks.

An Asset is a named identity over such files at workspace, project, or
experiment scope. Its records live in ``<scope>/assets/<asset>/`` where a
person can find them. Runs are not asset hosts.
"""

from __future__ import annotations

import builtins
import hashlib
import json
import os
import shutil
from collections.abc import Iterator, Sequence
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, cast, get_args

from pydantic import BaseModel, ConfigDict

from molab._typing import JSONValue
from molab.ids import generate_uuid7

from ._file_lock import file_lock
from .domain import (
    RESULT_SEMANTIC_TYPE,
    Artifact,
    ArtifactOrigin,
    ArtifactRef,
    Asset,
    AssetScope,
    AssetVersion,
    ContentRef,
    ImportAction,
    ImportOrigin,
)
from .errors import UnmigratedAssetError
from .execution_dirs import ARTIFACTS, execution_dir_names
from .fs import FileSystem, PathArg
from .fs_local import LocalFileSystem
from .history import SYSTEM_AGENT, AgentRef, EntityRef, GitHistory, Relation
from .naming import entity_slug
from .refs import MolabRef, parse_ref
from .schema_version import versioned_payload

if TYPE_CHECKING:
    from .workspace import Workspace

#: First path component under ``artifacts/`` that molab reserves (``_molab``).
RESERVED_ARTIFACT_DIR = "_molab"


def _hash_file(fs: FileSystem, path: str) -> tuple[str, int]:
    hasher = hashlib.sha256()
    size = 0
    with fs.open(path, "rb") as handle:
        while chunk := handle.read(1024 * 1024):
            hasher.update(chunk)
            size += len(chunk)
    return f"sha256:{hasher.hexdigest()}", size


def _hash_tree(fs: FileSystem, path: str) -> tuple[str, int]:
    hasher = hashlib.sha256()
    size = 0
    prefix = path.rstrip("/") + "/"
    for entry in sorted(item for item in fs.rglob(path, "*") if fs.is_file(item)):
        rel = entry[len(prefix) :] if entry.startswith(prefix) else fs.basename(entry)
        hasher.update(PurePosixPath(rel).as_posix().encode() + b"\0")
        with fs.open(entry, "rb") as handle:
            while chunk := handle.read(1024 * 1024):
                hasher.update(chunk)
                size += len(chunk)
        hasher.update(b"\0")
    return f"sha256:{hasher.hexdigest()}", size


def content_ref(fs: FileSystem, path: PathArg) -> ContentRef:
    """Identify bytes where they already live — no copy, no side store."""
    target = str(path)
    if fs.is_dir(target):
        digest, size = _hash_tree(fs, target)
        return ContentRef(digest=digest, size=size, kind="directory")
    digest, size = _hash_file(fs, target)
    return ContentRef(digest=digest, size=size, kind="file")


class ArtifactRepository:
    """Repository for outputs explicitly emitted by an Execution."""

    def __init__(
        self,
        workspace_root: PathArg,
        *,
        fs: FileSystem | None = None,
        history: GitHistory | None = None,
    ) -> None:
        self.root = str(workspace_root)
        self.fs = fs or LocalFileSystem()
        self.history = history or GitHistory(self.root)

    def emit(
        self,
        source: PathArg,
        *,
        execution_dir: PathArg,
        execution_id: str,
        run_id: str,
        project_id: str,
        created_by: AgentRef,
        name: str | None = None,
        media_type: str | None = None,
        semantic_type: str | None = None,
        declaration_id: str | None = None,
        input_entity_ids: tuple[str, ...] = (),
        metadata: dict[str, JSONValue] | None = None,
        recorded: Sequence[Artifact] = (),
        reserved: bool = False,
    ) -> Artifact:
        """Promote one file/package produced by this attempt into ``artifacts/``.

        The source may sit in any of the attempt's directories — scratch
        ``work/``, bulk ``out/``, or the attempt root where a solver dropped
        it. Anything outside the attempt is refused: an Artifact is a product
        of *this* attempt. Within one Execution a relative path maps to at
        most one Artifact.
        """
        source_path = self.fs.resolve(source)
        execution_root = self.fs.resolve(execution_dir).rstrip("/")
        if source_path != execution_root and not source_path.startswith(execution_root + "/"):
            raise ValueError(f"emit_artifact source must be inside this Execution: {source_path}")
        if not self.fs.exists(source_path):
            raise FileNotFoundError(source_path)

        # Promotion is the same from every tier: strip whichever declared
        # directory the source sits in, and land under ``artifacts/`` keeping
        # the rest of its shape. Scratch, bulk output and an already-promoted
        # file all take this one path — none of them is special-cased.
        from_exec = source_path[len(execution_root) :].lstrip("/")
        head, _, tail = from_exec.partition("/")
        rel_path = tail if head in execution_dir_names() and tail else from_exec
        rel_path = rel_path or self.fs.basename(source_path)
        out_rel = PurePosixPath(ARTIFACTS.name, rel_path).as_posix()
        out_path = self.fs.join(execution_root, out_rel)
        # Both refusals run before any write, so a rejected emit leaves bytes as they were.
        if not reserved and (
            PurePosixPath(rel_path).parts[0] == RESERVED_ARTIFACT_DIR
            or semantic_type == RESULT_SEMANTIC_TYPE
        ):
            raise ValueError("artifacts/_molab/ and semantic_type 'result' are reserved for molab")
        for existing in recorded:
            if existing.path == out_rel:
                raise ValueError(
                    f"artifact path {out_rel!r} is already recorded by Artifact "
                    f"{existing.id} in Execution {execution_id}; emit under a different name"
                )
        self.fs.mkdir(self.fs.dirname(out_path), parents=True, exist_ok=True)
        if self.fs.resolve(out_path) != source_path:
            if self.fs.is_dir(source_path):
                self.fs.copytree(source_path, out_path)
            else:
                self.fs.copy(source_path, out_path)

        now = datetime.now(UTC)
        artifact = Artifact(
            id=generate_uuid7(),
            execution_id=execution_id,
            run_id=run_id,
            project_id=project_id,
            name=name or self.fs.basename(source_path),
            content=content_ref(self.fs, out_path),
            created_at=now,
            created_by=created_by,
            path=out_rel,
            # Where it actually came from, verbatim — not reconstructed.
            source_path=from_exec or out_rel,
            media_type=media_type,
            semantic_type=semantic_type,
            declaration_id=declaration_id,
            input_entity_ids=input_entity_ids,
            metadata=metadata or {},
        )
        self.history.record(
            "ArtifactEmitted",
            subject=EntityRef(id=artifact.id, type="artifact"),
            agent=created_by,
            relations=(
                Relation(
                    predicate="wasGeneratedBy",
                    object=EntityRef(id=execution_id, type="execution"),
                ),
                *(
                    Relation(predicate="wasDerivedFrom", object=EntityRef(id=value, type="entity"))
                    for value in input_entity_ids
                ),
            ),
            summary=f"{artifact.name} from {self.fs.basename(execution_root)}",
            paths=(execution_root,),
            occurred_at=now,
        )
        return artifact

    def locate(self, artifact: Artifact, *, execution_dir: PathArg) -> str:
        """Resolve an Artifact record to a path on this repository's filesystem.

        The one path-to-location implementation. A new record stores a POSIX
        path relative to the execution directory. Its first segment is a
        declared execution-directory name (:func:`execution_dir_names`), not
        a hard-coded ``artifacts/`` prefix, and the result is
        ``fs.join(execution_dir, path)``.

        Anything else is the permanent legacy read. Records sealed before
        05b store a workspace-relative path, and a sealed ``execution.json``
        is never rewritten, so this branch stays: ``fs.resolve`` of the path
        joined onto the workspace root must land inside
        ``fs.resolve(execution_dir)``. No I/O except that ``fs.resolve``.

        Args:
            artifact: The record to resolve.
            execution_dir: Attempt directory the location must stay inside.

        Returns:
            A path string on ``self.fs``.

        Raises:
            ValueError: ``artifact.path`` is empty, absolute, or contains a
                ``..`` segment, or a legacy path resolves outside
                *execution_dir*.
        """
        path = artifact.path
        pure = PurePosixPath(path)
        if path == "" or pure.is_absolute() or ".." in pure.parts:
            raise ValueError(
                f"artifact path {path!r} must be a relative execution path without '..'"
            )
        if pure.parts[0] in execution_dir_names():
            return self.fs.join(execution_dir, path)
        resolved = self.fs.resolve(self.fs.join(self.root, path))
        execution_root = self.fs.resolve(execution_dir).rstrip("/")
        if resolved != execution_root and not resolved.startswith(execution_root + "/"):
            raise ValueError(
                f"artifact path {resolved} is outside Execution directory {execution_dir}"
            )
        return resolved

    def read_bytes(self, artifact: Artifact, *, execution_dir: PathArg) -> bytes:
        """Read the bytes of one emitted Artifact from inside one attempt.

        Resolves the record through :meth:`locate` and reads that file.

        Args:
            artifact: The record whose bytes to read.
            execution_dir: Attempt directory passed to :meth:`locate`.

        Returns:
            The file contents.

        Raises:
            ValueError: :meth:`locate` rejects the path.
            FileNotFoundError: The resolved location is not a file.
        """
        location = self.locate(artifact, execution_dir=execution_dir)
        if not self.fs.is_file(location):
            raise FileNotFoundError(location)
        return self.fs.read_bytes(location)


def _legacy_tree_size(fs: FileSystem, path: str) -> int:
    """Sum of file sizes under *path*, via ``scandir`` and without hashing."""
    total = 0
    for entry in fs.scandir(path, with_stat=True):
        if entry.is_dir and not entry.is_symlink:
            total += _legacy_tree_size(fs, fs.join(path, entry.name))
        elif entry.is_file:
            total += entry.size
    return total


def _legacy_content(fs: FileSystem, payload: str, digest: str | None) -> ContentRef | None:
    """Measure a legacy payload's size without hashing it again.

    Args:
        fs: Filesystem the payload lives on.
        payload: Absolute path of the bytes.
        digest: Stored content hash, or ``None`` when the import stored none.

    Returns:
        A content reference using *digest* and the measured size, or ``None``
        when there is no digest or the bytes are gone.
    """
    if digest is None or payload == "":
        return None
    try:
        info = fs.stat(payload)
    except FileNotFoundError:
        return None
    if info.is_dir:
        return ContentRef(digest=digest, size=_legacy_tree_size(fs, payload), kind="directory")
    if not info.is_file:
        return None
    return ContentRef(digest=digest, size=info.size, kind="file")


def _legacy_posix(value: object) -> str:
    if not isinstance(value, str) or value == "":
        return ""
    return value.replace("\\", "/")


def _legacy_data_asset(
    raw: dict[str, object],
    *,
    scope: AssetScope,
    fs: FileSystem,
    scope_dir: str,
) -> tuple[Asset, AssetVersion]:
    """Map one ``asset_id`` record (no ``id``) onto an Asset and its ``v001`` import.

    Migration only. :meth:`AssetRepository.rewrite_legacy` is the caller.
    Readers do not use this.

    Args:
        raw: Parsed ``asset.json`` with ``asset_id`` and no ``id``.
        scope: Scope that owns the directory.
        fs: Filesystem the bytes are on.
        scope_dir: Scope directory *path* is relative to.

    Returns:
        The synthesized asset and its single import version.

    Raises:
        ValueError: The record has no ``asset_id``.
    """
    asset_id = raw.get("asset_id")
    if not isinstance(asset_id, str) or asset_id == "":
        raise ValueError("legacy asset record has no asset_id")
    external = raw.get("external_uri")
    source = raw.get("source_path")
    if isinstance(external, str) and external:
        uri = external
        location: str | None = None
        payload = external
    else:
        uri = source if isinstance(source, str) else ""
        location = _legacy_posix(raw.get("path")) or None
        payload = fs.join(scope_dir, location) if location else ""
    producer = raw.get("producer")
    input_ids: tuple[str, ...] = ()
    if isinstance(producer, dict):
        raw_inputs = producer.get("inputs")
        if isinstance(raw_inputs, list) and all(isinstance(item, str) for item in raw_inputs):
            input_ids = tuple(item for item in raw_inputs if isinstance(item, str))
    name = raw.get("name")
    tags_raw = raw.get("tags")
    digest = raw.get("content_hash")
    asset = Asset.model_validate(
        {
            "id": asset_id,
            "scope": scope,
            "title": name if isinstance(name, str) else "",
            "tags": tags_raw if isinstance(tags_raw, dict) else {},
            "created_at": raw.get("created_at"),
            "created_by": SYSTEM_AGENT,
        }
    )
    version = AssetVersion.model_validate(
        {
            "id": f"{asset_id}-v001",
            "asset_id": asset_id,
            "version": 1,
            "created_at": raw.get("created_at"),
            "created_by": SYSTEM_AGENT,
            "origin": {
                "kind": "import",
                "uri": uri,
                "action": raw.get("import_action"),
                "location": location,
                "input_ids": input_ids,
            },
            "content": _legacy_content(
                fs, payload, digest if isinstance(digest, str) and digest else None
            ),
        }
    )
    return asset, version


def _legacy_asset_reason(raw: dict[str, object]) -> str | None:
    """Why *raw* ``asset.json`` is not the unified record, or ``None``.

    Shape keys only. ``schema_version`` is shared by every entity file and
    is not a reason. The four reasons, with :func:`_legacy_version_reason`,
    are the whole test.
    """
    if "id" not in raw:
        return "data-import record"
    if "project_id" in raw or "scope" in raw:
        return "persisted project_id"
    return None


def _legacy_version_reason(raw: dict[str, object]) -> str | None:
    """Why one version file is not the unified record, or ``None``."""
    if "origin" not in raw or "source_artifact_id" in raw or "path" in raw:
        return "pre-origin version"
    origin = raw.get("origin")
    if isinstance(origin, dict) and origin.get("kind") == "artifact" and not origin.get("ref"):
        return "unqualified artifact origin"
    return None


class LegacyRewrite(BaseModel):
    """What :meth:`AssetRepository.rewrite_legacy` rewrote or could not qualify."""

    model_config = ConfigDict(frozen=True)

    rewritten: tuple[str, ...]
    unresolved: tuple[str, ...]


class LegacyAssetMigration(BaseModel):
    """What :func:`migrate_legacy_assets` rewrote, removed, and committed.

    Paths are POSIX paths relative to the workspace root.
    """

    model_config = ConfigDict(frozen=True)

    dry_run: bool
    rewritten: tuple[str, ...]
    unresolved: tuple[str, ...]
    manifests_removed: tuple[str, ...]
    commit: str | None


class AssetRepository:
    """Long-term data identities and immutable versions at one scope.

    Records live under ``<scope>/assets/<slug>/``: ``asset.json`` plus one
    file per version. Listing assets is listing that directory; there is no
    derived index to fall out of step with it. A record that still uses an
    ``asset_id`` key, a persisted ``project_id`` or ``scope``, or a version
    without a qualified ``origin`` is unreadable until :meth:`rewrite_legacy`.
    """

    def __init__(
        self,
        workspace: Workspace,
        scope: AssetScope,
        scope_dir: PathArg,
        *,
        history: GitHistory | None = None,
    ) -> None:
        """Bind a repository to one scope directory.

        Args:
            workspace: Workspace that owns ``find`` and the artifact walk.
            scope: Scope injected into every record read from *scope_dir*.
            scope_dir: Directory whose ``assets/`` child holds the records.
            history: History writer. Defaults to the workspace history.
        """
        self.workspace = workspace
        self.root = str(workspace.root)
        self.scope = scope
        self.scope_dir = str(scope_dir)
        self.fs = workspace.fs
        self.history = history or GitHistory(self.root)

    @property
    def assets_dir(self) -> str:
        return self.fs.join(self.scope_dir, "assets")

    def promote(
        self,
        artifact: Artifact | ArtifactRef | str,
        *,
        created_by: AgentRef,
        title: str | None = None,
        into_asset_id: str | None = None,
        metadata: dict[str, JSONValue] | None = None,
    ) -> tuple[Asset, AssetVersion]:
        """Register an Artifact as a new Asset, or as the next version of one."""
        if not isinstance(artifact, Artifact):
            raise TypeError(
                "promote() needs the Artifact itself — read it from the Execution "
                "that emitted it (run.execution(...).artifact(id))"
            )
        if self.scope.project_id is not None and artifact.project_id != self.scope.project_id:
            raise ValueError("Artifact and target Asset project must match")
        with self._assets_lock():
            return self._promote_locked(
                artifact,
                created_by=created_by,
                title=title,
                into_asset_id=into_asset_id,
                metadata=metadata,
            )

    def import_asset(
        self,
        name: str,
        src: str | Path,
        action: ImportAction = "copy",
        meta: dict[str, str] | None = None,
        *,
        consumed: Sequence[str] | None = None,
    ) -> Asset:
        """Import bytes as a new asset with one import version.

        Args:
            name: Display title and slug source.
            src: File or directory to import.
            action: How the bytes are materialized.
            meta: String tags stored on the asset.
            consumed: Upstream ids recorded on the import origin.

        Returns:
            The new asset. Its version is ``versions(asset.id)``.

        Raises:
            NotImplementedError: The workspace filesystem is not local.
            FileNotFoundError: *src* does not exist.
            ValueError: *action* is not an import action.
        """
        self._require_local()
        source = Path(src)
        if not source.exists():
            raise FileNotFoundError(f"Source path does not exist: {src}")
        if action not in get_args(ImportAction):
            raise ValueError(f"Unknown import action: {action!r}")
        with self._assets_lock():
            return self._import_locked(name, source, action, meta or {}, tuple(consumed or ()))

    def register_in_place(
        self,
        name: str,
        src: str | Path,
        meta: dict[str, str] | None = None,
    ) -> Asset:
        """Register a file that already lives under this scope.

        Nothing is copied. The origin is a reference whose location is the
        scope-relative POSIX path, so a same-stem sidecar stays a sibling of
        :meth:`payload_path`.

        Args:
            name: Display title and slug source.
            src: Path that must already live under the scope directory.
            meta: String tags stored on the asset.

        Returns:
            The new asset.

        Raises:
            NotImplementedError: The workspace filesystem is not local.
            FileNotFoundError: *src* does not exist.
            ValueError: *src* is not under the scope directory.
        """
        self._require_local()
        source = Path(src).resolve()
        if not source.exists():
            raise FileNotFoundError(f"Source path does not exist: {src}")
        try:
            relative = source.relative_to(Path(self.scope_dir).resolve())
        except ValueError:
            raise ValueError(f"{source} is not under {self.scope_dir}") from None
        with self._assets_lock():
            return self._register_locked(name, source, relative.as_posix(), meta or {})

    def _require_local(self) -> None:
        if not isinstance(self.fs, LocalFileSystem):
            raise NotImplementedError("asset import/migration is local-filesystem only")

    def _assets_lock(self) -> AbstractContextManager[None]:
        """Scope asset lock. Creates the scope directory and the lock file's parent."""
        self.fs.mkdir(self.scope_dir, parents=True, exist_ok=True)
        locks = Path(self.root) / ".molab" / "locks"
        locks.mkdir(parents=True, exist_ok=True)
        return file_lock(locks / f"{self.scope.scope_id}.assets.lock")

    def _import_locked(
        self,
        name: str,
        source: Path,
        action: ImportAction,
        tags: dict[str, str],
        input_ids: tuple[str, ...],
    ) -> Asset:
        slug = self._free_slug(name)
        asset_root = self.fs.join(self.assets_dir, slug)
        payload = self.fs.join(asset_root, "payload")
        location = None if action == "reference" else f"assets/{slug}/payload"
        # Resolve while *source* still exists. ``move`` deletes it, and a
        # symlink would otherwise stop resolving to its target.
        uri = str(source.resolve())
        try:
            if action != "reference":
                self._materialize(source, Path(payload), action)
            content = None
            if action in ("copy", "move"):
                content = content_ref(self.fs, payload)
            elif action == "reference":
                content = content_ref(self.fs, source)
            asset, version = self._new_import(
                name,
                tags,
                uri=uri,
                action=action,
                location=location,
                input_ids=input_ids,
                content=content,
            )
            self._write_import(asset_root, asset, version)
        except Exception:
            if self.fs.exists(asset_root):
                self.fs.remove(asset_root, recursive=True)
            raise
        self._record_import(asset, version, slug, action, input_ids, asset_root)
        return asset

    def _register_locked(
        self,
        name: str,
        source: Path,
        location: str,
        tags: dict[str, str],
    ) -> Asset:
        slug = self._free_slug(name)
        asset_root = self.fs.join(self.assets_dir, slug)
        try:
            asset, version = self._new_import(
                name,
                tags,
                uri=str(source),
                action="reference",
                location=location,
                input_ids=(),
                content=content_ref(self.fs, source),
            )
            self._write_import(asset_root, asset, version)
        except Exception:
            if self.fs.exists(asset_root):
                self.fs.remove(asset_root, recursive=True)
            raise
        self._record_import(asset, version, slug, "reference", (), asset_root)
        return asset

    def _new_import(
        self,
        name: str,
        tags: dict[str, str],
        *,
        uri: str,
        action: ImportAction,
        location: str | None,
        input_ids: tuple[str, ...],
        content: ContentRef | None,
    ) -> tuple[Asset, AssetVersion]:
        now = datetime.now(UTC)
        asset_id = generate_uuid7()
        asset = Asset(
            id=asset_id,
            scope=self.scope,
            title=name,
            created_at=now,
            created_by=SYSTEM_AGENT,
            tags=tags,
        )
        version = AssetVersion(
            id=generate_uuid7(),
            asset_id=asset_id,
            origin=ImportOrigin(uri=uri, action=action, location=location, input_ids=input_ids),
            content=content,
            version=1,
            created_at=now,
            created_by=SYSTEM_AGENT,
        )
        return asset, version

    def _write_import(self, asset_root: str, asset: Asset, version: AssetVersion) -> None:
        versions = self.fs.join(asset_root, "versions")
        self.fs.mkdir(versions, parents=True, exist_ok=True)
        self.fs.atomic_write_json(
            self.fs.join(versions, f"v{version.version:03d}.json"),
            versioned_payload(version.model_dump(mode="json")),
        )
        self.fs.atomic_write_json(
            self.fs.join(asset_root, "asset.json"),
            versioned_payload(asset.model_dump(mode="json")),
        )

    def _record_import(
        self,
        asset: Asset,
        version: AssetVersion,
        slug: str,
        action: str,
        input_ids: tuple[str, ...],
        asset_root: str,
    ) -> None:
        relations = [
            Relation(predicate="specializationOf", object=EntityRef(id=asset.id, type="asset")),
            *(
                Relation(predicate="wasDerivedFrom", object=EntityRef(id=item, type="entity"))
                for item in input_ids
            ),
        ]
        self.history.record(
            "AssetVersionCreated",
            subject=EntityRef(id=version.id, type="asset-version"),
            relations=tuple(relations),
            summary=f"{slug} v1 ({action})",
            paths=(asset_root,),
        )

    @staticmethod
    def _materialize(src: Path, dest: Path, action: str) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if action == "copy":
            if src.is_file():
                shutil.copy2(src, dest)
            else:
                shutil.copytree(src, dest, dirs_exist_ok=True)
        elif action == "move":
            shutil.move(str(src), str(dest))
        elif action == "symlink":
            dest.symlink_to(src)
        elif action == "hardlink":
            if src.is_file():
                try:
                    os.link(src, dest)
                except (OSError, NotImplementedError):
                    shutil.copy2(src, dest)
            else:
                dest.mkdir(parents=True, exist_ok=True)
                for item in src.rglob("*"):
                    if item.is_file():
                        rel = item.relative_to(src)
                        target = dest / rel
                        target.parent.mkdir(parents=True, exist_ok=True)
                        try:
                            os.link(item, target)
                        except (OSError, NotImplementedError):
                            shutil.copy2(item, target)
        else:
            raise ValueError(f"Unknown import action: {action!r}")

    def _qualify_artifact(self, artifact_id: str, project_id: str | None) -> MolabRef:
        """Qualify one artifact id by filtering :func:`walk_artifacts`.

        Args:
            artifact_id: The artifact to locate.
            project_id: When set, the walk skips every other project.

        Returns:
            ``molab:experiment/<e>/run/<r>/artifact/<id>``.

        Raises:
            ValueError: The walk yielded no match.
        """
        located = next(
            (
                loc
                for loc in walk_artifacts(self.workspace, project_id=project_id)
                if loc.artifact.id == artifact_id
            ),
            None,
        )
        if located is None:
            raise ValueError(f"Artifact {artifact_id} is not readable")
        return MolabRef(
            experiment_id=located.experiment_id,
            run_id=located.run_id,
            artifact_id=artifact_id,
        )

    def _promote_locked(
        self,
        source: Artifact,
        *,
        created_by: AgentRef,
        title: str | None,
        into_asset_id: str | None,
        metadata: dict[str, JSONValue] | None,
    ) -> tuple[Asset, AssetVersion]:
        now = datetime.now(UTC)
        if into_asset_id is None:
            asset = Asset(
                id=generate_uuid7(),
                scope=self.scope,
                title=title or source.name,
                created_at=now,
                created_by=created_by,
            )
            slug = self._free_slug(asset.title)
        else:
            asset = self.get(into_asset_id)
            slug = self._slug_of(into_asset_id)

        prior = self.versions(asset.id)
        qualified = self._qualify_artifact(source.id, self.scope.project_id)
        version = AssetVersion(
            id=generate_uuid7(),
            asset_id=asset.id,
            origin=ArtifactOrigin(artifact_id=source.id, ref=str(qualified)),
            content=source.content,
            version=max((entry.version for entry in prior), default=0) + 1,
            created_at=now,
            created_by=created_by,
            media_type=source.media_type,
            semantic_type=source.semantic_type,
            metadata=metadata or {},
        )

        asset_root = self.fs.join(self.assets_dir, slug)
        self.fs.mkdir(self.fs.join(asset_root, "versions"), parents=True, exist_ok=True)
        self.fs.atomic_write_json(
            self.fs.join(asset_root, "asset.json"),
            versioned_payload(asset.model_dump(mode="json")),
        )
        self.fs.atomic_write_json(
            self.fs.join(asset_root, "versions", f"v{version.version:03d}.json"),
            versioned_payload(version.model_dump(mode="json")),
        )
        self.history.record(
            "AssetVersionCreated",
            subject=EntityRef(id=version.id, type="asset-version"),
            agent=created_by,
            relations=(
                Relation(predicate="specializationOf", object=EntityRef(id=asset.id, type="asset")),
                Relation(
                    predicate="wasDerivedFrom", object=EntityRef(id=source.id, type="artifact")
                ),
            ),
            summary=f"{slug} v{version.version}",
            paths=(asset_root,),
            occurred_at=now,
        )
        return asset, version

    def payload_path(self, asset_id: str, version: int | None = None) -> str:
        """Absolute path of one version's bytes on the workspace filesystem.

        Args:
            asset_id: Asset to resolve.
            version: Version number, or ``None`` for the latest.

        Returns:
            A path on ``self.fs``. An import whose bytes stayed at the source
            URI returns that URI.

        Raises:
            KeyError: *asset_id* or *version* does not exist.
            RefNotFoundError: A qualified artifact reference no longer resolves.
            UnmigratedAssetError: A record in this scope predates the unified schema.
        """
        found = self.versions(asset_id)
        if not found or self._find_slug(asset_id) is None:
            raise KeyError(self._missing(asset_id))
        if version is None:
            chosen = found[-1]
        else:
            chosen = next((item for item in found if item.version == version), None)
            if chosen is None:
                raise KeyError(self._missing(asset_id))
        origin = chosen.origin
        if isinstance(origin, ImportOrigin):
            if origin.location:
                return self.fs.join(self.scope_dir, origin.location)
            return origin.uri
        qualified = parse_ref(origin.ref)
        from .run import Run

        artifact = cast(Artifact, self.workspace.find(qualified))
        run = cast(
            Run,
            self.workspace.find(
                MolabRef(experiment_id=qualified.experiment_id, run_id=qualified.run_id)
            ),
        )
        return run.artifact_location(artifact.execution_id, artifact)

    # ── read ─────────────────────────────────────────────────────────────

    def list(self) -> builtins.list[Asset]:
        if not self.fs.exists(self.assets_dir):
            return []
        found: list[Asset] = []
        for path in sorted(self.fs.glob(self.assets_dir, "*/asset.json")):
            found.append(self._read_asset(self.fs.dirname(path)))
        return found

    def get(self, asset_id: str) -> Asset:
        slug = self._find_slug(asset_id)
        if slug is None:
            raise KeyError(self._missing(asset_id))
        return self._read_asset(self.fs.join(self.assets_dir, slug))

    def versions(self, asset_id: str) -> builtins.list[AssetVersion]:
        """Versions of *asset_id*, oldest first.

        An unknown id in a clean scope returns an empty list so a brand-new
        promotion can ask for the versions it does not have yet. A legacy
        record anywhere in the scope raises ``UnmigratedAssetError``.
        """
        slug = self._find_slug(asset_id)
        if slug is None:
            return []
        return self._read_versions(self.fs.join(self.assets_dir, slug))

    def _reject_legacy_asset(self, raw: dict[str, object], path: str) -> None:
        reason = _legacy_asset_reason(raw)
        if reason is not None:
            raise UnmigratedAssetError(path, reason, workspace_root=str(self.workspace.root))

    def _reject_legacy_version(self, raw: dict[str, object], path: str) -> None:
        reason = _legacy_version_reason(raw)
        if reason is not None:
            raise UnmigratedAssetError(path, reason, workspace_root=str(self.workspace.root))

    def _read_asset(self, directory: str) -> Asset:
        path = self.fs.join(directory, "asset.json")
        raw = self._read(path)
        self._reject_legacy_asset(raw, path)
        return Asset.model_validate({**raw, "scope": self.scope})

    def _read_versions(self, directory: str) -> builtins.list[AssetVersion]:
        path = self.fs.join(directory, "asset.json")
        raw = self._read(path)
        self._reject_legacy_asset(raw, path)
        return self._version_files(directory)

    def _version_files(self, directory: str) -> builtins.list[AssetVersion]:
        base = self.fs.join(directory, "versions")
        if not self.fs.exists(base):
            return []
        found: list[AssetVersion] = []
        for path in sorted(self.fs.glob(base, "*.json")):
            raw = self._read(path)
            self._reject_legacy_version(raw, path)
            found.append(AssetVersion.model_validate(raw))
        return sorted(found, key=lambda item: item.version)

    # ── internals ────────────────────────────────────────────────────────

    def _missing(self, asset_id: str) -> str:
        return f"Asset {asset_id!r} not found in scope {self.scope.urn!r}"

    def _read(self, path: str) -> dict[str, object]:
        raw = json.loads(self.fs.read_text(path))
        return {key: value for key, value in raw.items() if key != "schema_version"}

    def _slugs(self) -> set[str]:
        if not self.fs.exists(self.assets_dir):
            return set()
        return {
            name
            for name in self.fs.listdir(self.assets_dir)
            if self.fs.is_dir(self.fs.join(self.assets_dir, name))
        }

    def _free_slug(self, title: str) -> str:
        from .naming import disambiguate

        return disambiguate(entity_slug(title, fallback=title), self._slugs())

    def _find_slug(self, asset_id: str) -> str | None:
        """The directory holding *asset_id*, or None when nothing does.

        Every ``asset.json`` in the scope is checked. One legacy record
        makes the whole scope unreadable, including a unified id whose
        directory sorts first. Comparison uses the ``id`` key only.
        """
        matched: str | None = None
        for slug in sorted(self._slugs()):
            path = self.fs.join(self.assets_dir, slug, "asset.json")
            if not self.fs.exists(path):
                continue
            raw = self._read(path)
            self._reject_legacy_asset(raw, path)
            if raw.get("id") == asset_id:
                matched = slug
        return matched

    def _fold_legacy_record(
        self,
        raw: dict[str, object],
        version_raws: builtins.list[dict[str, object]],
    ) -> tuple[Asset, builtins.list[AssetVersion]]:
        """Turn one legacy directory's dicts into unified models.

        An ``asset_id`` record (no ``id``) becomes one import version; leftover
        version files are ignored. Any other legacy record drops ``project_id``
        and ``scope`` on the asset, drops ``path`` and ``source_artifact_id``
        on each version, and qualifies a missing artifact ``ref``.

        Raises:
            ValueError: An artifact origin cannot be qualified.
            ValidationError: The folded dict is not the unified schema.
        """
        if _legacy_asset_reason(raw) == "data-import record":
            asset, version = _legacy_data_asset(
                raw, scope=self.scope, fs=self.fs, scope_dir=self.scope_dir
            )
            return asset, [version]
        cleaned = {key: value for key, value in raw.items() if key not in {"project_id", "scope"}}
        asset = Asset.model_validate({**cleaned, "scope": self.scope})
        return asset, [self._upgrade_version(item) for item in version_raws]

    def _upgrade_version(self, raw: dict[str, object]) -> AssetVersion:
        """Fold one version dict onto :class:`AssetVersion`.

        A missing ``origin`` is built from ``source_artifact_id``. An artifact
        origin with an empty ``ref`` is qualified before validation, because
        ``ref`` is required.
        """
        cleaned = {
            key: value for key, value in raw.items() if key not in {"path", "source_artifact_id"}
        }
        origin = cleaned.get("origin")
        if not isinstance(origin, dict):
            source = raw.get("source_artifact_id")
            if not isinstance(source, str) or source == "":
                raise ValueError("legacy version has no artifact id")
            cleaned["origin"] = {
                "kind": "artifact",
                "artifact_id": source,
                "ref": str(self._qualify_artifact(source, self.scope.project_id)),
            }
        elif origin.get("kind") == "artifact" and not origin.get("ref"):
            artifact_id = origin.get("artifact_id")
            if not isinstance(artifact_id, str) or artifact_id == "":
                raise ValueError("legacy version has no artifact id")
            cleaned["origin"] = {
                **origin,
                "ref": str(self._qualify_artifact(artifact_id, self.scope.project_id)),
            }
        return AssetVersion.model_validate(cleaned)

    def rewrite_legacy(self, *, dry_run: bool = False) -> LegacyRewrite:
        """Rewrite legacy asset records in this scope to the unified schema.

        Ids, directory names, and payload bytes stay. An artifact origin
        whose ``ref`` is missing is qualified through :meth:`_qualify_artifact`.
        When ``_qualify_artifact`` cannot find that artifact, the asset id is
        reported in ``unresolved`` and the record is left untouched. A record
        that is not the unified schema raises ``ValidationError`` instead of
        being reported as a missing artifact. A dry run takes no lock and
        writes nothing.

        Args:
            dry_run: Classify only.

        Returns:
            Absolute directories that were (or would be) rewritten, and asset
            ids whose artifact origin could not be qualified.

        Raises:
            NotImplementedError: A real run on a non-local filesystem.
        """
        if not dry_run:
            self._require_local()

        def _apply() -> LegacyRewrite:
            rewritten: list[str] = []
            unresolved: list[str] = []
            if not self.fs.exists(self.assets_dir):
                return LegacyRewrite(rewritten=(), unresolved=())
            for slug in sorted(self._slugs()):
                directory = self.fs.join(self.assets_dir, slug)
                record_path = self.fs.join(directory, "asset.json")
                if not self.fs.exists(record_path):
                    continue
                raw = self._read(record_path)
                version_raws = self._raw_versions(directory)
                legacy = _legacy_asset_reason(raw) is not None or any(
                    _legacy_version_reason(item) is not None for item in version_raws
                )
                if not legacy:
                    continue
                asset_id = raw.get("id")
                if not isinstance(asset_id, str) or asset_id == "":
                    asset_id = raw.get("asset_id")
                if not isinstance(asset_id, str) or asset_id == "":
                    raise ValueError(f"legacy asset record {record_path} has no asset id")
                try:
                    asset, versions = self._fold_legacy_record(raw, version_raws)
                except ValueError as exc:
                    if not str(exc).startswith("Artifact ") or "is not readable" not in str(exc):
                        raise
                    unresolved.append(asset_id)
                    continue
                rewritten.append(directory)
                if dry_run:
                    continue
                self._write_rewritten(directory, asset, versions)
            return LegacyRewrite(rewritten=tuple(rewritten), unresolved=tuple(unresolved))

        if dry_run:
            return _apply()
        with self._assets_lock():
            return _apply()

    def _raw_versions(self, directory: str) -> builtins.list[dict[str, object]]:
        base = self.fs.join(directory, "versions")
        if not self.fs.exists(base):
            return []
        return [self._read(path) for path in sorted(self.fs.glob(base, "*.json"))]

    def _write_rewritten(
        self,
        directory: str,
        asset: Asset,
        versions: builtins.list[AssetVersion],
    ) -> None:
        base = self.fs.join(directory, "versions")
        self.fs.mkdir(base, parents=True, exist_ok=True)
        written: set[str] = set()
        for version in versions:
            name = f"v{version.version:03d}.json"
            written.add(name)
            self.fs.atomic_write_json(
                self.fs.join(base, name),
                versioned_payload(version.model_dump(mode="json")),
            )
        for path in self.fs.glob(base, "*.json"):
            if self.fs.basename(path) not in written:
                self.fs.remove(path)
        self.fs.atomic_write_json(
            self.fs.join(directory, "asset.json"),
            versioned_payload(asset.model_dump(mode="json")),
        )

    def _slug_of(self, asset_id: str) -> str:
        """Directory name of the record whose ``id`` is *asset_id*.

        Every ``asset.json`` in the scope is checked. One legacy record makes
        the scope unreadable. An asset is addressed by id; this name is only
        how ``promote`` finds the directory it already owns.

        Args:
            asset_id: Asset to locate.

        Returns:
            The record directory's name under ``assets_dir``.

        Raises:
            KeyError: *asset_id* is not in this repository.
            UnmigratedAssetError: A record in this scope predates the unified schema.
        """
        slug = self._find_slug(asset_id)
        if slug is None:
            raise KeyError(self._missing(asset_id))
        return slug


class ArtifactLocation(BaseModel):
    """One emitted Artifact and where its bytes live, if they can be resolved.

    ``location`` is ``None`` when :meth:`Run.artifact_location` rejects the
    record (a path :meth:`ArtifactRepository.locate` refuses, or a ``run_id``
    / ``execution_id`` that does not match the run and attempt that hold it).
    The walk does not abort on that record; a direct read still raises.
    """

    model_config = ConfigDict(frozen=True)

    project_id: str
    experiment_id: str
    run_id: str
    execution_id: str
    execution_dir: str
    location: str | None
    artifact: Artifact


def walk_artifacts(
    workspace: Workspace,
    *,
    project_id: str | None = None,
) -> Iterator[ArtifactLocation]:
    """Yield every emitted Artifact with the execution that holds it.

    Walks ``list_projects``, then ``list_experiments``, then ``list_runs``,
    then each run's executions. ``project_id`` skips every other project
    and does not descend into it. A :meth:`Run.artifact_location` ``ValueError``
    sets ``location`` to ``None`` and the walk continues.

    Args:
        workspace: The workspace to walk.
        project_id: When set, only this project's artifacts are yielded.

    Returns:
        One :class:`ArtifactLocation` per Artifact record, in tree order.
    """
    for project in workspace.list_projects():
        if project_id is not None and project.id != project_id:
            continue
        for experiment in project.list_experiments():
            for run in experiment.list_runs():
                for execution in run.executions:
                    execution_dir = str(run.execution_dir(execution.id))
                    for artifact in execution.artifacts:
                        try:
                            location = run.artifact_location(execution.id, artifact)
                        except ValueError:
                            location = None
                        yield ArtifactLocation(
                            project_id=project.id,
                            experiment_id=experiment.id,
                            run_id=run.id,
                            execution_id=execution.id,
                            execution_dir=execution_dir,
                            location=location,
                            artifact=artifact,
                        )


def scan_artifacts(workspace: Workspace) -> builtins.list[Artifact]:
    """Every Artifact in a workspace, read from the Executions that emitted them.

    Walking the tree is the query: an Execution owns its products, so there is
    no separate artifact index that can disagree with the runs on disk.
    """
    return [loc.artifact for loc in walk_artifacts(workspace)]


def scan_asset_repositories(workspace: Workspace) -> builtins.list[AssetRepository]:
    """Every asset host in *workspace*, in tree order.

    Workspace first, then each project, then each of that project's
    experiments. Runs are not hosts: nothing writes a run-level asset.
    A directory with no entity file is skipped. No index is built.

    Args:
        workspace: The workspace to walk.

    Returns:
        One repository per host.
    """
    from .naming import EXPERIMENT_CONTAINER, PROJECT_CONTAINER, RUN_CONTAINER
    from .workspace import Workspace

    def _entity_id(directory: str, filename: str) -> str | None:
        path = workspace.fs.join(directory, filename)
        if not workspace.fs.is_file(path):
            return None
        try:
            payload = json.loads(workspace.fs.read_text(path))
        except (OSError, ValueError):
            return None
        found = payload.get("id") if isinstance(payload, dict) else None
        return found if isinstance(found, str) else None

    repos: list[AssetRepository] = []
    root = str(workspace.root)
    for host in Workspace.list_hosts(workspace.root, fs=workspace.fs):
        host_s = str(host)
        if host_s == root:
            repos.append(workspace.assets)
            continue
        parent_name = PurePosixPath(host_s).parent.name
        if parent_name == RUN_CONTAINER:
            continue
        if parent_name == PROJECT_CONTAINER:
            project_id = _entity_id(host_s, "project.json")
            if project_id is None:
                continue
            repos.append(
                AssetRepository(
                    workspace,
                    AssetScope(kind="project", ids=(project_id,)),
                    host_s,
                )
            )
            continue
        if parent_name == EXPERIMENT_CONTAINER:
            experiment_id = _entity_id(host_s, "experiment.json")
            project_dir = str(PurePosixPath(host_s).parent.parent)
            project_id = _entity_id(project_dir, "project.json")
            if experiment_id is None or project_id is None:
                continue
            repos.append(
                AssetRepository(
                    workspace,
                    AssetScope(kind="experiment", ids=(project_id, experiment_id)),
                    host_s,
                )
            )
    return repos


#: Only the migration uses this name, to recognize an unmigrated tree.
_LEGACY_ASSET_MANIFEST = "assets.json"


def migrate_legacy_assets(workspace: Workspace, *, dry_run: bool = False) -> LegacyAssetMigration:
    """Rewrite legacy asset records and drop dead ``assets.json`` manifests.

    The owner of the migration. One git commit covers every path it touches
    when anything changed and history is enabled. A dry run writes nothing.

    Args:
        workspace: Workspace to migrate.
        dry_run: Classify and report only.

    Returns:
        Relative paths, unresolved asset ids, and the commit sha if one was made.

    Raises:
        NotImplementedError: *workspace* is not on a local filesystem.
    """
    if not isinstance(workspace.fs, LocalFileSystem):
        raise NotImplementedError("asset import/migration is local-filesystem only")
    rewritten_abs: list[str] = []
    unresolved: list[str] = []
    for repository in scan_asset_repositories(workspace):
        report = repository.rewrite_legacy(dry_run=dry_run)
        rewritten_abs.extend(report.rewritten)
        unresolved.extend(report.unresolved)
    removed_abs: list[str] = []
    for directory in _manifest_dirs(workspace):
        manifest = workspace.fs.join(directory, _LEGACY_ASSET_MANIFEST)
        if workspace.fs.exists(manifest):
            removed_abs.append(manifest)
            if not dry_run:
                workspace.fs.remove(manifest)
    commit = None
    if not dry_run and (rewritten_abs or removed_abs):
        commit = GitHistory(workspace.root).record(
            "AssetsMigrated",
            subject=EntityRef(id=workspace.id, type="workspace"),
            summary=(
                f"{len(rewritten_abs)} asset record(s) rewritten, "
                f"{len(removed_abs)} manifest(s) removed"
            ),
            paths=(*rewritten_abs, *removed_abs),
        )
    return LegacyAssetMigration(
        dry_run=dry_run,
        rewritten=tuple(_workspace_posix(workspace, path) for path in rewritten_abs),
        unresolved=tuple(unresolved),
        manifests_removed=tuple(_workspace_posix(workspace, path) for path in removed_abs),
        commit=commit,
    )


def _manifest_dirs(workspace: Workspace) -> list[str]:
    """Scope, run, and execution directories that may hold a dead manifest."""
    dirs = [str(workspace.root)]
    for project in workspace.list_projects():
        dirs.append(str(project.project_dir))
        for experiment in project.list_experiments():
            dirs.append(str(experiment.experiment_dir))
            for run in experiment.list_runs():
                dirs.append(str(run.run_dir))
                for execution in run.executions:
                    dirs.append(str(run.execution_dir(execution.id)))
    return dirs


def _workspace_posix(workspace: Workspace, path: str) -> str:
    root = Path(str(workspace.root))
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        return candidate.relative_to(root).as_posix()
    except ValueError:
        return candidate.resolve().relative_to(root.resolve()).as_posix()


__all__ = [
    "RESERVED_ARTIFACT_DIR",
    "ArtifactLocation",
    "ArtifactRepository",
    "AssetRepository",
    "LegacyAssetMigration",
    "LegacyRewrite",
    "content_ref",
    "migrate_legacy_assets",
    "scan_artifacts",
    "scan_asset_repositories",
    "walk_artifacts",
]
