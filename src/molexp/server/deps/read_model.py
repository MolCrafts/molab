"""Per-workspace :class:`WorkspaceReadModel` singletons — the FastAPI dependency.

One read model per live ``Workspace`` instance. The identity is deliberately
``id(workspace)`` rather than the root path: ``deps.workspace_state`` already
guarantees one ``Workspace`` object per active key and swaps it on a workspace
switch, so keying on the object means a switch (or a cache reset) naturally
yields a fresh read model instead of one holding snapshots of the old tree.

The registry keeps a strong reference to the workspace alongside the model, so
an ``id()`` key can never be recycled by the allocator while the entry lives.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends

from molexp.server.deps.resolution import get_workspace

if TYPE_CHECKING:
    from molexp.services.workspace_read_model import WorkspaceReadModel
    from molexp.workspace import Workspace

__all__ = ["get_read_model", "read_model_for", "reset_read_models"]

# id(workspace) → (workspace, model). The workspace is held to pin the id.
_models: dict[int, tuple[Workspace, WorkspaceReadModel]] = {}


def read_model_for(workspace: Workspace) -> WorkspaceReadModel:
    """The read model for *workspace*, created on first use."""
    from molexp.services.workspace_read_model import WorkspaceReadModel

    key = id(workspace)
    entry = _models.get(key)
    if entry is not None:
        return entry[1]
    model = WorkspaceReadModel(workspace)
    _models[key] = (workspace, model)
    return model


def get_read_model(workspace: Workspace = Depends(get_workspace)) -> WorkspaceReadModel:
    """FastAPI dependency: the active workspace's read model."""
    return read_model_for(workspace)


def reset_read_models() -> None:
    """Stop and drop every read model (workspace switch / shutdown / tests)."""
    entries = list(_models.values())
    _models.clear()
    for _workspace, model in entries:
        try:
            model.stop()
        except Exception:  # teardown is best-effort
            continue
