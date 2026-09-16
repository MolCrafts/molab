"""Pydantic response models for MolExp API.

All ``from_model()`` methods take typed domain objects — no ``Any``,
no ``getattr`` guessing.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# The typed AgentEvent discriminated union is the wire shape the live SSE event
# stream frames carry (spec 01). Re-exported here so the OpenAPI surface owns a
# typed reference; it supersedes the generic SessionEventResponse for the stream
# (SessionEventResponse stays the session-snapshot shape). Pure data — importing
# it pulls no pydantic-ai.
from molexp.agent.events import AgentEvent as AgentEvent
from molexp.workspace import (
    Asset,
    Experiment,
    Project,
    Run,
)
from molexp.workspace.read_model import RunRow


def _str_or_none(value: object) -> str | None:
    """Coerce a JSON-shaped opaque value into ``str | None`` for response fields."""
    if value is None:
        return None
    return str(value)


class WorkflowDocumentResponse(BaseModel):
    """The persisted (normalized) workflow IR document for an experiment."""

    project_id: str = Field(..., description="Owning project id")
    experiment_id: str = Field(..., description="Owning experiment id")
    document: dict[str, Any] = Field(..., description="Normalized workflow IR document")


# ── Project ─────────────────────────────────────────────────────────────────


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: str = ""
    owner: str = ""
    tags: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
    created: str
    experimentCount: int | None = None

    @classmethod
    def from_model(cls, project: Project, experiment_count: int | None = None) -> ProjectResponse:
        return cls(
            id=project.id,
            name=project.name,
            description=project.description,
            owner=project.owner,
            tags=project.tags,
            config=project.config,
            created=project.created_at.isoformat(),
            experimentCount=experiment_count,
        )


class ProjectListResponse(BaseModel):
    projects: list[ProjectResponse]
    total: int


# ── Experiment ──────────────────────────────────────────────────────────────


class ExperimentResponse(BaseModel):
    id: str
    projectId: str
    name: str
    description: str = ""
    workflow: str | None = None
    workflowType: str | None = None
    planRunId: str | None = None
    gitCommit: str | None = None
    parameterSpace: dict[str, Any] = Field(default_factory=dict)
    defaultTarget: str | None = None
    created: str
    runCount: int | None = None
    runs: list[RunSummary] = Field(default_factory=list)

    @classmethod
    def from_model(
        cls, experiment: Experiment, runs: list[Run] | None = None
    ) -> ExperimentResponse:
        run_list = []
        if runs:
            run_list = []
            for r in runs:
                # Hot state (status / finished_at) from ONE ``_ops`` sidecar
                # parse; ``results`` from the memoized run.json document.
                ops = r.read_ops()
                run_list.append(
                    RunSummary(
                        id=r.id,
                        status=ops.status.value,
                        created=r.metadata.created_at.isoformat(),
                        finished=(ops.finished_at.isoformat() if ops.finished_at else None),
                        parameters=r.parameters,
                        results=r.context_results,
                    )
                )
        return cls(
            id=experiment.id,
            projectId=experiment.project.id,
            name=experiment.name,
            description=experiment.description,
            workflow=experiment.metadata.workflow_source,
            workflowType=experiment.metadata.workflow_type,
            planRunId=experiment.metadata.plan_run_id,
            gitCommit=experiment.metadata.git_commit,
            parameterSpace=experiment.metadata.parameter_space,
            defaultTarget=experiment.metadata.default_target,
            created=experiment.created_at.isoformat(),
            runCount=len(runs) if runs else None,
            runs=run_list,
        )


# ── Run ─────────────────────────────────────────────────────────────────────


class RunSummary(BaseModel):
    id: str
    status: str
    created: str
    finished: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    results: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_row(cls, row: RunRow) -> RunSummary:
        """Summary from a read-model row — zero I/O (see :meth:`RunResponse.from_row`)."""
        return cls(
            id=row.run_id,
            status=row.status,
            created=row.created_at.isoformat(),
            finished=row.finished_at.isoformat() if row.finished_at else None,
            parameters=dict(row.parameters),
            results=dict(row.context_results),
        )


class WorkflowSnapshotResponse(BaseModel):
    source: str
    gitCommit: str | None = None
    codeHash: str | None = None
    configHash: str | None = None


class ExecutionRecordResponse(BaseModel):
    """One execution attempt of a Run.

    Mirrors :class:`molexp.workspace.models.ExecutionRecord` with
    JSON-friendly field names so the UI can render a per-attempt
    timeline.
    """

    executionId: str
    startedAt: str
    finishedAt: str | None = None
    status: str
    schedulerJobId: str | None = None


class RunResponse(BaseModel):
    id: str
    projectId: str
    experimentId: str
    status: str
    created: str
    finished: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    results: dict[str, Any] = Field(default_factory=dict)
    workflow: WorkflowSnapshotResponse | None = None
    workflowSource: str | None = None
    error: dict[str, str] | None = None
    executorInfo: dict[str, Any] = Field(default_factory=dict)
    profile: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    configHash: str | None = None
    executionHistory: list[ExecutionRecordResponse] = Field(default_factory=list)
    target: str | None = None

    @classmethod
    def from_row(cls, row: RunRow) -> RunResponse:
        """Build the run response from a read-model row — zero I/O.

        Field-for-field equivalent to :meth:`from_model` (a parity test locks
        that); the row already carries the experiment's ``workflow_source`` /
        ``git_commit``, which is why no parent lookup is needed here.
        """
        wf_snap = None
        snap = row.workflow_snapshot
        wf_source = row.workflow_source
        if isinstance(snap, dict):
            wf_snap = WorkflowSnapshotResponse(
                source=str(snap.get("source") or wf_source or ""),
                gitCommit=_str_or_none(snap.get("git_commit")) or row.git_commit,
                codeHash=_str_or_none(snap.get("code_hash")),
                configHash=_str_or_none(snap.get("config_hash")),
            )
        elif wf_source:
            wf_snap = WorkflowSnapshotResponse(
                source=wf_source, gitCommit=row.git_commit, codeHash=None, configHash=None
            )
        error = (
            {"type": row.error.type, "message": row.error.message}
            if row.error is not None
            else None
        )
        return cls(
            id=row.run_id,
            projectId=row.project_id,
            experimentId=row.experiment_id,
            status=row.status,
            created=row.created_at.isoformat(),
            finished=row.finished_at.isoformat() if row.finished_at else None,
            parameters=dict(row.parameters),
            results=dict(row.context_results),
            workflow=wf_snap,
            workflowSource=wf_source,
            error=error,
            executorInfo=dict(row.executor_info),
            profile=row.profile,
            config=dict(row.config),
            configHash=row.config_hash,
            executionHistory=[
                ExecutionRecordResponse(
                    executionId=rec.execution_id,
                    startedAt=rec.started_at.isoformat(),
                    finishedAt=rec.finished_at.isoformat() if rec.finished_at else None,
                    status=rec.status,
                    schedulerJobId=rec.scheduler_job_id,
                )
                for rec in row.executions
            ],
            target=row.target,
        )

    @classmethod
    def from_model(cls, run: Run) -> RunResponse:
        # ``workflow_snapshot`` is an opaque JSON dict on disk
        # (rectification 2026-05-09 — the canonical typed shape lives
        # in ``molexp.workflow.WorkflowSnapshotRef``). The response
        # fishes the well-known fields out by name. When the run has
        # no snapshot but the experiment carries a ``workflow_source``
        # advisory string, synthesize a minimal snapshot so callers
        # see the label without having to refetch the experiment.
        wf_snap = None
        snap = run.metadata.workflow_snapshot
        wf_source: str | None = run.experiment.metadata.workflow_source
        if isinstance(snap, dict):
            source = snap.get("source") or wf_source or ""
            wf_snap = WorkflowSnapshotResponse(
                source=str(source),
                gitCommit=_str_or_none(snap.get("git_commit"))
                or run.experiment.metadata.git_commit,
                codeHash=_str_or_none(snap.get("code_hash")),
                configHash=_str_or_none(snap.get("config_hash")),
            )
        elif wf_source:
            wf_snap = WorkflowSnapshotResponse(
                source=wf_source,
                gitCommit=run.experiment.metadata.git_commit,
                codeHash=None,
                configHash=None,
            )
        error = None
        if run.metadata.error:
            error = {
                "type": run.metadata.error.type,
                "message": run.metadata.error.message,
            }
        # Execution history + status + finished_at come from the OKF ``_ops``
        # sidecar (wsokf-07), parsed exactly once via ``run.read_ops()``.
        ops = run.read_ops()
        history = [
            ExecutionRecordResponse(
                executionId=rec.execution_id,
                startedAt=rec.started_at.isoformat(),
                finishedAt=rec.finished_at.isoformat() if rec.finished_at else None,
                status=rec.status,
                schedulerJobId=rec.scheduler_job_id,
            )
            for rec in ops.executions
        ]
        return cls(
            id=run.id,
            projectId=run.experiment.project.id,
            experimentId=run.experiment.id,
            status=ops.status.value,
            created=run.metadata.created_at.isoformat(),
            finished=ops.finished_at.isoformat() if ops.finished_at else None,
            parameters=run.parameters,
            results=run.context_results,
            workflow=wf_snap,
            workflowSource=wf_source,
            error=error,
            executorInfo=run.metadata.executor_info,
            profile=run.metadata.profile,
            config=run.metadata.config,
            configHash=run.metadata.config_hash,
            executionHistory=history,
            target=run.metadata.target,
        )


class RunStatusResponse(BaseModel):
    id: str
    status: str
    finished: str | None = None


# ── Asset ───────────────────────────────────────────────────────────────────


class AssetResponse(BaseModel):
    """Serialized typed ``Asset``.

    ``kind`` is the discriminator (``data`` / ``artifact`` / ``log`` / …).
    ``extra`` carries subclass-specific fields so the frontend can render
    per-kind details without a separate schema per kind.
    ``content_hash`` is the sha256 (``"sha256:<hex>"``) of the payload
    when the asset is content-addressable; ``None`` for streaming kinds.
    """

    id: str
    name: str
    kind: str
    scope_kind: str
    scope_ids: list[str]
    path: str
    created_at: str
    updated_at: str
    producer: dict[str, Any] | None = None
    tags: dict[str, str] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict)
    content_hash: str | None = None
    has_preview_sidecar: bool = False
    """True when the asset's on-disk file has a same-stem ``.py`` preview
    sidecar (existence-only signal; no user code is executed to compute it)."""

    @classmethod
    def from_model(cls, asset: Asset, *, has_preview_sidecar: bool = False) -> AssetResponse:
        from molexp.workspace.assets import ASSET_ADAPTER

        dumped = ASSET_ADAPTER.dump_python(asset, mode="json")
        common_fields = {
            "asset_id",
            "name",
            "scope",
            "path",
            "created_at",
            "updated_at",
            "producer",
            "tags",
            "kind",
            "content_hash",
        }
        extra = {k: v for k, v in dumped.items() if k not in common_fields}
        return cls(
            id=asset.asset_id,
            name=asset.name,
            kind=dumped["kind"],
            scope_kind=asset.scope.kind,
            scope_ids=list(asset.scope.ids),
            path=str(asset.path),
            created_at=asset.created_at.isoformat(),
            updated_at=asset.updated_at.isoformat(),
            producer=asset.producer.model_dump() if asset.producer else None,
            tags=dict(asset.tags),
            extra=extra,
            content_hash=asset.content_hash,
            has_preview_sidecar=has_preview_sidecar,
        )


# ── Workspace ───────────────────────────────────────────────────────────────


class WorkspaceInfoResponse(BaseModel):
    root: str
    projectCount: int
    assetCount: int
    warnings: list[str] = []
    # Read-model view versions (``runs`` / ``assets`` / ``knowledge``) — the
    # same numbers the list ETags are cut from, so a client can seed its
    # conditional-request state from one bootstrap call.
    versions: dict[str, int] = {}
    # Remote-cache lifecycle (null for local workspaces).
    # ``ready`` = connected AND navigation index built; missing ``_index.json``
    # on first open is normal — the server creates it.
    connected: bool | None = None
    indexed: bool | None = None
    ready: bool | None = None


class FolderEntryResponse(BaseModel):
    name: str
    path: str
    type: str
    size: int | None = None


class FolderBrowseResponse(BaseModel):
    path: str
    entries: list[FolderEntryResponse]


class WorkspaceFolderResponse(BaseModel):
    id: str
    path: str
    name: str
    added_at: str


class FileContentResponse(BaseModel):
    """A bounded UTF-8 window over a workspace file.

    ``content`` is the ``[offset, end)`` slice of a ``totalBytes`` file.  A
    file larger than the window used to be refused with 413; it is now served
    windowed, because a user opening a 500 MB log wants to see *something*
    and a viewer can page with ``since_offset=end``.
    """

    content: str
    offset: int = 0
    end: int = 0
    totalBytes: int = 0
    truncated: bool = False


# ── Execution ───────────────────────────────────────────────────────────────


class ExecutionPlanResponse(BaseModel):
    plan: list[str]
    nodeCount: int


class CacheStatsResponse(BaseModel):
    storeDir: str
    entryCount: int


class CacheClearResponse(BaseModel):
    removedCount: int


# ── Agent ───────────────────────────────────────────────────────────────────


class SessionEventResponse(BaseModel):
    type: str
    ts: str
    payload: dict[str, Any] = Field(default_factory=dict)


class SessionStatsResponse(BaseModel):
    inputTokens: int = 0
    outputTokens: int = 0
    cacheReadTokens: int = 0
    cacheWriteTokens: int = 0
    totalTokens: int = 0
    requests: int = 0
    toolCalls: int = 0
    events: int = 0
    startedAt: str | None = None
    completedAt: str | None = None
    durationSeconds: float | None = None


class AgentSessionResponse(BaseModel):
    sessionId: str
    status: str
    goalDescription: str
    createdAt: str
    events: list[SessionEventResponse] = Field(default_factory=list)
    stats: SessionStatsResponse = Field(default_factory=SessionStatsResponse)
    planMode: bool = False
    skillId: str | None = None


class AgentSessionListResponse(BaseModel):
    sessions: list[AgentSessionResponse]
    total: int


class AgentTaskResponse(BaseModel):
    """User-facing task wrapper around one current runtime session.

    ``taskId`` is the product identifier the UI should route on; ``sessionId``
    is the lower-level runtime handle used to continue the active execution.
    """

    taskId: str
    title: str
    goal: str
    status: str
    createdAt: str
    updatedAt: str | None = None
    sessionId: str
    events: list[SessionEventResponse] = Field(default_factory=list)
    stats: SessionStatsResponse = Field(default_factory=SessionStatsResponse)
    planMode: bool = False
    activeMode: Literal["chat", "plan"] = "chat"
    activeTurnId: str | None = None
    activePlanTaskId: str | None = None
    skillId: str | None = None
    #: Plan / mount scope — the same ids used by plan_emitted and Deliverables.
    projectId: str | None = None
    experimentId: str | None = None
    runId: str | None = None


class AgentTaskListResponse(BaseModel):
    tasks: list[AgentTaskResponse]
    total: int


class CommandParameterSpec(BaseModel):
    """One ``{{param}}`` slot in a slash command's goal_template."""

    name: str
    required: bool = True


class CommandSpec(BaseModel):
    """A single slash command — skill-backed or builtin."""

    slashName: str
    name: str
    description: str = ""
    parameters: list[CommandParameterSpec] = Field(default_factory=list)
    defaultPlanMode: bool = False
    isBuiltin: bool = False
    skillId: str | None = None


class CommandListResponse(BaseModel):
    commands: list[CommandSpec] = Field(default_factory=list)


class CommandParseResponse(BaseModel):
    """Parsed slash-command shape returned by the server.

    The agent-side slash-command parser (formerly ``molexp.agent.skills.commands``)
    was deleted by the ``agent-pydanticai-rectification`` spec; this response
    schema is now the canonical shape and any future parser must produce it.
    """

    kind: Literal["skill", "builtin", "error"]
    name: str = ""
    skillId: str = ""
    parameters: dict[str, str] = Field(default_factory=dict)
    planMode: bool = False
    error: str = ""


class AgentSystemPromptResponse(BaseModel):
    """Per-session system prompt breakdown for the inspector."""

    base: str
    workspaceInstructions: str = ""
    skillInstructions: str = ""
    sessionOverride: str | None = None
    planMode: bool = False
    effective: str


# ── Plugin Registry ─────────────────────────────────────────────────────────


class UiPluginResponse(BaseModel):
    """Per-bundle entry returned by ``GET /api/plugins``.

    Carries no UI semantics — those live in each bundle's own
    ``manifest.json`` (fetched by the browser-side loader). The shape
    is deliberately minimal: a stable ``id``, plus the two URLs the
    frontend needs to fetch the manifest and dynamic-import the entry.
    """

    id: str
    manifestUrl: str
    entryUrl: str


class UiPluginListResponse(BaseModel):
    plugins: list[UiPluginResponse]
    total: int


# ── Task-type registry ──────────────────────────────────────────────────────


class TaskTypeResponse(BaseModel):
    """Single registered task type the agent / UI can compose into IR."""

    slug: str = Field(..., description="Registry slug, e.g. 'core.add'")
    description: str = Field("", description="Human-readable summary")


class TaskTypeListResponse(BaseModel):
    task_types: list[TaskTypeResponse]
    total: int


# ── Generic ─────────────────────────────────────────────────────────────────


class MessageResponse(BaseModel):
    message: str


class HealthResponse(BaseModel):
    status: str
    workspace_available: bool
    capabilities: dict[str, bool] = Field(default_factory=dict)


# ── Run logs / execution ─────────────────────────────────────────────────────


class RunLogsResponse(BaseModel):
    """Per-execution stdout/stderr for a run, as a bounded tail window.

    ``execution_id`` is the attempt these logs belong to; the server
    defaults to the most recent attempt when no specific execution is
    requested.  Each value is a window over
    ``executions/<execution_id>/{stdout,stderr}.log`` (or ``None`` if the
    file is absent — e.g. local executions skip stdout capture).

    A run's stdout can be gigabytes, so the server returns at most
    ``max_bytes`` of it — by default the *tail*, which is what a log viewer
    wants.  The cursor triple makes incremental follow possible: pass
    ``stdout_end`` back as ``since_stdout`` and the next poll returns only
    what was appended.  ``*_truncated`` says the window is not the whole
    file, so a viewer can offer "load earlier".
    """

    execution_id: str | None = None
    stdout: str | None = None
    stderr: str | None = None
    stdout_offset: int | None = None
    stdout_end: int | None = None
    stdout_total: int | None = None
    stdout_truncated: bool = False
    stderr_offset: int | None = None
    stderr_end: int | None = None
    stderr_total: int | None = None
    stderr_truncated: bool = False


class MetricSeriesResponse(BaseModel):
    """Summary for one metric series in a run-local metrics query."""

    key: str
    type: str
    count: int
    latestStep: int | float | None = None
    latestTimestamp: str | None = None
    latestValue: Any | None = None


class RunMetricsResponse(BaseModel):
    """Run-local metrics query response.

    ``nextOffset`` is the cursor: a follow-up poll passing it as
    ``since_offset`` seeks straight to the new bytes, so each poll costs what
    was appended rather than the whole file so far.  ``truncated`` means the
    scan stopped at ``max_scan_bytes`` (or ``limit``) with more data available.
    """

    nextOffset: int = 0
    records: list[dict[str, Any]] = Field(default_factory=list)
    series: list[MetricSeriesResponse] = Field(default_factory=list)
    parseErrors: int = 0
    truncated: bool = False


class RunFileTextResponse(BaseModel):
    """A bounded UTF-8 window over a file under a run directory.

    ``size`` is the whole file; ``content`` is the ``[offset, end)`` slice of
    it that was actually read.  ``truncated`` says they differ, so a viewer
    can page with ``since_offset=end`` rather than pretending it has the file.
    """

    path: str
    content: str
    size: int
    offset: int = 0
    end: int = 0
    truncated: bool = False


class LammpsThermoStage(BaseModel):
    """One ``Per MPI rank ... Loop time`` block as columns + numeric rows."""

    columns: list[str] = Field(default_factory=list)
    rows: list[list[float]] = Field(default_factory=list)


class LammpsLogResponse(BaseModel):
    """Parsed LAMMPS log thermo stages, produced by ``molpy.io.LAMMPSLog``.

    A long MD run's log can be gigabytes.  Above the parse ceiling the server
    parses only the *tail* — the latest stages, which is what a progress view
    wants — and sets ``truncated``.  ``bytesParsed`` is how much was actually
    read, so a caller can tell a whole-file parse from a windowed one (and
    ``version``, read from line 1, is absent in the windowed case).
    """

    path: str
    version: str | None = None
    nStages: int = 0
    stages: list[LammpsThermoStage] = Field(default_factory=list)
    truncated: bool = False
    bytesParsed: int = 0


class TensorboardScalarPoint(BaseModel):
    """One scalar sample read from a tfevents file."""

    step: int
    wallTime: float
    value: float


class TensorboardScalarSeries(BaseModel):
    """All scalar samples for a single tag inside one logdir."""

    tag: str
    logdir: str  # path relative to run_dir
    points: list[TensorboardScalarPoint] = Field(default_factory=list)


class TensorboardScalarsResponse(BaseModel):
    """Parsed scalars across every tfevents logdir found under a run."""

    runId: str
    runDir: str
    logdirs: list[str] = Field(default_factory=list)
    series: list[TensorboardScalarSeries] = Field(default_factory=list)


class RunExecutionResponse(BaseModel):
    """Runtime workflow graph state read from ``workflow.json``.

    The document grows with node count *and* with the size of each node's
    persisted outputs, so it is served in three bands: inline below
    ``EXECUTION_JSON_INLINE_BYTES``; summarised below
    ``EXECUTION_JSON_MAX_BYTES`` (per-node status/snapshot/timestamps kept,
    the bulky ``outputs`` dropped) with ``workflowTruncated`` set; and
    refused with 413 above it.  ``workflowBytes`` is the document's real size
    either way.
    """

    execution_id: str | None = None
    status: str = "not_started"  # running | completed | failed | not_started
    workflow: dict[str, Any] | None = None
    workflowTruncated: bool = False
    workflowBytes: int | None = None


# ── Asset lineage (Producer.inputs DAG) ─────────────────────────────────────


class AssetLineageNode(BaseModel):
    """One node in an asset's lineage neighborhood.

    Carries just enough to render a clickable card in the UI; full
    asset detail is available via ``GET /api/assets/{id}``.
    """

    id: str
    name: str
    kind: str
    scope_kind: str


class AssetLineageResponse(BaseModel):
    """Upstream + downstream neighbours of an asset in the lineage DAG.

    ``ancestors`` is the transitive set of upstream asset_ids reached
    by walking ``producer.inputs`` in reverse; ``descendants`` is the
    transitive forward set. The starting asset is excluded from both.
    """

    asset_id: str
    ancestors: list[AssetLineageNode] = Field(default_factory=list)
    descendants: list[AssetLineageNode] = Field(default_factory=list)


# ── Catalog / file lineage ──────────────────────────────────────────────────


class CatalogProducerInfo(BaseModel):
    """Producer metadata for a catalog entry."""

    runId: str | None = None
    taskId: str | None = None
    executionId: str | None = None


class CatalogScopeInfo(BaseModel):
    """Scope chain that owns this asset (project/experiment/run ids)."""

    kind: str
    projectId: str | None = None
    experimentId: str | None = None
    runId: str | None = None


class CatalogSibling(BaseModel):
    """Other outputs from the same producer.task_id."""

    assetId: str
    name: str
    kind: str
    relPath: str


class CatalogByPathResponse(BaseModel):
    """Reverse-lookup: which run/experiment/project produced a file?"""

    matched: bool
    workspaceRelPath: str
    assetId: str | None = None
    assetKind: str | None = None
    producer: CatalogProducerInfo | None = None
    scope: CatalogScopeInfo | None = None
    siblings: list[CatalogSibling] = Field(default_factory=list)


class RunFileNode(BaseModel):
    """One node in a run's output file tree.

    On a folder, ``entryCount`` is how many children it really has and
    ``truncated`` says ``children`` holds fewer — either because the
    per-directory cap was hit or because the walk stopped at ``max_depth``.
    A run that wrote 100k frames into one directory therefore costs a bounded
    response instead of an unbounded one.
    """

    name: str
    relPath: str  # relative to run_dir
    type: str  # 'file' | 'folder'
    size: int | None = None
    modified: float | None = None
    assetId: str | None = None
    assetKind: str | None = None
    taskId: str | None = None
    entryCount: int | None = None
    truncated: bool = False
    children: list[RunFileNode] = Field(default_factory=list)


RunFileNode.model_rebuild()


class RunFilesResponse(BaseModel):
    """Per-run output file tree, enriched with catalog producer metadata."""

    runId: str
    runDir: str
    nodes: list[RunFileNode] = Field(default_factory=list)


# ── Experiment comparison ───────────────────────────────────────────────────


class ComparisonRunRow(BaseModel):
    """One run row in the experiment comparison matrix."""

    runId: str
    status: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    durationSec: float | None = None
    created: str
    finished: str | None = None
    error: dict[str, str] | None = None


class ExperimentComparisonResponse(BaseModel):
    """Comparison matrix: parameter columns x run rows + metric columns."""

    experimentId: str
    projectId: str
    paramKeys: list[str] = Field(default_factory=list)
    metricKeys: list[str] = Field(default_factory=list)
    runs: list[ComparisonRunRow] = Field(default_factory=list)


# ── Run actions ─────────────────────────────────────────────────────────────


class RunActionResponse(BaseModel):
    """Result of an actionable mutation on a run."""

    runId: str
    status: str
    message: str | None = None


class RunContinueResponse(BaseModel):
    """Result of continuing a run in place — ``resume`` or ``rerun``.

    Both verbs act on the same ``runId`` (no clone, no new run). ``executionId``
    is the execution the action targeted: the reopened one for ``resume``, the
    freshly-derived ``exec-{run_id}-N`` for ``rerun``.
    """

    runId: str
    executionId: str
    projectId: str
    experimentId: str
    status: str


# ── Skills / MCP / Tool admin ───────────────────────────────────────────────


class SkillResponse(BaseModel):
    """A saved skill (goal template + tool scope + system addendum)."""

    id: str
    name: str
    description: str = ""
    goalTemplate: str
    slashName: str = ""
    instructions: str = ""
    defaultPlanMode: bool = False
    constraints: list[str] = Field(default_factory=list)
    successCriteria: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    allowedTools: list[str] = Field(default_factory=list)
    deniedTools: list[str] = Field(default_factory=list)
    requiresExitTool: str = ""
    builtin: bool = False
    scope: str = "workspace"
    createdAt: str = ""
    updatedAt: str = ""


class SkillListResponse(BaseModel):
    skills: list[SkillResponse] = Field(default_factory=list)


class ToolParameterResponse(BaseModel):
    name: str
    annotation: str = "Any"
    required: bool = False


class AgentToolResponse(BaseModel):
    """One agent tool — molexp **builtin** or MCP-discovered.

    ``source`` is:

    * ``"builtin"`` — always-on molexp tools (``workspace_ensure``,
      ``run_land``, ``code_write``, …)
    * ``"mcp:<server-name>"`` — tool from an MCP server, so the UI can
      attach it to that server's expanded row
    """

    name: str
    description: str = ""
    parameters: list[ToolParameterResponse] = Field(default_factory=list)
    requiresApproval: bool = False
    source: str


class McpToolGroupResponse(BaseModel):
    """Per-server discovery status for the MCP server list.

    Even when a server is offline / misconfigured / unauthorized we want
    the UI to render *something* under that server's heading — a row with
    the error keeps users oriented instead of silently dropping the group.
    """

    server: str
    scope: Literal["user", "workspace"]
    ok: bool
    toolCount: int = 0
    error: str | None = None


class AgentToolListResponse(BaseModel):
    tools: list[AgentToolResponse] = Field(default_factory=list)
    mcpGroups: list[McpToolGroupResponse] = Field(default_factory=list)


class CustomToolHttpInvokerResponse(BaseModel):
    """Read-only view of a user/workspace HTTP-webhook tool's wiring.

    Header values are returned **with secret references intact**
    (``${SECRET:KEY}``); the actual secret value never leaves the
    server.
    """

    kind: Literal["http"] = "http"
    url: str
    method: Literal["GET", "POST", "PUT", "DELETE"] = "POST"
    headers: dict[str, str] = Field(default_factory=dict)
    bodyTemplate: str = ""


class CustomToolPythonInvokerResponse(BaseModel):
    """Read-only view of a Python-implementation tool reference."""

    kind: Literal["python"] = "python"
    target: str


class CustomToolResponse(BaseModel):
    """Single user/workspace/registration-tier tool record.

    Mirrors the `AgentToolResponse` shape but adds the persistence
    metadata (`scope`, `shadowed`, `valid`, `createdAt`, `updatedAt`)
    needed for tier-aware listing and inline error reporting.
    """

    id: str
    name: str
    description: str = ""
    category: Literal["workspace", "workflow", "chat", "control", "web"] = "workspace"
    mutates: bool = False
    requiresApproval: bool = False
    parametersSchema: dict[str, object] = Field(default_factory=dict)
    invoker: CustomToolHttpInvokerResponse | CustomToolPythonInvokerResponse = Field(
        discriminator="kind"
    )
    scope: Literal["native", "user", "workspace"] = "user"
    shadowed: bool = False
    valid: bool = True
    invalidReason: str = ""
    builtin: bool = False
    createdAt: str = ""
    updatedAt: str = ""


class CustomToolListResponse(BaseModel):
    tools: list[CustomToolResponse] = Field(default_factory=list)


class McpAuthSummary(BaseModel):
    """Public-safe view of a server's structured auth settings.

    Token values, refresh tokens, and client secrets are never exposed —
    only metadata the UI needs to render the connection card. ``connected``
    indicates the token store on disk has at least one persisted token
    (rough proxy for "user has completed Connect at least once").
    """

    type: Literal["oauth2"]
    scopes: list[str] = Field(default_factory=list)
    clientId: str | None = None
    connected: bool = False


class McpServerResponse(BaseModel):
    """One MCP server entry, possibly merged across scopes.

    ``shadowed`` is True when this entry exists at User scope but is
    overridden by a Workspace entry of the same name. ``unresolvedSecrets``
    lists ``${SECRET:KEY}`` references that have no value in either secret
    store — the runtime skips such entries.
    """

    name: str
    scope: Literal["native", "user", "workspace"]
    transport: str = ""
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    url: str | None = None
    envKeys: list[str] = Field(default_factory=list)
    headerKeys: list[str] = Field(default_factory=list)
    secretRefs: list[str] = Field(default_factory=list)
    unresolvedSecrets: list[str] = Field(default_factory=list)
    shadowed: bool = False
    valid: bool = True
    invalidReason: str = ""
    auth: McpAuthSummary | None = None


class McpServerListResponse(BaseModel):
    """Merged view of both scopes plus the resolved file paths.

    ``workspacePath`` and ``userPath`` are the absolute paths the store
    would read/write at each scope (whether or not the file currently
    exists) — useful for UI tooltips like "Edit ~/.molexp/mcp.json".
    """

    workspacePath: str
    userPath: str
    servers: list[McpServerResponse] = Field(default_factory=list)


class McpServerTestResponse(BaseModel):
    """Outcome of probing an MCP server (subprocess spawn or HTTP handshake)."""

    ok: bool
    name: str
    scope: Literal["native", "user", "workspace"]
    transport: str
    latencyMs: int = 0
    toolCount: int = 0
    error: str | None = None


class McpOAuthStartResponse(BaseModel):
    """Result of POST /mcp/servers/{name}/oauth/start.

    The UI opens ``authorizeUrl`` in a popup; once the IdP bounces back to
    the SPA the SPA POSTs ``code``+``state`` to the callback endpoint to
    finish the flow.
    """

    name: str
    scope: Literal["native", "user", "workspace"]
    authorizeUrl: str


class McpOAuthStatusResponse(BaseModel):
    """Whether the named server currently has a usable OAuth token on disk.

    ``hasTokens`` is True after a successful Connect; False if the user has
    never connected, has disconnected, or the token file got corrupted.
    """

    name: str
    scope: Literal["native", "user", "workspace"]
    hasTokens: bool
    scopes: list[str] = Field(default_factory=list)


class McpSecretRefRow(BaseModel):
    """One row in the secrets list — key + which servers reference it."""

    key: str
    isSet: bool
    referencedBy: list[str] = Field(default_factory=list)


class McpSecretListResponse(BaseModel):
    """Secrets at the requested scope. Plaintext values are never returned."""

    scope: Literal["native", "user", "workspace"]
    path: str
    secrets: list[McpSecretRefRow] = Field(default_factory=list)


# ── Agent provider config ───────────────────────────────────────────────────


class AgentProviderResponse(BaseModel):
    """Public view of the workspace's LLM provider config — never the raw key.

    ``apiKeyPreview`` is a masked rendering ("sk-...1234"); ``apiKeySet``
    is the boolean the UI uses to gate the "ready" indicator.
    """

    provider: str = "anthropic"
    model: str = "claude-sonnet-4-6"
    baseUrl: str = ""
    apiKeyPreview: str = ""
    apiKeySet: bool = False
    instructions: str = ""
    supportedProviders: list[str] = Field(default_factory=list)


class AgentProviderTestResponse(BaseModel):
    """Result of probing the configured provider with a minimal request.

    ``ok=True`` means we got a model response back. ``latencyMs`` is the
    wall-clock RTT for the probe; ``error`` is filled only on failure
    with a short, user-readable description (no stack trace, no key).
    """

    ok: bool = False
    provider: str = ""
    model: str = ""
    latencyMs: int = 0
    reply: str = ""
    error: str | None = None


class AgentHealthResponse(BaseModel):
    """Whether the agent runtime is ready to start a new session.

    ``ready=False`` indicates a configuration problem the user can
    resolve in Agent Settings (most commonly: no API key). ``source``
    is one of ``"stored"`` (workspace config), ``"env"`` (process env
    var), or ``"none"`` (not configured).
    """

    ready: bool = False
    provider: str = ""
    model: str = ""
    source: str = "none"
    reason: str = ""
    envVar: str = ""
