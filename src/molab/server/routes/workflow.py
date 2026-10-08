"""Workflow document routes.

``PUT`` compiles an IR and records it with ``Experiment.bind_workflow`` for
the document kind. A legacy experiment is 409 until ``molab migrate
workflow-kind`` runs, even when ``convertToDocument`` is set. A code-kind
experiment is 409 unless the body sets ``convertToDocument``. After a
successful bind the route drops any in-process binding memo and does not
install a new one.

``GET`` reads :attr:`Experiment.workflow_document` and returns 404 when the
experiment has no ``workflow.ir.json``. The codec remains the only IR parser.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from molab.workflow import default_binding_registry
from molab.workspace import (
    ExperimentNotFoundError as WorkspaceExperimentNotFoundError,
)
from molab.workspace import (
    ProjectNotFoundError as WorkspaceProjectNotFoundError,
)

from ..dependencies import get_workspace
from ..exceptions import ConflictError, ExperimentNotFoundError
from ..schemas import WorkflowDocumentRequest, WorkflowDocumentResponse
from ..workflow_documents import (
    compile_workflow_document,
    require_migrated_workflow_binding,
)

router = APIRouter(
    prefix="/projects/{project_id}/experiments/{experiment_id}/workflow",
    tags=["workflow"],
)


def _resolve_experiment(workspace, project_id: str, experiment_id: str):  # noqa: ANN001, ANN202
    """Strict-getter chain — returns the workspace ``Experiment`` or raises 404."""
    try:
        project = workspace.get_project(project_id)
    except WorkspaceProjectNotFoundError as exc:
        raise ExperimentNotFoundError(experiment_id) from exc
    try:
        return project.get_experiment(experiment_id)
    except WorkspaceExperimentNotFoundError as exc:
        raise ExperimentNotFoundError(experiment_id) from exc


@router.put("", response_model=WorkflowDocumentResponse)
def put_workflow_document(
    project_id: str,
    experiment_id: str,
    payload: WorkflowDocumentRequest,
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> WorkflowDocumentResponse:
    """Bind a normalized workflow IR as the document kind.

    Legacy experiments are 409 (migrate first). Code-kind experiments are
    409 unless ``convertToDocument`` is set. Invalid IR, including an
    unregistered ``task_type``, is 400. Nothing is written on 409 or 400.
    """
    experiment = _resolve_experiment(workspace, project_id, experiment_id)
    require_migrated_workflow_binding(experiment)
    _spec, normalized = compile_workflow_document(payload.document)
    kind = experiment.workflow_kind
    if kind == "code" and not payload.convert_to_document:
        raise ConflictError(
            message=(
                "experiment is bound as code; convertToDocument is required "
                "to replace it with a document"
            ),
            details={"workflow_kind": kind},
        )
    experiment.bind_workflow("document", document=normalized)
    default_binding_registry.unbind(experiment)

    return WorkflowDocumentResponse(
        project_id=project_id,
        experiment_id=experiment_id,
        document=normalized,
    )


@router.get("", response_model=WorkflowDocumentResponse)
def get_workflow_document(
    project_id: str,
    experiment_id: str,
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> WorkflowDocumentResponse:
    """Return the persisted workflow IR document, or 404 if none stored."""
    experiment = _resolve_experiment(workspace, project_id, experiment_id)
    document = experiment.workflow_document
    if document is None:
        raise ExperimentNotFoundError(f"{experiment_id} (no workflow document)")

    return WorkflowDocumentResponse(
        project_id=project_id,
        experiment_id=experiment_id,
        document=document,
    )
