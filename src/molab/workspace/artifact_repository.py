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
from typing import TYPE_CHECKING, NamedTuple, cast, get_args

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
from .fs_local import LocalFS
from .history import SYSTEM_AGENT, AgentRef, EntityRef, GitHistory, Relation
from .naming import ASSET_CONTAINER, entity_slug
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
        self.fs = fs or LocalFS()
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
                self.fs.cp(source_path, out_path, recursive=True)
            else:
                self.fs.cp(source_path, out_path)

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


def _same_content(held: ContentRef | None, incoming: ContentRef | None) -> bool:
    """True when both sides name the same non-empty content digest."""
    if held is None or incoming is None:
        return False
    return bool(held.digest) and held.digest == incoming.digest


class AssetRepository:
    """Long-term data identities and immutable versions at one scope.

    Records live under ``<scope>/assets/<slug>/``: ``asset.json`` plus one
    file per version. Listing assets is listing that directory; there is no
    derived index to fall out of step with it. A record that still uses an
    ``asset_id`` key, a persisted ``project_id`` or ``scope``, or a version
    without a qualified ``origin`` is unreadable. Readers refuse it and do
    not rewrite the file.
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
        self.root = str(workspace.resolve())
        self.scope = scope
        self.scope_dir = str(scope_dir)
        self.fs = workspace.fs
        self.history = history or GitHistory(self.root)

    @property
    def assets_dir(self) -> str:
        return self.fs.join(self.scope_dir, ASSET_CONTAINER)

    def promote(
        self,
        artifact: Artifact | ArtifactRef | str,
        *,
        created_by: AgentRef,
        title: str | None = None,
        into_asset_id: str | None = None,
        metadata: dict[str, JSONValue] | None = None,
    ) -> tuple[Asset, AssetVersion]:
        """Register an Artifact as a new Asset, or as the next version of one.

        The decision runs under the scope lock. An artifact id that is already
        an origin is returned as filed. An explicit *title* binds to the one
        asset with that title, or creates it; two assets with that title raise
        ``ValueError``. *into_asset_id* selects the target directly. With
        neither, an asset whose latest version already has this content digest
        is returned, and otherwise a new asset is created under the artifact's
        name. When the chosen asset's latest version has the same content
        digest, that version is returned and nothing is written.

        Args:
            artifact: The emitted artifact. A ref or a bare id is refused.
            created_by: Agent recorded on a version this call actually writes.
            title: Display title that selects or names the asset.
            into_asset_id: Asset to version. Wins over *title*.
            metadata: Stored on a version this call writes.

        Returns:
            The asset and the version that holds this artifact, or the
            existing version when this call did not write one.

        Raises:
            TypeError: *artifact* is not an :class:`Artifact`.
            ValueError: The artifact belongs to another project, *title*
                matches more than one asset, or the content digest is the
                latest version of more than one asset.
            KeyError: *into_asset_id* is not in this scope.
        """
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

        A copied or moved file keeps its extension (``payload.pdf``), and the
        version records its media type and original file name, so a reader
        knows what the bytes are without opening them.

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
        described = _described(source)
        with self._assets_lock():
            return self._import_locked(
                name, source, action, meta or {}, tuple(consumed or ()), described
            )

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
        described = _described(source)
        with self._assets_lock():
            return self._register_locked(name, source, relative.as_posix(), meta or {}, described)

    def _require_local(self) -> None:
        if not isinstance(self.fs, LocalFS):
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
        described: _Description,
    ) -> Asset:
        slug = self._free_slug(name)
        asset_root = self.fs.join(self.assets_dir, slug)
        stored = f"payload{source.suffix}" if source.is_file() else "payload"
        payload = self.fs.join(asset_root, stored)
        location = None if action == "reference" else f"assets/{slug}/{stored}"
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
                described=described,
            )
            self._write_import(asset_root, asset, version)
        except Exception:
            if self.fs.exists(asset_root):
                self.fs.rm(asset_root, recursive=True)
            raise
        self._record_import(asset, version, slug, action, input_ids, asset_root)
        return asset

    def _register_locked(
        self,
        name: str,
        source: Path,
        location: str,
        tags: dict[str, str],
        described: _Description,
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
                described=described,
            )
            self._write_import(asset_root, asset, version)
        except Exception:
            if self.fs.exists(asset_root):
                self.fs.rm(asset_root, recursive=True)
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
        described: _Description,
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
            media_type=described.media_type,
            metadata=described.metadata,
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
        filed = self._promotion_of(source.id)
        if filed is not None:
            return filed

        now = datetime.now(UTC)
        if into_asset_id is not None:
            asset = self.get(into_asset_id)
            slug = self._slug_of(into_asset_id)
        elif title:
            bound = self._asset_by_title(title)
            if bound is None:
                asset = Asset(
                    id=generate_uuid7(),
                    scope=self.scope,
                    title=title,
                    created_at=now,
                    created_by=created_by,
                )
                slug = self._free_slug(asset.title)
            else:
                asset = bound
                slug = self._slug_of(asset.id)
        else:
            same_bytes = self._latest_with_digest(source.content)
            if same_bytes is not None:
                return same_bytes
            asset = Asset(
                id=generate_uuid7(),
                scope=self.scope,
                title=source.name,
                created_at=now,
                created_by=created_by,
            )
            slug = self._free_slug(asset.title)

        prior = self.versions(asset.id)
        if prior and _same_content(prior[-1].content, source.content):
            return asset, prior[-1]

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

    def _promotion_of(self, artifact_id: str) -> tuple[Asset, AssetVersion] | None:
        """The version whose origin is *artifact_id*, if this scope has one."""
        for asset in self.list():
            for version in self.versions(asset.id):
                origin = version.origin
                if isinstance(origin, ArtifactOrigin) and origin.artifact_id == artifact_id:
                    return asset, version
        return None

    def _asset_by_title(self, title: str) -> Asset | None:
        """The one asset titled *title*, or ``None`` when the scope has none.

        Raises:
            ValueError: More than one asset has this display title.
        """
        matches = [item for item in self.list() if item.title == title]
        if not matches:
            return None
        if len(matches) > 1:
            ids = ", ".join(item.id for item in matches)
            raise ValueError(f"Asset title {title!r} matches more than one asset ({ids})")
        return matches[0]

    def _latest_with_digest(self, content: ContentRef | None) -> tuple[Asset, AssetVersion] | None:
        """The asset whose latest version has *content*'s digest.

        Raises:
            ValueError: More than one asset's latest version has that digest.
        """
        digest = content.digest if content is not None and content.digest else None
        if digest is None:
            return None
        found: list[tuple[Asset, AssetVersion]] = []
        for asset in self.list():
            versions = self.versions(asset.id)
            if not versions:
                continue
            latest = versions[-1]
            if latest.content is not None and latest.content.digest == digest:
                found.append((asset, latest))
        if not found:
            return None
        if len(found) > 1:
            ids = ", ".join(asset.id for asset, _version in found)
            raise ValueError(
                f"Content digest {digest} is the latest version of more than one asset ({ids})"
            )
        return found[0]

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
            raise UnmigratedAssetError(path, reason, workspace_root=self.root)

    def _reject_legacy_version(self, raw: dict[str, object], path: str) -> None:
        reason = _legacy_version_reason(raw)
        if reason is not None:
            raise UnmigratedAssetError(path, reason, workspace_root=self.root)

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
            for name in self.fs.ls(self.assets_dir, A=True)
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

    Walks every run at or below the served node (a workspace, or a project,
    experiment or run opened by ``molab serve``), then each run's executions.
    ``project_id`` keeps only that project's runs. A :meth:`Run.artifact_location` ``ValueError``
    sets ``location`` to ``None`` and the walk continues.

    Args:
        workspace: The workspace to walk.
        project_id: When set, only this project's artifacts are yielded.

    Returns:
        One :class:`ArtifactLocation` per Artifact record, in tree order.
    """
    from .folder import WORKSPACE_EXPERIMENT_KIND, WORKSPACE_PROJECT_KIND
    from .run import Run
    from .scope import as_folder, descendants

    for run in descendants(as_folder(workspace), Run):
        owner = run.ancestor_id(WORKSPACE_PROJECT_KIND)
        if project_id is not None and owner != project_id:
            continue
        for execution in run.executions:
            execution_dir = str(run.execution_dir(execution.id))
            for artifact in execution.artifacts:
                try:
                    location = run.artifact_location(execution.id, artifact)
                except ValueError:
                    location = None
                yield ArtifactLocation(
                    project_id=owner,
                    experiment_id=run.ancestor_id(WORKSPACE_EXPERIMENT_KIND),
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
    A directory with no ``index.md`` record is skipped. No index is built.

    Args:
        workspace: The workspace to walk.

    Returns:
        One repository per host.
    """
    from molab import frontmatter

    from .entity_record import ENTITY_FILENAME
    from .folder import WORKSPACE_EXPERIMENT_KIND, WORKSPACE_PROJECT_KIND
    from .naming import EXPERIMENT_CONTAINER, PROJECT_CONTAINER, RUN_CONTAINER
    from .workspace import Workspace

    def _entity_id(directory: str, kind: str) -> str | None:
        head = frontmatter.read_head(workspace.fs, workspace.fs.join(directory, ENTITY_FILENAME))
        if not head or head.get("type") != kind:
            return None
        found = head.get("id")
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
            project_id = _entity_id(host_s, WORKSPACE_PROJECT_KIND)
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
            experiment_id = _entity_id(host_s, WORKSPACE_EXPERIMENT_KIND)
            project_dir = str(PurePosixPath(host_s).parent.parent)
            project_id = _entity_id(project_dir, WORKSPACE_PROJECT_KIND)
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


__all__ = [
    "RESERVED_ARTIFACT_DIR",
    "ArtifactLocation",
    "ArtifactRepository",
    "AssetRepository",
    "content_ref",
    "scan_artifacts",
    "scan_asset_repositories",
    "walk_artifacts",
]


class _Description(NamedTuple):
    """What the file itself says about its bytes: media type and original name."""

    media_type: str | None
    metadata: dict[str, JSONValue]


def _described(source: Path) -> _Description:
    """Media type and file name, read off the source path. Nothing else is assumed."""
    import mimetypes

    if not source.is_file():
        return _Description(media_type=None, metadata={})
    return _Description(
        media_type=mimetypes.guess_type(source.name)[0], metadata={"filename": source.name}
    )
