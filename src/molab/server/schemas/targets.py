"""API schemas for the workspace ComputeTarget registry.

A :class:`~molab.workspace.ComputeTarget` is the cross-product of the
*transport* axis (local vs SSH) and the *scheduler* axis (local / slurm /
pbs / lsf).  These models are the wire format for ``/api/targets``.
"""

from __future__ import annotations

from pydantic import Field

from molab.workspace.models import ComputeTarget

from ._wire import ApiModel


class TargetCreateRequest(ApiModel):
    """A semantic target referencing the molq destination registry."""

    name: str
    scratch_root: str = Field(alias="scratchRoot")
    registry_id: str | None = Field(default=None, alias="registryId")
    cluster_id: str | None = Field(default=None, alias="clusterId")


class TargetResponse(TargetCreateRequest):
    is_remote: bool = Field(alias="isRemote")

    @classmethod
    def from_model(cls, target: ComputeTarget) -> TargetResponse:
        return cls(
            name=target.name,
            scratchRoot=target.scratch_root,
            registryId=target.registry_id,
            clusterId=target.cluster_id,
            isRemote=target.is_remote,
        )


class TargetListResponse(ApiModel):
    """Response for ``GET /api/targets``."""

    targets: list[TargetResponse]
    total: int


class TargetTestResponse(ApiModel):
    """Response for ``POST /api/targets/{name}/test``."""

    name: str
    ok: bool
    checks: list[TargetTestCheck]
    error: str | None = None


class TargetTestCheck(ApiModel):
    """One step of the target connectivity probe."""

    label: str = Field(..., description="Human-readable check name")
    ok: bool
    detail: str | None = None


TargetTestResponse.model_rebuild()
