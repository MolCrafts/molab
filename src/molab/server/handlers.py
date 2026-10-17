"""FastAPI exception handlers for Molab API.

This module registers exception handlers that convert MolabError exceptions
to consistent JSON error responses.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from molab.workflow.types import WorkflowError
from molab.workspace.errors import AmbiguousRefError, RefNotFoundError, UnmigratedAssetError
from molab.workspace.errors import (
    ExperimentExistsError as WorkspaceExperimentExistsError,
)
from molab.workspace.errors import (
    ExperimentNotFoundError as WorkspaceExperimentNotFoundError,
)
from molab.workspace.errors import (
    ProjectExistsError as WorkspaceProjectExistsError,
)
from molab.workspace.errors import (
    ProjectNotFoundError as WorkspaceProjectNotFoundError,
)
from molab.workspace.errors import (
    RunExistsError as WorkspaceRunExistsError,
)
from molab.workspace.errors import (
    RunNotFoundError as WorkspaceRunNotFoundError,
)
from molab.workspace.refs import InvalidRefError

from .exceptions import (
    ConflictError,
    DuplicateResourceError,
    ExperimentNotFoundError,
    MolabError,
    ProjectNotFoundError,
    RemoteWorkspaceUnreachableError,
    RunNotFoundError,
)


def register_exception_handlers(app: FastAPI) -> None:
    """Register exception handlers on the FastAPI app.

    Args:
        app: FastAPI application instance
    """

    @app.exception_handler(MolabError)
    async def molab_error_handler(request: Request, exc: MolabError) -> JSONResponse:  # noqa: ARG001
        """Handle MolabError exceptions with consistent JSON responses."""
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_dict(),
        )

    @app.exception_handler(ConnectionError)
    async def connection_error_handler(
        request: Request,  # noqa: ARG001
        exc: ConnectionError,  # noqa: ARG001
    ) -> JSONResponse:
        """SSH/transport soft-fail — never 500 / traceback noise.

        Remote 2FA hosts raise ConnectionError on BatchMode probe before
        login; map to the same envelope as RemoteWorkspaceUnreachableError.
        """
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "REMOTE_WORKSPACE_UNREACHABLE",
                    "message": "needs_auth",
                    "details": {"reason": "needs_auth"},
                }
            },
        )

    @app.exception_handler(RemoteWorkspaceUnreachableError)
    async def remote_unreachable_handler(
        request: Request,  # noqa: ARG001
        exc: RemoteWorkspaceUnreachableError,
    ) -> JSONResponse:
        """Explicit remote-unreachable path (same envelope as ConnectionError)."""
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_dict(),
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:  # noqa: ARG001
        """Handle ValueError exceptions as validation errors."""
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": str(exc),
                }
            },
        )

    @app.exception_handler(WorkflowError)
    async def workflow_error_handler(request: Request, exc: WorkflowError) -> JSONResponse:  # noqa: ARG001
        """Map workflow-layer compile errors (cycles, unknown tasks, unreachable
        nodes, …) raised by ``ir_to_spec`` onto a structured 4xx — never a 500."""
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "WORKFLOW_INVALID",
                    "message": str(exc),
                }
            },
        )

    @app.exception_handler(UnmigratedAssetError)
    async def unmigrated_asset_handler(
        request: Request,  # noqa: ARG001
        exc: UnmigratedAssetError,
    ) -> JSONResponse:
        """A scope still holds a pre-unified asset record."""
        return JSONResponse(
            status_code=409,
            content={
                "error": {
                    "code": "MIGRATION_REQUIRED",
                    "message": str(exc),
                }
            },
        )

    @app.exception_handler(FileNotFoundError)
    async def file_not_found_handler(request: Request, exc: FileNotFoundError) -> JSONResponse:  # noqa: ARG001
        """Handle Python FileNotFoundError."""
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "NOT_FOUND",
                    "message": str(exc),
                }
            },
        )

    # ── Workspace-layer error → HTTP 404 / 409 ────────────────────────────
    #
    # The workspace layer raises typed entity errors at the storage
    # boundary; the server layer maps them onto its existing
    # ``NotFoundError`` / ``DuplicateResourceError`` HTTP envelopes so
    # routes can simply re-raise without per-route try/except.

    @app.exception_handler(WorkspaceProjectNotFoundError)
    async def workspace_project_not_found_handler(
        request: Request,  # noqa: ARG001
        exc: WorkspaceProjectNotFoundError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content=ProjectNotFoundError(exc.entity_id).to_dict(),
        )

    @app.exception_handler(WorkspaceExperimentNotFoundError)
    async def workspace_experiment_not_found_handler(
        request: Request,  # noqa: ARG001
        exc: WorkspaceExperimentNotFoundError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content=ExperimentNotFoundError(exc.entity_id).to_dict(),
        )

    @app.exception_handler(WorkspaceRunNotFoundError)
    async def workspace_run_not_found_handler(
        request: Request,  # noqa: ARG001
        exc: WorkspaceRunNotFoundError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content=RunNotFoundError(exc.entity_id).to_dict(),
        )

    @app.exception_handler(WorkspaceProjectExistsError)
    async def workspace_project_exists_handler(
        request: Request,  # noqa: ARG001
        exc: WorkspaceProjectExistsError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content=DuplicateResourceError("Project", exc.entity_id).to_dict(),
        )

    @app.exception_handler(WorkspaceExperimentExistsError)
    async def workspace_experiment_exists_handler(
        request: Request,  # noqa: ARG001
        exc: WorkspaceExperimentExistsError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content=DuplicateResourceError("Experiment", exc.entity_id).to_dict(),
        )

    @app.exception_handler(RefNotFoundError)
    async def ref_not_found_handler(
        request: Request,  # noqa: ARG001
        exc: RefNotFoundError,
    ) -> JSONResponse:
        details: dict[str, str] = {"resource": exc.segment, "identifier": exc.entity_id}
        if exc.ref is not None:
            details["ref"] = str(exc.ref)
        return JSONResponse(
            status_code=404,
            content={
                "error": {"code": "NOT_FOUND", "message": str(exc), "details": details},
            },
        )

    @app.exception_handler(AmbiguousRefError)
    async def ambiguous_ref_handler(
        request: Request,  # noqa: ARG001
        exc: AmbiguousRefError,
    ) -> JSONResponse:
        details: dict[str, Any] = {
            "identifier": exc.entity_id,
            "candidates": [str(candidate) for candidate in exc.candidates],
        }
        if exc.locations:
            details["locations"] = list(exc.locations)
        conflict = ConflictError(str(exc), details=details)
        return JSONResponse(status_code=conflict.status_code, content=conflict.to_dict())

    @app.exception_handler(InvalidRefError)
    async def invalid_ref_handler(
        request: Request,  # noqa: ARG001
        exc: InvalidRefError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "INVALID_REF", "message": str(exc)}},
        )

    @app.exception_handler(WorkspaceRunExistsError)
    async def workspace_run_exists_handler(
        request: Request,  # noqa: ARG001
        exc: WorkspaceRunExistsError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content=DuplicateResourceError("Run", exc.entity_id).to_dict(),
        )
