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

NOTE_KIND = "note.note"
REFERENCE_KIND = "reference.reference"
_LOG = logging.getLogger(__name__)


class Note(Concept):
    """None of the other classes: free text with no claim on the reasoning.

    ``knowledges/<name>.md`` with ``class: Note`` frontmatter.
    """

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
    """What does a published source say? Bib fields in the frontmatter."""

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
    """Every class but Note and Literature: a document that names its sources.

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

        from .naming import is_knowledge_file

        if (
            self.exists()
            and self.FILE_DOCUMENT
            and is_knowledge_file(PurePosixPath(self._path).name)
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

    The single planning document. Its work items live in its narrative. The
    claims to test are :class:`Hypothesis` documents.
    """


class Observation(_SourcedKnowledge):
    """What was observed or given, before any interpretation?

    A conclusion is a :class:`Finding`.
    """


class Hypothesis(_SourcedKnowledge):
    """What do we claim will turn out to be true?

    ``verdict`` in the frontmatter is the whole record: ``open``,
    ``supported``, ``refuted``, or ``unsettled`` (the evidence cannot tell).
    The evidence itself is a :class:`Finding` that links here with role
    ``supports`` or ``contradicts``.
    """

    def verdict(self) -> str:
        """``open``, ``supported``, ``refuted``, or ``unsettled``."""
        from .reasoning import parse_hypothesis

        return str(parse_hypothesis(self.frontmatter()).verdict)

    @classmethod
    def check_record(
        cls,
        record: Mapping[str, object] | None,
        *,
        existing: Mapping[str, object] | None,
    ) -> None:
        """Refuse a ``verdict`` outside the vocabulary, in the write or already stored."""
        from .reasoning import parse_hypothesis

        parse_hypothesis({**(existing or {}), **(record or {})})


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
    "Hypothesis": Hypothesis,
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
    """Open the document file at *path* as the class named in its record.

    A ``.md`` / ``.mdx`` / ``.html`` path is opened as written. A suffix-less
    path is the same file with ``.md`` appended, or with ``.html`` when only
    that exists. A directory is not a document. An unknown
    ``class`` opens as :class:`Note`. This function lives beside the classes.
    :class:`~molab.knowledge.concept.Concept` does not construct them.

    Raises:
        KnowledgeNotFoundError: The file is absent.
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

    meta, _body = split_frontmatter(text, path=path)
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
    "Hypothesis",
    "Literature",
    "Note",
    "Observation",
    "Plan",
    "Report",
]
