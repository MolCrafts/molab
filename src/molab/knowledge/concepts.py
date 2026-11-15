"""Knowledge classes: one file each, and the fields each class declares.

A document is ``knowledges/<name>.md`` (or ``.html``). Its frontmatter names
the class and carries the fields that class declares in ``FIELDS``; the
narrative holds the links. A new class subclasses an existing one, and its
fields model extends the parent's, so everything that handles the parent
handles it.
"""

from __future__ import annotations

import logging
import math
from collections import Counter
from graphlib import TopologicalSorter
from types import MappingProxyType
from typing import TYPE_CHECKING, ClassVar, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from molab.fs import FileSystem, LocalFS, PathArg

from .concept import Concept
from .knowledge_item import SourceRef

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from molab._typing import JSONValue
    from molab.workspace.run import Run

_LOG = logging.getLogger(__name__)


class NoteFields(BaseModel):
    """What a Note stores beyond the common keys: its lifecycle status.

    ``proposed`` (the default, so every Note written without a status, and
    every Note that predates the field, reads as unreviewed), ``active``
    (a person reviewed it and it applies; set explicitly, never by
    default), ``retired`` (it no longer applies). Anything else is refused.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: NoteStatus = "proposed"


class LiteratureFields(BaseModel):
    """The bibliographic fields a Literature stores.

    A write folds in only the fields its caller set, so the ``source`` default
    is what an absent ``source`` reads as, never a value stamped over a stored
    one. A PDF is pointed at (``pdf_path`` / ``pdf_asset_id``), never copied.

    Attributes:
        title: Work title.
        authors: Ordered author names.
        year: Publication year.
        doi: Digital Object Identifier.
        venue: Journal / conference / publisher.
        url: Canonical URL.
        pdf_path: Filesystem pointer to a PDF (never copied).
        pdf_asset_id: Asset id of an imported PDF, if any.
        source: Provenance label (``"manual"`` / ``"zotero"`` / …).
        source_key: Stable key in the external source (e.g. a Zotero key).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str | None = None
    authors: tuple[str, ...] = ()
    year: int | None = None
    doi: str | None = None
    venue: str | None = None
    url: str | None = None
    pdf_path: str | None = None
    pdf_asset_id: str | None = None
    source: str = "manual"
    source_key: str | None = None


HypothesisVerdict = Literal["open", "supported", "refuted", "unsettled"]


class HypothesisFields(BaseModel):
    """Where a Hypothesis stands against the evidence. A closed vocabulary."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    verdict: HypothesisVerdict = "open"


DecisionStatus = Literal["open", "made"]
TodoStatus = Literal["open", "done", "blocked"]
MilestoneStatus = Literal["open", "met", "missed"]
NoteStatus = Literal["proposed", "active", "retired"]


def _require_unique(what: str, ids: list[str]) -> None:
    """Refuse *ids* that repeat. Raises ``ValueError`` naming them."""
    repeated = sorted(key for key, count in Counter(ids).items() if count > 1)
    if repeated:
        raise ValueError(f"{what} ids repeat: {repeated}")


class DecisionFields(BaseModel):
    """Whether the choice is ``made``, or ``open`` while it waits for a person."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: DecisionStatus = "made"


class TodoItem(BaseModel):
    """One piece of work. ``stage`` names a Roadmap stage; it does not copy it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    title: str
    status: TodoStatus = "open"
    stage: str | None = None


class TodoFields(BaseModel):
    """A Todo's work items, each id once."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    items: tuple[TodoItem, ...] = ()

    @model_validator(mode="after")
    def _ids_unique(self) -> TodoFields:
        _require_unique("todo item", [item.id for item in self.items])
        return self


class RoadmapStage(BaseModel):
    """One stage on a Roadmap.

    Attributes:
        id: The stable id a Todo item or a Milestone names. Not a title.
        title: What the stage is.
        experiment: The experiment directory that carries the stage, if any.
        depends_on: Stage ids that finish before this one.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    title: str
    experiment: str | None = None
    depends_on: tuple[str, ...] = ()


class RoadmapFields(BaseModel):
    """A Roadmap's stages: each id once, every dependency a stage, no cycle."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    stages: tuple[RoadmapStage, ...] = ()

    @model_validator(mode="after")
    def _an_acyclic_order(self) -> RoadmapFields:
        _require_unique("roadmap stage", [stage.id for stage in self.stages])
        graph = {stage.id: stage.depends_on for stage in self.stages}
        for stage_id, depends_on in graph.items():
            unknown = [dep for dep in depends_on if dep not in graph]
            if unknown:
                raise ValueError(f"stage {stage_id!r} depends on unknown stage(s) {unknown}")
        # CycleError is a ValueError: pydantic reports it as this model's error.
        TopologicalSorter(graph).prepare()
        return self


CheckComparison = Literal["within", "at_most", "at_least"]


class MilestoneCheck(BaseModel):
    """One number a Milestone is held to, and where a run's file holds it.

    Attributes:
        id: The stable id a measurement names.
        span: Where the measured value sits in a registered asset: a JSON
            pointer (``/ffv``) or a series point (``loss@10000``), the
            spellings :meth:`_SourcedKnowledge.read_cited` reads.
        expected: The value the measurement is compared with.
        tolerance: How far a ``within`` measurement may sit from *expected*.
        relative: Whether *tolerance* is a fraction of ``|expected|``.
        compare: ``within`` (the default), or a one-sided bound: ``at_most`` /
            ``at_least`` *expected*, where *tolerance* is not used.
        critical: Whether a failure misses the Milestone.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    span: str = Field(min_length=1)
    expected: float = Field(allow_inf_nan=False)
    tolerance: float = Field(default=0.0, ge=0, allow_inf_nan=False)
    relative: bool = False
    compare: CheckComparison = "within"
    critical: bool = True

    @model_validator(mode="after")
    def _relative_needs_a_scale(self) -> MilestoneCheck:
        if self.relative and self.expected == 0:
            raise ValueError(
                f"check {self.id!r}: a relative tolerance is a fraction of expected, which is 0"
            )
        return self

    def passes(self, value: float) -> bool:
        """Whether a measured *value* meets this check.

        A value that sits on the bound passes: the comparison allows for the
        last bits a decimal bound loses in binary (0.4 against 0.3 ± 0.1). A
        value that is not finite never passes.
        """
        if not math.isfinite(value):
            return False
        if self.compare == "at_most":
            return value <= self.expected or _same(value, self.expected)
        if self.compare == "at_least":
            return value >= self.expected or _same(value, self.expected)
        bound = self.tolerance * abs(self.expected) if self.relative else self.tolerance
        distance = abs(value - self.expected)
        return distance <= bound or _same(distance, bound, scale=abs(self.expected))


def _same(left: float, right: float, *, scale: float = 0.0) -> bool:
    """Whether two numbers differ only by floating-point rounding at their scale."""
    return abs(left - right) <= _ROUNDING * max(abs(left), abs(right), scale)


#: The relative slack a comparison at a bound allows for binary rounding.
_ROUNDING: Final = 1e-9


class MilestoneMeasurement(BaseModel):
    """What one check measured, and the bytes it was read from.

    Attributes:
        check: The :class:`MilestoneCheck` id this answers.
        ref: The ``molab:asset/<id>`` the value was read from.
        digest: The content digest of that asset when it was read.
        value: The number at the check's span.
        passed: Whether *value* met the check.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    check: str
    ref: str
    digest: str
    value: float = Field(allow_inf_nan=False)
    passed: bool


class MilestoneFields(BaseModel):
    """When the work is accepted: the criterion, where it stands, the stage it closes.

    ``stage`` is optional: a reproduction checkpoint closes no Roadmap stage.

    ``checks`` are the numbers the criterion comes down to, when it comes down
    to numbers. A Milestone that declares them takes its status from
    ``measurements``: ``met`` needs every critical check measured and passed,
    ``missed`` needs a critical check measured and failed, and each
    measurement's ``passed`` is what its check computes from the value.
    :func:`molab.knowledge.acceptance.evaluate_milestone` writes both from the
    registered files; fields typed by hand are held to the same arithmetic.
    A Milestone with no checks is judged by reading, and stores no measurement.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    criterion: str
    status: MilestoneStatus = "open"
    stage: str | None = None
    checks: tuple[MilestoneCheck, ...] = ()
    measurements: tuple[MilestoneMeasurement, ...] = ()

    @model_validator(mode="after")
    def _status_follows_measurements(self) -> MilestoneFields:
        _require_unique("milestone check", [check.id for check in self.checks])
        _require_unique("measured check", [item.check for item in self.measurements])
        checks = {check.id: check for check in self.checks}
        if not checks:
            if self.measurements:
                raise ValueError("a Milestone with no checks stores no measurement")
            return self
        if not any(check.critical for check in self.checks):
            raise ValueError("a Milestone's checks need at least one critical check")
        for item in self.measurements:
            check = checks.get(item.check)
            if check is None:
                raise ValueError(f"measurement names check {item.check!r}, which is not declared")
            if item.passed != check.passes(item.value):
                raise ValueError(
                    f"check {item.check!r}: passed={item.passed} disagrees with value {item.value}"
                )
        settled = settled_status(self.checks, self.measurements)
        if self.status != "open" and self.status != settled:
            raise ValueError(
                f"status {self.status!r} disagrees with the measurements, which give {settled!r}"
            )
        return self


def settled_status(
    checks: Sequence[MilestoneCheck], measurements: Sequence[MilestoneMeasurement]
) -> MilestoneStatus:
    """The status *measurements* give a Milestone that declares *checks*.

    ``missed`` when a critical check failed, ``met`` when every critical
    check was measured and passed, ``open`` while one is still unmeasured.
    """
    passed = {item.check: item.passed for item in measurements}
    critical = [check.id for check in checks if check.critical]
    if any(passed.get(check) is False for check in critical):
        return "missed"
    if all(passed.get(check) for check in critical):
        return "met"
    return "open"


class Note(Concept):
    """None of the other classes: free text with no claim on the reasoning.

    ``knowledges/<name>.md`` with ``class: Note`` frontmatter.
    """

    FILE_DOCUMENT: ClassVar[bool] = True
    FIELDS: ClassVar[type[NoteFields]] = NoteFields

    def fields(self) -> NoteFields:
        """This note's fields, read from its frontmatter."""
        return self._fields_of(type(self).FIELDS)

    def status(self) -> NoteStatus:
        """This note's lifecycle status (``"proposed"`` until a person sets another)."""
        return self.fields().status

    @classmethod
    def mount(cls, host: object, name: str, *, body: str = "") -> Note:
        """Idempotently mount this note under *host*.

        A mount materializes the document even with an empty body. A repeat
        call never truncates an existing body, including a repeat that passes
        ``body=""``.
        """
        from .write import write_knowledge

        return write_knowledge(host, name=name, of=cls, created_by="", text=body)  # ty: ignore[invalid-argument-type, invalid-return-type]


class Literature(Concept):
    """What does a published source say? Bib fields in the frontmatter."""

    FILE_DOCUMENT: ClassVar[bool] = True
    FIELDS: ClassVar[type[LiteratureFields]] = LiteratureFields

    def fields(self) -> LiteratureFields:
        """This literature item's bibliographic fields, from its frontmatter."""
        return self._fields_of(type(self).FIELDS)


class _SourcedKnowledge(Concept):
    """Every class but Note and Literature: a document that names its sources.

    ``sources`` is required when the document is created by name. An existing
    file reopens with ``Finding(path)`` and reads its sources from edges.
    """

    FILE_DOCUMENT: ClassVar[bool] = True

    def __init__(
        self,
        path: PathArg,
        name: str | None = None,
        *,
        sources: list[SourceRef] | None = None,
        fs: FileSystem | None = None,
    ) -> None:
        """Bind this document, keeping ``sources`` mandatory.

        Args:
            path: The document's path, or — with *name* given — its host (a
                ``str`` / :class:`os.PathLike` directory, or a workspace
                ``Folder``).
            name: A human document name; the host then derives the landed path.
            sources: The :class:`~molab.knowledge.knowledge_item.SourceRef` list
                this document harvests from; at least one is required.
            fs: The filesystem to read and write through; defaults to the host's
                own disk in the *name* form.

        Raises:
            ValueError: If *sources* is empty and this is not a file already on
                disk. ``Finding(path)`` reopens that file; ``Finding(host, name)``
                still requires sources.
            TypeError: If *name* is given and *path* is not a recognised host.
        """
        if not sources:
            if name is not None:
                raise ValueError(f"{self.__class__.__name__} requires at least one SourceRef")
            super().__init__(path, None, fs=fs)
            if not self.exists():
                raise ValueError(f"{self.__class__.__name__} requires at least one SourceRef")
            self._sources = []
            return
        super().__init__(path, name, fs=fs)
        self._sources = list(sources)

    @property
    def sources(self) -> list[SourceRef]:
        """Edges with role ``derived_from`` or ``cites``.

        A document that is not on disk yet returns the constructor list.
        """
        if self.exists():
            from molab.workspace.refs import InvalidRefError

            found: list[SourceRef] = []
            for edge in self.links():
                if edge.role not in {"derived_from", "cites"}:
                    continue
                try:
                    found.append(SourceRef.from_edge(edge))
                except InvalidRefError:
                    _LOG.warning("skipping malformed source edge %s", edge.target)
            return found
        return list(self._sources)

    @property
    def inputs(self) -> tuple[str, ...]:
        """Asset ids this document cites, in source order.

        Run and experiment sources are skipped. The same asset cited at more
        than one point is returned once. Pass the tuple to
        ``Experiment.add_run(inputs=...)``.
        """
        from molab.workspace.refs import parse_ref

        found: list[str] = []
        for source in self.sources:
            if source.kind != "asset":
                continue
            asset_id = parse_ref(source.ref).asset_id
            if asset_id and asset_id not in found:
                found.append(asset_id)
        return tuple(found)

    def read_cited(self, span: str) -> JSONValue:
        """The value at *span* in the one asset source that carries it.

        ``/loss`` is a JSON pointer. ``loss@10000`` is the series ``loss`` at
        step 10000. The narrative is :meth:`read`.

        Raises:
            ValueError: *span* is empty, is not exactly one asset citation, or
                the asset bytes do not contain that point.
        """
        if not span:
            raise ValueError("read_cited requires a span")
        matches = [
            source for source in self.sources if source.kind == "asset" and source.span == span
        ]
        if len(matches) != 1:
            raise ValueError(f"span {span!r} is not one asset citation on {self.name}")
        from molab.workspace import Workspace
        from molab.workspace.asset_repository import payload_path_for
        from molab.workspace.refs import parse_ref

        from .harvest import _document_at, _value_at
        from .location import enclosing_workspace_root

        root = enclosing_workspace_root(self.path, fs=self.fs)
        if root is None:
            raise ValueError(f"{self.path} is not inside a workspace")
        workspace = Workspace(root)
        asset_id = parse_ref(matches[0].ref).asset_id
        if not asset_id:
            raise ValueError(f"{matches[0].ref} is not an asset reference")
        path = payload_path_for(workspace, asset_id)
        body = _document_at(workspace.fs, path)
        if body is None:
            raise ValueError(f"asset {asset_id} has no JSON point at {span}")
        return _value_at(body, span)

    @classmethod
    def harvest(
        cls,
        run: Run,
        *,
        narrative: str,
        created_by: str,
        results: dict[str, JSONValue] | None = None,
        name: str | None = None,
    ) -> Concept:
        """Harvest a terminal *run* into this class under its experiment."""
        from .harvest import perform

        return perform(
            cls,
            run,
            narrative=narrative,
            created_by=created_by,
            results=results,
            name=name,
        )


class Report(_SourcedKnowledge):
    """What do we tell readers? It compiles; it claims nothing new.

    A Report is defined by its purpose, not its length: a result written up
    at length is still a :class:`Finding`. A failed run's analysis is a Report.
    """


class Finding(_SourcedKnowledge):
    """What does the evidence establish? Not a choice, and not a plan."""


class Plan(_SourcedKnowledge):
    """What are we asking, in what scope, under what constraints?

    A Plan does not list stages, todos or criteria: those live in
    :class:`Roadmap`, :class:`Todo` and :class:`Milestone` documents that cite
    the Plan. The claims to test are :class:`Hypothesis` documents.
    """


class Roadmap(_SourcedKnowledge):
    """In what order is the work done?

    ``stages`` is its one field: each stage's id and title, the experiment
    that carries it, and the stages it depends on. It cites the :class:`Plan`
    it orders. It lists no work items and no criterion.
    """

    FIELDS: ClassVar[type[RoadmapFields]] = RoadmapFields

    def fields(self) -> RoadmapFields:
        """This roadmap's stages, read from its frontmatter."""
        return self._fields_of(type(self).FIELDS)


class Todo(_SourcedKnowledge):
    """What work remains?

    ``items`` is its one field: each item's id, title, ``status`` (``open``,
    ``done`` or ``blocked``) and the Roadmap ``stage`` it serves. It cites the
    :class:`Plan` the work is for. It does not define the stage order.
    """

    FIELDS: ClassVar[type[TodoFields]] = TodoFields

    def fields(self) -> TodoFields:
        """This todo's items, read from its frontmatter."""
        return self._fields_of(type(self).FIELDS)


class Milestone(_SourcedKnowledge):
    """When is the work accepted?

    ``criterion`` is required; ``status`` is ``open``, ``met`` or ``missed``;
    ``stage`` names the Roadmap stage it closes, when it closes one. It cites
    the :class:`Plan`. It does not list the work that meets the criterion.
    """

    FIELDS: ClassVar[type[MilestoneFields]] = MilestoneFields

    def fields(self) -> MilestoneFields:
        """This milestone's criterion, status and stage, read from its frontmatter."""
        return self._fields_of(type(self).FIELDS)


class Observation(_SourcedKnowledge):
    """What was observed or given, before any interpretation?

    A conclusion is a :class:`Finding`.
    """


class Hypothesis(_SourcedKnowledge):
    """What do we claim will turn out to be true?

    ``verdict`` is its one field: ``open``, ``supported``, ``refuted``, or
    ``unsettled`` (the evidence cannot tell). A value outside the vocabulary
    is refused on write and reported by ``molab validate``; it is never read
    as the default. The evidence itself is a :class:`Finding` that links here
    with role ``supports`` or ``contradicts``.
    """

    FIELDS: ClassVar[type[HypothesisFields]] = HypothesisFields

    def fields(self) -> HypothesisFields:
        """This hypothesis's fields, read from its frontmatter."""
        return self._fields_of(type(self).FIELDS)

    def verdict(self) -> str:
        """``open``, ``supported``, ``refuted``, or ``unsettled``."""
        return self.fields().verdict


class Decision(_SourcedKnowledge):
    """What was chosen, by whom, and why?

    ``status`` is its one field: ``made`` (the default), or ``open`` while the
    choice waits for a person. An observed fact is an :class:`Observation`; a
    result is a :class:`Finding`.
    """

    FIELDS: ClassVar[type[DecisionFields]] = DecisionFields

    def fields(self) -> DecisionFields:
        """This decision's status, read from its frontmatter."""
        return self._fields_of(type(self).FIELDS)


#: The one class-name → Knowledge subclass table on the knowledge side. The
#: keys are the names callers already spell in a config, a CLI flag or an agent
#: tool payload.
_PRODUCTS: dict[str, type[Concept]] = {
    "Note": Note,
    "Literature": Literature,
    "Report": Report,
    "Finding": Finding,
    "Plan": Plan,
    "Roadmap": Roadmap,
    "Todo": Todo,
    "Milestone": Milestone,
    "Observation": Observation,
    "Hypothesis": Hypothesis,
    "Decision": Decision,
}


def _product(name: str) -> type[Concept]:
    """The document class *name* spells. Does not construct it.

    Raises:
        ValueError: *name* is not a knowledge class. The message lists them.
    """
    if name in _PRODUCTS:
        return _PRODUCTS[name]
    raise ValueError(
        f"unknown knowledge class {name!r}; expected one of: {', '.join(sorted(_PRODUCTS))}"
    )


def class_of(meta: Mapping[str, object]) -> type[Concept] | None:
    """The knowledge class a document's frontmatter ``class:`` names, or ``None``.

    A file whose ``class:`` is absent or names no class is not a document:
    nothing is guessed for it.
    """
    declared = meta.get("class")
    return _PRODUCTS.get(declared) if isinstance(declared, str) else None


def class_problem(meta: Mapping[str, object]) -> str | None:
    """Why *meta* names no knowledge class, or ``None`` when :func:`class_of` finds one."""
    if class_of(meta) is not None:
        return None
    declared = meta.get("class")
    if not isinstance(declared, str) or not declared:
        return "has no class:"
    return f"class {declared!r} is not one of {sorted(_PRODUCTS)}"


def _open_document(path: PathArg, *, fs: FileSystem | None = None) -> Concept:
    """Open the document file at *path* as the class its frontmatter names.

    A ``.md`` / ``.mdx`` / ``.html`` path is opened as written. A suffix-less
    path is the same file with ``.md`` appended, or with ``.html`` when only
    that exists. A directory is not a document. This function lives beside the
    classes. :class:`~molab.knowledge.concept.Concept` does not construct them.

    Raises:
        KnowledgeNotFoundError: The file is absent.
        ValueError: The frontmatter names no knowledge class (:func:`class_of`).
    """
    from .concept import read_text_or_none
    from .errors import KnowledgeNotFoundError
    from .frontmatter import split_frontmatter
    from .naming import KNOWLEDGE_FORMATS, as_knowledge_file, is_knowledge_file

    disk = fs if fs is not None else LocalFS()
    raw = str(path)
    if not is_knowledge_file(raw):
        found = next(
            (
                candidate
                for candidate in (as_knowledge_file(raw, fmt) for fmt in KNOWLEDGE_FORMATS)
                if disk.is_file(candidate)
            ),
            None,
        )
        if found is None:
            raise KnowledgeNotFoundError(str(path))
        raw = found
    text = read_text_or_none(raw, fs=disk)
    if text is None:
        raise KnowledgeNotFoundError(raw)
    meta, _body = split_frontmatter(text, path=raw)
    klass = class_of(meta)
    if klass is None:
        raise ValueError(f"frontmatter {class_problem(meta)}")
    return klass(raw, fs=disk)


HARVEST_TARGETS: MappingProxyType[str, type[_SourcedKnowledge]] = MappingProxyType(
    {
        "Finding": Finding,
        "Observation": Observation,
        "Report": Report,
    }
)
"""The classes a run can be harvested into."""


__all__ = [
    "Decision",
    "DecisionFields",
    "Finding",
    "Hypothesis",
    "HypothesisFields",
    "Literature",
    "LiteratureFields",
    "Milestone",
    "MilestoneCheck",
    "MilestoneFields",
    "MilestoneMeasurement",
    "Note",
    "NoteFields",
    "Observation",
    "Plan",
    "Report",
    "Roadmap",
    "RoadmapFields",
    "RoadmapStage",
    "Todo",
    "TodoFields",
    "TodoItem",
    "settled_status",
]
