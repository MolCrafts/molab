"""MolExp v2 scientific, execution, and data domain records."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from molexp._typing import JSONValue

from .content_store import ContentRef
from .provenance import AgentRef, EntityRef


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
    def from_executions(
        cls, executions: Sequence[ExecutionRecord | ExecutionState]
    ) -> RunStatusSummary:
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


class EvidenceRef(BaseModel):
    """Integrity descriptor for execution evidence that is not an Artifact."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str
    rel_path: str
    digest: str
    size: int


class ExecutionState(BaseModel):
    """Mutable materialized view of an Execution before it is sealed.

    This file is operational state, not provenance truth. Once the
    Execution reaches a terminal state the corresponding immutable
    :class:`ExecutionRecord` event is the authority.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
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
    artifact_ids: tuple[str, ...] = ()
    error: dict[str, JSONValue] | None = None
    sealed_event_id: str | None = None


class ExecutionRecord(BaseModel):
    """Immutable final record of one physical realization of a Run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    run_id: str
    project_id: str
    mode: ExecutionMode
    status: ExecutionStatus
    created_at: datetime
    started_at: datetime
    finished_at: datetime
    created_by: AgentRef
    based_on_execution_id: str | None = None
    checkpoint_artifact_id: str | None = None
    executor: dict[str, JSONValue] = Field(default_factory=dict)
    environment: dict[str, JSONValue] = Field(default_factory=dict)
    observed_input_ids: tuple[str, ...] = ()
    artifact_ids: tuple[str, ...] = ()
    evidence: tuple[EvidenceRef, ...] = ()
    declaration_diff: dict[str, JSONValue] = Field(default_factory=dict)
    error: dict[str, JSONValue] | None = None


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
    source_path: str
    media_type: str | None = None
    semantic_type: str | None = None
    declaration_id: str | None = None
    input_entity_ids: tuple[str, ...] = ()
    metadata: dict[str, JSONValue] = Field(default_factory=dict)

    @property
    def ref(self) -> ArtifactRef:
        return ArtifactRef(id=self.id, execution_id=self.execution_id)


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


class AssetVersion(BaseModel):
    """Immutable Asset version created by promoting an Artifact."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    asset_id: str
    source_artifact_id: str
    content: ContentRef
    version: int
    created_at: datetime
    created_by: AgentRef
    media_type: str | None = None
    semantic_type: str | None = None
    metadata: dict[str, JSONValue] = Field(default_factory=dict)


__all__ = [
    "ACTIVE_EXECUTION_STATUSES",
    "TERMINAL_EXECUTION_STATUSES",
    "Artifact",
    "ArtifactRef",
    "Asset",
    "AssetRef",
    "AssetVersion",
    "EvidenceRef",
    "ExecutionMode",
    "ExecutionRecord",
    "ExecutionState",
    "ExecutionStatus",
    "ExperimentRevision",
    "RunDefinition",
    "RunStatusSummary",
]
