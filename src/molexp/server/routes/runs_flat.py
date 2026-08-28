"""Top-level run routes — flat create without nested project/experiment path."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from molexp.workflow import default_binding_registry, default_codec
from molexp.workspace import (
    ExperimentNotFoundError as WorkspaceExperimentNotFoundError,
)
from molexp.workspace import (
    ProjectNotFoundError as WorkspaceProjectNotFoundError,
)

from ..dependencies import get_workspace
from ..exceptions import ExperimentNotFoundError, ProjectNotFoundError
from ..schemas import ExecutionCreateRequest, RunResponse

flat_router = APIRouter(prefix="/runs", tags=["runs"])


@flat_router.post("", response_model=RunResponse, status_code=201)
def create_run(
    request: ExecutionCreateRequest,
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> RunResponse:
    """Create a run in a specific project/experiment (body carries scope ids).

    If ``request.workflow_json`` is supplied and the experiment has no
    workflow bound, compile and persist the IR before the run is
    materialized so worker processes can pick it up off disk.
    """
    try:
        project = workspace.get_project(request.project_id)
    except WorkspaceProjectNotFoundError:
        raise ProjectNotFoundError(request.project_id) from None

    try:
        experiment = project.get_experiment(request.experiment_id)
    except WorkspaceExperimentNotFoundError:
        raise ExperimentNotFoundError(request.project_id, request.experiment_id) from None

    if (
        request.workflow_json is not None
        and default_binding_registry.for_experiment(experiment) is None
    ):
        spec = default_codec.ir_to_spec(request.workflow_json)
        default_binding_registry.bind(experiment, spec)

    new_run = experiment.add_run(params=request.params)
    return RunResponse.from_model(new_run)


router = flat_router
