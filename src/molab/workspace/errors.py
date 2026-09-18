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

from molab.knowledge.errors import ConceptNotFoundError as _KnowledgeConceptNotFoundError


class _WorkspaceLookupError(LookupError):
    """Base for ``*NotFoundError`` — strict getter miss."""

    _entity_kind: str = "entity"

    def __init__(self, entity_id: str) -> None:
        super().__init__(f"{self._entity_kind} {entity_id!r} not found")
        self.entity_id = entity_id


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


class KnowledgeNotFoundError(_WorkspaceLookupError):
    """Raised by ``Project.knowledge`` / ``Experiment.knowledge`` when missing."""

    _entity_kind = "knowledge"


class KnowledgeExistsError(_WorkspaceConflictError):
    """Raised by a strict-create knowledge factory when the item exists."""

    _entity_kind = "knowledge"


#: Re-exported from the OKF library, where ``Bundle`` lives. The **same class
#: object**, so every ``except ConceptNotFoundError`` site catches what the
#: bundle actually raises no matter which module it imported from — two classes
#: for one failure is how a 404 silently becomes a 500. It subclasses
#: ``LookupError`` like the workspace ``*NotFoundError`` family, so the server's
#: not-found mapping is unchanged.
ConceptNotFoundError = _KnowledgeConceptNotFoundError


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


__all__ = [
    "ConceptNotFoundError",
    "ExperimentExistsError",
    "ExperimentNotFoundError",
    "FolderMoveCollisionError",
    "KnowledgeExistsError",
    "KnowledgeNotFoundError",
    "ProjectExistsError",
    "ProjectNotFoundError",
    "RunExistsError",
    "RunNotFoundError",
]
