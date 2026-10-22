"""Compute-target registry helpers — the molab side of the two-axis model.

A :class:`~molab.workspace.models.ComputeTarget` is a value object stored on
the workspace's ``WorkspaceMetadata.targets`` list.  This module exposes thin
helpers around that list (list/get/add/remove) and the bridge functions
:func:`to_filesystem` and :func:`target_run_dir` that turn a target into the
molq objects used at submission time.

The workspace itself is the source of truth — these functions read and write
``workspace.json`` via the workspace's own atomic-write path.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .fs import FileSystem
from .models import ComputeTarget

if TYPE_CHECKING:
    from .run import Run
    from .workspace import Workspace


#: Name of the always-available built-in target: this machine, molq ``local``
#: scheduler. A workspace that registers its own ``local`` target overrides it.
LOCAL_TARGET_NAME = "local"


# ---------------------------------------------------------------------------
# Registry CRUD
# ---------------------------------------------------------------------------


def _target_list(ws: object) -> list[ComputeTarget]:
    """Targets on *ws*, or on a real parent workspace when this node has none."""
    current: object | None = ws
    seen = 0
    while current is not None and seen < 8:
        metadata = getattr(current, "metadata", None)
        found = getattr(metadata, "targets", None) or ()
        if found:
            return list(found)
        current = getattr(current, "_parent", None)
        seen += 1
    return []


def list_targets(ws: Workspace) -> list[ComputeTarget]:
    """All compute targets registered on *ws*."""
    return _target_list(ws)


def get_target(ws: Workspace, name: str) -> ComputeTarget:
    """Return the named target.

    Raises:
        KeyError: if no target with this name is registered.
    """
    for target in _target_list(ws):
        if target.name == name:
            return target
    raise KeyError(f"no compute target named {name!r}")


def has_target(ws: Workspace, name: str) -> bool:
    """True if a target with *name* is registered."""
    return any(target.name == name for target in _target_list(ws))


def add_target(ws: Workspace, target: ComputeTarget) -> None:
    """Register *target* on the workspace.

    Raises:
        ValueError: if a target with the same name already exists.
    """
    if has_target(ws, target.name):
        raise ValueError(f"compute target {target.name!r} already exists")
    ws.metadata = ws.metadata.model_copy(update={"targets": [*ws.metadata.targets, target]})
    ws.save()


def remove_target(ws: Workspace, name: str) -> None:
    """Remove the named target from the workspace registry.

    Raises:
        KeyError: if no target with this name is registered.
    """
    if not has_target(ws, name):
        raise KeyError(f"no compute target named {name!r}")
    ws.metadata = ws.metadata.model_copy(
        update={"targets": [t for t in ws.metadata.targets if t.name != name]}
    )
    ws.save()


# ---------------------------------------------------------------------------
# Built-in ``local`` target — the default any workspace can always resolve
# ---------------------------------------------------------------------------


def builtin_local_target(ws: Workspace) -> ComputeTarget:
    """The default local target: this machine, molq ``local`` scheduler.

    A run can always be started on *this machine* without first registering
    a target. The registry stays the source of truth — this is a derived
    convenience, never persisted.
    """
    return ComputeTarget(name=LOCAL_TARGET_NAME, scratch_root=str(ws.root))


def effective_targets(ws: Workspace) -> list[ComputeTarget]:
    """Registered targets, with the built-in ``local`` prepended unless the
    workspace already registers a target named ``local``."""
    registered = list_targets(ws)
    if any(t.name == LOCAL_TARGET_NAME for t in registered):
        return registered
    return [builtin_local_target(ws), *registered]


def resolve_compute_target(ws: Workspace, name: str) -> ComputeTarget:
    """``get_target`` with the built-in ``local`` fallback.

    The single named-target resolution path shared by the CLI
    (``resolve_target("@name", ws)``) and the server (``routes/run.py``).

    Raises:
        KeyError: for any unregistered name other than ``local``.
    """
    try:
        return get_target(ws, name)
    except KeyError:
        if name == LOCAL_TARGET_NAME:
            return builtin_local_target(ws)
        raise


# ---------------------------------------------------------------------------
# Bridge to molq
# ---------------------------------------------------------------------------


def target_definition(target: ComputeTarget) -> dict[str, object]:
    """Resolve the one molq destination used by files and scheduling."""
    from .connection import get_client

    if target.cluster_id is None:
        raise ValueError("A submitted target requires an explicit molq destination")
    return get_client(target.registry_id).cluster(target.cluster_id).definition()


def to_filesystem(target: ComputeTarget) -> FileSystem:
    """Create the existing FileSystem adapter over the registered destination."""
    from .connection import get_client
    from .fs_local import LocalFileSystem
    from .fs_remote import RemoteFileSystem

    if target.cluster_id is None:
        return LocalFileSystem()
    return RemoteFileSystem(get_client(target.registry_id), target.cluster_id, target.scratch_root)


def target_run_dir(target: ComputeTarget, ws: Workspace, run: Run) -> str:
    """Working directory for *run* on *target*'s filesystem.

    For **local targets**, the run dir is already an absolute path on this
    machine — we just return it.  ``scratch_root`` is informational for local
    targets (e.g. shown in `molab target list`) but doesn't relocate the
    workspace's own directory tree, which would only confuse `molab explore`
    and break asset paths.

    For **remote targets**, return an absolute path under
    ``target.scratch_root`` namespaced by workspace / project / experiment /
    run ids so concurrent runs on the same target don't collide. Within that
    namespace retain the workspace-relative hierarchy, so the standard Run
    loader can reconstruct the staged worker context.
    """
    if not target.is_remote:
        return str(run.run_dir)
    project = run.experiment.project
    experiment = run.experiment
    relative = Path(str(run.run_dir)).relative_to(Path(str(ws.root))).as_posix()
    namespace = (
        f"{target.scratch_root.rstrip('/')}/{ws.metadata.id}/{project.id}/{experiment.id}/{run.id}"
    )
    return f"{namespace}/{relative}"
