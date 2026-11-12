"""Remote Operations API for the molq plugin.

Read-only endpoints powering the workspace-level Remote Operations overview.
All routes are mounted under ``/api/plugins/molq``. The plugin owns its wire:
the response models live here, beside the routes that convert the plugin's
dashboard dataclasses into them, not in ``server/schemas/``.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from molq import MolqError
from pydantic import BaseModel, Field

from molab.plugins.submit_molq import dashboard
from molab.plugins.submit_molq.dashboard import (
    JobDetail,
    JobsPage,
    JobSummary,
    QueueStats,
    TargetSummary,
)

from ..deps.auth import require_registry_access
from ..schemas._wire import ApiModel

router = APIRouter(
    prefix="/plugins/molq", tags=["molq"], dependencies=[Depends(require_registry_access)]
)

_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


class MolqTargetSummary(ApiModel):
    name: str
    scheduler: str
    clusterName: str | None = None
    healthy: bool
    healthReason: str | None = None
    activeJobs: int

    @classmethod
    def from_dataclass(cls, target: TargetSummary) -> MolqTargetSummary:
        return cls(
            name=target.name,
            scheduler=target.scheduler,
            clusterName=target.cluster_name,
            healthy=target.healthy,
            healthReason=target.health_reason,
            activeJobs=target.active_jobs,
        )


class MolqTargetListResponse(ApiModel):
    targets: list[MolqTargetSummary]
    total: int


class MolqJobSummary(ApiModel):
    target: str
    jobId: str
    schedulerJobId: str | None = None
    clusterName: str | None = None
    scheduler: str | None = None
    name: str | None = None
    state: str
    submittedAt: datetime | None = None
    startedAt: datetime | None = None
    finishedAt: datetime | None = None
    exitCode: int | None = None
    durationSeconds: float | None = None
    cwd: str | None = None

    @classmethod
    def from_dataclass(cls, job: JobSummary) -> MolqJobSummary:
        return cls(
            target=job.target,
            jobId=job.job_id,
            schedulerJobId=job.scheduler_job_id,
            clusterName=job.cluster_name,
            scheduler=job.scheduler,
            name=job.name,
            state=job.state,
            submittedAt=job.submitted_at,
            startedAt=job.started_at,
            finishedAt=job.finished_at,
            exitCode=job.exit_code,
            durationSeconds=job.duration_seconds,
            cwd=job.cwd,
        )


class MolqQueueStats(ApiModel):
    running: int = 0
    pending: int = 0
    failed: int = 0
    succeeded: int = 0
    avgWaitSeconds: float | None = None

    @classmethod
    def from_dataclass(cls, stats: QueueStats) -> MolqQueueStats:
        return cls(
            running=stats.running,
            pending=stats.pending,
            failed=stats.failed,
            succeeded=stats.succeeded,
            avgWaitSeconds=stats.avg_wait_seconds,
        )


class MolqJobsResponse(ApiModel):
    jobs: list[MolqJobSummary]
    stats: MolqQueueStats
    total: int

    @classmethod
    def from_page(cls, page: JobsPage) -> MolqJobsResponse:
        jobs = [MolqJobSummary.from_dataclass(j) for j in page.jobs]
        return cls(
            jobs=jobs,
            stats=MolqQueueStats.from_dataclass(page.stats),
            total=len(jobs),
        )


class MolqJobTransition(ApiModel):
    timestamp: datetime
    fromState: str | None = None
    toState: str
    reason: str | None = None


class MolqJobDetailResponse(MolqJobSummary):
    failureReason: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)
    commandDisplay: str | None = None
    transitions: list[MolqJobTransition] = Field(default_factory=list)
    upstreamTotal: int = 0
    upstreamSatisfied: int = 0
    downstreamTotal: int = 0

    @classmethod
    def from_dataclass(cls, detail: JobDetail) -> MolqJobDetailResponse:  # ty: ignore[invalid-method-override]
        base = MolqJobSummary.from_dataclass(detail.summary).model_dump()
        return cls(
            **base,
            failureReason=detail.failure_reason,
            metadata=detail.metadata,
            commandDisplay=detail.command_display,
            transitions=[
                MolqJobTransition(
                    timestamp=t.timestamp,
                    fromState=t.from_state,
                    toState=t.to_state,
                    reason=t.reason,
                )
                for t in detail.transitions
            ],
            upstreamTotal=detail.upstream_total,
            upstreamSatisfied=detail.upstream_satisfied,
            downstreamTotal=detail.downstream_total,
        )


class DestinationSummary(BaseModel):
    id: str
    name: str
    scheduler: str


class DestinationsResponse(BaseModel):
    registryId: str
    destinations: list[DestinationSummary]


@router.get("/destinations", response_model=DestinationsResponse)
def list_destinations() -> DestinationsResponse:
    """List registered destinations without contacting schedulers or SSH hosts."""
    from molab.workspace.connection import get_client

    client = get_client()
    return DestinationsResponse(
        registryId=client.rpc("molq.hello")["registry_id"],
        destinations=[DestinationSummary(**item) for item in client.clusters.list()],
    )


@router.get("/targets", response_model=MolqTargetListResponse)
def list_targets() -> MolqTargetListResponse:
    """List configured molq targets (one per cluster in the molq registry)."""
    try:
        targets = dashboard.list_targets()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    summaries = [MolqTargetSummary.from_dataclass(t) for t in targets]
    return MolqTargetListResponse(targets=summaries, total=len(summaries))


@router.get("/jobs", response_model=MolqJobsResponse)
def list_jobs(
    target: str | None = Query(default=None, description="Profile name to filter by."),
    include_terminal: bool = Query(default=True, alias="includeTerminal"),
    limit: int = Query(default=200, ge=1, le=1000),
) -> MolqJobsResponse:
    """List jobs across one or all targets, plus aggregate queue stats."""
    try:
        page = dashboard.fetch_page(
            target,
            include_terminal=include_terminal,
            limit=limit,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return MolqJobsResponse.from_page(page)


@router.get("/jobs/{job_id}", response_model=MolqJobDetailResponse)
def get_job(
    job_id: str,
    target: str = Query(..., description="Profile name owning the job."),
) -> MolqJobDetailResponse:
    """Return a single job's detail including transitions and dependency state."""
    try:
        detail = dashboard.get_job(target, job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MolqError as exc:
        if exc.kind not in {"NOT_FOUND", "JOB_NOT_FOUND"}:
            raise
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return MolqJobDetailResponse.from_dataclass(detail)


@router.get("/jobs/{job_id}/logs")
async def stream_logs(
    job_id: str,
    target: str = Query(..., description="Profile name owning the job."),
    stream: str = Query(default="stdout", pattern="^(stdout|stderr)$"),
) -> StreamingResponse:
    """SSE stream of newline-terminated log chunks.

    Each event payload is ``data: {"line": "..."}\\n\\n`` so the client's
    EventSource ``message`` handler parses one log line per event.
    """
    try:
        # Fail fast: invalid target / unknown job becomes a 404 instead of an
        # SSE stream that opens then closes empty (harder to debug client-side).
        dashboard.get_job(target, job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MolqError as exc:
        if exc.kind not in {"NOT_FOUND", "JOB_NOT_FOUND"}:
            raise
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    async def _generate() -> AsyncGenerator[str]:
        async for line in dashboard.tail_log(target, job_id, stream=stream):
            payload = json.dumps({"line": line})
            yield f"data: {payload}\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )
