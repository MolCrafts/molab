"""History routes — read the workspace's git log, sync, and push.

The route bodies call the same :class:`molab.workspace.GitHistory` the
``molab history`` CLI calls (Python ≡ UI — one backend code path).
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from molab.server.dependencies import get_workspace
from molab.services.document_history import DocumentHistory, document_history
from molab.workspace.history import GitHistory

if TYPE_CHECKING:
    from molab.workspace import Workspace

__all__ = ["router"]

router = APIRouter(prefix="/history", tags=["history"])


@router.get("/document", response_model=DocumentHistory)
def read_document_history(
    document: str,
    commit: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    workspace=Depends(get_workspace),  # noqa: ANN001
) -> DocumentHistory:
    """Read one knowledge file's Git revisions and compare with its working copy."""
    try:
        return document_history(workspace, document, commit=commit, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


class HistoryFact(BaseModel):
    """One recorded fact, read back from a commit."""

    commit: str
    event: str
    subjectType: str
    subjectId: str
    summary: str
    occurredAt: str


class HistorySyncResponse(BaseModel):
    """Result of committing whatever was left uncommitted."""

    commit: str | None = Field(None, description="New commit sha, or null if nothing changed.")


class HistoryPushRequest(BaseModel):
    """Body for pushing the workspace history to a remote."""

    remote: str = Field(..., description="Git remote URL or path.")


@router.get("", response_model=list[HistoryFact])
def read_history(
    entity: str | None = None,
    event: str | None = None,
    limit: int = 50,
    workspace: Workspace = Depends(get_workspace),
) -> list[HistoryFact]:
    """List recorded facts, newest first."""
    history = GitHistory(workspace.root)
    return [
        HistoryFact(
            commit=item.commit,
            event=item.event,
            subjectType=item.subject.type,
            subjectId=item.subject.id,
            summary=item.summary,
            occurredAt=item.occurred_at.isoformat(),
        )
        for item in history.entries(entity_id=entity, event=event, limit=limit)
    ]


@router.post("/sync", response_model=HistorySyncResponse)
def sync_history(workspace: Workspace = Depends(get_workspace)) -> HistorySyncResponse:
    """Commit anything a worker left uncommitted."""
    return HistorySyncResponse(commit=GitHistory(workspace.root).sweep())


@router.post("/push", response_model=HistorySyncResponse)
def push_history(
    body: HistoryPushRequest,
    workspace: Workspace = Depends(get_workspace),
) -> HistorySyncResponse:
    """Push the workspace history to a remote — this is the backup."""
    history = GitHistory(workspace.root)
    commit = history.sweep()
    proc = subprocess.run(
        ["git", "push", body.remote, "HEAD"],
        cwd=history.root,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise HTTPException(status_code=502, detail=proc.stderr.strip())
    return HistorySyncResponse(commit=commit)
