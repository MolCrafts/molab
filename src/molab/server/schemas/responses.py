"""Pydantic response models for Molab API.

All ``from_model()`` methods take typed domain objects — no ``Any``,
no ``getattr`` guessing.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from molab.workspace import (
    Execution,
    Experiment,
    Project,
    Run,
    WorkflowKind,
)
from molab.workspace.domain import ArtifactOrigin, Asset, AssetVersion, ImportOrigin
from molab.workspace.execution_dirs import ExecutionDir, list_execution_dirs
from molab.workspace.experiment import WORKFLOW_DOC_FILENAME

from ._wire import ApiModel


def _str_or_none(value: object) -> str | None:
    """Coerce a JSON-shaped opaque value into ``str | None`` for response fields."""
    if value is None:
        return None
    return str(value)


def _latest_execution(executions: Iterable[Execution]) -> Execution | None:
    """The newest attempt, keyed by ``(created_at, seq)``.

    Args:
        executions: Attempts of one run, or of every run on a detail response.

    Returns:
        The latest execution, or ``None`` when *executions* is empty.
    """
    found = list(executions)
    if not found:
        return None
    return max(found, key=lambda execution: (execution.created_at, execution.seq))


def _latest_source_commit(executions: Iterable[Execution]) -> str | None:
    """``source.vcs_commit`` of the newest attempt.

    Args:
        executions: Attempts to scan. An empty sequence returns ``None``.

    Returns:
        The commit string, or ``None`` when there is no attempt or it captured
        no source.
    """
    latest = _latest_execution(executions)
    if latest is None or latest.source is None:
        return None
    return latest.source.vcs_commit


class WorkflowDocumentResponse(ApiModel):
    """The persisted (normalized) workflow IR document for an experiment."""

    project_id: str = Field(..., description="Owning project id")
    experiment_id: str = Field(..., description="Owning experiment id")
    document: dict[str, Any] = Field(..., description="Normalized workflow IR document")


def _read_context_results(run: Run) -> dict[str, Any]:
    """Read a legacy results mapping if an old run record still carries one.

    Current attempts keep products on the Execution. This helper only looks
    at a leftover mapping inside ``run.json`` so an old record can still
    answer. It does not write.
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
    ref: str

    @classmethod
    def from_model(cls, project: Project, experiment_count: int | None = None) -> ProjectResponse:
        from molab.workspace.refs import ref_of

        return cls(
            id=project.id,
            name=project.name,
            ref=str(ref_of(project)),
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
    workflowKind: WorkflowKind | None = None
    workflowEntrypoint: str | None = None
    planRunId: str | None = None
    gitCommit: str | None = None
    parameterSpace: dict[str, Any] = Field(default_factory=dict)
    defaultTarget: str | None = None
    created: str
    runCount: int | None = None
    runs: list[RunSummary] = Field(default_factory=list)
    ref: str

    @classmethod
    def from_model(
        cls, experiment: Experiment, runs: list[Run] | None = None
    ) -> ExperimentResponse:
        # Always expose runCount so the nav shows "2 runs" before expand.
        # Full run rows are only included when *runs* is passed (detail GET).
        git_commit = None
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
        from molab.workspace.refs import ref_of

        document = experiment.workflow_document
        workflow = json.dumps(document, sort_keys=True) if document is not None else None
        entrypoint = experiment.metadata.workflow_entrypoint
        if experiment.workflow_kind == "document":
            entrypoint = None
        if runs is not None:
            git_commit = _latest_source_commit(
                execution for run in run_objs for execution in run.executions
            )
        return cls(
            id=experiment.id,
            projectId=experiment.project.id,
            name=experiment.name,
            path=workspace_relative(experiment.project.workspace.resolve(), experiment.path),
            description=experiment.description,
            workflow=workflow,
            workflowKind=experiment.workflow_kind,
            workflowEntrypoint=entrypoint,
            planRunId=experiment.metadata.plan_run_id,
            gitCommit=git_commit,
            parameterSpace=experiment.metadata.parameter_space,
            defaultTarget=experiment.metadata.default_target,
            created=experiment.created_at.isoformat(),
            runCount=run_count,
            runs=run_list,
            ref=str(ref_of(experiment)),
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
    ref: str
    """Canonical reference. Only the server composes it."""

    @classmethod
    def from_model(cls, run: Run) -> RunResponse:
        from molab.workspace.refs import ref_of

        experiment = run.experiment
        document = experiment.workflow_document
        wf_source = json.dumps(document, sort_keys=True) if document is not None else None
        kind = experiment.workflow_kind
        wf_snap = None
        if kind is not None:
            entrypoint = experiment.metadata.workflow_entrypoint
            if entrypoint:
                source = entrypoint
            elif document is not None:
                source = WORKFLOW_DOC_FILENAME
            else:
                source = kind
            latest = _latest_execution(run.executions)
            wf_snap = WorkflowSnapshotResponse(
                source=source,
                gitCommit=_latest_source_commit(run.executions),
                codeHash=None if latest is None else latest.workflow_digest,
                configHash=(
                    None if latest is None else _str_or_none(latest.environment.get("config_hash"))
                ),
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
            ref=str(ref_of(run)),
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
    ref: str

    @classmethod
    def from_model(cls, asset: Asset, version_count: int) -> ManagedAssetResponse:
        """Map a domain asset onto the wire.

        Args:
            asset: The asset. ``projectId`` comes from its scope.
            version_count: How many versions the asset has.

        Returns:
            The response model.
        """
        from molab.workspace.refs import ref_of

        return cls(
            id=asset.id,
            projectId=asset.project_id or "",
            title=asset.title,
            createdAt=asset.created_at.isoformat(),
            versionCount=version_count,
            ref=str(ref_of(asset)),
        )


class AssetVersionResponse(ApiModel):
    id: str
    assetId: str
    sourceArtifactId: str | None = None
    originKind: Literal["artifact", "import"]
    originRef: str | None = None
    originUri: str | None = None
    importAction: str | None = None
    version: int
    digest: str | None = None
    size: int | None = None
    contentKind: str | None = None
    mediaType: str | None = None
    semanticType: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    createdAt: str

    @classmethod
    def from_model(cls, version: AssetVersion) -> AssetVersionResponse:
        """Map one asset version, including its origin, onto the wire.

        Args:
            version: The version record.

        Returns:
            The response model. Digest fields are ``None`` when the version
            has no content reference.
        """
        origin = version.origin
        content = version.content
        origin_ref: str | None = None
        origin_uri: str | None = None
        import_action: str | None = None
        if isinstance(origin, ArtifactOrigin):
            origin_ref = origin.ref
        elif isinstance(origin, ImportOrigin):
            origin_uri = origin.uri
            import_action = origin.action
        return cls(
            id=version.id,
            assetId=version.asset_id,
            sourceArtifactId=version.source_artifact_id,
            originKind=origin.kind,
            originRef=origin_ref,
            originUri=origin_uri,
            importAction=import_action,
            version=version.version,
            digest=None if content is None else content.digest,
            size=None if content is None else content.size,
            contentKind=None if content is None else content.kind,
            mediaType=version.media_type,
            semanticType=version.semantic_type,
            metadata=dict(version.metadata),
            createdAt=version.created_at.isoformat(),
        )


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
