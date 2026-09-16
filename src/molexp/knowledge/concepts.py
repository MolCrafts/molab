"""OKF ``Note`` + ``Reference`` Concepts.

In OKF a Concept is a **directory** whose path is its identity:

- A :class:`Note` is a Concept whose body is its ``index.md`` and whose
  citations are markdown links (resolved by :meth:`Concept.out_edges`).
- A :class:`ReferenceConcept` is a Concept whose structured bib record lives in
  ``meta.yaml`` (:class:`ReferenceMeta`) and whose human citation text lives in
  ``index.md``. PDFs are *pointed at* via ``ReferenceMeta.pdf_path`` /
  ``pdf_asset_id`` — never copied.

Both register via ``@concept_type(...)``, so
:func:`~molexp.knowledge.concept.concept_from_dir` rebuilds the right subclass
from a directory's ``meta.yaml`` ``type``.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar, cast

from molexp.fs import PathArg

from .concept import META_YAML_FILENAME, Concept, append_link, read_text_or_none
from .edges import DEFAULT_EDGE_ROLE, EdgeRole
from .note_meta import NOTE_TYPE, NoteMeta
from .reference_meta import ReferenceMeta
from .types import concept_type

NOTE_KIND = NOTE_TYPE
REFERENCE_KIND = "reference.reference"


@concept_type(NOTE_KIND)
class Note(Concept):
    """A note Concept — narrative in ``index.md``, citations as markdown links.

    Mountable anywhere (convention, not enforcement): a note is just a directory,
    so it sits equally well at a wiki root or beside a workspace experiment.
    :meth:`cite` records a reference as a markdown link so
    :meth:`Concept.out_edges` resolves it back.
    """

    DEFAULT_TYPE: ClassVar[str] = NOTE_KIND

    def cite(
        self,
        ref: Concept | PathArg,
        *,
        text: str | None = None,
        role: EdgeRole = DEFAULT_EDGE_ROLE,
    ) -> None:
        """Cite *ref* — append a typed markdown link resolvable via ``out_edges``.

        A thin delegator over the single
        :func:`~molexp.knowledge.concept.append_link` writer; *role* is recovered
        by :meth:`Concept.typed_out_edges`.

        Args:
            ref: The Concept — or bare directory path — being cited.
            text: Optional link label; defaults to *ref*'s directory name.
            role: The declared :class:`~molexp.knowledge.edges.EdgeRole`.
        """
        append_link(self, ref, text=text, role=role)

    # -- typed meta.yaml (tags / status) ----------------------------------

    def read_note_meta(self) -> NoteMeta:
        """Load this note's typed document ``meta.yaml`` as a :class:`NoteMeta`.

        A legacy bare marker (only ``{type, id}``) — or an absent ``meta.yaml``
        — reads back with the additive defaults (``tags == []`` /
        ``status == "active"``), so no migration is needed.
        """
        text = read_text_or_none(self._fs.join(str(self.path), META_YAML_FILENAME), fs=self._fs)
        if text is None:
            return NoteMeta(type=self._type, id=self.name)
        return cast("NoteMeta", NoteMeta.from_yaml(text))

    def write_note_meta(self, meta: NoteMeta) -> None:
        """Atomically write this note's typed document ``meta.yaml``.

        ``type`` / ``id`` are stamped by :meth:`Concept.write_meta`, so identity
        stays path-derived and ``concept_from_dir`` rebuilds a :class:`Note`.
        Any other keys on *meta* are preserved verbatim (``ConceptMeta`` is
        ``extra="allow"``).
        """
        self.write_meta(meta)

    def tags(self) -> list[str]:
        """This note's categorical tags (``[]`` when untagged)."""
        return list(self.read_note_meta().tags)

    def status(self) -> str:
        """This note's lifecycle status (``"active"`` by default)."""
        return self.read_note_meta().status

    def set_tags(self, tags: Iterable[str]) -> None:
        """Set this note's tags, preserving ``status`` and any other meta keys."""
        current = self.read_note_meta()
        self.write_note_meta(current.model_copy(update={"tags": list(tags)}))

    def set_status(self, status: str) -> None:
        """Set this note's status, preserving ``tags`` and any other meta keys."""
        current = self.read_note_meta()
        self.write_note_meta(current.model_copy(update={"status": status}))


@concept_type(REFERENCE_KIND)
class ReferenceConcept(Concept):
    """A reference Concept — a bibliographic record (one Concept per work).

    Structured bib fields live in ``meta.yaml`` (:class:`ReferenceMeta`); the
    human-readable citation text lives in ``index.md``. PDFs are pointed at via
    ``ReferenceMeta.pdf_path`` / ``pdf_asset_id`` — never copied.

    Named ``ReferenceConcept`` (not ``Reference``) because the name is load-bearing
    at a great many ``isinstance`` sites across the server, CLI and harness.
    """

    DEFAULT_TYPE: ClassVar[str] = REFERENCE_KIND

    def read_ref_meta(self) -> ReferenceMeta:
        """Load this reference's typed bib ``meta.yaml`` as a :class:`ReferenceMeta`."""
        fpath = self._fs.join(str(self.path), META_YAML_FILENAME)
        return cast("ReferenceMeta", ReferenceMeta.from_yaml(self._fs.read_text(fpath)))

    def write_reference_meta(self, meta: ReferenceMeta) -> None:
        """Atomically write this reference's typed bib ``meta.yaml``.

        The on-disk ``type`` is stamped to the registered concept type
        (``reference.reference``) so :func:`concept_from_dir` rebuilds a
        :class:`ReferenceConcept` — note ``ReferenceMeta.type`` itself defaults
        to the bare ``"reference"`` for the OKF bib payload.
        """
        self.write_meta(meta)

    def citation(self) -> str:
        """The human-readable citation text (its ``index.md``)."""
        return self.read_index()

    def set_citation(self, text: str) -> None:
        """Set the human-readable citation text (its ``index.md``)."""
        self.write_index(text)


__all__ = ["NOTE_KIND", "REFERENCE_KIND", "Note", "ReferenceConcept"]
