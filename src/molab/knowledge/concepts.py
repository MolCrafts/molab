"""Knowledge classes: one markdown file each.

A :class:`Note` and a :class:`Literature` are ``knowledges/<name>.md`` files.
Frontmatter holds the structured fields; the narrative holds the links.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from types import MappingProxyType
from typing import TYPE_CHECKING, ClassVar

from molab.fs import FileSystem, LocalFS, PathArg

from .concept import Concept
from .knowledge_item import SourceRef
from .reference_meta import ReferenceMeta

if TYPE_CHECKING:
    from molab._typing import JSONValue
    from molab.workspace.run import Run

    from .planning import MilestoneRecord

NOTE_KIND = "note.note"
REFERENCE_KIND = "reference.reference"
_LOG = logging.getLogger(__name__)


class Note(Concept):
    """A note — ``knowledges/<name>.md`` with ``class: Note`` frontmatter."""

    FILE_DOCUMENT: ClassVar[bool] = True
    DEFAULT_TYPE: ClassVar[str] = NOTE_KIND

    def status(self) -> str:
        """This note's lifecycle status (``"active"`` by default)."""
        raw = self.frontmatter().get("status")
        if isinstance(raw, str) and raw:
            return raw
        return "active"

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
    """A literature record — bib fields in markdown frontmatter."""

    FILE_DOCUMENT: ClassVar[bool] = True
    DEFAULT_TYPE: ClassVar[str] = REFERENCE_KIND

    @property
    def record(self) -> ReferenceMeta:
        """This literature item's bibliographic record, from its frontmatter."""
        payload = {
            k: v
            for k, v in self.frontmatter().items()
            if k not in {"class", "type", "kind", "id", "sources", "tags", "status"}
        }
        if "type" not in payload:
            payload = {**payload, "type": "reference"}
        authors = payload.get("authors")
        if isinstance(authors, list):
            payload["authors"] = tuple(str(a) for a in authors)
        return ReferenceMeta.model_validate(payload)

    def citation(self) -> str:
        """The human-readable citation text."""
        return self.read()


class _SourcedKnowledge(Concept):
    """Finding / Report / Plan / Observation.

    ``sources`` is required when the document is created by name. An existing
    file reopens with ``Finding(path)`` and reads its sources from edges.
    """

    FILE_DOCUMENT: ClassVar[bool] = True
    REQUIRES_SOURCES: ClassVar[bool] = True

    def __init__(
        self,
        path: PathArg,
        name: str | None = None,
        *,
        sources: list[SourceRef] | None = None,
        declared_type: str | None = None,
        fs: FileSystem | None = None,
        type: str | None = None,
    ) -> None:
        """Bind this document, keeping ``sources`` mandatory.

        Args:
            path: The document's path, or — with *name* given — its host (a
                ``str`` / :class:`os.PathLike` directory, or a workspace
                ``Folder``).
            name: A human document name; the host then derives the landed path.
            sources: The :class:`~molab.knowledge.knowledge_item.SourceRef` list
                this document harvests from; at least one is required.
            declared_type: Legacy spelling of *type*.
            fs: The filesystem to read and write through; defaults to the host's
                own disk in the *name* form.
            type: Declared type; defaults to :attr:`DEFAULT_TYPE`.

        Raises:
            ValueError: If *sources* is empty and this is not a file already on
                disk. ``Finding(path)`` reopens that file; ``Finding(host, name)``
                still requires sources.
            TypeError: If *name* is given and *path* is not a recognised host.
        """
        if not sources:
            if name is not None:
                raise ValueError(f"{self.__class__.__name__} requires at least one SourceRef")
            super().__init__(
                path,
                None,
                type=declared_type if declared_type is not None else type,
                fs=fs,
            )
            if not self.exists():
                raise ValueError(f"{self.__class__.__name__} requires at least one SourceRef")
            self._sources = []
            return
        super().__init__(
            path,
            name,
            type=declared_type if declared_type is not None else type,
            fs=fs,
        )
        self._sources = list(sources)

    @property
    def sources(self) -> list[SourceRef]:
        """Edges with role ``derived_from`` or ``cites``.

        A document that is not on disk yet returns the constructor list.
        Frontmatter ``sources:`` rows are not a second record.
        """
        from pathlib import PurePosixPath

        if (
            self.exists()
            and self.FILE_DOCUMENT
            and PurePosixPath(self._path).suffix.lower() in {".md", ".mdx"}
        ):
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
    """A written-up analysis (including failed-run reports)."""


class Finding(_SourcedKnowledge):
    """A harvested scientific outcome."""


class Plan(_SourcedKnowledge):
    """Campaign overview: the question, the scope, and the constraints.

    A Plan does not list stages, todos, or milestone criteria. Those are
    :class:`Roadmap`, :class:`Todo`, and :class:`Milestone` documents that
    cite this Plan.
    """

    PLANNING_ROLE: ClassVar[str] = "overview"
    FOREIGN_FIELDS: ClassVar[frozenset[str]] = frozenset({"stages", "items", "criterion", "status"})

    def planning_role(self) -> str:
        """This document is the overview."""
        return self.PLANNING_ROLE

    def planning_fields(self) -> dict[str, object]:
        """A Plan's record is its narrative. It has no planning fields."""
        return {}


class Roadmap(_SourcedKnowledge):
    """Ordered stages of a campaign, and which experiment each stage is.

    ``stages`` in the frontmatter is the whole record. A Roadmap does not
    store todos or completion criteria.
    """

    PLANNING_ROLE: ClassVar[str] = "roadmap"
    FOREIGN_FIELDS: ClassVar[frozenset[str]] = frozenset({"items", "criterion", "status"})

    def planning_role(self) -> str:
        """This document is the roadmap."""
        return self.PLANNING_ROLE

    def stages(self) -> tuple[object, ...]:
        """The stages in frontmatter order."""
        from .planning import parse_stages

        return parse_stages(self.frontmatter().get("stages", []))

    def planning_fields(self) -> dict[str, object]:
        """The stage list, and nothing else."""
        return {"stages": self.stages()}


class Todo(_SourcedKnowledge):
    """Work items and their status. Not the stage order, and not a criterion."""

    PLANNING_ROLE: ClassVar[str] = "todo"
    FOREIGN_FIELDS: ClassVar[frozenset[str]] = frozenset({"stages", "criterion"})

    def planning_role(self) -> str:
        """This document is the todo list."""
        return self.PLANNING_ROLE

    def items(self) -> tuple[object, ...]:
        """The work items in frontmatter order."""
        from .planning import parse_items

        return parse_items(self.frontmatter().get("items", []))

    def planning_fields(self) -> dict[str, object]:
        """The item list, and nothing else."""
        return {"items": self.items()}


class Milestone(_SourcedKnowledge):
    """One checkpoint: the roadmap stage it closes, and the criterion.

    A Milestone does not list the work that meets the criterion.
    """

    PLANNING_ROLE: ClassVar[str] = "milestone"
    FOREIGN_FIELDS: ClassVar[frozenset[str]] = frozenset({"stages", "items"})

    def planning_role(self) -> str:
        """This document is one milestone."""
        return self.PLANNING_ROLE

    def stage(self) -> str:
        """The roadmap stage id this checkpoint closes."""
        return str(self._milestone().stage)

    def criterion(self) -> str:
        """What must be true for this checkpoint to be met."""
        return str(self._milestone().criterion)

    def status(self) -> str:
        """``open``, ``met``, or ``missed``."""
        return str(self._milestone().status)

    def planning_fields(self) -> dict[str, object]:
        """Stage, criterion, and status. Not the work items."""
        record = self._milestone()
        return {"stage": record.stage, "criterion": record.criterion, "status": record.status}

    def _milestone(self) -> MilestoneRecord:
        from .planning import parse_milestone

        return parse_milestone(self.frontmatter())


class Observation(_SourcedKnowledge):
    """A recorded observation or standing choice."""


class Delegation(_SourcedKnowledge):
    """One bounded, resumable piece of supervised work.

    The frontmatter record (:class:`~molab.knowledge.delegation.DelegationRecord`)
    holds the scope, goal, authorized actions, budget and spend, acceptance and
    stop conditions, open waits and worker attempts. The source is the scope
    the delegation is bound to. A supervising agent writes it; molab validates
    and stores it, so the work survives the agent that did it.
    """

    FOREIGN_FIELDS: ClassVar[frozenset[str]] = frozenset({"stages", "items", "criterion"})

    def record(self) -> object:
        """The validated :class:`~molab.knowledge.delegation.DelegationRecord`."""
        from .delegation import parse_delegation

        return parse_delegation(self.frontmatter())

    @classmethod
    def check_record(
        cls,
        record: Mapping[str, object] | None,
        *,
        existing: Mapping[str, object] | None,
    ) -> None:
        """Validate a write's record merged over the stored one."""
        from .delegation import check_delegation_record

        crossed = sorted(set(record or {}) & cls.FOREIGN_FIELDS)
        if crossed:
            raise ValueError(f"Delegation does not store {crossed}")
        check_delegation_record(record, existing=existing)


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
    "Delegation": Delegation,
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


def _open_document(path: PathArg, *, fs: FileSystem | None = None) -> Concept:
    """Open the markdown file at *path* as the class named in its frontmatter.

    A ``.md`` / ``.mdx`` path is opened as written. A suffix-less path is the
    same file with ``.md`` appended. A directory is not a document. An unknown
    ``class`` opens as :class:`Note`. This function lives beside the classes.
    :class:`~molab.knowledge.concept.Concept` does not construct them.

    Raises:
        KnowledgeNotFoundError: The file is absent.
    """
    from .concept import read_text_or_none
    from .errors import KnowledgeNotFoundError
    from .frontmatter import split_frontmatter
    from .naming import as_knowledge_file, is_knowledge_file

    disk = fs if fs is not None else LocalFS()
    raw = str(path)
    if not is_knowledge_file(raw):
        md = as_knowledge_file(raw)
        if not disk.is_file(md):
            raise KnowledgeNotFoundError(str(path))
        raw = md
    text = read_text_or_none(raw, fs=disk)
    if text is None:
        raise KnowledgeNotFoundError(raw)
    meta, _body = split_frontmatter(text)
    raw_class = meta.get("class")
    class_name = raw_class if isinstance(raw_class, str) and raw_class else "Note"
    if class_name not in _PRODUCTS:
        raise ValueError(
            f"frontmatter class {class_name!r} is not one of {', '.join(sorted(_PRODUCTS))}"
        )
    return _PRODUCTS[class_name](raw, fs=disk)


def _write_document(path: PathArg, text: str, *, fs: FileSystem | None = None) -> Concept:
    """Persist *text* verbatim. The class comes from its frontmatter ``class``.

    A sourced class is bound without constructor sources, so a legacy
    ``sources:`` row is never passed into a constructor that requires them.
    The file need not exist yet. :class:`~molab.knowledge.concept.Concept`
    does not choose or construct the subclass.

    Raises:
        ValueError: Frontmatter has no ``class``, or the name is unknown.
    """
    from .frontmatter import split_frontmatter

    meta, _body = split_frontmatter(text)
    class_name = meta.get("class")
    if not isinstance(class_name, str) or class_name == "":
        raise ValueError("knowledge document requires a frontmatter class")
    klass = _product(class_name)
    disk = fs if fs is not None else LocalFS()
    if issubclass(klass, _SourcedKnowledge):
        handle = klass.__new__(klass)
        Concept.__init__(handle, str(path), fs=disk)
        handle._sources = []
    else:
        handle = klass(path, fs=disk)
    handle.write(text, replace=True)
    return handle


HARVEST_TARGETS: MappingProxyType[str, type[_SourcedKnowledge]] = MappingProxyType(
    {
        "Finding": Finding,
        "Observation": Observation,
        "Report": Report,
    }
)
"""Finding, Observation and Report — the classes a run can be harvested into."""


__all__ = [
    "NOTE_KIND",
    "REFERENCE_KIND",
    "Finding",
    "Literature",
    "Milestone",
    "Note",
    "Observation",
    "Plan",
    "Report",
    "Roadmap",
    "Todo",
]
