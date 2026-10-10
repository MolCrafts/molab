"""Experiment routes for Molab API."""

from __future__ import annotations

from shutil import rmtree

from fastapi import APIRouter, Depends

from ..dependencies import get_workspace
from ..exceptions import ConflictError
from ..schemas import (
    ComparisonRunRow,
    ExperimentComparisonResponse,
    ExperimentCreateRequest,
    ExperimentResponse,
    MessageResponse,
)
from ..workflow_documents import (
    compile_workflow_document,
    require_migrated_workflow_binding,
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
    """Create an experiment, or return the existing one when the binding matches.

    ``workflow_source``, when set, is a workflow IR object (a string is 422).
    It is compiled before any directory is created; an invalid IR is 400 and
    leaves no experiment directory. The normalized IR is stored as a document
    binding via ``Project.add_experiment(workflow_document=...)``.

    An existing experiment is returned unchanged when it is already bound to
    that same normalized document (idempotent 201, no write). A different
    binding, a non-document kind, or a missing document is 409. A legacy
    experiment that still needs ``molab migrate workflow-kind`` is 409.
    Nothing is written on 409. A missing or unknown ``default_target`` is 422.
    """
    project = workspace.get_project(project_id)
    if req.default_target is not None and not _target_exists(workspace, req.default_target):
        from fastapi import HTTPException

        raise HTTPException(
            status_code=422,
            detail=f"compute target {req.default_target!r} is not registered on this workspace",
        )
    if req.workflow_source is not None:
        _spec, normalized = compile_workflow_document(req.workflow_source)
        if project.has_experiment(req.name):
            existing = project.get_experiment(req.name)
            require_migrated_workflow_binding(existing)
            bound = existing.workflow_document
            differs = (
                existing.workflow_kind != "document"
                or bound is None
                or compile_workflow_document(bound)[1] != normalized
            )
            if differs:
                raise ConflictError(
                    message=(
                        f"experiment {req.name} already exists with a different "
                        "workflow binding; PUT .../workflow to change it"
                    ),
                    details={"workflow_kind": existing.workflow_kind},
                )
            return ExperimentResponse.from_model(existing)
        exp = project.add_experiment(
            name=req.name,
            description=req.description,
            workflow_document=normalized,
            params=req.parameter_space,
            target=req.default_target,
        )
        return ExperimentResponse.from_model(exp)
    exp = project.add_experiment(
        name=req.name,
        description=req.description,
        params=req.parameter_space,
        target=req.default_target,
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
