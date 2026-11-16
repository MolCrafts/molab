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
``?source=code`` instead previews current source in an isolated scratch child,
using the same application service as the CLI. Registered runs are separate
from the source's declared sweep; the response names its provenance.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Literal

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
    source: Literal["stored", "code"] = "stored",
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> WorkflowDryRunResponse:
    """Walk the stored workflow IR without running a task or importing code.

    Reports the task waves, the declared branches, each task's dependencies
    and the runs the experiment would dispatch (its declared runs). 404 when
    no ``workflow.ir.json`` is stored, 400 when the IR does not compile.
    Nothing is written.
    """
    experiment = _resolve_experiment(workspace, project_id, experiment_id)
    path = Path(str(experiment.resolve())).relative_to(Path(str(workspace.root))).as_posix()
    if source == "code" and experiment.metadata.workflow_kind == "code":
        entrypoint = experiment.metadata.workflow_entrypoint
        if not entrypoint:
            raise ValueError("code workflow has no entrypoint")
        script = Path(str(experiment.resolve())) / entrypoint.split(":", 1)[0]
        # Source loading changes process-global bindings and workspace overrides.
        # Keep those changes out of the server and any concurrently running job.
        try:
            preview = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "molab.services.workflow_preview",
                    str(script),
                    str(workspace.root),
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            raise ValueError(f"source preview failed: {exc.stderr[-4000:]}") from exc
        except subprocess.TimeoutExpired as exc:
            raise ValueError("source preview exceeded 60 seconds") from exc
        reports = json.loads(preview.stdout)
        for report in reports:
            if report["experiment"]["path"] == path:
                report["experiment"]["id"] = experiment.id
                report["registered_runs"] = [
                    {"params": run.parameters} for run in experiment.list_runs()
                ]
                return WorkflowDryRunResponse.model_validate(report)
        raise ValueError(f"source does not declare experiment {path}")
    document = experiment.workflow_document
    if document is None:
        raise ExperimentNotFoundError(f"{experiment_id} (no workflow document)")
    compiled = compiled_for_simulation(document)
    report = report_from_compiled(
        compiled,
        experiment={"id": experiment.id, "name": experiment.metadata.name, "path": path},
        runs=[run.parameters for run in experiment.declared_runs()],
    )
    report.update(
        source="stored",
        definition_hash=experiment.metadata.definition_hash,
        entrypoint=experiment.metadata.workflow_entrypoint,
        registered_runs=[{"params": run.parameters} for run in experiment.list_runs()],
    )
    return WorkflowDryRunResponse.model_validate(report)
