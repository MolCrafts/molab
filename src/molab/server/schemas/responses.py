"""Pydantic response models for Molab API.

All ``from_model()`` methods take typed domain objects — no ``Any``,
no ``getattr`` guessing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import Field

from molab.workspace import (
    Experiment,
    Project,
    Run,
)
from molab.workspace.execution_dirs import ExecutionDir, list_execution_dirs

from ._wire import ApiModel


def _str_or_none(value: object) -> str | None:
    """Coerce a JSON-shaped opaque value into ``str | None`` for response fields."""
    if value is None:
        return None
    return str(value)


class WorkflowDocumentResponse(ApiModel):
    """The persisted (normalized) workflow IR document for an experiment."""

    project_id: str = Field(..., description="Owning project id")
    experiment_id: str = Field(..., description="Owning experiment id")
    document: dict[str, Any] = Field(..., description="Normalized workflow IR document")


def _read_context_results(run: Run) -> dict[str, Any]:
    """Read the ``context.results`` block from run.json on disk.

    The ``Context`` object is owned by the active ``RunContext`` only; once
    a run has finished, the only place ``results`` survives is the
    ``context`` sub-object inside ``run.json``. We read it lazily so the
    REST response can show "what did this run produce" without bringing
    runtime state into the persisted ``RunMetadata`` model.
    """
    run_json = Path(run.run_dir / "run.json")
    if not run_json.exists():
        return {}
    try:
        with open(run_json) as fh:  # noqa: PTH123
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    ctx = data.get("context") or {}
    results = ctx.get("results") or {}
    return dict(results) if isinstance(results, dict) else {}


# ── Project ─────────────────────────────────────────────────────────────────


class ProjectResponse(ApiModel):
    id: str
    name: str
    path: str
    """Workspace-relative directory. See :func:`workspace_relative`."""

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
            path=workspace_relative(project.workspace.resolve(), project.path),
            description=project.description,
            owner=project.owner,
            tags=project.tags,
            config=project.config,
            created=project.created_at.isoformat(),
            experimentCount=experiment_count,
        )


# ── Experiment ──────────────────────────────────────────────────────────────


class ExperimentResponse(ApiModel):
    id: str
    projectId: str
    name: str
    path: str
    """Workspace-relative directory. See :func:`workspace_relative`."""

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
        # Always expose runCount so the nav shows "2 runs" before expand.
        # Full run rows are only included when *runs* is passed (detail GET).
        if runs is not None:
            run_objs = runs
            run_list = [
                RunSummary(
                    id=r.id,
                    statusSummary=RunStatusSummaryResponse(
                        total=r.status_summary.total,
                        active=r.status_summary.active,
                        notStarted=r.status_summary.not_started,
                        byStatus=r.status_summary.by_status,
                    ),
                    created=r.metadata.created_at.isoformat(),
                    finished=(r.finished_at.isoformat() if r.finished_at else None),
                    parameters=r.parameters,
                )
                for r in run_objs
            ]
            run_count = len(run_objs)
        else:
            run_list = []
            run_count = len(experiment.list_runs())
        return cls(
            id=experiment.id,
            projectId=experiment.project.id,
            name=experiment.name,
            path=workspace_relative(experiment.project.workspace.resolve(), experiment.path),
            description=experiment.description,
            workflow=experiment.metadata.workflow_source,
            workflowType=experiment.metadata.workflow_type,
            planRunId=experiment.metadata.plan_run_id,
            gitCommit=experiment.metadata.git_commit,
            parameterSpace=experiment.metadata.parameter_space,
            defaultTarget=experiment.metadata.default_target,
            created=experiment.created_at.isoformat(),
            runCount=run_count,
            runs=run_list,
        )


# ── Run ─────────────────────────────────────────────────────────────────────


class RunStatusSummaryResponse(ApiModel):
    total: int
    active: int
    notStarted: bool
    byStatus: dict[str, int] = Field(default_factory=dict)


class RunSummary(ApiModel):
    id: str
    statusSummary: RunStatusSummaryResponse
    created: str
    finished: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class WorkflowSnapshotResponse(ApiModel):
    source: str
    gitCommit: str | None = None
    codeHash: str | None = None
    configHash: str | None = None


class ExecutionResponse(ApiModel):
    """One execution attempt of a Run.

    Mirrors :class:`molab.workspace.models.ExecutionRecord` with
    JSON-friendly field names so the UI can render a per-attempt
    timeline.
    """

    id: str
    runId: str
    mode: str
    status: str
    createdAt: str
    startedAt: str | None = None
    finishedAt: str | None = None
    basedOnExecutionId: str | None = None
    checkpointArtifactId: str | None = None
    executor: dict[str, Any] = Field(default_factory=dict)
    environment: dict[str, Any] = Field(default_factory=dict)
    artifactIds: list[str] = Field(default_factory=list)
    error: dict[str, Any] | None = None


def workspace_relative(root: object, full: object) -> str:
    """*full* as a path under the workspace *root*, or *full* if outside it.

    Every entity response carries one, because only the server knows it: each
    segment of a workspace path is a *name* — a project's slug, an
    experiment's slug, a run's parameters — and none of them is recoverable
    from the ids a client holds. A path composed there points at a directory
    that was never created.
    """
    root_text = str(root).rstrip("/")
    full_text = str(full)
    return full_text[len(root_text) :].lstrip("/") if full_text.startswith(root_text) else full_text


def _workspace_relative(run: Run) -> str:
    """A run's directory, relative to the workspace root."""
    return workspace_relative(run.experiment.project.workspace.resolve(), run.run_dir)


class RunResponse(ApiModel):
    id: str
    name: str
    """What the run is called: its parameters. This is what a person reads;
    ``id`` is the UUIDv7 other records cite."""

    path: str
    """Workspace-relative directory. Sent because only the server knows it:
    every segment is a *name*, and a client that rebuilt one from ids would
    get a path that does not exist."""

    projectId: str
    experimentId: str
    definitionHash: str
    experimentRevisionId: str
    statusSummary: RunStatusSummaryResponse
    created: str
    finished: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    workflow: WorkflowSnapshotResponse | None = None
    workflowSource: str | None = None
    executions: list[ExecutionResponse] = Field(default_factory=list)
    target: str | None = None

    @classmethod
    def from_model(cls, run: Run) -> RunResponse:
        # ``workflow_snapshot`` is an opaque, read-only legacy JSON dict
        # on disk with no typed model. The response fishes the
        # well-known fields out by name. When the run has
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
        executions = [
            ExecutionResponse(
                id=rec.id,
                runId=rec.run_id,
                mode=rec.mode.value,
                status=rec.status.value,
                createdAt=rec.created_at.isoformat(),
                startedAt=rec.started_at.isoformat() if rec.started_at else None,
                finishedAt=rec.finished_at.isoformat() if rec.finished_at else None,
                basedOnExecutionId=rec.based_on_execution_id,
                checkpointArtifactId=rec.checkpoint_artifact_id,
                executor=rec.executor,
                environment=rec.environment,
                artifactIds=list(rec.artifact_ids),
                error=rec.error,
            )
            for rec in run.executions
        ]
        summary = run.status_summary
        return cls(
            id=run.id,
            name=run.name,
            path=_workspace_relative(run),
            projectId=run.experiment.project.id,
            experimentId=run.experiment.id,
            definitionHash=run.metadata.definition_hash,
            experimentRevisionId=run.metadata.experiment_revision_id,
            statusSummary=RunStatusSummaryResponse(
                total=summary.total,
                active=summary.active,
                notStarted=summary.not_started,
                byStatus=summary.by_status,
            ),
            created=run.metadata.created_at.isoformat(),
            finished=run.finished_at.isoformat() if run.finished_at else None,
            parameters=run.parameters,
            workflow=wf_snap,
            workflowSource=wf_source,
            executions=executions,
            target=run.metadata.target,
        )


# ── Workspace ───────────────────────────────────────────────────────────────


class WorkspaceInfoResponse(ApiModel):
    root: str
    projectCount: int
    assetCount: int
    warnings: list[str] = Field(default_factory=list)
    # Remote-cache lifecycle (null for local workspaces).
    # ``ready`` = connected AND navigation index built; missing ``_index.json``
    # on first open is normal — the server creates it.
    connected: bool | None = None
    indexed: bool | None = None
    ready: bool | None = None


class FileContentResponse(ApiModel):
    content: str


# ── Plugin Registry ─────────────────────────────────────────────────────────


class UiPluginResponse(ApiModel):
    """Per-bundle entry returned by ``GET /api/plugins``.

    Carries no UI semantics — those live in each bundle's own
    ``manifest.json`` (fetched by the browser-side loader). The shape
    is deliberately minimal: a stable ``id``, plus the two URLs the
    frontend needs to fetch the manifest and dynamic-import the entry.
    """

    id: str
    manifestUrl: str
    entryUrl: str


class UiPluginListResponse(ApiModel):
    plugins: list[UiPluginResponse]
    total: int


# ── Task-type registry ──────────────────────────────────────────────────────


class TaskTypeResponse(ApiModel):
    """Single registered task type the agent / UI can compose into IR."""

    slug: str = Field(..., description="Registry slug, e.g. 'core.add'")
    description: str = Field("", description="Human-readable summary")


class TaskTypeListResponse(ApiModel):
    task_types: list[TaskTypeResponse]
    total: int


# ── Generic ─────────────────────────────────────────────────────────────────


class MessageResponse(ApiModel):
    message: str


class HealthResponse(ApiModel):
    status: str
    workspace_available: bool
    capabilities: dict[str, bool] = Field(default_factory=dict)
    auth_required: bool = Field(
        default=False,
        description="True when the server process has auth enabled (UI should gate on login).",
    )


# ── Run logs / execution ─────────────────────────────────────────────────────


class RunLogsResponse(ApiModel):
    """Per-execution stdout/stderr for a run.

    ``execution_id`` is the attempt these logs belong to; the server
    defaults to the most recent attempt when no specific execution is
    requested.  Each value is the full content of
    ``executions/<execution_id>/{stdout,stderr}.log`` (or ``None`` if the
    file is absent — e.g. local executions skip stdout capture).
    """

    execution_id: str | None = None
    stdout: str | None = None
    stderr: str | None = None


class RunFileTextResponse(ApiModel):
    """Raw UTF-8 text content of a file under a run directory."""

    path: str
    content: str
    size: int


class TensorboardScalarPoint(ApiModel):
    """One scalar sample read from a tfevents file."""

    step: int
    wallTime: float
    value: float


class TensorboardScalarSeries(ApiModel):
    """All scalar samples for a single tag inside one logdir."""

    tag: str
    logdir: str  # path relative to run_dir
    points: list[TensorboardScalarPoint] = Field(default_factory=list)


class TensorboardScalarsResponse(ApiModel):
    """Parsed scalars across every tfevents logdir found under a run."""

    runId: str
    runDir: str
    logdirs: list[str] = Field(default_factory=list)
    series: list[TensorboardScalarSeries] = Field(default_factory=list)


class RunExecutionResponse(ApiModel):
    """One Execution's node journal as the workflow layer reports it (``molab.workflow.read_journal``).

    ``status`` is the Execution record's status; ``workflow`` is the journal
    document (header + ``task_configs``), or null before the journal exists.
    """

    execution_id: str | None = None
    status: str = "not_started"  # queued | running | finalizing | succeeded | failed | cancelled | interrupted
    workflow: dict[str, Any] | None = None


# ── Catalog / file lineage ──────────────────────────────────────────────────


class CatalogProducerInfo(ApiModel):
    """Producer metadata for a catalog entry."""

    runId: str | None = None
    taskId: str | None = None
    executionId: str | None = None


class CatalogScopeInfo(ApiModel):
    """Scope chain that owns this asset (project/experiment/run ids)."""

    kind: str
    projectId: str | None = None
    experimentId: str | None = None
    runId: str | None = None


class CatalogSibling(ApiModel):
    """Other outputs from the same producer.task_id."""

    assetId: str
    name: str
    kind: str
    relPath: str


class CatalogByPathResponse(ApiModel):
    """Reverse-lookup: which run/experiment/project produced a file?"""

    matched: bool
    workspaceRelPath: str
    assetId: str | None = None
    assetKind: str | None = None
    producer: CatalogProducerInfo | None = None
    scope: CatalogScopeInfo | None = None
    siblings: list[CatalogSibling] = Field(default_factory=list)


class RunFileNode(ApiModel):
    """One node in a run's output file tree."""

    name: str
    relPath: str  # relative to run_dir
    type: str  # 'file' | 'folder'
    size: int | None = None
    modified: float | None = None
    assetId: str | None = None
    assetKind: str | None = None
    taskId: str | None = None
    children: list[RunFileNode] = Field(default_factory=list)


RunFileNode.model_rebuild()


class ExecutionDirResponse(ApiModel):
    """One of an attempt's directories, and what it promises.

    Sent so a client never has to know a layout. Which directory holds
    results, and which is scratch it should not chart, is answered by these
    flags — the same declaration the server itself queries.
    """

    name: str
    purpose: str
    versioned: bool
    products: bool

    @classmethod
    def from_declaration(cls, directory: ExecutionDir) -> ExecutionDirResponse:
        return cls(
            name=directory.name,
            purpose=directory.purpose,
            versioned=directory.versioned,
            products=directory.products,
        )


class RunFilesResponse(ApiModel):
    """Per-run output file tree, enriched with catalog producer metadata."""

    runId: str
    runDir: str
    nodes: list[RunFileNode] = Field(default_factory=list)
    dirs: list[ExecutionDirResponse] = Field(
        default_factory=lambda: [
            ExecutionDirResponse.from_declaration(d) for d in list_execution_dirs()
        ]
    )
    """Every declared attempt directory, in lookup order.

    Travels with the tree because that is where a client decides what to
    read: a ``.mlp.jsonl`` in a ``products`` directory is a result, the same
    name under scratch is a half-written intermediate."""


class ArtifactResponse(ApiModel):
    id: str
    executionId: str
    runId: str
    projectId: str
    name: str
    sourcePath: str
    digest: str
    size: int
    contentKind: str
    mediaType: str | None = None
    semanticType: str | None = None
    declarationId: str | None = None
    inputEntityIds: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    createdAt: str


class ExecutionEvidenceResponse(ApiModel):
    kind: str
    path: str
    digest: str | None = None
    size: int


class ExecutionOutputsResponse(ApiModel):
    executionId: str
    stdout: str | None = None
    stderr: str | None = None
    runtime: str | None = None
    artifacts: list[ArtifactResponse] = Field(default_factory=list)
    evidence: list[ExecutionEvidenceResponse] = Field(default_factory=list)
    unregistered: list[RunFileNode] = Field(default_factory=list)
    results: dict[str, Any] = Field(default_factory=dict)


class ManagedAssetResponse(ApiModel):
    id: str
    projectId: str
    title: str
    createdAt: str
    versionCount: int = 0


class AssetVersionResponse(ApiModel):
    id: str
    assetId: str
    sourceArtifactId: str
    version: int
    digest: str
    size: int
    contentKind: str
    mediaType: str | None = None
    semanticType: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    createdAt: str


class ArtifactPromotionResponse(ApiModel):
    asset: ManagedAssetResponse
    version: AssetVersionResponse


# ── Experiment comparison ───────────────────────────────────────────────────


class ComparisonRunRow(ApiModel):
    """One immutable Run definition in the experiment comparison matrix."""

    runId: str
    definitionHash: str
    experimentRevisionId: str
    inputAssetIds: list[str] = Field(default_factory=list)
    statusSummary: RunStatusSummaryResponse
    parameters: dict[str, Any] = Field(default_factory=dict)
    created: str


class ExperimentComparisonResponse(ApiModel):
    """Comparison matrix of scientific Run definitions only."""

    experimentId: str
    projectId: str
    paramKeys: list[str] = Field(default_factory=list)
    runs: list[ComparisonRunRow] = Field(default_factory=list)
