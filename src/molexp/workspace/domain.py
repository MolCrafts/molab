"""MolExp v2 scientific, execution, and data domain records."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from molexp._typing import JSONValue

from .history import AgentRef, EntityRef


def _as_utc(value: datetime | None) -> datetime | None:
    """Attach UTC to a naive timestamp so records stay comparable.

    A timestamp without a zone is ambiguous, and two records that disagree
    about whether they carry one cannot be ordered at all — which is how a
    run's attempts become unsortable. Older records were written naive in
    local time; read them as UTC rather than refusing to compare them.
    """
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


class ContentRef(BaseModel):
    """Location-independent identity and shape of stored bytes."""

    model_config = ConfigDict(frozen=True)

    digest: str
    size: int
    kind: Literal["file", "directory"] = "file"


class ExecutionMode(StrEnum):
    INITIAL = "initial"
    RETRY = "retry"
    RERUN = "rerun"
    RESUME = "resume"
    REPRODUCE = "reproduce"


class ExecutionStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    FINALIZING = "finalizing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


ACTIVE_EXECUTION_STATUSES = frozenset(
    {ExecutionStatus.QUEUED, ExecutionStatus.RUNNING, ExecutionStatus.FINALIZING}
)
TERMINAL_EXECUTION_STATUSES = frozenset(set(ExecutionStatus) - ACTIVE_EXECUTION_STATUSES)


class RunStatusSummary(BaseModel):
    """Derived aggregate over all Executions realizing a Run."""

    model_config = ConfigDict(frozen=True)

    total: int
    active: int
    not_started: bool
    by_status: dict[str, int] = Field(default_factory=dict)

    @classmethod
    def from_executions(cls, executions: Sequence[Execution]) -> RunStatusSummary:
        counts: dict[str, int] = {}
        for execution in executions:
            key = execution.status.value
            counts[key] = counts.get(key, 0) + 1
        active = sum(counts.get(status.value, 0) for status in ACTIVE_EXECUTION_STATUSES)
        return cls(
            total=len(executions),
            active=active,
            not_started=not executions,
            by_status=counts,
        )


class ExperimentRevision(BaseModel):
    """Immutable scientific design snapshot referenced by every Run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    experiment_id: str
    revision: int
    created_at: datetime
    created_by: AgentRef
    definition_hash: str
    goal: str = ""
    parameter_space: dict[str, JSONValue] = Field(default_factory=dict)
    input_asset_ids: tuple[str, ...] = ()
    workflow: dict[str, JSONValue] | None = None
    metadata: dict[str, JSONValue] = Field(default_factory=dict)

    @field_validator("created_at", mode="after")
    @classmethod
    def _utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value)


class RunDefinition(BaseModel):
    """Immutable logical computation identity."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    experiment_id: str
    experiment_revision_id: str
    created_at: datetime
    created_by: AgentRef
    definition_hash: str
    parameters: dict[str, JSONValue] = Field(default_factory=dict)
    input_asset_ids: tuple[str, ...] = ()
    workflow_ref: EntityRef | None = None
    target_hint: str | None = None

    @field_validator("created_at", mode="after")
    @classmethod
    def _utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value)


class EvidenceRef(BaseModel):
    """Integrity descriptor for execution evidence that is not an Artifact."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str
    rel_path: str
    digest: str
    size: int


class ArtifactRef(BaseModel):
    """Stable reference to one observed Execution output."""

    model_config = ConfigDict(frozen=True)

    id: str
    execution_id: str


class Artifact(BaseModel):
    """Immutable output explicitly emitted by an Execution."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    execution_id: str
    run_id: str
    project_id: str
    name: str
    content: ContentRef
    created_at: datetime
    created_by: AgentRef
    path: str
    """Workspace-relative POSIX path of the bytes — the artifact *is* this file."""
    source_path: str
    """Where inside the Execution workdir it was produced (``work/...``)."""
    media_type: str | None = None
    semantic_type: str | None = None
    declaration_id: str | None = None
    input_entity_ids: tuple[str, ...] = ()
    metadata: dict[str, JSONValue] = Field(default_factory=dict)

    @property
    def ref(self) -> ArtifactRef:
        return ArtifactRef(id=self.id, execution_id=self.execution_id)

    @field_validator("created_at", mode="after")
    @classmethod
    def _utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value)


class Execution(BaseModel):
    """One physical attempt at a Run — the whole of it, in one file.

    There is no second "sealed record" living somewhere else: sealing sets
    :attr:`sealed_at` (and the history commit that recorded it) and freezes
    the terminal fields in place. ``executions/e01/execution.json`` is the
    complete, authoritative account of attempt 1.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    seq: int
    run_id: str
    project_id: str
    mode: ExecutionMode
    status: ExecutionStatus = ExecutionStatus.QUEUED
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_by: AgentRef
    based_on_execution_id: str | None = None
    checkpoint_artifact_id: str | None = None
    executor: dict[str, JSONValue] = Field(default_factory=dict)
    environment: dict[str, JSONValue] = Field(default_factory=dict)
    observed_input_ids: tuple[str, ...] = ()
    artifacts: tuple[Artifact, ...] = ()
    evidence: tuple[EvidenceRef, ...] = ()
    declaration_diff: dict[str, JSONValue] = Field(default_factory=dict)
    error: dict[str, JSONValue] | None = None
    sealed_at: datetime | None = None
    sealed_commit: str | None = None

    @property
    def sealed(self) -> bool:
        return self.sealed_at is not None

    @property
    def artifact_ids(self) -> tuple[str, ...]:
        return tuple(artifact.id for artifact in self.artifacts)

    def artifact(self, artifact_id: str) -> Artifact:
        for artifact in self.artifacts:
            if artifact.id == artifact_id:
                return artifact
        raise KeyError(f"Artifact {artifact_id!r} not found in Execution {self.id!r}")

    @field_validator("created_at", "started_at", "finished_at", "sealed_at", mode="after")
    @classmethod
    def _utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value)


class AssetRef(BaseModel):
    """Stable reference to a Project-managed data identity."""

    model_config = ConfigDict(frozen=True)

    id: str
    project_id: str


class Asset(BaseModel):
    """Long-lived Project data identity with append-only versions."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    project_id: str
    title: str
    created_at: datetime
    created_by: AgentRef

    @property
    def ref(self) -> AssetRef:
        return AssetRef(id=self.id, project_id=self.project_id)

    @field_validator("created_at", mode="after")
    @classmethod
    def _utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value)


class AssetVersion(BaseModel):
    """Immutable Asset version created by promoting an Artifact."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    asset_id: str
    source_artifact_id: str
    content: ContentRef
    path: str = ""
    """Workspace-relative POSIX path of the underlying bytes."""
    version: int
    created_at: datetime
    created_by: AgentRef
    media_type: str | None = None
    semantic_type: str | None = None
    metadata: dict[str, JSONValue] = Field(default_factory=dict)

    @field_validator("created_at", mode="after")
    @classmethod
    def _utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value)


__all__ = [
    "ACTIVE_EXECUTION_STATUSES",
    "TERMINAL_EXECUTION_STATUSES",
    "Artifact",
    "ArtifactRef",
    "Asset",
    "AssetRef",
    "AssetVersion",
    "ContentRef",
    "EvidenceRef",
    "Execution",
    "ExecutionMode",
    "ExecutionStatus",
    "ExperimentRevision",
    "RunDefinition",
    "RunStatusSummary",
]
