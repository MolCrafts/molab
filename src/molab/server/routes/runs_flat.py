"""Top-level run routes — flat create without nested project/experiment path."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from molab.workspace import (
    ExperimentNotFoundError as WorkspaceExperimentNotFoundError,
)
from molab.workspace import (
    ProjectNotFoundError as WorkspaceProjectNotFoundError,
)

from ..dependencies import get_workspace
from ..exceptions import ConflictError, ExperimentNotFoundError, ProjectNotFoundError
from ..schemas import ExecutionCreateRequest, RunResponse
from ..workflow_documents import (
    compile_workflow_document,
    require_migrated_workflow_binding,
)

flat_router = APIRouter(prefix="/runs", tags=["runs"])


@flat_router.post("", response_model=RunResponse, status_code=201)
def create_run(
    request: ExecutionCreateRequest,
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> RunResponse:
    """Create a run in a specific project/experiment (body carries scope ids).

    ``workflow_json``, when set, is compiled first (invalid IR is 400). An
    unbound experiment is bound as the document kind before the run is
    created, so the run records the revision from that binding. A document
    experiment must already carry the same normalized IR; a difference is
    409 (``PUT .../workflow`` first). A code experiment is 409; convert it
    with ``PUT .../workflow`` and ``convertToDocument``. A legacy experiment
    that still needs ``molab migrate workflow-kind`` is 409. This route
    never writes the in-process binding memo.
    """
    try:
        project = workspace.get_project(request.project_id)
    except WorkspaceProjectNotFoundError:
        raise ProjectNotFoundError(request.project_id) from None

    try:
        experiment = project.get_experiment(request.experiment_id)
    except WorkspaceExperimentNotFoundError:
        raise ExperimentNotFoundError(request.project_id, request.experiment_id) from None

    if request.workflow_json is not None:
        require_migrated_workflow_binding(experiment)
        _spec, normalized = compile_workflow_document(request.workflow_json)
        kind = experiment.workflow_kind
        if kind is None:
            experiment.bind_workflow("document", document=normalized)
        elif kind == "document":
            bound = experiment.workflow_document
            if bound is None or compile_workflow_document(bound)[1] != normalized:
                raise ConflictError(
                    message=(
                        "workflowJson differs from the experiment's bound document; "
                        "PUT .../workflow first"
                    ),
                )
        elif kind == "code":
            raise ConflictError(
                message=(
                    "workflowJson is only accepted for document experiments; "
                    "convert with PUT .../workflow and convertToDocument"
                ),
            )

    new_run = experiment.add_run(params=request.params)
    return RunResponse.from_model(new_run)


router = flat_router
