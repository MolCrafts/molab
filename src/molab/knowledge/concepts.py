"""OKF ``Note`` + ``Reference`` Concepts.

In OKF a Concept is a **directory** whose path is its identity:

- A :class:`Note` is a Concept whose body is its ``index.md`` and whose
  citations are markdown links (resolved by :meth:`Concept.out_edges`).
- A :class:`Literature` is a Knowledge directory whose structured bib record lives in
  ``meta.json`` (:class:`ReferenceMeta`) and whose human citation text lives in
  ``index.md``. PDFs are *pointed at* via ``ReferenceMeta.pdf_path`` /
  ``pdf_asset_id`` — never copied.

Both register via ``@concept_type(...)``, so
:func:`~molab.knowledge.concept.concept_from_dir` rebuilds the right subclass
from a directory's ``meta.json`` ``type``.
"""

from __future__ import annotations

from typing import ClassVar, cast

from molab.fs import FileSystem, PathArg

from .concept import (
    META_JSON_FILENAME,
    Concept,
    read_text_or_none,
    register_marker_filenames,
)
from .knowledge_item import SourceRef
from .naming import KNOWLEDGE_HEAD_FILES
from .note_meta import NOTE_TYPE, NoteMeta
from .reference_meta import ReferenceMeta
from .types import concept_type

NOTE_KIND = NOTE_TYPE
REFERENCE_KIND = "reference.reference"


@concept_type(NOTE_KIND)
class Note(Concept):
    """A note — ``knowledges/<name>.md`` with ``class: Note`` frontmatter."""

    FILE_DOCUMENT: ClassVar[bool] = True
    DEFAULT_TYPE: ClassVar[str] = NOTE_KIND

    # -- typed meta.json (tags / status) ----------------------------------

    def read_note_meta(self) -> NoteMeta:
        """Load this note's typed document ``meta.json`` as a :class:`NoteMeta`.

        A legacy bare marker (only ``{type, id}``) — or an absent ``meta.json``
        — reads back with the additive defaults (``tags == []`` /
        ``status == "active"``), so no migration is needed.
        """
        text = read_text_or_none(self._fs.join(str(self.path), META_JSON_FILENAME), fs=self._fs)
        if text is None:
            return NoteMeta(type=self._type, id=self.name)
        return cast("NoteMeta", NoteMeta.from_json(text))

    def write_note_meta(self, meta: NoteMeta) -> None:
        """Atomically write this note's typed document ``meta.json``.

        ``type`` / ``id`` are stamped by :meth:`Concept.write_meta`, so identity
        stays path-derived and ``concept_from_dir`` rebuilds a :class:`Note`.
        Any other keys on *meta* are preserved verbatim (``ConceptMeta`` is
        ``extra="allow"``).
        """
        self.write_meta(meta)

    def tags(self) -> list[str]:
        """This note's categorical tags (``[]`` when untagged)."""
        raw = self.frontmatter().get("tags")
        if isinstance(raw, list):
            return [str(item) for item in raw]
        return list(self.read_note_meta().tags)

    def status(self) -> str:
        """This note's lifecycle status (``"active"`` by default)."""
        raw = self.frontmatter().get("status")
        if isinstance(raw, str) and raw:
            return raw
        return self.read_note_meta().status


@concept_type(REFERENCE_KIND)
class Literature(Concept):
    """A literature record — bib fields in markdown frontmatter."""

    FILE_DOCUMENT: ClassVar[bool] = True
    DEFAULT_TYPE: ClassVar[str] = REFERENCE_KIND

    @property
    def record(self) -> ReferenceMeta:
        """This literature item's bibliographic record."""
        return self.read_reference_meta()

    def read_reference_meta(self) -> ReferenceMeta:
        """Load bibliographic fields from this file's frontmatter."""
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
        """The human-readable citation text (its ``index.md``)."""
        return self.read()


class _SourcedKnowledge(Concept):
    """Finding / Report / Plan / Observation — require ``sources`` at construct."""

    FILE_DOCUMENT: ClassVar[bool] = True

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
                ``str`` / :class:`os.PathLike` directory, or a ``Folder``-family
                object carrying ``_disk()``).
            name: A human document name; the host then derives the landed path.
            sources: The :class:`~molab.knowledge.knowledge_item.SourceRef` list
                this document harvests from; at least one is required.
            declared_type: Legacy spelling of *type*.
            fs: The filesystem to read and write through; defaults to the host's
                own disk in the *name* form.
            type: The ``type`` :meth:`~molab.knowledge.concept.Concept.write_meta`
                stamps.

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

    @property
    def sources(self) -> list[SourceRef]:
        """The SourceRef list persisted in the class-named head."""
        return list(self._sources)


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


def parse_knowledge_class(name: str) -> type[Concept]:
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


register_marker_filenames(*sorted(KNOWLEDGE_HEAD_FILES))

__all__ = [
    "NOTE_KIND",
    "REFERENCE_KIND",
    "Finding",
    "Literature",
    "Note",
    "Observation",
    "Plan",
    "Report",
    "parse_knowledge_class",
]
