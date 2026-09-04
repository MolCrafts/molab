"""Execution Artifact emission and Project Asset promotion."""

from __future__ import annotations

import builtins
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from molexp._typing import JSONValue
from molexp.ids import generate_uuid7

from ._file_lock import file_lock
from .content_store import ContentStore
from .domain import Artifact, ArtifactRef, Asset, AssetVersion
from .fs import FileSystem, PathArg
from .fs_local import LocalFileSystem
from .index_store import JsonIndexStore
from .provenance import (
    AgentRef,
    EntityRef,
    ProvenanceRelation,
    ProvenanceStore,
    create_event,
)


def _record_attributes(record: dict[str, JSONValue]) -> dict[str, JSONValue]:
    return {"record": record}


class ArtifactRepository:
    """Repository for outputs explicitly emitted by an Execution."""

    def __init__(
        self,
        workspace_root: PathArg,
        *,
        fs: FileSystem | None = None,
        provenance: ProvenanceStore | None = None,
        content: ContentStore | None = None,
        index: JsonIndexStore | None = None,
    ) -> None:
        self.root = str(workspace_root)
        self.fs = fs or LocalFileSystem()
        self.provenance = provenance or ProvenanceStore(self.root, fs=self.fs)
        self.content = content or ContentStore(self.root, fs=self.fs)
        self.index = index or JsonIndexStore(self.root, fs=self.fs)

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
        """Snapshot one work file/package and append its generation fact."""
        source_path = self.fs.resolve(source)
        execution_root = self.fs.resolve(execution_dir).rstrip("/")
        work_root = self.fs.join(execution_root, "work").rstrip("/")
        if source_path != work_root and not source_path.startswith(work_root + "/"):
            raise ValueError(
                f"emit_artifact source must be inside this Execution workdir: {source_path}"
            )
        if not self.fs.exists(source_path):
            raise FileNotFoundError(source_path)

        rel_path = source_path[len(work_root) :].lstrip("/")
        content_ref = self.content.put(source_path)
        now = datetime.now(UTC)
        artifact = Artifact(
            id=generate_uuid7(),
            execution_id=execution_id,
            run_id=run_id,
            project_id=project_id,
            name=name or self.fs.basename(source_path),
            content=content_ref,
            created_at=now,
            created_by=created_by,
            source_path=PurePosixPath("work", rel_path).as_posix(),
            media_type=media_type,
            semantic_type=semantic_type,
            declaration_id=declaration_id,
            input_entity_ids=input_entity_ids,
            metadata=metadata or {},
        )
        relations = (
            ProvenanceRelation(
                predicate="wasGeneratedBy",
                object=EntityRef(id=execution_id, type="execution"),
            ),
            *(
                ProvenanceRelation(
                    predicate="wasDerivedFrom", object=EntityRef(id=value, type="entity")
                )
                for value in input_entity_ids
            ),
        )
        event = create_event(
            "ArtifactEmitted",
            subject=EntityRef(id=artifact.id, type="artifact"),
            agent=created_by,
            relations=relations,
            attributes=_record_attributes(artifact.model_dump(mode="json")),
            occurred_at=now,
        )
        self.provenance.append(event)
        self.index.index_event(event)

        record_path = self.fs.join(execution_root, "artifacts", artifact.id, "artifact.json")
        self.fs.mkdir(self.fs.dirname(record_path), parents=True, exist_ok=True)
        self.fs.atomic_write_json(
            record_path,
            {"schema_version": 2, **artifact.model_dump(mode="json")},
        )
        return artifact

    def get(self, artifact_id: str) -> Artifact:
        record = self.index.get_entity("artifact", artifact_id)
        if record is None:
            self.index.rebuild(self.provenance)
            record = self.index.get_entity("artifact", artifact_id)
        if record is None:
            raise KeyError(f"Artifact {artifact_id!r} not found")
        return Artifact.model_validate(record)

    def list_for_execution(self, execution_id: str) -> list[Artifact]:
        records = self.index.list_entities("artifact")
        if not records and self.provenance.iter_events():
            self.index.rebuild(self.provenance)
            records = self.index.list_entities("artifact")
        return [
            artifact
            for raw in records
            if (artifact := Artifact.model_validate(raw)).execution_id == execution_id
        ]


class AssetRepository:
    """Project-scoped long-term data identities and immutable versions."""

    def __init__(
        self,
        workspace_root: PathArg,
        project_id: str,
        project_dir: PathArg,
        *,
        fs: FileSystem | None = None,
        provenance: ProvenanceStore | None = None,
        index: JsonIndexStore | None = None,
    ) -> None:
        self.root = str(workspace_root)
        self.project_id = project_id
        self.project_dir = str(project_dir)
        self.fs = fs or LocalFileSystem()
        self.provenance = provenance or ProvenanceStore(self.root, fs=self.fs)
        self.index = index or JsonIndexStore(self.root, fs=self.fs)
        self.artifacts = ArtifactRepository(
            self.root,
            fs=self.fs,
            provenance=self.provenance,
            index=self.index,
        )

    def promote(
        self,
        artifact: Artifact | ArtifactRef | str,
        *,
        created_by: AgentRef,
        title: str | None = None,
        into_asset_id: str | None = None,
        metadata: dict[str, JSONValue] | None = None,
    ) -> tuple[Asset, AssetVersion]:
        """Append one registration/version event under a project-wide lock."""
        self.fs.mkdir(self.project_dir, parents=True, exist_ok=True)
        with file_lock(Path(self.project_dir) / ".asset-registry.lock"):
            return self._promote_locked(
                artifact,
                created_by=created_by,
                title=title,
                into_asset_id=into_asset_id,
                metadata=metadata,
            )

    def _promote_locked(
        self,
        artifact: Artifact | ArtifactRef | str,
        *,
        created_by: AgentRef,
        title: str | None = None,
        into_asset_id: str | None = None,
        metadata: dict[str, JSONValue] | None = None,
    ) -> tuple[Asset, AssetVersion]:
        source = (
            artifact
            if isinstance(artifact, Artifact)
            else self.artifacts.get(artifact.id if isinstance(artifact, ArtifactRef) else artifact)
        )
        if source.project_id != self.project_id:
            raise ValueError("Artifact and target Asset project must match in v2")

        now = datetime.now(UTC)
        if into_asset_id is None:
            asset = Asset(
                id=generate_uuid7(),
                project_id=self.project_id,
                title=title or source.name,
                created_at=now,
                created_by=created_by,
            )
            asset_event = create_event(
                "AssetCreated",
                subject=EntityRef(id=asset.id, type="asset"),
                agent=created_by,
                attributes=_record_attributes(asset.model_dump(mode="json")),
                occurred_at=now,
            )
            self.provenance.append(asset_event)
            self.index.index_event(asset_event)
        else:
            raw = self.index.get_entity("asset", into_asset_id)
            if raw is None:
                raise KeyError(f"Asset {into_asset_id!r} not found")
            asset = Asset.model_validate(raw)
            if asset.project_id != self.project_id:
                raise ValueError("Asset belongs to another project")

        prior = [
            AssetVersion.model_validate(raw)
            for raw in self.index.list_entities("asset-version")
            if raw.get("asset_id") == asset.id
        ]
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
            metadata=metadata or {},
        )
        version_event = create_event(
            "AssetVersionCreated",
            subject=EntityRef(id=version.id, type="asset-version"),
            agent=created_by,
            relations=(
                ProvenanceRelation(
                    predicate="specializationOf",
                    object=EntityRef(id=asset.id, type="asset"),
                ),
                ProvenanceRelation(
                    predicate="wasDerivedFrom",
                    object=EntityRef(id=source.id, type="artifact"),
                ),
            ),
            attributes=_record_attributes(version.model_dump(mode="json")),
            occurred_at=now,
        )
        promoted_event = create_event(
            "ArtifactPromoted",
            subject=EntityRef(id=source.id, type="artifact"),
            agent=created_by,
            relations=(
                ProvenanceRelation(
                    predicate="registeredAs",
                    object=EntityRef(id=version.id, type="asset-version"),
                ),
            ),
            attributes={"asset_id": asset.id},
            occurred_at=now,
        )
        for event in (version_event, promoted_event):
            self.provenance.append(event)
            self.index.index_event(event)

        asset_root = self.fs.join(self.project_dir, "assets", asset.id)
        self.fs.mkdir(self.fs.join(asset_root, "versions"), parents=True, exist_ok=True)
        self.fs.atomic_write_json(
            self.fs.join(asset_root, "asset.json"),
            {"schema_version": 2, **asset.model_dump(mode="json")},
        )
        self.fs.atomic_write_json(
            self.fs.join(asset_root, "versions", f"{version.id}.json"),
            {"schema_version": 2, **version.model_dump(mode="json")},
        )
        return asset, version

    def list(self) -> builtins.list[Asset]:
        records = self.index.list_entities("asset")
        if not records and self.provenance.iter_events():
            self.index.rebuild(self.provenance)
            records = self.index.list_entities("asset")
        return [
            asset
            for raw in records
            if (asset := Asset.model_validate(raw)).project_id == self.project_id
        ]

    def get(self, asset_id: str) -> Asset:
        raw = self.index.get_entity("asset", asset_id)
        if raw is None:
            self.index.rebuild(self.provenance)
            raw = self.index.get_entity("asset", asset_id)
        if raw is None:
            raise KeyError(f"Asset {asset_id!r} not found")
        asset = Asset.model_validate(raw)
        if asset.project_id != self.project_id:
            raise KeyError(f"Asset {asset_id!r} is not in Project {self.project_id!r}")
        return asset

    def versions(self, asset_id: str) -> builtins.list[AssetVersion]:
        records = self.index.list_entities("asset-version")
        if not records and self.provenance.iter_events():
            self.index.rebuild(self.provenance)
            records = self.index.list_entities("asset-version")
        versions = [
            version
            for raw in records
            if (version := AssetVersion.model_validate(raw)).asset_id == asset_id
        ]
        return sorted(versions, key=lambda item: item.version)


__all__ = ["ArtifactRepository", "AssetRepository"]
