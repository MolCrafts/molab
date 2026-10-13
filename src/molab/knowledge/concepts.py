"""The six knowledge classes: one markdown file each.

A :class:`Note` and a :class:`Literature` are ``knowledges/<name>.md`` files.
Frontmatter holds the structured fields; the narrative holds the links.
"""

from __future__ import annotations

import logging
from types import MappingProxyType
from typing import TYPE_CHECKING, ClassVar

from molab.fs import FileSystem, LocalFileSystem, PathArg

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


def _product(name: str) -> type[Concept]:
    """The document class *name* spells. Does not construct it.

    Raises:
        ValueError: *name* is not one of the six classes. The message lists them.
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
    ``class`` opens as :class:`Note`. This function lives beside the six
    classes. :class:`~molab.knowledge.concept.Concept` does not construct them.

    Raises:
        KnowledgeNotFoundError: The file is absent.
    """
    from .concept import read_text_or_none
    from .errors import KnowledgeNotFoundError
    from .frontmatter import split_frontmatter
    from .naming import as_knowledge_file, is_knowledge_file

    disk = fs if fs is not None else LocalFileSystem()
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
    class_name = str(meta.get("class") or "Note")
    klass = _PRODUCTS.get(class_name, Note)
    return klass(raw, fs=disk)


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
    disk = fs if fs is not None else LocalFileSystem()
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
    "Note",
    "Observation",
    "Plan",
    "Report",
]
