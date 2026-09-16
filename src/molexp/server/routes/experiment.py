"""Experiment routes for MolExp API."""

from __future__ import annotations

from shutil import rmtree

from fastapi import APIRouter, Depends, Request, Response

from molexp.services.workspace_read_model import WorkspaceReadModel

from ..dependencies import get_workspace
from ..deps.read_model import get_read_model
from ..executors import run_heavy
from ..http_cache import not_modified, weak_etag
from ..mutations import after_mutation
from ..schemas import (
    ComparisonRunRow,
    ExperimentComparisonResponse,
    ExperimentCreateRequest,
    ExperimentResponse,
    MessageResponse,
    RunSummary,
)

router = APIRouter(prefix="/projects/{project_id}/experiments", tags=["experiments"])


@router.get("", response_model=list[ExperimentResponse])
def list_experiments(
    project_id: str,
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> list[ExperimentResponse]:
    project = workspace.get_project(project_id)
    return [ExperimentResponse.from_model(e) for e in project.list_experiments()]


@router.get("/{experiment_id}", response_model=ExperimentResponse)
def get_experiment(
    project_id: str,
    experiment_id: str,
    request: Request,
    response: Response,
    workspace=Depends(get_workspace),  # noqa: ANN001
    read_model: WorkspaceReadModel = Depends(get_read_model),
) -> ExperimentResponse:
    """One experiment plus its run summaries.

    The run rows come from the read-model snapshot (zero I/O once warm) and
    the validator is this experiment's own version, so activity in a *different*
    experiment does not invalidate this page.
    """
    project = workspace.get_project(project_id)
    experiment = project.get_experiment(experiment_id)
    snapshot = read_model.runs()
    cached = not_modified(
        request,
        response,
        weak_etag("experiment", snapshot.version_for_experiment(project_id, experiment_id)),
    )
    if cached is not None:
        return cached  # type: ignore[return-value]
    rows = snapshot.experiment_rows(project_id, experiment_id)
    detail = ExperimentResponse.from_model(experiment)
    return detail.model_copy(
        update={
            "runCount": len(rows) or None,
            "runs": [RunSummary.from_row(row) for row in rows],
        }
    )


@router.post("", response_model=ExperimentResponse, status_code=201)
def create_experiment(
    project_id: str,
    req: ExperimentCreateRequest,
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> ExperimentResponse:
    project = workspace.get_project(project_id)
    if req.default_target is not None and not _target_exists(workspace, req.default_target):
        from fastapi import HTTPException

        raise HTTPException(
            status_code=422,
            detail=f"compute target {req.default_target!r} is not registered on this workspace",
        )
    exp = project.add_experiment(
        name=req.name,
        description=req.description,
        workflow_source=req.workflow_source,
        params=req.parameter_space,
        default_target=req.default_target,
    )
    after_mutation(workspace, "experiment", ref=exp.id, project_id=project_id, experiment_id=exp.id)
    return ExperimentResponse.from_model(exp)


def _target_exists(workspace, name: str) -> bool:  # noqa: ANN001
    return any(t.name == name for t in workspace.metadata.targets)


@router.get("/{experiment_id}/comparison", response_model=ExperimentComparisonResponse)
async def get_experiment_comparison(
    project_id: str,
    experiment_id: str,
    workspace=Depends(get_workspace),  # noqa: ANN001
    read_model: WorkspaceReadModel = Depends(get_read_model),
) -> ExperimentComparisonResponse:
    """Comparison matrix: parameter columns x run rows + final metric values per run.

    Run rows come from the read-model snapshot; the per-run metric fold is
    memoized against each ``metrics.jsonl``'s ``(size, mtime)`` and read
    incrementally, so a re-request parses only lines appended since the last
    one instead of re-scanning up to 50 000 records per run. The whole matrix
    is assembled on the heavy pool — it is the one endpoint whose cost still
    scales with the *data* a run wrote, not with the run count.
    """
    project = workspace.get_project(project_id)
    project.get_experiment(experiment_id)  # 404s on an unknown experiment
    snapshot = read_model.runs()
    rows_in = snapshot.experiment_rows(project_id, experiment_id)

    def _build() -> ExperimentComparisonResponse:
        rows: list[ComparisonRunRow] = []
        param_keys: set[str] = set()
        metric_keys: set[str] = set()
        for row in rows_in:
            param_keys.update(row.parameters.keys())
            run_dir = (
                project.resolve() / "experiments" / experiment_id / "runs" / f"run-{row.run_id}"
            )
            metrics_summary = read_model.metrics_summary(run_dir)
            metric_keys.update(metrics_summary)

            duration: float | None = None
            if row.finished_at and row.created_at:
                duration = (row.finished_at - row.created_at).total_seconds()
            error_dict = (
                {"type": row.error.type, "message": row.error.message}
                if row.error is not None
                else None
            )
            rows.append(
                ComparisonRunRow(
                    runId=row.run_id,
                    status=row.status,
                    parameters=dict(row.parameters),
                    metrics=dict(metrics_summary),
                    durationSec=duration,
                    created=row.created_at.isoformat(),
                    finished=row.finished_at.isoformat() if row.finished_at else None,
                    error=error_dict,
                )
            )
        return ExperimentComparisonResponse(
            experimentId=experiment_id,
            projectId=project_id,
            paramKeys=sorted(param_keys),
            metricKeys=sorted(metric_keys),
            runs=rows,
        )

    return await run_heavy(_build)


@router.delete("/{experiment_id}", response_model=MessageResponse)
def delete_experiment(
    project_id: str,
    experiment_id: str,
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> MessageResponse:
    project = workspace.get_project(project_id)
    experiment = project.get_experiment(experiment_id)
    rmtree(experiment.experiment_dir)
    after_mutation(
        workspace,
        "experiment",
        ref=experiment_id,
        project_id=project_id,
        experiment_id=experiment_id,
    )
    return MessageResponse(message="Experiment deleted")
