"""Execution Artifact emission and Project Asset promotion.

An Artifact is a *file that stayed*: emitting one moves it out of the
attempt's scratch ``work/`` into its durable ``out/``, hashes it in place,
and attaches the record to the Execution that produced it. There is no
second copy in a content-addressed side store — the file is the artifact,
and git already deduplicates the small ones it tracks.

An Asset is a Project-level identity over such files. Its records live in
``projects/<project>/assets/<asset>/`` where a person can find them.
"""

from __future__ import annotations

import builtins
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from molab._typing import JSONValue
from molab.ids import generate_uuid7

from ._file_lock import file_lock
from .domain import Artifact, ArtifactRef, Asset, AssetVersion, ContentRef
from .execution_dirs import ARTIFACTS, execution_dir_names
from .fs import FileSystem, PathArg
from .fs_local import LocalFileSystem
from .history import AgentRef, EntityRef, GitHistory, Relation
from .naming import entity_slug


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

    def _workspace_rel(self, path: str) -> str:
        """Path relative to the workspace root — how anyone else finds the bytes."""
        root = self.fs.resolve(self.root).rstrip("/") + "/"
        resolved = self.fs.resolve(path)
        return resolved[len(root) :] if resolved.startswith(root) else resolved

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
    ) -> Artifact:
        """Promote one file/package produced by this attempt into ``artifacts/``.

        The source may sit in any of the attempt's directories — scratch
        ``work/``, bulk ``out/``, or the attempt root where a solver dropped
        it. Anything outside the attempt is refused: an Artifact is a product
        of *this* attempt.
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
        workspace_rel = self._workspace_rel(out_path)
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
            path=workspace_rel,
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


class AssetRepository:
    """Project-scoped long-term data identities and immutable versions.

    Records live under ``<project>/assets/<slug>/`` — ``asset.json`` plus one
    file per version. Listing assets is listing that directory; there is no
    derived index to fall out of step with it.
    """

    def __init__(
        self,
        workspace_root: PathArg,
        project_id: str,
        project_dir: PathArg,
        *,
        fs: FileSystem | None = None,
        history: GitHistory | None = None,
    ) -> None:
        self.root = str(workspace_root)
        self.project_id = project_id
        self.project_dir = str(project_dir)
        self.fs = fs or LocalFileSystem()
        self.history = history or GitHistory(self.root)

    @property
    def assets_dir(self) -> str:
        return self.fs.join(self.project_dir, "assets")

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
        if artifact.project_id != self.project_id:
            raise ValueError("Artifact and target Asset project must match")
        self.fs.mkdir(self.project_dir, parents=True, exist_ok=True)
        locks = Path(self.root) / ".molab" / "locks"
        locks.mkdir(parents=True, exist_ok=True)
        with file_lock(locks / f"{self.project_id}.assets.lock"):
            return self._promote_locked(
                artifact,
                created_by=created_by,
                title=title,
                into_asset_id=into_asset_id,
                metadata=metadata,
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
                project_id=self.project_id,
                title=title or source.name,
                created_at=now,
                created_by=created_by,
            )
            slug = self._free_slug(asset.title)
        else:
            asset = self.get(into_asset_id)
            slug = self._slug_of(into_asset_id)

        prior = self.versions(asset.id)
        version = AssetVersion(
            id=generate_uuid7(),
            asset_id=asset.id,
            source_artifact_id=source.id,
            content=source.content,
            version=max((entry.version for entry in prior), default=0) + 1,
            created_at=now,
            created_by=created_by,
            media_type=source.media_type,
            semantic_type=source.semantic_type,
            path=source.path,
            metadata=metadata or {},
        )

        asset_root = self.fs.join(self.assets_dir, slug)
        self.fs.mkdir(self.fs.join(asset_root, "versions"), parents=True, exist_ok=True)
        self.fs.atomic_write_json(
            self.fs.join(asset_root, "asset.json"),
            {"schema_version": 3, **asset.model_dump(mode="json")},
        )
        self.fs.atomic_write_json(
            self.fs.join(asset_root, "versions", f"v{version.version:03d}.json"),
            {"schema_version": 3, **version.model_dump(mode="json")},
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

    # ── read ─────────────────────────────────────────────────────────────

    def list(self) -> builtins.list[Asset]:
        if not self.fs.exists(self.assets_dir):
            return []
        found: list[Asset] = []
        for path in sorted(self.fs.glob(self.assets_dir, "*/asset.json")):
            raw = self._read(path)
            asset = Asset.model_validate(raw)
            if asset.project_id == self.project_id:
                found.append(asset)
        return found

    def get(self, asset_id: str) -> Asset:
        for asset in self.list():
            if asset.id == asset_id:
                return asset
        raise KeyError(f"Asset {asset_id!r} not found in Project {self.project_id!r}")

    def versions(self, asset_id: str) -> builtins.list[AssetVersion]:
        slug = self._find_slug(asset_id)
        if slug is None:
            return []
        base = self.fs.join(self.assets_dir, slug, "versions")
        if not self.fs.exists(base):
            return []
        found: list[AssetVersion] = []
        for path in sorted(self.fs.glob(base, "*.json")):
            found.append(AssetVersion.model_validate(self._read(path)))
        return sorted(found, key=lambda item: item.version)

    # ── internals ────────────────────────────────────────────────────────

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
        """The directory holding *asset_id*, or None when nothing does."""
        for slug in sorted(self._slugs()):
            path = self.fs.join(self.assets_dir, slug, "asset.json")
            if not self.fs.exists(path):
                continue
            if self._read(path).get("id") == asset_id:
                return slug
        return None

    def _slug_of(self, asset_id: str) -> str:
        """The directory holding *asset_id*. Raises when there is none."""
        slug = self._find_slug(asset_id)
        if slug is None:
            raise KeyError(f"Asset {asset_id!r} not found in Project {self.project_id!r}")
        return slug


__all__ = ["ArtifactRepository", "AssetRepository", "content_ref"]


def scan_artifacts(workspace: object) -> builtins.list[Artifact]:
    """Every Artifact in a workspace, read from the Executions that emitted them.

    Walking the tree is the query: an Execution owns its products, so there is
    no separate artifact index that can disagree with the runs on disk.
    """
    found: list[Artifact] = []
    for project in workspace.list_projects():  # ty: ignore[unresolved-attribute]
        for experiment in project.list_experiments():
            for run in experiment.list_runs():
                for execution in run.executions:
                    found.extend(execution.artifacts)
    return found
