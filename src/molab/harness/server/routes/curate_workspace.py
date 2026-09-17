"""``POST /api/workspace/curate`` — gated, LLM-free destructive curation.

The endpoint's path lives under molab's ``/workspace`` prefix because that is
where an operator looks for it, but everything it does is harness: it builds a
§8 ``ChangeProposal``, drives it through the shared ``run_curation_proposal``
backend (the one ``molab curate`` uses — Python ≡ UI), and files the audit
artifact. It is mounted by :data:`molab.harness.server.SERVER_PLUGIN`.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from molab.server.dependencies import get_workspace

if TYPE_CHECKING:
    from molab.harness.schemas import ApprovalDecision, ApprovalRequest

router = APIRouter(prefix="/workspace", tags=["workspace"])


class CurateRequest(BaseModel):
    """A structured, LLM-free destructive-curation request.

    Builds a §8 ``ChangeProposal`` directly from typed args and drives it through
    the shared ``run_curation_proposal`` backend (the same one the CLI + NL flow
    use). ``approve`` defaults to ``False`` so a destructive mutation over HTTP
    never auto-executes — the proposal is recorded and refused unless the caller
    opts in.
    """

    op: Literal["move_run", "delete_folder", "rehome_asset"]
    run: str | None = None
    target_experiment: str | None = None
    folder: str | None = None
    asset: str | None = None
    source: dict[str, str] | None = None
    target: dict[str, str] | None = None
    action: str = "copy"
    approve: bool = False
    project: str = "curations"
    experiment: str = "curate"


class CurateResponse(BaseModel):
    """The gated-execution outcome for a deterministic curation request."""

    proposalId: str
    status: str
    reason: str | None = None
    resultArtifactIds: list[str] = Field(default_factory=list)


async def _curate_reject_approver(request: ApprovalRequest) -> ApprovalDecision:
    from datetime import UTC

    from molab.harness.schemas import ApprovalDecision

    return ApprovalDecision(
        request_id=request.id,
        granted=False,
        decided_by="http-operator",
        decided_at=datetime.now(tz=UTC),
        reason="approve=false",
    )


async def _curate_grant_approver(request: ApprovalRequest) -> ApprovalDecision:
    """Grant carried by the HTTP request body's explicit ``approve: true``.

    An explicit per-request decision by the HTTP caller — NOT a silent
    default — so ``decided_by`` names the caller, never "auto-approver".
    """
    from datetime import UTC

    from molab.harness.schemas import ApprovalDecision

    return ApprovalDecision(
        request_id=request.id,
        granted=True,
        decided_by="http-operator",
        decided_at=datetime.now(tz=UTC),
        reason="approve=true (explicit in the request body)",
    )


@router.post("/curate", response_model=CurateResponse)
async def curate_workspace(
    request: CurateRequest,
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> CurateResponse:
    """Gate + execute one deterministic destructive-curation op (single stack).

    Shares the ``run_curation_proposal`` backend with ``molab curate`` (Python ≡
    UI). ``approve=false`` (default) records the proposal and refuses; ``true``
    executes the mutation. Either way the §8 ``change_proposal`` artifact is the audit.
    """
    from molab.harness.services.curate_runtime import (
        build_curation_proposal,
        run_curation_proposal,
    )
    from molab.workspace.utils import derive_run_id

    try:
        proposal = build_curation_proposal(
            request.op,
            run=request.run,
            target_experiment=request.target_experiment,
            folder=request.folder,
            asset=request.asset,
            source=request.source,
            target=request.target,
            action=request.action,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    params: dict[str, Any] = {"mode": "curate-propose", "op": request.op, "proposal": proposal.id}
    audit_run = (
        workspace.add_project(request.project)
        .add_experiment(request.experiment)
        .add_run(params, id=derive_run_id(params))
    )
    approver = _curate_grant_approver if request.approve else _curate_reject_approver
    result = await run_curation_proposal(
        proposal, workspace=workspace, run=audit_run, approve=approver
    )
    outcome = result.execution_result
    return CurateResponse(
        proposalId=proposal.id,
        status=outcome.status if outcome is not None else "failed",
        reason=outcome.reason if outcome is not None else None,
        resultArtifactIds=list(outcome.result_artifact_ids) if outcome is not None else [],
    )
