"""Workflow document routes.

``PUT`` compiles an IR and records it with ``Experiment.bind_workflow`` for
the document kind. An unbound experiment is bound as a document. A code-kind
experiment is 409 unless the body sets ``convertToDocument``. After a
successful bind the route drops any in-process binding memo and does not
install a new one.

``GET`` reads :attr:`Experiment.workflow_document` and returns 404 when the
experiment has no ``workflow.ir.json``. The codec remains the only IR parser.

``GET …/dry-run`` walks that stored IR with the workflow layer's dry run and
never imports the experiment's script: a code experiment's graph snapshot is
compiled with stub bodies (:func:`molab.workflow.dry_run.compiled_for_simulation`).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends

from molab.workflow import default_binding_registry
from molab.workflow.dry_run import compiled_for_simulation, report_from_compiled
from molab.workspace import (
    ExperimentNotFoundError as WorkspaceExperimentNotFoundError,
)
from molab.workspace import (
    ProjectNotFoundError as WorkspaceProjectNotFoundError,
)

from ..dependencies import get_workspace
from ..exceptions import ConflictError, ExperimentNotFoundError
from ..schemas import WorkflowDocumentRequest, WorkflowDocumentResponse, WorkflowDryRunResponse
from ..workflow_documents import compile_workflow_document

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

    An unbound experiment is bound as a document. Code-kind experiments are
    409 unless ``convertToDocument`` is set. Invalid IR, including an
    unregistered ``task_type``, is 400. Nothing is written on 409 or 400.
    """
    experiment = _resolve_experiment(workspace, project_id, experiment_id)
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


@router.get("/dry-run", response_model=WorkflowDryRunResponse)
def dry_run_workflow_document(
    project_id: str,
    experiment_id: str,
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> WorkflowDryRunResponse:
    """Walk the stored workflow IR without running a task or importing code.

    Reports the task waves, the declared branches, each task's dependencies
    and the runs the experiment would dispatch (its declared runs). 404 when
    no ``workflow.ir.json`` is stored, 400 when the IR does not compile.
    Nothing is written.
    """
    experiment = _resolve_experiment(workspace, project_id, experiment_id)
    document = experiment.workflow_document
    if document is None:
        raise ExperimentNotFoundError(f"{experiment_id} (no workflow document)")
    compiled = compiled_for_simulation(document)
    path = Path(str(experiment.resolve())).relative_to(Path(str(workspace.root))).as_posix()
    report = report_from_compiled(
        compiled,
        experiment={"id": experiment.id, "name": experiment.metadata.name, "path": path},
        runs=[run.parameters for run in experiment.declared_runs()],
    )
    return WorkflowDryRunResponse.model_validate(report)
