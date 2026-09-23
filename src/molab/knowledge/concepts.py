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
        *,
        sources: list[SourceRef] | None = None,
        declared_type: str | None = None,
        fs: FileSystem | None = None,
        type: str | None = None,
    ) -> None:
        if not sources:
            raise ValueError(f"{self.__class__.__name__} requires at least one SourceRef")
        super().__init__(path, type=declared_type if declared_type is not None else type, fs=fs)
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
]
