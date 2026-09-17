"""Response schema for ``GET /api/workspace/context``.

A camelCase serialization wrapper over the workspace-layer ``WorkspaceContext``
read-model (``molab.workspace.workspace_context``). It is a presentation DTO —
not a second model — built directly from the frozen assembler output via
:meth:`WorkspaceContextResponse.from_context`. Field names follow the existing
server convention (camelCase field names, e.g. ``projectCount``).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import Field

from molab._typing import JSONValue

from ._wire import ApiModel

if TYPE_CHECKING:
    from molab.workspace.workspace_context import (
        ArtifactRef,
        ContextFocus,
        ExperimentRef,
        HealthFlag,
        KnowledgeRef,
        ProjectRef,
        RunRef,
        WorkflowRef,
        WorkspaceContext,
        WorkspaceRef,
    )


class WorkspaceRefResponse(ApiModel):
    id: str
    name: str
    root: str
    targets: list[str] = Field(default_factory=list)

    @classmethod
    def from_ref(cls, ref: WorkspaceRef) -> WorkspaceRefResponse:
        return cls(id=ref.id, name=ref.name, root=ref.root, targets=list(ref.targets))


class ProjectRefResponse(ApiModel):
    id: str
    name: str

    @classmethod
    def from_ref(cls, ref: ProjectRef) -> ProjectRefResponse:
        return cls(id=ref.id, name=ref.name)


class ExperimentRefResponse(ApiModel):
    id: str
    name: str
    projectId: str
    parameterSpace: dict[str, JSONValue] = Field(default_factory=dict)

    @classmethod
    def from_ref(cls, ref: ExperimentRef) -> ExperimentRefResponse:
        return cls(
            id=ref.id,
            name=ref.name,
            projectId=ref.project_id,
            parameterSpace=dict(ref.parameter_space),
        )


class WorkflowRefResponse(ApiModel):
    experimentId: str
    name: str
    irHash: str | None = None

    @classmethod
    def from_ref(cls, ref: WorkflowRef) -> WorkflowRefResponse:
        return cls(experimentId=ref.experiment_id, name=ref.name, irHash=ref.ir_hash)


class RunRefResponse(ApiModel):
    runId: str
    experimentId: str
    projectId: str
    status: str
    configHash: str | None = None
    startedAt: datetime | None = None
    finishedAt: datetime | None = None
    currentExecutionId: str | None = None

    @classmethod
    def from_ref(cls, ref: RunRef) -> RunRefResponse:
        return cls(
            runId=ref.run_id,
            experimentId=ref.experiment_id,
            projectId=ref.project_id,
            status=ref.status,
            configHash=ref.config_hash,
            startedAt=ref.started_at,
            finishedAt=ref.finished_at,
            currentExecutionId=ref.current_execution_id,
        )


class ArtifactRefResponse(ApiModel):
    assetId: str
    scope: str
    kind: str
    path: str
    contentHash: str | None = None
    runId: str | None = None
    executionId: str | None = None
    taskId: str | None = None

    @classmethod
    def from_ref(cls, ref: ArtifactRef) -> ArtifactRefResponse:
        return cls(
            assetId=ref.asset_id,
            scope=ref.scope,
            kind=ref.kind,
            path=ref.path,
            contentHash=ref.content_hash,
            runId=ref.run_id,
            executionId=ref.execution_id,
            taskId=ref.task_id,
        )


class KnowledgeRefResponse(ApiModel):
    path: str
    type: str
    title: str
    id: str | None = None

    @classmethod
    def from_ref(cls, ref: KnowledgeRef) -> KnowledgeRefResponse:
        return cls(path=ref.path, type=ref.type, title=ref.title, id=ref.id)


class HealthFlagResponse(ApiModel):
    kind: str
    ref: str
    detail: str

    @classmethod
    def from_flag(cls, flag: HealthFlag) -> HealthFlagResponse:
        return cls(kind=flag.kind, ref=flag.ref, detail=flag.detail)


class ContextFocusResponse(ApiModel):
    projectId: str | None = None
    experimentId: str | None = None
    runId: str | None = None
    selectedObjectRefs: list[str] = Field(default_factory=list)

    @classmethod
    def from_focus(cls, focus: ContextFocus) -> ContextFocusResponse:
        return cls(
            projectId=focus.project_id,
            experimentId=focus.experiment_id,
            runId=focus.run_id,
            selectedObjectRefs=list(focus.selected_object_refs),
        )


class WorkspaceContextResponse(ApiModel):
    """Camel-cased HTTP view of the canonical ``WorkspaceContext`` read-model."""

    workspace: WorkspaceRefResponse
    focus: ContextFocusResponse
    projects: list[ProjectRefResponse] = Field(default_factory=list)
    experiments: list[ExperimentRefResponse] = Field(default_factory=list)
    workflows: list[WorkflowRefResponse] = Field(default_factory=list)
    recentRuns: list[RunRefResponse] = Field(default_factory=list)
    failedRuns: list[RunRefResponse] = Field(default_factory=list)
    runningRuns: list[RunRefResponse] = Field(default_factory=list)
    artifacts: list[ArtifactRefResponse] = Field(default_factory=list)
    knowledge: list[KnowledgeRefResponse] = Field(default_factory=list)
    openQuestions: list[KnowledgeRefResponse] = Field(default_factory=list)
    staleOrMissing: list[HealthFlagResponse] = Field(default_factory=list)

    @classmethod
    def from_context(cls, ctx: WorkspaceContext) -> WorkspaceContextResponse:
        """Build the HTTP view from a frozen :class:`WorkspaceContext`."""
        return cls(
            workspace=WorkspaceRefResponse.from_ref(ctx.workspace),
            focus=ContextFocusResponse.from_focus(ctx.focus),
            projects=[ProjectRefResponse.from_ref(r) for r in ctx.projects],
            experiments=[ExperimentRefResponse.from_ref(r) for r in ctx.experiments],
            workflows=[WorkflowRefResponse.from_ref(r) for r in ctx.workflows],
            recentRuns=[RunRefResponse.from_ref(r) for r in ctx.recent_runs],
            failedRuns=[RunRefResponse.from_ref(r) for r in ctx.failed_runs],
            runningRuns=[RunRefResponse.from_ref(r) for r in ctx.running_runs],
            artifacts=[ArtifactRefResponse.from_ref(r) for r in ctx.artifacts],
            knowledge=[KnowledgeRefResponse.from_ref(r) for r in ctx.knowledge],
            openQuestions=[KnowledgeRefResponse.from_ref(r) for r in ctx.open_questions],
            staleOrMissing=[HealthFlagResponse.from_flag(r) for r in ctx.stale_or_missing],
        )
