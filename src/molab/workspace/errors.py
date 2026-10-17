"""Typed exceptions for workspace storage operations.

The two families:

* ``*NotFoundError`` (``LookupError`` subclasses) — strict getter
  raised when the requested entity does not exist.
* ``*ExistsError`` (``ValueError`` subclasses) — strict-create
  raised when the entity already exists and the caller asked for
  a brand-new one.

The idempotent ``add_*`` factories (``Workspace.add_project`` /
``Project.add_experiment`` / ``Experiment.add_run``) raise neither —
they return the existing entity if found.

These classes carry the entity identifier in the message so that
upstream layers (``server/exceptions.py``) can format HTTP
responses without re-parsing.

The two abstract bases (``_WorkspaceLookupError`` /
``_WorkspaceConflictError``) exist to give the server layer a
single ``isinstance`` check for the 404 / 409 mapping; they are
intentionally not exported from ``molab.workspace``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from molab.workspace.refs import MolabRef


class _WorkspaceLookupError(LookupError):
    """Base for ``*NotFoundError`` — strict getter miss."""

    _entity_kind: str = "entity"

    def __init__(self, entity_id: str) -> None:
        super().__init__(f"{self._entity_kind} {entity_id!r} not found")
        self.entity_id = entity_id


class RefNotFoundError(_WorkspaceLookupError):
    """A ``molab:`` reference names an entity that is not in the workspace.

    ``entity_id`` is the id of the first missing segment. ``segment`` is that
    segment's kind (``project``, ``experiment``, ``run``, ``execution``,
    ``artifact``). ``ref`` is the reference that was walked, or ``None`` when
    a bare id missed.
    """

    def __init__(self, ref: MolabRef | None, segment: str, entity_id: str) -> None:
        if ref is None:
            message = f"{segment} {entity_id!r} not found"
        else:
            message = f"{ref}: {segment} {entity_id!r} not found"
        LookupError.__init__(self, message)
        self.ref = ref
        self.segment = segment
        self.entity_id = entity_id


class AmbiguousRefError(LookupError):
    """More than one entity matches an id, so no reference is chosen.

    Attributes:
        entity_id: The id that matched more than once.
        candidates: One reference per match.
        locations: Optional extra locations (asset scope), empty by default.
    """

    def __init__(
        self,
        entity_id: str,
        candidates: tuple[MolabRef, ...],
        *,
        locations: tuple[str, ...] = (),
    ) -> None:
        listed = ", ".join(str(candidate) for candidate in candidates)
        message = f"{entity_id!r} is ambiguous: {listed}"
        if locations:
            message = f"{message} ({', '.join(locations)})"
        super().__init__(message)
        self.entity_id = entity_id
        self.candidates = candidates
        self.locations = locations


class _WorkspaceConflictError(ValueError):
    """Base for ``*ExistsError`` — strict-create collision."""

    _entity_kind: str = "entity"

    def __init__(self, entity_id: str) -> None:
        super().__init__(f"{self._entity_kind} {entity_id!r} already exists")
        self.entity_id = entity_id


class ProjectNotFoundError(_WorkspaceLookupError):
    """Raised by ``Workspace.get_project(id)`` when no such project exists."""

    _entity_kind = "project"


class ExperimentNotFoundError(_WorkspaceLookupError):
    """Raised by ``Project.experiment(id)`` when no such experiment exists."""

    _entity_kind = "experiment"


class RunNotFoundError(_WorkspaceLookupError):
    """Raised by ``Experiment.run(id)`` when no such run exists."""

    _entity_kind = "run"


class ProjectExistsError(_WorkspaceConflictError):
    """Raised by ``Workspace.create_project`` when the project exists."""

    _entity_kind = "project"


class ExperimentExistsError(_WorkspaceConflictError):
    """Raised by ``Project.create_experiment`` when the experiment exists."""

    _entity_kind = "experiment"


class RunExistsError(_WorkspaceConflictError):
    """Raised by ``Experiment.create_run`` when the run exists."""

    _entity_kind = "run"


class FolderMoveCollisionError(ValueError):
    """Raised by ``Folder.move_to`` when the destination already exists.

    Distinct from ``*ExistsError`` because the colliding party is not a
    workspace entity but any pre-existing path at the move destination.
    The message names both source and target paths so the caller can act
    without re-running the operation.
    """

    def __init__(self, src: str, dst: str) -> None:
        super().__init__(f"cannot move {src!r} to {dst!r}: destination exists")
        self.src = src
        self.dst = dst


class UnmigratedAssetError(RuntimeError):
    """An on-disk asset record predates the unified schema.

    The message names the record and the migration command. Readers raise
    this and never rewrite the file.
    """

    def __init__(self, path: str, reason: str, *, workspace_root: str) -> None:
        super().__init__(
            f"asset record {path!r} predates the unified asset schema ({reason}); "
            f"run `molab migrate assets {workspace_root}`"
        )
        self.path = path
        self.reason = reason
        self.workspace_root = workspace_root


__all__ = [
    "AmbiguousRefError",
    "ExperimentExistsError",
    "ExperimentNotFoundError",
    "FolderMoveCollisionError",
    "ProjectExistsError",
    "ProjectNotFoundError",
    "RefNotFoundError",
    "RunExistsError",
    "RunNotFoundError",
    "UnmigratedAssetError",
]
