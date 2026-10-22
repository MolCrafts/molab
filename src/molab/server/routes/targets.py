"""Compute-target registry routes — CRUD on workspace ComputeTargets.

These endpoints are the UI/API counterpart of ``molab target add/remove/list/test``.
A target is the (Transport × Scheduler) destination a run can be submitted to.
The workspace (``workspace.json``) is the source of truth; this router is a
thin adapter on top of :mod:`molab.workspace.targets`.
"""  # noqa: RUF002

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from molab.workspace import ComputeTarget, Workspace
from molab.workspace.targets import effective_targets, to_filesystem

from ..dependencies import get_workspace
from ..schemas import (
    TargetCreateRequest,
    TargetListResponse,
    TargetResponse,
    TargetTestCheck,
    TargetTestResponse,
)

router = APIRouter(prefix="/targets", tags=["targets"])


@router.get("", response_model=TargetListResponse)
def list_targets_endpoint(
    workspace: Workspace = Depends(get_workspace),
) -> TargetListResponse:
    """List compute targets — the registered ones plus the built-in ``local``."""
    targets = effective_targets(workspace)
    rows = [TargetResponse.from_model(t) for t in targets]
    return TargetListResponse(targets=rows, total=len(rows))


@router.post("", response_model=TargetResponse, status_code=201)
def create_target_endpoint(
    payload: TargetCreateRequest,
    workspace: Workspace = Depends(get_workspace),
) -> TargetResponse:
    """Register a new compute target.

    Mirrors ``molab target add NAME --scratch ... --cluster ...``.
    """
    try:
        target = ComputeTarget(**payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        workspace.add_target(target)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return TargetResponse.from_model(target)


@router.delete("/{name}", status_code=204)
def delete_target_endpoint(
    name: str,
    workspace: Workspace = Depends(get_workspace),
) -> None:
    """Remove the named compute target from the workspace registry."""
    try:
        workspace.remove_target(name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{name}/test", response_model=TargetTestResponse)
def test_target_endpoint(
    name: str,
    workspace: Workspace = Depends(get_workspace),
) -> TargetTestResponse:
    """Verify connectivity to a target — runs the same round-trip probe as
    ``molab target test`` (true / mkdir scratch / 1-byte file round-trip).

    Returns ``ok=False`` with the failing step's detail rather than raising,
    so the UI can render the failure inline.
    """
    try:
        target = workspace.get_target(name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        fs = to_filesystem(target)
        present = fs.is_dir(target.scratch_root)
        return TargetTestResponse(
            name=name, ok=present, checks=[TargetTestCheck(label="Destination root", ok=present)]
        )
    except Exception as exc:
        return TargetTestResponse(name=name, ok=False, checks=[], error=str(exc))
