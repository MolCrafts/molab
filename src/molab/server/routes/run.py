"""Run routes for Molab API."""

from __future__ import annotations

import io
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from molab.plugins.submit_molq.submit import SubmitHandler
from molab.workflow import read_journal
from molab.workspace import (
    ExperimentNotFoundError as WorkspaceExperimentNotFoundError,
)
from molab.workspace import (
    ProjectNotFoundError as WorkspaceProjectNotFoundError,
)
from molab.workspace import (
    RunNotFoundError as WorkspaceRunNotFoundError,
)
from molab.workspace.domain import Artifact, ExecutionMode, ExecutionStatus
from molab.workspace.execution_dirs import JOBS, product_dirs
from molab.workspace.execution_repository import ExecutionRepository
from molab.workspace.fs_cached import CachedRemoteFileSystem
from molab.workspace.fs_tree import list_tree_children, tree_to_run_file_dicts
from molab.workspace.history import AgentRef
from molab.workspace.targets import get_target

from ..dependencies import get_workspace
from ..exceptions import RunNotFoundError
from ..schemas import (
    ArtifactPromoteRequest,
    ArtifactPromotionResponse,
    ArtifactResponse,
    AssetVersionResponse,
    ExecutionAttemptCreateRequest,
    ExecutionEvidenceResponse,
    ExecutionOutputsResponse,
    ExecutionResponse,
    ManagedAssetResponse,
    RunAnalyzeFailureRequest,
    RunCreateRequest,
    RunExecutionResponse,
    RunFileNode,
    RunFilesResponse,
    RunFileTextResponse,
    RunHarvestRequest,
    RunLogsResponse,
    RunResponse,
)

router = APIRouter(
    prefix="/projects/{project_id}/experiments/{experiment_id}/runs",
    tags=["runs"],
)


def _get_experiment(workspace, project_id: str, experiment_id: str):  # noqa: ANN001, ANN202
    """Strict-getter chain — returns ``Experiment`` or ``None``.

    Translates the workspace-layer ``*NotFoundError`` exceptions to a
    boolean miss so the existing ``if not experiment:`` callers continue
    to map missing entities onto their HTTP 404 responses.
    """
    try:
        project = workspace.get_project(project_id)
    except WorkspaceProjectNotFoundError:
        return None
    try:
        return project.get_experiment(experiment_id)
    except WorkspaceExperimentNotFoundError:
        return None


def _get_run_or_none(experiment, run_id: str):  # noqa: ANN001, ANN202
    """Wrap ``experiment.get_run(run_id)`` to map ``RunNotFoundError`` → ``None``."""
    try:
        return experiment.get_run(run_id)
    except WorkspaceRunNotFoundError:
        return None


def _execution_repository(workspace, run) -> ExecutionRepository:  # noqa: ANN001
    return ExecutionRepository(
        workspace.root,
        run.run_dir,
        run_id=run.id,
        project_id=run.experiment.project.id,
        fs=workspace.fs,
    )


def _execution_response(state) -> ExecutionResponse:  # noqa: ANN001
    return ExecutionResponse(
        id=state.id,
        runId=state.run_id,
        mode=state.mode.value,
        status=state.status.value,
        createdAt=state.created_at.isoformat(),
        startedAt=state.started_at.isoformat() if state.started_at else None,
        finishedAt=state.finished_at.isoformat() if state.finished_at else None,
        basedOnExecutionId=state.based_on_execution_id,
        checkpointArtifactId=state.checkpoint_artifact_id,
        executor=state.executor,
        environment=state.environment,
        artifactIds=list(state.artifact_ids),
        error=state.error,
    )


def _artifact_response(artifact: Artifact) -> ArtifactResponse:
    """Map an Execution Artifact record onto the API response shape."""
    content = artifact.content
    return ArtifactResponse(
        id=artifact.id,
        executionId=artifact.execution_id,
        runId=artifact.run_id,
        projectId=artifact.project_id,
        name=artifact.name,
        sourcePath=artifact.source_path,
        digest=content.digest,
        size=content.size,
        contentKind=content.kind,
        mediaType=artifact.media_type,
        semanticType=artifact.semantic_type,
        declarationId=artifact.declaration_id,
        inputEntityIds=list(artifact.input_entity_ids),
        metadata=dict(artifact.metadata),
        createdAt=artifact.created_at.isoformat(),
    )


def _dispatch_to_molq(target, run, execution_id: str | None = None) -> None:  # noqa: ANN001
    """Submit *run* through molq onto *target*.

    Resources and scheduling come from the target's defaults — the API
    has no per-run CLI overrides like ``molab run --cpus``. When
    *execution_id* is given the worker starts that record (a RESUME record
    is the new Execution; rerun runs the freshly-derived id) instead of
    deriving its own.
    """
    from molab.workflow import can_recover_workflow

    if not can_recover_workflow(run):
        kind = run.experiment.workflow_kind
        if kind is None:
            root = run.experiment.project.workspace.root
            remedy = f"run `molab migrate workflow-kind {root}`"
        elif kind == "code":
            remedy = "run the experiment's defining script to bind a code locator"
        else:
            remedy = "PUT a workflow document on the experiment's /workflow route"
        raise HTTPException(
            status_code=422,
            detail=(
                f"experiment {run.experiment.id!r} cannot be dispatched "
                f"(workflow_kind={kind!r}); {remedy}"
            ),
        )

    handler = SubmitHandler(
        scheduler=target.scheduler,
        cluster=None,
        resources=target.default_resources,
        scheduling=target.default_scheduling,
        target=target,
    )
    handler(None, run, run.experiment, run.experiment.project, execution_id=execution_id)


def _invalidate_run_nav_cache(workspace, run_or_exp_path: str) -> None:  # noqa: ANN001
    """Drop pinned remote dir listings for *run_or_exp_path* so new files appear.

    Secondary fix for pin-until-refresh caches that hide newly-landed
    ``*.mlp.jsonl`` / run dirs until an explicit refresh.
    """
    fs = getattr(workspace, "fs", None)
    if isinstance(fs, CachedRemoteFileSystem):
        fs.invalidate(run_or_exp_path)


@router.get("", response_model=list[RunResponse])
def list_runs(
    project_id: str,
    experiment_id: str,
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> list[RunResponse]:
    experiment = _get_experiment(workspace, project_id, experiment_id)
    if not experiment:
        raise RunNotFoundError(project_id, experiment_id, "")
    # Fresh listdir for remote pin caches (new runs on the host).
    runs_dir = workspace.fs.join(str(experiment.experiment_dir), "runs")
    _invalidate_run_nav_cache(workspace, runs_dir)
    return [RunResponse.from_model(r) for r in experiment.list_runs()]


@router.get("/{run_id}", response_model=RunResponse)
def get_run(
    project_id: str,
    experiment_id: str,
    run_id: str,
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> RunResponse:
    experiment = _get_experiment(workspace, project_id, experiment_id)
    if not experiment:
        raise RunNotFoundError(project_id, experiment_id, run_id)
    run = _get_run_or_none(experiment, run_id)
    if not run:
        raise RunNotFoundError(project_id, experiment_id, run_id)
    return RunResponse.from_model(run)


@router.post(
    "/{run_id}/executions",
    response_model=ExecutionResponse,
    status_code=201,
)
def create_execution(
    project_id: str,
    experiment_id: str,
    run_id: str,
    body: ExecutionAttemptCreateRequest,
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> ExecutionResponse:
    """Create one queued physical attempt without mutating the Run."""
    experiment = _get_experiment(workspace, project_id, experiment_id)
    if not experiment:
        raise RunNotFoundError(project_id, experiment_id, run_id)
    run = _get_run_or_none(experiment, run_id)
    if not run:
        raise RunNotFoundError(project_id, experiment_id, run_id)
    target = None
    if body.target is not None:
        try:
            target = get_target(workspace, body.target)
        except KeyError as exc:
            raise HTTPException(status_code=422, detail=f"unknown target {body.target!r}") from exc
    if body.dispatch and target is None:
        raise HTTPException(status_code=422, detail="dispatch requires a compute target")
    try:
        state = run._create_execution(
            mode=ExecutionMode(body.mode),
            created_by=AgentRef(id="ui", type="person", name="Molab UI"),
            predecessor=body.based_on_execution_id,
            checkpoint=body.checkpoint_artifact_id,
            bypass_cache=body.bypass_cache,
            executor={"backend": "molq", "target": body.target},
            environment={"submit_cwd": str(Path.cwd().resolve())},
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if body.dispatch:
        assert target is not None
        try:
            _dispatch_to_molq(target, run, execution_id=state.id)
        except Exception as exc:
            _execution_repository(workspace, run).seal(
                state.id,
                ExecutionStatus.FAILED,
                error={"type": type(exc).__name__, "message": str(exc)},
            )
            raise
    return _execution_response(state)


@router.get(
    "/{run_id}/executions",
    response_model=list[ExecutionResponse],
)
def list_executions(
    project_id: str,
    experiment_id: str,
    run_id: str,
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> list[ExecutionResponse]:
    """Every attempt at this Run, oldest first (``e01``, ``e02``, …).

    The Run detail already embeds these; this is the addressable list for a
    caller that wants the attempts alone, and the GET counterpart of the POST
    on the same path.
    """
    experiment = _get_experiment(workspace, project_id, experiment_id)
    run = _get_run_or_none(experiment, run_id) if experiment else None
    if run is None:
        raise RunNotFoundError(project_id, experiment_id, run_id)
    return [_execution_response(state) for state in _execution_repository(workspace, run).list()]


@router.get(
    "/{run_id}/executions/{execution_id}",
    response_model=ExecutionResponse,
)
def get_execution_record(
    project_id: str,
    experiment_id: str,
    run_id: str,
    execution_id: str,
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> ExecutionResponse:
    experiment = _get_experiment(workspace, project_id, experiment_id)
    run = _get_run_or_none(experiment, run_id) if experiment else None
    if run is None:
        raise RunNotFoundError(project_id, experiment_id, run_id)
    try:
        return _execution_response(_execution_repository(workspace, run).get(execution_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/{run_id}/executions/{execution_id}/outputs",
    response_model=ExecutionOutputsResponse,
)
def get_execution_outputs(
    project_id: str,
    experiment_id: str,
    run_id: str,
    execution_id: str,
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> ExecutionOutputsResponse:
    """Separate stdio, managed Artifacts, evidence, and unregistered product files."""
    experiment = _get_experiment(workspace, project_id, experiment_id)
    run = _get_run_or_none(experiment, run_id) if experiment else None
    if run is None:
        raise RunNotFoundError(project_id, experiment_id, run_id)
    repo = _execution_repository(workspace, run)
    try:
        repo.get(execution_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    fs = workspace.fs
    execution_dir = repo.execution_dir(execution_id)

    def read_optional(name: str) -> str | None:
        path = fs.join(execution_dir, name)
        return fs.read_text(path, encoding="utf-8") if fs.is_file(path) else None

    artifacts = run.execution(execution_id).artifacts
    artifact_responses = [_artifact_response(artifact) for artifact in artifacts]
    registered = {artifact.path for artifact in artifacts}
    # Where a reader looks for results is declared data (``products``), not a
    # name: tasks write ``out/<task>/``, and a registered artifact is already
    # listed above, so only the rest of the product tiers is "unregistered".
    unregistered: list[RunFileNode] = []
    exec_prefix = execution_dir.rstrip("/") + "/"
    for tier in product_dirs():
        tier_dir = fs.join(execution_dir, tier.name)
        if not fs.is_dir(tier_dir):
            continue
        for path in sorted(fs.rglob(tier_dir, "*")):
            if not fs.is_file(path):
                continue
            rel = path[len(exec_prefix) :] if path.startswith(exec_prefix) else path
            if rel in registered:
                continue
            stat = fs.stat(path)
            unregistered.append(
                RunFileNode(
                    name=fs.basename(path),
                    relPath=rel,
                    type="file",
                    size=stat.size,
                    modified=stat.mtime,
                )
            )
    sealed_record = repo.record(execution_id)
    evidence = (
        [
            ExecutionEvidenceResponse(
                kind=item.kind,
                path=item.rel_path,
                digest=item.digest,
                size=item.size,
            )
            for item in sealed_record.evidence
        ]
        if sealed_record is not None
        else []
    )
    results = run.results(execution_id)
    return ExecutionOutputsResponse(
        executionId=execution_id,
        stdout=read_optional("stdout.log"),
        stderr=read_optional("stderr.log"),
        runtime=read_optional("runtime.log"),
        artifacts=artifact_responses,
        evidence=evidence,
        unregistered=unregistered,
        results=results,
    )


@router.post(
    "/{run_id}/executions/{execution_id}/artifacts/{artifact_id}/promote",
    response_model=ArtifactPromotionResponse,
    status_code=201,
)
def promote_artifact(
    project_id: str,
    experiment_id: str,
    run_id: str,
    execution_id: str,
    artifact_id: str,
    body: ArtifactPromoteRequest,
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> ArtifactPromotionResponse:
    experiment = _get_experiment(workspace, project_id, experiment_id)
    run = _get_run_or_none(experiment, run_id) if experiment else None
    if run is None:
        raise RunNotFoundError(project_id, experiment_id, run_id)
    try:
        artifact = _execution_repository(workspace, run).get(execution_id).artifact(artifact_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    asset, version = run.experiment.project.assets.promote(
        artifact,
        created_by=AgentRef(id=body.created_by, type="person", name=body.created_by),
        title=body.title,
        into_asset_id=body.into_asset_id,
        metadata=body.metadata,
    )
    return ArtifactPromotionResponse(
        asset=ManagedAssetResponse.from_model(
            asset,
            len(run.experiment.project.assets.versions(asset.id)),
        ),
        version=AssetVersionResponse.from_model(version),
    )


@router.get(
    "/{run_id}/executions/{execution_id}/artifacts/{artifact_id}/content",
)
def download_artifact_content(
    project_id: str,
    experiment_id: str,
    run_id: str,
    execution_id: str,
    artifact_id: str,
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> StreamingResponse:
    """Stream one Execution Artifact's bytes."""
    experiment = _get_experiment(workspace, project_id, experiment_id)
    run = _get_run_or_none(experiment, run_id) if experiment else None
    if run is None:
        raise RunNotFoundError(project_id, experiment_id, run_id)
    try:
        artifact = run.execution(execution_id).artifact(artifact_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    try:
        location = run.artifact_location(execution_id, artifact)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not workspace.fs.is_file(location):
        raise HTTPException(status_code=404, detail="artifact payload not found")
    filename = Path(artifact.name).name
    return StreamingResponse(
        workspace.fs.open(location, "rb"),
        media_type=artifact.media_type or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.post("", response_model=RunResponse, status_code=201)
def create_scoped_run(
    project_id: str,
    experiment_id: str,
    run_req: RunCreateRequest,
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> RunResponse:
    experiment = _get_experiment(workspace, project_id, experiment_id)
    if not experiment:
        raise RunNotFoundError(project_id, experiment_id, "")

    run = experiment.add_run(
        params=run_req.params,
        target=run_req.target,
    )
    return RunResponse.from_model(run)


def _execution_stream(exec_dir: Path, name: str) -> Path | None:
    """Stdout/stderr live under ``jobs/<id>/``."""
    jobs = exec_dir / JOBS.name
    if not jobs.is_dir():
        return None
    found = sorted(p for p in jobs.glob(f"*/{name}") if p.is_file() or p.is_symlink())
    return found[0] if found else None


def _read_execution_logs(run, execution_id: str) -> RunLogsResponse:  # noqa: ANN001
    exec_dir = Path(run.run_dir) / "executions" / execution_id
    stdout: str | None = None
    stderr: str | None = None
    out_file = _execution_stream(exec_dir, "stdout.log")
    err_file = _execution_stream(exec_dir, "stderr.log")
    if out_file is not None:
        stdout = out_file.read_text(errors="replace")
    if err_file is not None:
        stderr = err_file.read_text(errors="replace")
    # Fall back to the workflow runtime log when stdout wasn't captured (e.g. an
    # in-process / non-molq execution writes only ``logs/run.log``), so the Logs
    # panel still shows what the run did rather than "No stdout captured."
    if not stdout:
        run_log = exec_dir / "logs" / "run.log"
        if run_log.exists():
            stdout = run_log.read_text(errors="replace")
    return RunLogsResponse(execution_id=execution_id, stdout=stdout, stderr=stderr)


@router.get(
    "/{run_id}/executions/{execution_id}/logs",
    response_model=RunLogsResponse,
)
def get_run_execution_logs(
    project_id: str,
    experiment_id: str,
    run_id: str,
    execution_id: str,
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> RunLogsResponse:
    """Return stdout/stderr for a specific execution attempt."""
    experiment = _get_experiment(workspace, project_id, experiment_id)
    if not experiment:
        raise RunNotFoundError(project_id, experiment_id, run_id)
    run = _get_run_or_none(experiment, run_id)
    if not run:
        raise RunNotFoundError(project_id, experiment_id, run_id)
    return _read_execution_logs(run, execution_id)


@router.get(
    "/{run_id}/executions/{execution_id}/file/text",
    response_model=RunFileTextResponse,
)
def get_run_file_text(
    project_id: str,
    experiment_id: str,
    run_id: str,
    execution_id: str,
    path: str = Query(..., description="Relative path under the Execution directory"),
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> RunFileTextResponse:
    """Return the raw text content of a file under the run directory.

    Routes through ``workspace.fs`` — same path as workspace file reads —
    so remote workspaces resolve correctly.
    """
    experiment = _get_experiment(workspace, project_id, experiment_id)
    if not experiment:
        raise RunNotFoundError(project_id, experiment_id, run_id)
    run = _get_run_or_none(experiment, run_id)
    if not run:
        raise RunNotFoundError(project_id, experiment_id, run_id)

    fs = workspace.fs
    try:
        execution_dir = _execution_repository(workspace, run).execution_dir(execution_id)
        _execution_repository(workspace, run).get(execution_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    rel = path.lstrip("/")
    if ".." in Path(rel).parts:
        raise HTTPException(status_code=400, detail="path escapes run directory")
    target = fs.join(execution_dir, rel) if rel else execution_dir
    execution_norm = execution_dir.rstrip("/")
    if target != execution_norm and not target.startswith(execution_norm + "/"):
        raise HTTPException(status_code=400, detail="path escapes run directory")
    if not fs.exists(target) or not fs.is_file(target):
        raise HTTPException(status_code=404, detail=f"file not found: {path}")

    try:
        content = fs.read_text(target, encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=415, detail="file is not text-decodable as UTF-8") from exc
    return RunFileTextResponse(path=path, content=content, size=fs.getsize(target))


@router.get(
    "/{run_id}/executions/{execution_id}/workflow",
    response_model=RunExecutionResponse,
)
def get_run_execution(
    project_id: str,
    experiment_id: str,
    run_id: str,
    execution_id: str,
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> RunExecutionResponse:
    """Return one Execution's node journal.

    The journal is owned by the workflow layer and read through
    ``molab.workflow.read_journal``; ``status`` is the Execution record's
    status. ``workflow`` is null while the attempt has no journal yet.
    """
    experiment = _get_experiment(workspace, project_id, experiment_id)
    if not experiment:
        raise RunNotFoundError(project_id, experiment_id, run_id)
    run = _get_run_or_none(experiment, run_id)
    if not run:
        raise RunNotFoundError(project_id, experiment_id, run_id)

    repo = _execution_repository(workspace, run)
    try:
        state = repo.get(execution_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RunExecutionResponse(
        execution_id=execution_id,
        status=state.status.value,
        workflow=read_journal(run, execution_id),
    )


@router.get(
    "/{run_id}/executions/{execution_id}/files",
    response_model=RunFilesResponse,
)
def get_run_files(
    project_id: str,
    experiment_id: str,
    run_id: str,
    execution_id: str,
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> RunFilesResponse:
    """Return the on-disk file tree for a run, enriched with catalog metadata.

    Uses the **same** :func:`~molab.workspace.fs_tree.list_tree_children` walk
    as workspace file listing (via ``workspace.fs``) so remote workspaces
    activate plugins the same way as local ones. Catalog enrichment is
    best-effort for local asset scans only.
    """
    experiment = _get_experiment(workspace, project_id, experiment_id)
    if not experiment:
        raise RunNotFoundError(project_id, experiment_id, run_id)
    run = _get_run_or_none(experiment, run_id)
    if not run:
        raise RunNotFoundError(project_id, experiment_id, run_id)

    fs = workspace.fs
    try:
        execution = run.execution(execution_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    execution_dir = run.execution_dir(execution_id)
    run_dir = str(execution_dir)
    # Drop pinned listings so newly-written ``*.mlp.jsonl`` / artifacts show up.
    _invalidate_run_nav_cache(workspace, run_dir)

    artifact_index: dict[str, Artifact] = {}
    base = str(execution_dir).rstrip("/")
    for artifact in execution.artifacts:
        try:
            location = run.artifact_location(execution_id, artifact)
        except ValueError:
            continue
        loc = str(location).rstrip("/")
        if loc == base:
            rel = ""
        elif loc.startswith(base + "/"):
            rel = loc[len(base) + 1 :]
        else:
            try:
                rel = Path(loc).resolve().relative_to(Path(base).resolve()).as_posix()
            except (ValueError, OSError):
                continue
        artifact_index[rel] = artifact

    tree = list_tree_children(fs, run_dir, max_depth=8)
    raw_nodes = tree_to_run_file_dicts(tree)

    def enrich(node: dict) -> RunFileNode:
        rel = node.get("relPath") or ""
        info = artifact_index.get(rel)
        children_raw = node.get("children") or []
        return RunFileNode(
            name=node.get("name") or "",
            relPath=rel,
            type=node.get("type") or "file",
            size=node.get("size"),
            modified=node.get("modified"),
            assetId=info.id if info else None,
            assetKind=info.semantic_type if info else None,
            taskId=str(info.metadata.get("task_id"))
            if info and info.metadata.get("task_id")
            else None,
            children=[enrich(c) for c in children_raw],
        )

    nodes = [enrich(n) for n in raw_nodes]
    try:
        run_dir_rel = str(Path(run_dir).relative_to(Path(str(workspace.root))))
    except ValueError:
        # Remote roots: strip workspace root prefix via string ops.
        root = str(workspace.root).rstrip("/")
        run_dir_rel = run_dir[len(root) + 1 :] if run_dir.startswith(root + "/") else run_dir

    return RunFilesResponse(
        runId=run_id,
        runDir=run_dir_rel,
        nodes=nodes,
    )


@router.post(
    "/{run_id}/executions/{execution_id}/cancel",
    response_model=ExecutionResponse,
)
def cancel_execution(
    project_id: str,
    experiment_id: str,
    run_id: str,
    execution_id: str,
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> ExecutionResponse:
    """Cancel one explicit Execution; Run has no cancellable scalar state."""
    experiment = _get_experiment(workspace, project_id, experiment_id)
    run = _get_run_or_none(experiment, run_id) if experiment else None
    if run is None:
        raise RunNotFoundError(project_id, experiment_id, run_id)
    repo = _execution_repository(workspace, run)
    try:
        state = repo.get(execution_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if state.status.value not in {"queued", "running"}:
        raise HTTPException(
            status_code=409,
            detail=f"Execution {execution_id!r} is already {state.status.value}",
        )
    # Executor-specific signalling belongs to the Execution adapter. Until all
    # adapters expose a common cancel hook, refuse to claim a running process
    # was cancelled when no signal can be proven.
    if state.status.value == "running" and state.executor.get("backend"):
        raise HTTPException(
            status_code=409,
            detail="executor cancellation is unavailable for this active Execution",
        )
    return _execution_response(repo.seal(execution_id, ExecutionStatus.CANCELLED))


@router.get("/{run_id}/export")
def export_run(
    project_id: str,
    experiment_id: str,
    run_id: str,
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> StreamingResponse:
    """Stream a zip archive of the run directory (artifacts, logs, metadata)."""
    experiment = _get_experiment(workspace, project_id, experiment_id)
    if not experiment:
        raise RunNotFoundError(project_id, experiment_id, run_id)
    run = _get_run_or_none(experiment, run_id)
    if not run:
        raise RunNotFoundError(project_id, experiment_id, run_id)

    from molab.workspace.archive import archive_folder_zip

    # The one workspace zip writer (molab.workspace.archive).
    payload = archive_folder_zip(run)
    buffer = io.BytesIO(payload)
    buffer.seek(0)

    filename = f"run-{run.id}.zip"
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{run_id}/harvest")
def harvest_run_route(
    project_id: str,
    experiment_id: str,
    run_id: str,
    body: RunHarvestRequest,
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> dict[str, str]:
    """Harvest a terminal run into sourced Knowledge under its experiment."""
    from molab.knowledge.concepts import HARVEST_TARGETS

    harvest_ok = HARVEST_TARGETS
    experiment = _get_experiment(workspace, project_id, experiment_id)
    if not experiment:
        raise RunNotFoundError(project_id, experiment_id, run_id)
    run = _get_run_or_none(experiment, run_id)
    if not run:
        raise RunNotFoundError(project_id, experiment_id, run_id)
    if body.cls not in harvest_ok:
        raise HTTPException(
            status_code=422,
            detail=f"{body.cls} is not a harvest target",
        )
    try:
        item = harvest_ok[body.cls].harvest(
            run,
            narrative=body.narrative,
            created_by=body.created_by,
            results=body.results,
            name=body.name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        rel = Path(item.path).relative_to(workspace.resolve()).as_posix()
    except Exception:
        rel = item.name
    return {"name": item.name, "path": rel}


@router.post("/{run_id}/executions/{execution_id}/molplot/ingest")
def ingest_run_metrics(
    project_id: str,
    experiment_id: str,
    run_id: str,
    execution_id: str,
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> dict[str, object]:
    """Ingest foreign logs into the run host metrics surface (additive).

    Shares :func:`molab.plugins.metrics_ingest.ingest_run` with the CLI.
    Skips are returned; the route does not fail the whole call when one
    converter cannot run.
    """
    from molab.plugins.metrics_ingest import ingest_run

    experiment = _get_experiment(workspace, project_id, experiment_id)
    if not experiment:
        raise RunNotFoundError(project_id, experiment_id, run_id)
    run = _get_run_or_none(experiment, run_id)
    if not run:
        raise RunNotFoundError(project_id, experiment_id, run_id)
    execution_dir = _execution_repository(workspace, run).execution_dir(execution_id)
    try:
        _execution_repository(workspace, run).get(execution_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    # Read from the whole attempt; the WAL is written to the attempt root, so
    # it lands in ``out/metrics.mlp.jsonl`` where the metrics reader looks.
    result = ingest_run(Path(execution_dir))
    return {
        "runId": run.id,
        "records": result.records,
        "ingested": dict(result.ingested),
        "skipped": [
            {
                "format": s.format,
                "path": s.path.name,
                "reason": s.reason,
            }
            for s in result.skipped
        ],
    }


@router.post("/{run_id}/analyze-failure")
def analyze_run_failure_route(
    project_id: str,
    experiment_id: str,
    run_id: str,
    body: RunAnalyzeFailureRequest,
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> dict[str, str]:
    """Analyze a failed run into a sourced Report.

    Shares :func:`molab.services.run_failure.analyze_run_failure` with the CLI
    (close-loop-02). Deterministic narrative when ``narrative`` is omitted.
    """
    from molab.services.run_failure import analyze_run_failure

    experiment = _get_experiment(workspace, project_id, experiment_id)
    if not experiment:
        raise RunNotFoundError(project_id, experiment_id, run_id)
    run = _get_run_or_none(experiment, run_id)
    if not run:
        raise RunNotFoundError(project_id, experiment_id, run_id)
    try:
        item = analyze_run_failure(
            run,
            created_by=body.created_by,
            narrative=body.narrative,
            force=body.force,
            name=body.name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        rel = Path(item.path).relative_to(workspace.resolve()).as_posix()
    except Exception:
        rel = item.name
    return {"name": item.name, "path": rel}
