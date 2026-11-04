"""Orthogonal planning documents.

A campaign is four documents, each with one job:

* :class:`~molab.knowledge.concepts.Plan` — the overview: question, scope,
  constraints. It does not list stages, todos, or completion criteria.
* :class:`~molab.knowledge.concepts.Roadmap` — ordered stages and which
  experiment each stage is. It does not list work items or criteria.
* :class:`~molab.knowledge.concepts.Todo` — work items and their status. It
  does not define the stage order.
* :class:`~molab.knowledge.concepts.Milestone` — one checkpoint: the stage it
  closes and the criterion that closes it. It does not list the work.

Roadmap, Todo, and Milestone cite the Plan. They do not cite each other's
fields. :func:`campaign_of` reads that set back; :func:`check_campaign`
checks that a todo or milestone names a stage the roadmap actually has.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from .concept import Concept
    from .concepts import Milestone, Plan, Roadmap, Todo

TodoStatus = Literal["open", "done", "blocked"]
MilestoneStatus = Literal["open", "met", "missed"]
PlanningRole = Literal["overview", "roadmap", "todo", "milestone"]


@runtime_checkable
class PlanningDocument(Protocol):
    """A document that owns exactly one planning role.

    ``planning_role`` is the job. ``planning_fields`` is the structured
    record that job owns, and nothing from the other three.
    """

    def planning_role(self) -> PlanningRole:
        """``overview``, ``roadmap``, ``todo``, or ``milestone``."""
        ...

    def planning_fields(self) -> Mapping[str, object]:
        """The fields this role stores. Other roles' fields are absent."""
        ...


class RoadmapStage(BaseModel):
    """One stage on a roadmap.

    Attributes:
        id: Stable id other documents name. Not a title.
        title: What the stage is.
        experiment: Experiment directory name that carries this stage, if any.
        depends_on: Stage ids that finish before this one. Not a todo list.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    title: str
    experiment: str | None = None
    depends_on: tuple[str, ...] = ()


class TodoItem(BaseModel):
    """One piece of work. The stage id points at a roadmap; it does not copy it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    title: str
    status: TodoStatus = "open"
    stage: str | None = None


class MilestoneRecord(BaseModel):
    """The checkpoint a Milestone document stores."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    stage: str
    criterion: str
    status: MilestoneStatus = "open"


def parse_stages(raw: object) -> tuple[RoadmapStage, ...]:
    """Validate a roadmap's ``stages`` list, including its dependency graph.

    Raises:
        ValueError: The list is not stages, an id repeats, a dependency is
            missing, or the dependencies cycle.
    """
    if not isinstance(raw, list):
        raise ValueError("a Roadmap's stages are a list")
    stages = tuple(RoadmapStage.model_validate(item) for item in raw)
    ids = [stage.id for stage in stages]
    if len(ids) != len(set(ids)):
        raise ValueError(f"roadmap stage ids repeat: {ids}")
    known = set(ids)
    graph = {stage.id: stage.depends_on for stage in stages}
    for stage_id, deps in graph.items():
        missing = [dep for dep in deps if dep not in known]
        if missing:
            raise ValueError(f"stage {stage_id!r} depends on unknown stage(s) {missing}")
    _require_acyclic(graph)
    return stages


def parse_items(raw: object) -> tuple[TodoItem, ...]:
    """Validate a todo document's ``items`` list.

    Raises:
        ValueError: *raw* is not a list of todo items, or an id repeats.
    """
    if not isinstance(raw, list):
        raise ValueError("a Todo's items are a list")
    items = tuple(TodoItem.model_validate(item) for item in raw)
    ids = [item.id for item in items]
    if len(ids) != len(set(ids)):
        raise ValueError(f"todo ids repeat: {ids}")
    return items


def parse_milestone(raw: Mapping[str, object]) -> MilestoneRecord:
    """Validate the three fields a Milestone owns."""
    return MilestoneRecord.model_validate(
        {
            "stage": raw.get("stage"),
            "criterion": raw.get("criterion"),
            "status": raw.get("status", "open"),
        }
    )


def check_planning_record(of: type, record: Mapping[str, object] | None, *, creating: bool) -> None:
    """Reject a planning document that stores another role's fields.

    On create, a Roadmap must name ``stages``, a Todo must name ``items``,
    and a Milestone must name ``stage`` and ``criterion``. A later rewrite
    that does not touch those fields is left alone.

    Raises:
        ValueError: The record crosses roles, or a new document is missing
            the fields its role owns.
    """
    role = getattr(of, "PLANNING_ROLE", None)
    if role is None:
        return
    payload = dict(record or {})
    foreign = set(getattr(of, "FOREIGN_FIELDS", ()))
    crossed = sorted(set(payload) & foreign)
    if crossed:
        raise ValueError(
            f"{of.__name__} does not store {crossed}; that belongs to another planning document"
        )
    if role == "roadmap" and "stages" in payload:
        parse_stages(payload["stages"])
    if role == "todo" and "items" in payload:
        parse_items(payload["items"])
    if role == "milestone" and any(key in payload for key in ("stage", "criterion", "status")):
        parse_milestone(payload)
    if not creating:
        return
    if role == "roadmap" and "stages" not in payload:
        raise ValueError("a Roadmap stores stages, not todos or completion criteria")
    if role == "todo" and "items" not in payload:
        raise ValueError("a Todo stores items, not the stage order or a completion criterion")
    if role == "milestone" and ("stage" not in payload or "criterion" not in payload):
        raise ValueError("a Milestone stores the stage it closes and the criterion, not the work")


class Campaign(BaseModel):
    """The Plan plus the planning documents that cite it."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    plan: object
    roadmaps: tuple[object, ...] = ()
    todos: tuple[object, ...] = ()
    milestones: tuple[object, ...] = Field(default=())


def campaign_of(plan: Plan) -> Campaign:
    """The planning documents that cite *plan*.

    The search is the enclosing workspace when the plan lives in one, and
    the plan's own directory otherwise. A document that does not link to the
    Plan is not part of the campaign. Other knowledge is ignored.
    """
    from .concept import Knowledge
    from .concepts import Milestone, Roadmap, Todo
    from .location import enclosing_workspace_root

    disk = plan.fs
    plan_path = Path(str(plan.path)).resolve()
    root = enclosing_workspace_root(plan.path, fs=disk)
    if root is not None:
        documents = Knowledge(root, fs=disk).walk()
    else:
        documents = _documents_beside(plan)
    roadmaps: list[Roadmap] = []
    todos: list[Todo] = []
    milestones: list[Milestone] = []
    for doc in documents:
        if Path(str(doc.path)).resolve() == plan_path:
            continue
        if not _cites(doc, plan_path):
            continue
        if isinstance(doc, Roadmap):
            roadmaps.append(doc)
        elif isinstance(doc, Todo):
            todos.append(doc)
        elif isinstance(doc, Milestone):
            milestones.append(doc)
    return Campaign(
        plan=plan, roadmaps=tuple(roadmaps), todos=tuple(todos), milestones=tuple(milestones)
    )


def check_campaign(campaign: Campaign) -> None:
    """Every todo stage and milestone stage exists on the cited roadmap.

    Raises:
        ValueError: A stage id is declared twice, or a todo or milestone
            names a stage the roadmap does not have.
    """
    stages: dict[str, RoadmapStage] = {}
    for roadmap in campaign.roadmaps:
        for stage in roadmap.stages():  # ty: ignore[unresolved-attribute]
            if stage.id in stages:
                raise ValueError(f"stage {stage.id!r} is declared on more than one roadmap")
            stages[stage.id] = stage
    for todo in campaign.todos:
        for item in todo.items():  # ty: ignore[unresolved-attribute]
            if item.stage is not None and item.stage not in stages:
                raise ValueError(
                    f"todo {item.id!r} names stage {item.stage!r}, which is not on the roadmap"
                )
    for milestone in campaign.milestones:
        stage = milestone.stage()  # ty: ignore[unresolved-attribute]
        if stage not in stages:
            raise ValueError(
                f"milestone {milestone.name!r} closes stage {stage!r}, which is not on the roadmap"  # ty: ignore[unresolved-attribute]
            )


def _documents_beside(plan: Plan) -> list[Concept]:
    """Documents in the plan's directory, when it is not inside a workspace."""
    from .concepts import _open_document

    disk = plan.fs
    container = disk.dirname(str(plan.path))
    found: list[Concept] = []
    try:
        entries = disk.ls(container, A=True, l=True)
    except OSError:
        return found
    for entry in sorted(entries, key=lambda item: item.name):
        if entry.is_dir:
            continue
        try:
            found.append(_open_document(disk.join(container, entry.name), fs=disk))
        except (OSError, ValueError):
            continue
    return found


def _cites(doc: object, plan_path: Path) -> bool:
    """True when one of *doc*'s source edges resolves to *plan_path*.

    ``links()`` already resolves a local target against the document's own
    directory, so the target is compared as it comes.
    """
    links = getattr(doc, "links", None)
    if not callable(links):
        return False
    for edge in links():
        target = str(edge.target).split("#", 1)[0]
        if target.startswith("molab:"):
            continue
        if Path(target).resolve() == plan_path:
            return True
    return False


def _require_acyclic(graph: Mapping[str, tuple[str, ...]]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def walk(node: str) -> None:
        if node in visited:
            return
        if node in visiting:
            raise ValueError(f"roadmap stages cycle through {node!r}")
        visiting.add(node)
        for dep in graph.get(node, ()):
            walk(dep)
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        walk(node)


__all__ = [
    "Campaign",
    "MilestoneRecord",
    "MilestoneStatus",
    "PlanningDocument",
    "PlanningRole",
    "RoadmapStage",
    "TodoItem",
    "TodoStatus",
    "campaign_of",
    "check_campaign",
    "check_planning_record",
    "parse_items",
    "parse_milestone",
    "parse_stages",
]
