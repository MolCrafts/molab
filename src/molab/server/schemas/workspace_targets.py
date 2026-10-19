"""API schemas for the workspace-target registry (``/api/workspace/targets``).

A *workspace target* describes a remote root that the server can open
as the active :class:`~molab.workspace.Workspace` — distinct from a
:class:`~molab.workspace.ComputeTarget` (which describes a scratch
host for run execution).  These two concepts share the connectivity
probe envelope; :class:`TargetTestCheck` / :class:`TargetTestResponse`
are re-imported from ``.targets`` rather than duplicated.
"""

from __future__ import annotations

from typing import Literal

from molab.server.workspace_targets import WorkspaceTarget

from ._wire import ApiModel
from .targets import TargetTestCheck, TargetTestResponse


class WorkspaceTargetCreateRequest(ApiModel):
    """One workspace root and its molq destination identity."""

    name: str
    registry_id: str
    cluster_id: str
    root_path: str
    cache_dir: str | None = None
    cache_mode: Literal["pinned", "strict"] = "pinned"


class WorkspaceTargetResponse(WorkspaceTargetCreateRequest):
    @classmethod
    def from_model(cls, target: WorkspaceTarget) -> WorkspaceTargetResponse:
        return cls(**target.model_dump())


class WorkspaceTargetListResponse(ApiModel):
    """Response for ``GET /api/workspace/targets``."""

    targets: list[WorkspaceTargetResponse]
    total: int


__all__ = [
    "TargetTestCheck",
    "TargetTestResponse",
    "WorkspaceTargetCreateRequest",
    "WorkspaceTargetListResponse",
    "WorkspaceTargetResponse",
]
