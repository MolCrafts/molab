"""One call a mutating route makes after it changed something.

Two things have to happen when a route writes: the read model must stop
serving the pre-write snapshot, and every attached browser must learn what
changed so it can invalidate exactly the queries affected. Doing them
separately invites the bug where one is added and the other forgotten — a UI
that shows stale data until the next full refresh — so they are one call.

Mutations that go through the workspace event spine (the run verbs) are
*already* published by the spine observer; calling this as well is harmless
(the client coalesces) and keeps the route readable without the reader having
to know which verbs emit.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from molexp.services.workspace_notify import (
    ChangeKind,
    WorkspaceChange,
    notify_workspace_changed,
)

if TYPE_CHECKING:
    from molexp.services.workspace_read_model import WorkspaceReadModel
    from molexp.workspace import Workspace

__all__ = ["after_mutation"]

# Which read-model view each change kind dirties.
_VIEW_FOR: dict[str, Literal["runs", "assets", "knowledge", "all"]] = {
    "run": "runs",
    "project": "runs",
    "experiment": "runs",
    "asset": "assets",
    "knowledge": "knowledge",
    "workspace": "all",
    "all": "all",
}


def after_mutation(
    workspace: Workspace,
    kind: ChangeKind,
    *,
    read_model: WorkspaceReadModel | None = None,
    ref: str | None = None,
    project_id: str | None = None,
    experiment_id: str | None = None,
    run_id: str | None = None,
) -> None:
    """Invalidate the affected view and publish the change to subscribers.

    Never raises: a failed notification must not fail the mutation that
    already succeeded on disk.
    """
    try:
        root = str(workspace.resolve())
    except Exception:
        return
    try:
        if read_model is None:
            from molexp.server.deps.read_model import read_model_for

            read_model = read_model_for(workspace)
        read_model.invalidate(_VIEW_FOR.get(kind, "all"), ref=ref)
        versions = read_model.versions()
    except Exception:
        versions = {}
    try:
        notify_workspace_changed(
            WorkspaceChange(
                root=root,
                kind=kind,
                ref=ref,
                project_id=project_id,
                experiment_id=experiment_id,
                run_id=run_id,
                versions=versions,
            )
        )
    except Exception:
        return
