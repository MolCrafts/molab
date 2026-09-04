"""Workspace Run projection with physical Executions nested below intent.

This is deliberately not a flattened job model. A Run contributes immutable
scientific definition fields and an aggregate status summary; every scheduler,
runtime, timing, and terminal-status field belongs to an Execution row.
"""

from __future__ import annotations

from pydantic import Field

from molexp._typing import JSONValue
from molexp.workspace import Run
from molexp.workspace.domain import ACTIVE_EXECUTION_STATUSES, ExecutionState

from ._wire import ApiModel
from .molq import MolqJobSummary  # noqa: F401  (preserve import surface)
from .responses import RunStatusSummaryResponse


class WorkspaceExecutionRow(ApiModel):
    """One physical attempt that realizes a logical Run."""

    executionId: str
    runId: str
    mode: str
    status: str
    createdAt: str
    startedAt: str | None = None
    finishedAt: str | None = None
    durationSeconds: float | None = None
    basedOnExecutionId: str | None = None
    checkpointArtifactId: str | None = None
    schedulerJobId: str | None = None
    backend: str | None = None
    backendMetadata: dict[str, str] = Field(default_factory=dict)


class WorkspaceRunRow(ApiModel):
    """Logical Run definition plus a derived summary of its Executions."""

    id: str
    name: str
    projectId: str
    projectName: str
    experimentId: str
    experimentName: str
    definitionHash: str
    experimentRevisionId: str
    inputAssetIds: list[str] = Field(default_factory=list)
    targetHint: str | None = None
    statusSummary: RunStatusSummaryResponse
    parameters: dict[str, JSONValue] = Field(default_factory=dict)
    createdAt: str
    executions: list[WorkspaceExecutionRow] = Field(default_factory=list)

    @classmethod
    def from_run(
        cls,
        run: Run,
        *,
        project_name: str,
        experiment_name: str,
    ) -> WorkspaceRunRow:
        executions = [_build_execution_row(run.id, record) for record in run.executions]
        summary = run.status_summary
        return cls(
            id=run.id,
            name=run.id,
            projectId=run.experiment.project.id,
            projectName=project_name,
            experimentId=run.experiment.id,
            experimentName=experiment_name,
            definitionHash=run.metadata.definition_hash,
            experimentRevisionId=run.metadata.experiment_revision_id,
            inputAssetIds=list(run.metadata.input_asset_ids),
            targetHint=run.metadata.target,
            statusSummary=RunStatusSummaryResponse(
                total=summary.total,
                active=summary.active,
                notStarted=summary.not_started,
                byStatus=summary.by_status,
            ),
            parameters=dict(run.parameters),
            createdAt=run.metadata.created_at.isoformat(),
            executions=executions,
        )


def _string_metadata(values: dict[str, JSONValue]) -> dict[str, str]:
    """Expose small executor facets without moving them onto the Run."""
    metadata: dict[str, str] = {}
    for key, value in values.items():
        if isinstance(value, str):
            metadata[str(key)] = value
        elif isinstance(value, bool):
            metadata[str(key)] = str(value).lower()
        elif isinstance(value, int | float):
            metadata[str(key)] = str(value)
    return metadata


def _build_execution_row(run_id: str, record: ExecutionState) -> WorkspaceExecutionRow:
    started = record.started_at
    finished = record.finished_at
    duration: float | None = None
    if started is not None and finished is not None:
        duration = max(0.0, (finished - started).total_seconds())

    executor = _string_metadata(record.executor)
    scheduler_job_id = executor.get("scheduler_job_id") or executor.get("job_id")
    backend = executor.get("backend") or executor.get("kind")

    return WorkspaceExecutionRow(
        executionId=record.id,
        runId=run_id,
        mode=record.mode.value,
        status=record.status.value,
        createdAt=record.created_at.isoformat(),
        startedAt=started.isoformat() if started else None,
        finishedAt=finished.isoformat() if finished else None,
        durationSeconds=duration,
        basedOnExecutionId=record.based_on_execution_id,
        checkpointArtifactId=record.checkpoint_artifact_id,
        schedulerJobId=scheduler_job_id,
        backend=backend,
        backendMetadata=executor,
    )


class WorkspaceRunsStats(ApiModel):
    """Execution aggregates for the complete (unpaginated) Run result set."""

    totalRuns: int = 0
    totalExecutions: int = 0
    activeExecutions: int = 0
    byStatus: dict[str, int] = Field(default_factory=dict)


class WorkspaceRunsResponse(ApiModel):
    runs: list[WorkspaceRunRow]
    stats: WorkspaceRunsStats
    total: int
    truncated: bool = False


def compute_workspace_runs_stats(rows: list[WorkspaceRunRow]) -> WorkspaceRunsStats:
    counts: dict[str, int] = {}
    for row in rows:
        for status, count in row.statusSummary.byStatus.items():
            counts[status] = counts.get(status, 0) + count
    return WorkspaceRunsStats(
        totalRuns=len(rows),
        totalExecutions=sum(row.statusSummary.total for row in rows),
        activeExecutions=sum(counts.get(status.value, 0) for status in ACTIVE_EXECUTION_STATUSES),
        byStatus=counts,
    )


__all__ = [
    "WorkspaceExecutionRow",
    "WorkspaceRunRow",
    "WorkspaceRunsResponse",
    "WorkspaceRunsStats",
    "compute_workspace_runs_stats",
]
