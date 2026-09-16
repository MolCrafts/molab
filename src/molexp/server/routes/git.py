"""Git projection routes — checkpoint / rebuild / push over the shared backend.

``POST /git/checkpoint`` and ``POST /git/rebuild`` materialize the workspace's
bare object DB (local, cheap, ungated); ``POST /git/push`` mirrors
``refs/molexp/*`` to a remote (outward-facing).

The route bodies call the EXACT same ``checkpoint`` / ``rebuild`` / ``push``
symbols the ``molexp git`` CLI calls (Python ≡ UI — one backend code path).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from molexp.server.dependencies import get_workspace
from molexp.server.executors import run_heavy
from molexp.workspace.git_projection import (
    checkpoint,
    push,
    rebuild,
)

if TYPE_CHECKING:
    from molexp.workspace import Workspace

__all__ = ["router"]

router = APIRouter(prefix="/git", tags=["git"])


def _blocking(coro_factory):  # noqa: ANN001, ANN202
    """Run an async projection verb to completion on a worker thread.

    The projection's own I/O (``iterdir`` / ``read_bytes`` over every run's
    blobs) is synchronous *inside* its coroutines, so awaiting them directly
    on the event loop stalls the whole server for the length of a checkpoint.
    Running them on the heavy pool — each in its own loop — keeps the loop
    free and bounds concurrent checkpoints at the pool size.
    """
    import asyncio as _asyncio

    return _asyncio.run(coro_factory())


class GitPushRequest(BaseModel):
    """Body for pushing the projected refs to a remote."""

    remote: str = Field(..., description="Git remote URL or path.")


class GitCheckpointResponse(BaseModel):
    """Result of a checkpoint / rebuild: the projected runs + workspace tree OID."""

    runs: int
    workspace_tree: str


@router.post("/checkpoint", response_model=GitCheckpointResponse)
async def git_checkpoint_route(
    workspace: Workspace = Depends(get_workspace),
) -> GitCheckpointResponse:
    result = await run_heavy(_blocking, lambda: checkpoint(workspace))
    return GitCheckpointResponse(runs=len(result.runs), workspace_tree=result.workspace_tree.hex)


@router.post("/rebuild", response_model=GitCheckpointResponse)
async def git_rebuild_route(
    workspace: Workspace = Depends(get_workspace),
) -> GitCheckpointResponse:
    result = await run_heavy(_blocking, lambda: rebuild(workspace))
    return GitCheckpointResponse(runs=len(result.runs), workspace_tree=result.workspace_tree.hex)


@router.post("/push")
async def git_push_route(
    body: GitPushRequest,
    workspace: Workspace = Depends(get_workspace),
) -> dict[str, str]:
    await run_heavy(_blocking, lambda: push(workspace, remote=body.remote))
    return {"pushed": body.remote}
