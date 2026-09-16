"""Run routes for MolExp API."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from molexp.fs.window import MAX_TEXT_WINDOW_BYTES, TextWindow, read_text_window
from molexp.plugins.submit_molq.cancel import try_cancel
from molexp.plugins.submit_molq.submit import SubmitHandler
from molexp.workflow import (
    WorkflowSnapshotRef,
    default_binding_registry,
    make_execution_id,
    request_fresh_execution,
    resolve_spec_entrypoint,
)
from molexp.workspace import (
    LOCAL_TARGET_NAME,
    RETRYABLE_STATUSES,
    Experiment,
    RunStatus,
    reap_zombie_run,
)
from molexp.workspace import (
    ExperimentNotFoundError as WorkspaceExperimentNotFoundError,
)
from molexp.workspace import (
    ProjectNotFoundError as WorkspaceProjectNotFoundError,
)
from molexp.workspace import (
    RunNotFoundError as WorkspaceRunNotFoundError,
)
from molexp.workspace import resolve_compute_target as resolve_target
from molexp.workspace.events import read_workspace_events
from molexp.workspace.metrics import read_run_metrics
from molexp.workspace.targets import get_target

from ..dependencies import get_workspace
from ..exceptions import InvalidStatusError, RunNotFoundError
from ..executors import run_heavy
from ..mutations import after_mutation
from ..schemas import (
    LammpsLogResponse,
    LammpsThermoStage,
    MetricSeriesResponse,
    RunActionResponse,
    RunContinueResponse,
    RunCreateRequest,
    RunExecutionResponse,
    RunFileNode,
    RunFilesResponse,
    RunFileTextResponse,
    RunHarvestRequest,
    RunLogsResponse,
    RunMetricsResponse,
    RunResponse,
    RunStartRequest,
    RunStatusResponse,
)
from .workspace import WorkspaceEventResponse

router = APIRouter(
    prefix="/projects/{project_id}/experiments/{experiment_id}/runs",
    tags=["runs"],
)

DEFAULT_LOG_WINDOW_BYTES = 256_000
"""Default log tail — a few screenfuls, which is what a viewer actually shows."""

DEFAULT_METRICS_SCAN_BYTES = 8 * 1024 * 1024
"""How much of ``metrics.jsonl`` one request may scan before reporting truncation."""

LAMMPS_LOG_MAX_BYTES = 32 * 1024 * 1024
"""Parse ceiling for a LAMMPS log; above this only the tail is parsed."""

EXECUTION_JSON_INLINE_BYTES = 8 * 1024 * 1024
"""``workflow.json`` up to this size is returned whole."""

EXECUTION_JSON_MAX_BYTES = 64 * 1024 * 1024
"""``workflow.json`` above this is refused (413) rather than parsed."""

EXPORT_MAX_BYTES = 2 * 1024 * 1024 * 1024
"""Uncompressed run size above which ``/export`` refuses rather than streams."""

DEFAULT_RUN_FILES_DEPTH = 6
"""Run-tree walk depth.

Deep enough for every path in the documented run layout — ``executions/<id>/
jobs/<uuid>/<file>`` is the deepest at 5 — because the UI feeds this tree to
plugin discovery, and a shallower default would make files silently
undiscoverable rather than merely unlisted.
"""

DEFAULT_DIR_ENTRIES = 2000
"""Children returned per directory before the node reports ``truncated``."""

MAX_DIR_ENTRIES = 10000


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


def _synthesize_snapshot(experiment: Experiment) -> dict | None:
    """Build the opaque snapshot dict the run record should carry.

    The route does not require an explicit snapshot from the caller —
    if the experiment already has a workflow bound in the workflow-
    layer registry, we resolve its entrypoint here so molq workers
    can re-import it without re-running the user script. When no
    binding exists, returns ``None`` (the run still materializes;
    submit_handler dispatch will refuse it later if a target is
    requested).
    """
    spec = default_binding_registry.for_experiment(experiment)
    if spec is None:
        return None
    try:
        entrypoint = resolve_spec_entrypoint(spec)
    except ValueError:
        # Spec isn't bound to a module-level name — most often a
        # promote_callable result on a fixture. Fall back to source-
        # only snapshot.
        entrypoint = None
    snap = WorkflowSnapshotRef(
        source=experiment.metadata.workflow_source or "",
        entrypoint=entrypoint,
        git_commit=experiment.metadata.git_commit,
    )
    return snap.model_dump(mode="json")


def _run_has_workflow_source(run) -> bool:  # noqa: ANN001
    """True if the run carries a generated ``workflow_source`` harness artifact
    the worker can compile + execute in place (the PlanMode flow)."""
    from molexp.harness.store.file_artifact_store import FileArtifactStore

    try:
        store = FileArtifactStore(root=Path(run.run_dir) / "artifacts")
        return store.latest_by_kind("workflow_source") is not None
    except Exception:
        return False


def _dispatch_to_molq(target, run, execution_id: str | None = None) -> None:  # noqa: ANN001
    """Submit *run* through molq onto *target*.

    Resources and scheduling come from the target's defaults — the API
    has no per-run CLI overrides like ``molexp run --cpus``. When
    *execution_id* is given the worker reuses it (resume reopens; rerun
    runs the freshly-derived id) instead of deriving its own.
    """
    snapshot = run.metadata.workflow_snapshot
    entrypoint = snapshot.get("entrypoint") if isinstance(snapshot, dict) else None
    # A run is executable either via an importable entrypoint (``molexp run``
    # script flow) OR a generated ``build_workflow()`` source the worker compiles
    # in place (the PlanMode flow — the experiment has no importable module).
    if not entrypoint and not _run_has_workflow_source(run):
        raise HTTPException(
            status_code=422,
            detail=(
                f"experiment {run.experiment.id!r} has no workflow entrypoint and no "
                "generated workflow source; bind a Python Workflow/callable on the "
                "experiment, or generate one via `molexp plan`, before submitting."
            ),
        )

    # Worker chdirs to submit_cwd before importing user code so cwd-relative
    # paths resolve the same as at submit time.
    if not run.metadata.submit_cwd:
        run._update_metadata(submit_cwd=str(Path.cwd().resolve()))

    handler = SubmitHandler(
        scheduler=target.scheduler,
        cluster=None,
        resources=target.default_resources,
        scheduling=target.default_scheduling,
        target=target,
    )
    handler(None, run, run.experiment, run.experiment.project, execution_id=execution_id)


@router.get("", response_model=list[RunResponse])
def list_runs(
    project_id: str,
    experiment_id: str,
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> list[RunResponse]:
    experiment = _get_experiment(workspace, project_id, experiment_id)
    if not experiment:
        raise RunNotFoundError(project_id, experiment_id, "")
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


@router.post("", response_model=RunResponse, status_code=201)
def create_run(
    project_id: str,
    experiment_id: str,
    run_req: RunCreateRequest,
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> RunResponse:
    experiment = _get_experiment(workspace, project_id, experiment_id)
    if not experiment:
        raise RunNotFoundError(project_id, experiment_id, "")

    target = None
    if run_req.target is not None:
        try:
            target = get_target(workspace, run_req.target)
        except KeyError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"compute target {run_req.target!r} is not registered on this workspace",
            ) from exc

    run = experiment.add_run(
        params=run_req.parameters,
        target=run_req.target,
        workflow_snapshot=_synthesize_snapshot(experiment),
    )
    if target is not None:
        _dispatch_to_molq(target, run)
    return RunResponse.from_model(run)


def _resolve_under_run(run, rel: str) -> str:  # noqa: ANN001
    """Resolve *rel* inside the run directory, refusing anything that escapes.

    Goes through ``run.fs`` rather than ``pathlib`` so remote-backed runs
    resolve on the filesystem that actually holds them. Containment is checked
    on the resolved paths, so ``..`` and symlinks out of the tree are caught
    rather than merely discouraged.
    """
    fs = run.fs
    run_dir = str(run.run_dir)
    target = fs.join(run_dir, rel)
    try:
        real_target = fs.resolve(target)
        real_root = fs.resolve(run_dir)
    except OSError:
        real_target, real_root = target, run_dir
    if real_target != real_root and not real_target.startswith(real_root.rstrip("/") + "/"):
        raise HTTPException(status_code=400, detail="path escapes run directory")
    return real_target


def _log_window(fs, path: str, *, max_bytes: int, since: int | None) -> TextWindow | None:  # noqa: ANN001
    """Tail window over a log file, or ``None`` when it does not exist.

    One ``stat`` plus one bounded range read, so a 10 GB stdout costs the same
    as a 10 KB one.
    """
    try:
        return read_text_window(fs, path, max_bytes=max_bytes, mode="tail", since_offset=since)
    except (FileNotFoundError, NotADirectoryError, IsADirectoryError, OSError):
        return None


def _read_execution_logs(
    run,  # noqa: ANN001
    execution_id: str,
    *,
    max_bytes: int = DEFAULT_LOG_WINDOW_BYTES,
    since_stdout: int | None = None,
    since_stderr: int | None = None,
) -> RunLogsResponse:
    fs = run.fs
    exec_dir = fs.join(str(run.run_dir), "executions", execution_id)
    out = _log_window(fs, fs.join(exec_dir, "stdout.log"), max_bytes=max_bytes, since=since_stdout)
    err = _log_window(fs, fs.join(exec_dir, "stderr.log"), max_bytes=max_bytes, since=since_stderr)
    # Fall back to the workflow runtime log when stdout wasn't captured (e.g. an
    # in-process / non-molq execution writes only ``logs/run.log``), so the Logs
    # panel still shows what the run did rather than "No stdout captured."
    if out is None or not out.text:
        fallback = _log_window(
            fs, fs.join(exec_dir, "logs", "run.log"), max_bytes=max_bytes, since=since_stdout
        )
        if fallback is not None:
            out = fallback
    return RunLogsResponse(
        execution_id=execution_id,
        stdout=out.text if out is not None else None,
        stderr=err.text if err is not None else None,
        stdout_offset=out.start if out is not None else None,
        stdout_end=out.end if out is not None else None,
        stdout_total=out.total_bytes if out is not None else None,
        stdout_truncated=out.truncated if out is not None else False,
        stderr_offset=err.start if err is not None else None,
        stderr_end=err.end if err is not None else None,
        stderr_total=err.total_bytes if err is not None else None,
        stderr_truncated=err.truncated if err is not None else False,
    )


@router.get("/{run_id}/logs", response_model=RunLogsResponse)
def get_run_logs(
    project_id: str,
    experiment_id: str,
    run_id: str,
    max_bytes: int = Query(default=DEFAULT_LOG_WINDOW_BYTES, ge=1, le=MAX_TEXT_WINDOW_BYTES),
    since_stdout: int | None = Query(default=None, ge=0),
    since_stderr: int | None = Query(default=None, ge=0),
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> RunLogsResponse:
    """Return a stdout/stderr tail window for the most recent execution.

    Poll incrementally by passing the previous response's ``stdout_end`` /
    ``stderr_end`` back as ``since_stdout`` / ``since_stderr``.
    """
    experiment = _get_experiment(workspace, project_id, experiment_id)
    if not experiment:
        raise RunNotFoundError(project_id, experiment_id, run_id)
    run = _get_run_or_none(experiment, run_id)
    if not run:
        raise RunNotFoundError(project_id, experiment_id, run_id)

    history = run.execution_history
    if not history:
        return RunLogsResponse()
    return _read_execution_logs(
        run,
        history[-1].execution_id,
        max_bytes=max_bytes,
        since_stdout=since_stdout,
        since_stderr=since_stderr,
    )


@router.get(
    "/{run_id}/executions/{execution_id}/logs",
    response_model=RunLogsResponse,
)
def get_run_execution_logs(
    project_id: str,
    experiment_id: str,
    run_id: str,
    execution_id: str,
    max_bytes: int = Query(default=DEFAULT_LOG_WINDOW_BYTES, ge=1, le=MAX_TEXT_WINDOW_BYTES),
    since_stdout: int | None = Query(default=None, ge=0),
    since_stderr: int | None = Query(default=None, ge=0),
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> RunLogsResponse:
    """Return a stdout/stderr tail window for a specific execution attempt."""
    experiment = _get_experiment(workspace, project_id, experiment_id)
    if not experiment:
        raise RunNotFoundError(project_id, experiment_id, run_id)
    run = _get_run_or_none(experiment, run_id)
    if not run:
        raise RunNotFoundError(project_id, experiment_id, run_id)
    return _read_execution_logs(
        run,
        execution_id,
        max_bytes=max_bytes,
        since_stdout=since_stdout,
        since_stderr=since_stderr,
    )


@router.get("/{run_id}/metrics", response_model=RunMetricsResponse)
def get_run_metrics(
    project_id: str,
    experiment_id: str,
    run_id: str,
    metric_type: str | None = Query(default=None, alias="type"),
    key: str | None = None,
    since_offset: int | None = Query(
        default=None, ge=0, description="Byte cursor from a previous nextOffset (O(1) resume)."
    ),
    max_scan_bytes: int = Query(default=DEFAULT_METRICS_SCAN_BYTES, ge=1024, le=64 * 1024 * 1024),
    limit: int = Query(default=5000, ge=1, le=50000),
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> RunMetricsResponse:
    """Return run-local metrics from ``metrics/metrics.jsonl``.

    A live chart should follow by passing the previous ``nextOffset`` back as
    ``since_offset``: that seeks straight to the appended bytes instead of
    re-reading the stream from line 0 on every poll.
    """
    experiment = _get_experiment(workspace, project_id, experiment_id)
    if not experiment:
        raise RunNotFoundError(project_id, experiment_id, run_id)
    run = _get_run_or_none(experiment, run_id)
    if not run:
        raise RunNotFoundError(project_id, experiment_id, run_id)

    result = read_run_metrics(
        run.run_dir,
        metric_type=metric_type,
        key=key,
        since_offset=since_offset,
        max_scan_bytes=max_scan_bytes,
        limit=limit,
    )
    return RunMetricsResponse(
        nextOffset=result.next_offset,
        records=result.records,
        # ``entry`` is ``dict[str, JSONValue]``; ``model_validate`` runs
        # pydantic's per-field coercion / validation rather than the
        # static-typed positional constructor.
        series=[MetricSeriesResponse.model_validate(entry) for entry in result.series],
        parseErrors=result.parse_errors,
        truncated=result.truncated,
    )


@router.get("/{run_id}/file/text", response_model=RunFileTextResponse)
def get_run_file_text(
    project_id: str,
    experiment_id: str,
    run_id: str,
    path: str = Query(..., description="Relative path under run_dir"),
    mode: Literal["head", "tail"] = Query(default="head"),
    max_bytes: int = Query(default=MAX_TEXT_WINDOW_BYTES, ge=1, le=MAX_TEXT_WINDOW_BYTES),
    since_offset: int | None = Query(default=None, ge=0),
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> RunFileTextResponse:
    """Return a bounded text window over a file under the run directory.

    Defaults to the *head* — a source or config viewer reads from the top —
    and to the largest window the server will emit, so small files come back
    whole exactly as before.  Page with ``since_offset=end``.
    """
    experiment = _get_experiment(workspace, project_id, experiment_id)
    if not experiment:
        raise RunNotFoundError(project_id, experiment_id, run_id)
    run = _get_run_or_none(experiment, run_id)
    if not run:
        raise RunNotFoundError(project_id, experiment_id, run_id)

    target = _resolve_under_run(run, path)
    fs = run.fs
    if not fs.is_file(target):
        raise HTTPException(status_code=404, detail=f"file not found: {path}")

    try:
        window = read_text_window(
            fs, target, max_bytes=max_bytes, mode=mode, since_offset=since_offset, errors="strict"
        )
    except UnicodeDecodeError as exc:
        # A *partial* window may legitimately split a multi-byte character at
        # its edge, so retry leniently; a window covering the whole file that
        # still fails is genuinely not text, which stays a 415 as before.
        window = read_text_window(
            fs, target, max_bytes=max_bytes, mode=mode, since_offset=since_offset
        )
        if not window.truncated:
            raise HTTPException(
                status_code=415, detail="file is not text-decodable as UTF-8"
            ) from exc
    return RunFileTextResponse(
        path=path,
        content=window.text,
        size=window.total_bytes,
        offset=window.start,
        end=window.end,
        truncated=window.truncated,
    )


@router.get("/{run_id}/lammps-log", response_model=LammpsLogResponse)
async def get_run_lammps_log(
    project_id: str,
    experiment_id: str,
    run_id: str,
    path: str = Query(..., description="Relative path of the log file under run_dir"),
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> LammpsLogResponse:
    """Parse a LAMMPS log file and return thermo stages.

    Inlined parser — ``molpy.io`` does not export a multi-stage log
    reader, so the route owns this lightweight regex-based parse to
    avoid coupling the API surface to a transient molpy refactor.

    A production MD log can be gigabytes; above
    :data:`LAMMPS_LOG_MAX_BYTES` only the tail is parsed (the latest stages,
    which is what a progress view wants) and ``truncated`` is set. Reading
    and regexing the file is CPU- and IO-bound, so it runs on the heavy pool
    rather than the shared request threads.
    """
    experiment = _get_experiment(workspace, project_id, experiment_id)
    if not experiment:
        raise RunNotFoundError(project_id, experiment_id, run_id)
    run = _get_run_or_none(experiment, run_id)
    if not run:
        raise RunNotFoundError(project_id, experiment_id, run_id)

    target = _resolve_under_run(run, path)
    fs = run.fs
    if not fs.is_file(target):
        raise HTTPException(status_code=404, detail=f"log file not found: {path}")

    return await run_heavy(_parse_lammps_log, fs, target, path)


def _parse_lammps_log(fs, target: str, path: str) -> LammpsLogResponse:  # noqa: ANN001
    """Read (at most the tail of) a LAMMPS log and extract its thermo stages."""
    import re

    window = read_text_window(
        fs, target, max_bytes=LAMMPS_LOG_MAX_BYTES, mode="tail", line_aligned=True
    )
    text = window.text
    # Line 1 carries the LAMMPS banner; a tail window never contains it.
    version = text.split("\n", 1)[0].strip() if text and not window.truncated else None

    stages: list[LammpsThermoStage] = []
    for block in re.findall(
        r"Per MPI rank memory allocation .*?\n(.*?)Loop time of",
        text,
        flags=re.DOTALL,
    ):
        lines = [ln for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        columns = lines[0].split()
        rows: list[list[float]] = []
        for ln in lines[1:]:
            parts = ln.split()
            if len(parts) != len(columns):
                continue
            try:
                rows.append([float(x) for x in parts])
            except ValueError:
                continue
        stages.append(LammpsThermoStage(columns=columns, rows=rows))

    return LammpsLogResponse(
        path=path,
        version=version,
        nStages=len(stages),
        stages=stages,
        truncated=window.truncated,
        bytesParsed=window.end - window.start,
    )


_NODE_SUMMARY_KEYS = (
    "task_id",
    "id",
    "name",
    "status",
    "snapshot_key",
    "outputs_lossy",
    "started_at",
    "finished_at",
    "error",
)


def _summarize_workflow_doc(data: dict) -> dict:
    """Drop per-node ``outputs`` while keeping everything a graph view renders.

    What makes a ``workflow.json`` huge is the persisted task outputs, not the
    graph: status, snapshot key, timestamps and links are all small. Summarised
    nodes keep those and lose only the payload, so the Executions panel still
    draws the graph while the response stays bounded.
    """
    if not isinstance(data, dict):
        return data
    summary = {k: v for k, v in data.items() if k != "task_configs"}
    nodes: list[dict] = []
    for task in data.get("task_configs", []) or []:
        if not isinstance(task, dict):
            continue
        node = {k: task[k] for k in _NODE_SUMMARY_KEYS if k in task}
        if "outputs" in task:
            # Say the payload existed rather than silently implying it did not.
            node["outputs_omitted"] = True
        nodes.append(node)
    summary["task_configs"] = nodes
    return summary


@router.get("/{run_id}/execution", response_model=RunExecutionResponse)
def get_run_execution(
    project_id: str,
    experiment_id: str,
    run_id: str,
    execution_id: str | None = Query(default=None, description="Execution attempt id."),
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> RunExecutionResponse:
    """Return runtime workflow graph state from workflow.json."""
    experiment = _get_experiment(workspace, project_id, experiment_id)
    if not experiment:
        raise RunNotFoundError(project_id, experiment_id, run_id)
    run = _get_run_or_none(experiment, run_id)
    if not run:
        raise RunNotFoundError(project_id, experiment_id, run_id)

    history = run.execution_history
    if not history:
        return RunExecutionResponse()

    known_ids = {rec.execution_id for rec in history}
    selected_id = execution_id or history[-1].execution_id
    if selected_id not in known_ids:
        raise HTTPException(status_code=404, detail=f"Execution {selected_id!r} not found")

    fs = run.fs
    wf_file = fs.join(str(run.run_dir), "executions", selected_id, "workflow.json")
    try:
        size = fs.stat(wf_file).size
    except (FileNotFoundError, NotADirectoryError, OSError):
        return RunExecutionResponse(execution_id=selected_id)

    if size > EXECUTION_JSON_MAX_BYTES:
        # Parsing it would cost more memory than the response is worth; say so
        # rather than melting the worker.
        raise HTTPException(
            status_code=413,
            detail=(
                f"workflow.json is {size} bytes, above the "
                f"{EXECUTION_JSON_MAX_BYTES}-byte inspection ceiling"
            ),
        )

    data = json.loads(fs.read_text(wf_file))
    truncated = False
    if size > EXECUTION_JSON_INLINE_BYTES:
        data = _summarize_workflow_doc(data)
        truncated = True
    # Status-vocabulary migration (run-recovery): the workflow-level result
    # status is now "succeeded"; documents persisted before the migration
    # carry the legacy "completed" and are normalized on read.
    raw_status = data.get("status", "running")
    return RunExecutionResponse(
        execution_id=data.get("execution_id", selected_id),
        status="succeeded" if raw_status == "completed" else raw_status,
        workflow=data,
        workflowTruncated=truncated,
        workflowBytes=size,
    )


@router.get("/{run_id}/files", response_model=RunFilesResponse)
async def get_run_files(
    project_id: str,
    experiment_id: str,
    run_id: str,
    max_depth: int = Query(default=DEFAULT_RUN_FILES_DEPTH, ge=0, le=8),
    max_entries: int = Query(default=DEFAULT_DIR_ENTRIES, ge=1, le=MAX_DIR_ENTRIES),
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> RunFilesResponse:
    """Return the on-disk file tree for a run, enriched with catalog metadata.

    Files registered in the asset catalog (artifacts, logs, checkpoints,
    error traces) carry ``assetId``, ``assetKind``, and ``taskId`` so the
    UI can render lineage chips inline.

    The walk is bounded in both directions: ``max_depth`` levels down, and
    ``max_entries`` children per directory. A run that wrote 100k frames into
    one directory therefore costs a bounded response; the containing folder
    node reports ``entryCount`` and ``truncated`` so the UI can say so.
    """
    # The run directory can hold a very large tree, so the walk runs on
    # the bounded heavy pool: it never occupies the shared request
    # threads that cheap reads and /api/health use.

    def _work() -> RunFilesResponse:
        experiment = _get_experiment(workspace, project_id, experiment_id)
        if not experiment:
            raise RunNotFoundError(project_id, experiment_id, run_id)
        run = _get_run_or_none(experiment, run_id)
        if not run:
            raise RunNotFoundError(project_id, experiment_id, run_id)

        run_dir = Path(run.run_dir)
        fs = run.fs
        from molexp.workspace.assets import AssetScope, scan

        run_scope = AssetScope(kind="run", ids=(project_id, experiment_id, run_id))
        scoped_assets = scan.scan_assets(workspace.root, scope=run_scope)
        asset_index: dict[str, tuple[str, str, str | None]] = {}
        for a in scoped_assets:
            rel = str(a.path)
            asset_index[rel] = (
                a.asset_id,
                a.kind,  # type: ignore[attr-defined]
                a.producer.task_id if a.producer else None,
            )

        def _entries(dir_path: Path) -> list[tuple[str, bool, int, float]]:
            """``(name, is_dir, size, mtime)`` per child — one scandir, no re-stat."""
            out: list[tuple[str, bool, int, float]] = []
            try:
                for entry in fs.scandir(str(dir_path)):
                    out.append((entry.name, entry.is_dir, entry.size, entry.mtime))
            except (FileNotFoundError, NotADirectoryError, OSError):
                return []
            # Dirs first, then files; stable by name within each group.
            out.sort(key=lambda t: (not t[1], t[0]))
            return out

        def build(
            node_path: Path, *, is_dir: bool, size: int, mtime: float, depth: int
        ) -> RunFileNode:
            rel = node_path.relative_to(run_dir).as_posix() if node_path != run_dir else ""
            info = asset_index.get(rel)
            node = RunFileNode(
                name=node_path.name or run_dir.name,
                relPath=rel,
                type="folder" if is_dir else "file",
                size=None if is_dir else size,
                modified=mtime,
                assetId=info[0] if info else None,
                assetKind=info[1] if info else None,
                taskId=info[2] if info else None,
            )
            if not is_dir:
                return node
            children_meta = _entries(node_path)
            node.entryCount = len(children_meta)
            if depth >= max_depth:
                # Stop here, but say the folder has contents so the UI can
                # offer to go deeper rather than showing it as empty.
                node.truncated = len(children_meta) > 0
                return node
            shown = children_meta[:max_entries]
            node.truncated = len(shown) < len(children_meta)
            node.children = [
                build(
                    node_path / name, is_dir=child_is_dir, size=csize, mtime=cmtime, depth=depth + 1
                )
                for name, child_is_dir, csize, cmtime in shown
            ]
            return node

        nodes: list[RunFileNode] = []
        root_meta = _entries(run_dir)
        for name, child_is_dir, csize, cmtime in root_meta[:max_entries]:
            nodes.append(
                build(run_dir / name, is_dir=child_is_dir, size=csize, mtime=cmtime, depth=1)
            )

        return RunFilesResponse(
            runId=run_id,
            runDir=str(run_dir.relative_to(Path(workspace.root))),
            nodes=nodes,
        )

    return await run_heavy(_work)


def _resumable_execution_id(run) -> str | None:  # noqa: ANN001
    """Return the most recent non-succeeded execution_id, or ``None``."""
    for record in reversed(run.execution_history):
        if record.status != "succeeded":
            return record.execution_id
    return None


def _require_retryable(run, run_id: str) -> None:  # noqa: ANN001
    """409 unless *run* is in a retryable state (``failed`` / ``cancelled``).

    resume / rerun own exactly the finished-but-not-succeeded runs. ``pending``
    is started via the normal run/create flow, ``succeeded`` is done, and a live
    ``running`` run must not get a second concurrent execution — keeping the
    three verbs orthogonal. The retryable domain is the shared
    :data:`molexp.workspace.RETRYABLE_STATUSES`.
    """
    if run.status not in RETRYABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=(
                f"run {run_id!r} is {run.status!r}; resume/rerun apply only to "
                "failed or cancelled runs"
            ),
        )


def _dispatch_continuation(workspace, run, execution_id: str) -> None:  # noqa: ANN001
    """Re-dispatch *run* on *execution_id* through its inherited target (if any).

    Mirrors the create path: a targeted run is submitted via molq onto the
    chosen execution_id; a target-less run is not executed server-side (the
    operator runs ``molexp run`` locally). 422 when the target is unregistered.
    """
    inherited_target = run.metadata.target
    if inherited_target is None:
        return
    try:
        target = get_target(workspace, inherited_target)
    except KeyError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"compute target {inherited_target!r} is not registered on this workspace",
        ) from exc
    # Ensure the run carries a workflow entrypoint the worker can re-import.
    snapshot = run.metadata.workflow_snapshot
    if not (isinstance(snapshot, dict) and snapshot.get("entrypoint")):
        synthesized = _synthesize_snapshot(run.experiment)
        if synthesized is not None:
            run._update_metadata(workflow_snapshot=synthesized)
    _dispatch_to_molq(target, run, execution_id=execution_id)


@router.post("/{run_id}/run", response_model=RunContinueResponse, status_code=201)
def start_run(
    project_id: str,
    experiment_id: str,
    run_id: str,
    start_req: RunStartRequest,
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> RunContinueResponse:
    """Start a pending run by dispatching it to a compute target (the ``run`` verb).

    The disjoint counterpart to resume/rerun: ``run`` owns ``pending`` runs only
    (409 otherwise — retrying a failed/cancelled run is resume/rerun's job, and a
    live ``running`` run must not get a second execution). A pending run is
    target-less (the create+dispatch contract dispatches a targeted run on
    create), so Start supplies the target to execute on; a target-less Start
    (no body target, none recorded) 422s — those run via ``molexp run`` on the
    host, since the server never executes a workflow in-process.
    """
    experiment = _get_experiment(workspace, project_id, experiment_id)
    if not experiment:
        raise RunNotFoundError(project_id, experiment_id, run_id)
    run = _get_run_or_none(experiment, run_id)
    if not run:
        raise RunNotFoundError(project_id, experiment_id, run_id)
    # A stale 'running' run whose owner died is reaped to 'failed' BEFORE the
    # verb decides (same policy as the CLI — run-recovery bug 5); a live run
    # is never touched.
    reap_zombie_run(run)
    if run.status != "pending":
        raise HTTPException(
            status_code=409,
            detail=(
                f"run {run_id!r} is {run.status!r}; Start (run) applies only to pending runs — "
                "use resume/rerun for failed/cancelled, or cancel a running run first"
            ),
        )
    # Default to the built-in `local` target — a run can always start on this
    # machine without registering anything first.
    target_name = start_req.target or run.metadata.target or LOCAL_TARGET_NAME
    try:
        target = resolve_target(workspace, target_name)
    except KeyError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"compute target {target_name!r} is not registered on this workspace",
        ) from exc
    # Apply edited inputs before dispatch — a pending run is not yet hashed, so
    # its config_hash (computed at execution start) picks up the new parameters.
    if start_req.parameters is not None:
        run._update_metadata(parameters=dict(start_req.parameters))
    # Record a newly-chosen target so any later resume/rerun inherits it.
    if start_req.target and start_req.target != run.metadata.target:
        run._update_metadata(target=start_req.target)
    # Ensure the run carries a re-importable workflow entrypoint (mirrors continuation).
    snapshot = run.metadata.workflow_snapshot
    if not (isinstance(snapshot, dict) and snapshot.get("entrypoint")):
        synthesized = _synthesize_snapshot(run.experiment)
        if synthesized is not None:
            run._update_metadata(workflow_snapshot=synthesized)
    execution_id = make_execution_id(run.id, Path(run.run_dir))
    _dispatch_to_molq(target, run, execution_id=execution_id)
    after_mutation(
        workspace,
        "run",
        ref=run.id,
        project_id=project_id,
        experiment_id=experiment_id,
        run_id=run.id,
    )
    return RunContinueResponse(
        runId=run.id,
        executionId=execution_id,
        projectId=project_id,
        experimentId=experiment_id,
        status=run.status,
    )


@router.post("/{run_id}/resume", response_model=RunContinueResponse, status_code=201)
def resume_run(
    project_id: str,
    experiment_id: str,
    run_id: str,
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> RunContinueResponse:
    """Resume a failed/cancelled run: reopen its last non-succeeded execution.

    The reopened execution is re-dispatched on the same ``execution_id``; the
    worker seeds already-completed nodes from disk and recomputes the rest.
    409 unless the run is failed/cancelled (pending/succeeded/running are not
    resume's job). A stale ``running`` run with a dead owner is reaped to
    ``failed`` first, so it enters the retryable domain instead of 409-ing
    forever (run-recovery bug 5).
    """
    experiment = _get_experiment(workspace, project_id, experiment_id)
    if not experiment:
        raise RunNotFoundError(project_id, experiment_id, run_id)
    run = _get_run_or_none(experiment, run_id)
    if not run:
        raise RunNotFoundError(project_id, experiment_id, run_id)
    reap_zombie_run(run)
    _require_retryable(run, run_id)

    execution_id = _resumable_execution_id(run) or make_execution_id(run.id, Path(run.run_dir))
    _dispatch_continuation(workspace, run, execution_id)
    after_mutation(
        workspace,
        "run",
        ref=run.id,
        project_id=project_id,
        experiment_id=experiment_id,
        run_id=run.id,
    )
    return RunContinueResponse(
        runId=run.id,
        executionId=execution_id,
        projectId=project_id,
        experimentId=experiment_id,
        status=run.status,
    )


@router.post("/{run_id}/rerun", response_model=RunContinueResponse, status_code=201)
def rerun_run(
    project_id: str,
    experiment_id: str,
    run_id: str,
    fresh: bool = Query(
        default=False,
        description=(
            "Bypass content-addressed cache reads for the new execution: every "
            "task body actually re-runs (results are still written back to the "
            "cache). Same capability as the CLI's `molexp run --rerun --fresh`."
        ),
    ),
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> RunContinueResponse:
    """Rerun a failed/cancelled run in a new execution (no clone).

    A fresh ``exec-{run_id}-N`` is derived and, for a targeted run, dispatched
    through molq; no parameters are cloned and no new Run is created. Note the
    content-addressed cache may still serve deterministic tasks — pass
    ``fresh=true`` to bypass cache reads (persisted as a marker in the new
    execution slot, so whichever process executes it honors the request).
    409 unless the run is failed/cancelled (pending/succeeded/running are not
    rerun's job). A stale ``running`` run with a dead owner is reaped to
    ``failed`` first (run-recovery bug 5).
    """
    experiment = _get_experiment(workspace, project_id, experiment_id)
    if not experiment:
        raise RunNotFoundError(project_id, experiment_id, run_id)
    run = _get_run_or_none(experiment, run_id)
    if not run:
        raise RunNotFoundError(project_id, experiment_id, run_id)
    reap_zombie_run(run)
    _require_retryable(run, run_id)

    execution_id = make_execution_id(run.id, Path(run.run_dir))
    if fresh:
        request_fresh_execution(str(run.run_dir), execution_id)
    _dispatch_continuation(workspace, run, execution_id)
    after_mutation(
        workspace,
        "run",
        ref=run.id,
        project_id=project_id,
        experiment_id=experiment_id,
        run_id=run.id,
    )
    return RunContinueResponse(
        runId=run.id,
        executionId=execution_id,
        projectId=project_id,
        experimentId=experiment_id,
        status=run.status,
    )


@router.post("/{run_id}/cancel", response_model=RunActionResponse)
def cancel_run(
    project_id: str,
    experiment_id: str,
    run_id: str,
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> RunActionResponse:
    """Cancel a run.

    ``cancel`` is the canonical — and only — verb, matching the CLI
    ``molexp runs cancel`` and the resulting ``cancelled`` status.

    Routes through :func:`molexp.plugins.submit_molq.cancel.try_cancel`, which signals
    molq via :class:`molq.Submitor` for cluster-submitted runs and
    sends ``SIGTERM`` for runs still owned by a local pid.  When neither
    path applies (run never submitted, terminal, or executor info
    missing) we fall back to flipping the metadata status so the UI
    still reflects user intent.
    """
    experiment = _get_experiment(workspace, project_id, experiment_id)
    if not experiment:
        raise RunNotFoundError(project_id, experiment_id, run_id)
    run = _get_run_or_none(experiment, run_id)
    if not run:
        raise RunNotFoundError(project_id, experiment_id, run_id)

    warning = try_cancel(run)
    if warning is not None:
        run.cancel()
    after_mutation(
        workspace,
        "run",
        ref=run.id,
        project_id=project_id,
        experiment_id=experiment_id,
        run_id=run.id,
    )
    return RunActionResponse(
        runId=run.id,
        status=run.status,
        message="Run cancelled" if warning is None else warning,
    )


# The per-run events route reuses the workspace-wide wire shape — one frozen
# model for every spine read; the alias keeps this module's public name.
RunEventResponse = WorkspaceEventResponse


@router.get("/{run_id}/events", response_model=list[RunEventResponse])
def get_run_events(
    project_id: str,
    experiment_id: str,
    run_id: str,
    limit: int = Query(default=50, ge=1, le=500),
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> list[RunEventResponse]:
    """Return the run's recent workspace-timeline events, newest first.

    Reads the default-on ``workspace.events.sqlite`` spine via the shared
    :func:`molexp.workspace.events.read_workspace_events` (the same code path
    ``molexp runs info`` uses). A workspace with no timeline yet (nothing has
    emitted) returns ``[]``.
    """
    experiment = _get_experiment(workspace, project_id, experiment_id)
    if not experiment:
        raise RunNotFoundError(project_id, experiment_id, run_id)
    run = _get_run_or_none(experiment, run_id)
    if not run:
        raise RunNotFoundError(project_id, experiment_id, run_id)

    events = read_workspace_events(workspace.root, ref=run.id, limit=limit)
    return [RunEventResponse.from_event(e) for e in events]


@router.get("/{run_id}/export")
async def export_run(
    project_id: str,
    experiment_id: str,
    run_id: str,
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> StreamingResponse:
    """Stream a zip archive of the run directory (artifacts, logs, metadata).

    Genuinely streamed: the archive is produced chunk by chunk, so exporting a
    run with gigabytes of trajectories never sizes the server's memory to the
    run. Above :data:`EXPORT_MAX_BYTES` the request is refused outright rather
    than tying up a worker for minutes.
    """
    experiment = _get_experiment(workspace, project_id, experiment_id)
    if not experiment:
        raise RunNotFoundError(project_id, experiment_id, run_id)
    run = _get_run_or_none(experiment, run_id)
    if not run:
        raise RunNotFoundError(project_id, experiment_id, run_id)

    from molexp.workspace.archive import archive_folder_zip_iter, archive_size

    # Walking for the size check is itself filesystem-bound, so it goes to the
    # heavy pool; the streaming body then runs outside the request handler.
    total = await run_heavy(archive_size, run)
    if total > EXPORT_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail={
                "detail": (f"run export is {total} bytes, above the {EXPORT_MAX_BYTES}-byte limit"),
                "totalBytes": total,
            },
        )

    filename = f"run-{run.id}.zip"
    # One zip writer for CLI/agent/server (agent-record-export-03/07).
    return StreamingResponse(
        archive_folder_zip_iter(run),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{run_id}/harvest")
async def harvest_run_route(
    project_id: str,
    experiment_id: str,
    run_id: str,
    body: RunHarvestRequest,
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> dict[str, str]:
    """Harvest a terminal run into a sourced KnowledgeItem under its experiment.

    Harvest reads the run's outputs and writes a Concept, so it is
    filesystem-bound; it runs on the heavy pool to keep the shared request
    threads free for cheap reads.
    """
    from molexp.workspace import harvest_run as harvest_run_core

    experiment = _get_experiment(workspace, project_id, experiment_id)
    if not experiment:
        raise RunNotFoundError(project_id, experiment_id, run_id)
    run = _get_run_or_none(experiment, run_id)
    if not run:
        raise RunNotFoundError(project_id, experiment_id, run_id)

    def _work() -> dict[str, str]:
        try:
            item = harvest_run_core(
                run,
                kind=body.kind,
                narrative=body.narrative,
                created_by=body.created_by,
                results=body.results,
                name=body.name,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        # Bundle-relative path so the UI can open Knowledge without stripping roots.
        try:
            rel = item.resolve().relative_to(workspace.resolve()).as_posix()
        except Exception:
            rel = item.name
        return {"name": item.name, "path": rel}

    return await run_heavy(_work)


@router.patch("/{run_id}/status", response_model=RunStatusResponse)
def update_run_status(
    project_id: str,
    experiment_id: str,
    run_id: str,
    status: dict[str, str],
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> RunStatusResponse:
    experiment = _get_experiment(workspace, project_id, experiment_id)
    if not experiment:
        raise RunNotFoundError(project_id, experiment_id, run_id)
    run = _get_run_or_none(experiment, run_id)
    if not run:
        raise RunNotFoundError(project_id, experiment_id, run_id)

    new_status_str = status.get("status", run.status)
    try:
        new_status = RunStatus(new_status_str)
    except ValueError:
        raise InvalidStatusError(run.status, new_status_str)  # noqa: B904

    # Status / finished_at are hot state → the OKF ``_ops`` sidecar (wsokf-10).
    finished = datetime.now() if new_status_str in ("succeeded", "failed", "cancelled") else None
    run.update_ops(
        lambda s: s.model_copy(
            update=(
                {"status": new_status, "finished_at": finished}
                if finished is not None
                else {"status": new_status}
            )
        )
    )

    return RunStatusResponse(
        id=run.id,
        status=run.status,
        finished=run.finished_at.isoformat() if run.finished_at else None,
    )
