"""``molab:`` references — the one id-based way to name a workspace entity.

The scheme literal and the syntactic test live only here. A reference names
ids, never a path. ``molab://…`` is a path-shaped URI and is not a reference.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final, Literal

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from .errors import AmbiguousRefError, RefNotFoundError

if TYPE_CHECKING:
    from .workspace import Workspace

REF_SCHEME: Final = "molab:"

RefKind = Literal["project", "experiment", "run", "execution", "artifact", "asset"]

_SEGMENT = re.compile(r"[^/\s?#]+")
_ORDERS: dict[tuple[str, ...], RefKind] = {
    ("project",): "project",
    ("experiment",): "experiment",
    ("experiment", "run"): "run",
    ("experiment", "run", "execution"): "execution",
    ("experiment", "run", "artifact"): "artifact",
    ("asset",): "asset",
}


class InvalidRefError(ValueError):
    """A string is not a well-formed ``molab:`` reference of the requested kind."""


def is_ref(text: str) -> bool:
    """Whether *text* uses the ``molab:`` scheme and is not a ``molab://`` URI.

    This is only the scheme test. Well-formedness is :func:`parse_ref`.
    """
    return text.startswith(REF_SCHEME) and not text.startswith(REF_SCHEME + "//")


def _valid_segment(value: str) -> bool:
    return value not in {".", ".."} and _SEGMENT.fullmatch(value) is not None


class MolabRef(BaseModel):
    """One canonical ``molab:`` reference.

    Exactly one of these shapes:

    - ``molab:project/<p>``
    - ``molab:experiment/<e>``
    - ``molab:experiment/<e>/run/<r>``
    - ``molab:experiment/<e>/run/<r>/execution/<x>``
    - ``molab:experiment/<e>/run/<r>/artifact/<a>``
    - ``molab:asset/<id>``
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    project_id: str | None = None
    experiment_id: str | None = None
    run_id: str | None = None
    execution_id: str | None = None
    artifact_id: str | None = None
    asset_id: str | None = None

    @model_validator(mode="after")
    def _shape(self) -> MolabRef:
        segments = {
            "project": self.project_id,
            "experiment": self.experiment_id,
            "run": self.run_id,
            "execution": self.execution_id,
            "artifact": self.artifact_id,
            "asset": self.asset_id,
        }
        for value in segments.values():
            if value is not None and not _valid_segment(value):
                raise ValueError(f"illegal reference segment {value!r}")
        if self.asset_id is not None and any(
            value is not None
            for value in (
                self.project_id,
                self.experiment_id,
                self.run_id,
                self.execution_id,
                self.artifact_id,
            )
        ):
            raise ValueError("an asset reference cannot name another entity")
        if self.project_id is not None and any(
            value is not None
            for value in (
                self.experiment_id,
                self.run_id,
                self.execution_id,
                self.artifact_id,
                self.asset_id,
            )
        ):
            raise ValueError("a project reference cannot name another entity")
        if self.asset_id is None and self.project_id is None and self.experiment_id is None:
            raise ValueError("a reference needs a project, an experiment, or an asset")
        if self.run_id is not None and self.experiment_id is None:
            raise ValueError("a run reference needs an experiment")
        if (self.execution_id is not None or self.artifact_id is not None) and self.run_id is None:
            raise ValueError("an execution or artifact reference needs a run")
        if self.execution_id is not None and self.artifact_id is not None:
            raise ValueError("a reference names an execution or an artifact, not both")
        return self

    @property
    def kind(self) -> RefKind:
        """The deepest segment this reference names."""
        if self.asset_id is not None:
            return "asset"
        if self.artifact_id is not None:
            return "artifact"
        if self.execution_id is not None:
            return "execution"
        if self.run_id is not None:
            return "run"
        if self.experiment_id is not None:
            return "experiment"
        return "project"

    def __str__(self) -> str:
        if self.asset_id is not None:
            return f"{REF_SCHEME}asset/{self.asset_id}"
        parts: list[str] = []
        if self.project_id is not None:
            parts.extend(("project", self.project_id))
        if self.experiment_id is not None:
            parts.extend(("experiment", self.experiment_id))
        if self.run_id is not None:
            parts.extend(("run", self.run_id))
        if self.execution_id is not None:
            parts.extend(("execution", self.execution_id))
        if self.artifact_id is not None:
            parts.extend(("artifact", self.artifact_id))
        return REF_SCHEME + "/".join(parts)


def parse_ref(text: str, *, kind: RefKind | None = None) -> MolabRef:
    """Parse a canonical ``molab:`` reference.

    Args:
        text: The reference string.
        kind: When given, the reference's deepest segment must be this kind.

    Returns:
        The parsed reference. ``str(parse_ref(s)) == s`` for a canonical string.

    Raises:
        InvalidRefError: *text* is not a reference, names an unknown segment,
            is nested non-canonically, or is not of *kind*.
    """
    if not isinstance(text, str) or not is_ref(text):
        raise InvalidRefError(f"not a molab reference: {text!r}")
    body = text[len(REF_SCHEME) :]
    if not body or body.endswith("/") or "//" in body:
        raise InvalidRefError(f"malformed molab reference: {text!r}")
    parts = body.split("/")
    if len(parts) % 2 != 0:
        raise InvalidRefError(f"malformed molab reference: {text!r}")
    pairs = list(zip(parts[0::2], parts[1::2], strict=True))
    order = tuple(name for name, _value in pairs)
    if order not in _ORDERS:
        raise InvalidRefError(f"malformed molab reference: {text!r}")
    fields = {
        "project": "project_id",
        "experiment": "experiment_id",
        "run": "run_id",
        "execution": "execution_id",
        "artifact": "artifact_id",
        "asset": "asset_id",
    }
    try:
        ref = MolabRef(**{fields[name]: value for name, value in pairs})
    except ValidationError as exc:
        raise InvalidRefError(f"malformed molab reference: {text!r}") from exc
    if kind is not None and ref.kind != kind:
        raise InvalidRefError(f"expected a {kind} reference, got {ref.kind}: {text}")
    return ref


def ref_of(entity: object, *, artifact_id: str | None = None) -> MolabRef:
    """The canonical reference for a live workspace entity.

    Entity classes are imported inside the function so this module does not
    cycle with ``workspace.py``. Not exported from ``molab.workspace``.

    Args:
        entity: A ``Project``, ``Experiment``, ``Run``, or ``Asset``.
        artifact_id: When *entity* is a ``Run``, names that run's artifact.

    Returns:
        The reference ``Workspace.find`` accepts.

    Raises:
        TypeError: *entity* is not one of those classes, or *artifact_id* is
            set on anything other than a ``Run``.
    """
    from molab.workspace.domain import Asset
    from molab.workspace.experiment import Experiment
    from molab.workspace.project import Project
    from molab.workspace.run import Run

    if isinstance(entity, Run):
        if artifact_id is None:
            return MolabRef(experiment_id=entity.experiment.id, run_id=entity.id)
        return MolabRef(
            experiment_id=entity.experiment.id,
            run_id=entity.id,
            artifact_id=artifact_id,
        )
    if artifact_id is not None:
        raise TypeError(f"artifact_id is only valid on a Run, got {type(entity).__name__}")
    if isinstance(entity, Project):
        return MolabRef(project_id=entity.id)
    if isinstance(entity, Experiment):
        return MolabRef(experiment_id=entity.id)
    if isinstance(entity, Asset):
        return MolabRef(asset_id=entity.id)
    raise TypeError(
        f"ref_of expects a Project, Experiment, Run, or Asset, got {type(entity).__name__}"
    )


def qualify_run_id(workspace: Workspace, run_id: str) -> MolabRef:
    """Turn a bare run id into the one experiment-qualified reference.

    Kept permanently (D18): a bare run id from legacy data becomes a
    :class:`MolabRef`. Zero hits raise :class:`RefNotFoundError`. More than
    one hit raises :class:`AmbiguousRefError` listing every candidate. Not
    exported from ``molab.workspace``; callers import it from this module.

    Args:
        workspace: The tree to search.
        run_id: The run's id, not a directory name.

    Returns:
        ``molab:experiment/<e>/run/<run_id>``.
    """
    from .run import Run

    found: list[MolabRef] = []
    for project in workspace.list_projects():
        for experiment in project.list_experiments():
            if experiment._child_by_id(run_id, cls=Run) is not None:
                found.append(MolabRef(experiment_id=experiment.id, run_id=run_id))
    if not found:
        raise RefNotFoundError(None, "run", run_id)
    if len(found) > 1:
        raise AmbiguousRefError(run_id, tuple(found))
    return found[0]
