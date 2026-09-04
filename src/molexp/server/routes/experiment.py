"""Experiment routes for MolExp API."""

from __future__ import annotations

from shutil import rmtree

from fastapi import APIRouter, Depends

from ..dependencies import get_workspace
from ..schemas import (
    ComparisonRunRow,
    ExperimentComparisonResponse,
    ExperimentCreateRequest,
    ExperimentResponse,
    MessageResponse,
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
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> ExperimentResponse:
    project = workspace.get_project(project_id)
    experiment = project.get_experiment(experiment_id)
    return ExperimentResponse.from_model(experiment, runs=experiment.list_runs())


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
    return ExperimentResponse.from_model(exp)


def _target_exists(workspace, name: str) -> bool:  # noqa: ANN001
    return any(t.name == name for t in workspace.metadata.targets)


@router.get("/{experiment_id}/comparison", response_model=ExperimentComparisonResponse)
def get_experiment_comparison(
    project_id: str,
    experiment_id: str,
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> ExperimentComparisonResponse:
    """Compare immutable logical Run definitions.

    Execution outcomes are intentionally absent: callers must select explicit
    Execution identities before comparing observed metrics or results.
    """
    project = workspace.get_project(project_id)
    experiment = project.get_experiment(experiment_id)

    runs = experiment.list_runs()
    rows: list[ComparisonRunRow] = []
    param_keys: set[str] = set()

    for run in runs:
        param_keys.update(run.parameters.keys())
        summary = run.status_summary
        rows.append(
            ComparisonRunRow(
                runId=run.id,
                definitionHash=run.metadata.definition_hash,
                experimentRevisionId=run.metadata.experiment_revision_id,
                inputAssetIds=list(run.metadata.input_asset_ids),
                statusSummary={
                    "total": summary.total,
                    "active": summary.active,
                    "notStarted": summary.not_started,
                    "byStatus": summary.by_status,
                },
                parameters=dict(run.parameters),
                created=run.metadata.created_at.isoformat(),
            )
        )

    return ExperimentComparisonResponse(
        experimentId=experiment_id,
        projectId=project_id,
        paramKeys=sorted(param_keys),
        runs=rows,
    )


@router.delete("/{experiment_id}", response_model=MessageResponse)
def delete_experiment(
    project_id: str,
    experiment_id: str,
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> MessageResponse:
    project = workspace.get_project(project_id)
    experiment = project.get_experiment(experiment_id)
    rmtree(experiment.experiment_dir)
    return MessageResponse(message="Experiment deleted")
