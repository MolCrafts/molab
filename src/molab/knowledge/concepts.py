"""The six knowledge classes: one markdown file each.

A :class:`Note` and a :class:`Literature` are ``knowledges/<name>.md`` files.
Frontmatter holds the structured fields; the narrative holds the links.
"""

from __future__ import annotations

import logging
from types import MappingProxyType
from typing import TYPE_CHECKING, ClassVar

from molab.fs import FileSystem, PathArg

from .concept import Concept
from .knowledge_item import SourceRef
from .reference_meta import ReferenceMeta

if TYPE_CHECKING:
    from molab._typing import JSONValue
    from molab.workspace.run import Run

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
    """Finding / Report / Plan / Observation — require ``sources`` at construct."""

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
            ValueError: If *sources* is empty.
            TypeError: If *name* is given and *path* is not a recognised host.
        """
        if not sources:
            raise ValueError(f"{self.__class__.__name__} requires at least one SourceRef")
        super().__init__(
            path,
            name,
            type=declared_type if declared_type is not None else type,
            fs=fs,
        )
        self._sources = list(sources)

    @classmethod
    def _from_disk(cls, path: str, *, fs: FileSystem | None = None) -> _SourcedKnowledge:
        """Open a file that already exists. Constructor sources stay empty.

        The ``sources`` property then reads ``derived_from`` and ``cites``
        edges only. A frontmatter ``sources:`` row stays opaque. This skips
        the writer rule that ``sources`` must be non-empty.
        """
        self = cls.__new__(cls)
        Concept.__init__(self, path, fs=fs)
        self._sources = []
        return self

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
    """The experiment or project plan book."""


class Observation(_SourcedKnowledge):
    """A recorded observation or standing choice."""


#: The one class-name → Knowledge subclass table on the knowledge side. The
#: keys are the names callers already spell in a config, a CLI flag or an agent
#: tool payload.
_PRODUCTS: dict[str, type[Concept]] = {
    "Note": Note,
    "Literature": Literature,
    "Report": Report,
    "Finding": Finding,
    "Plan": Plan,
    "Observation": Observation,
}


HARVEST_TARGETS: MappingProxyType[str, type[_SourcedKnowledge]] = MappingProxyType(
    {
        "Finding": Finding,
        "Observation": Observation,
        "Report": Report,
    }
)
"""Finding, Observation and Report — the classes a run can be harvested into."""


def parse_class(name: str) -> type[Concept]:
    """Map a class name onto a Knowledge subclass (including condemned aliases).

    The single class-name entry point on the knowledge side: a config file, a
    CLI flag or an agent-tool payload spells a Knowledge class by name, and this
    turns that name into the class object it denotes.

    Args:
        name: A class name — ``"Note"`` / ``"Literature"`` / ``"Report"`` /
            ``"Finding"`` / ``"Plan"`` / ``"Observation"``.

    Returns:
        The Knowledge subclass *name* denotes.

    Raises:
        ValueError: If *name* matches none of the six classes; the message lists
            the candidates.
    """
    if name in _PRODUCTS:
        return _PRODUCTS[name]
    raise ValueError(
        f"unknown knowledge class {name!r}; expected one of: {', '.join(sorted(_PRODUCTS))}"
    )


__all__ = [
    "NOTE_KIND",
    "REFERENCE_KIND",
    "Finding",
    "Literature",
    "Note",
    "Observation",
    "Plan",
    "Report",
    "parse_class",
]
