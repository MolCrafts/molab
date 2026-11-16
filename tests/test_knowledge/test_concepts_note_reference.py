"""The OKF ``Note`` + ``Literature`` concept types.

Notes and references are ``Concept`` subclasses — directories whose path is
their identity, mountable anywhere and usable with no workspace at all. A note's
body lives in ``index.md`` and its citations are markdown links (resolved by
``out_edges``); a reference's structured bib fields live in ``meta.json``
(``LiteratureFields``). Each is its own Concept directory, reconstructed from its
``meta.json`` ``type`` via the shared concept-type registry.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from molab.knowledge.concept import Concept, append_link
from molab.knowledge.concepts import Literature, LiteratureFields, Note


def _mount[C: Concept](cls: type[C], root: Path, name: str) -> C:
    """Materialize a Concept of *cls* named *name* directly under *root*.

    A Knowledge is one file: writing it stamps the ``class`` frontmatter marker
    ``_open_document`` reads the subclass from. The base class does not.
    """
    concept = cls(root / name)
    concept.write()
    return concept


class TestLiteratureFields:
    """The bibliographic fields of a Literature."""

    def test_an_unknown_key_is_refused(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            LiteratureFields.model_validate({"title": "T", "tags": ["x"]})


class TestConceptRegistry:
    """Frontmatter ``class`` is how a file reopens as its subclass."""

    def test_mount_writes_the_registered_type_marker(self, tmp_path: Path) -> None:
        note = _mount(Note, tmp_path, "idea")
        ref = _mount(Literature, tmp_path, "smith2024")
        assert note.frontmatter()["class"] == "Note"
        assert ref.frontmatter()["class"] == "Literature"

    def test_concept_from_dir_rebuilds_typed_subclass(self, tmp_path: Path) -> None:
        note = _mount(Note, tmp_path, "idea")
        ref = _mount(Literature, tmp_path, "smith2024")
        from molab.knowledge.concepts import _open_document

        assert isinstance(_open_document(note.path), Note)
        assert isinstance(_open_document(ref.path), Literature)

    def test_a_file_without_a_class_is_not_a_document(self, tmp_path: Path) -> None:
        from molab.fs import LocalFS
        from molab.knowledge import Knowledge
        from molab.knowledge.concepts import _open_document
        from molab.knowledge.index_section import section_rows

        container = tmp_path / "knowledges"
        container.mkdir()
        (container / "bare.md").write_text("---\nname: Bare\n---\n# Bare glass\n")
        _mount(Note, container, "kept").write("# Kept glass\n")

        with pytest.raises(ValueError, match="no class"):
            _open_document(container / "bare.md")
        tree = Knowledge(container)
        assert [Path(doc.path).name for doc in tree.walk()] == ["kept.md"]
        assert [hit.entry.path for hit in tree.search("glass").hits] == ["kept.md"]
        rows = section_rows(str(tmp_path), fs=LocalFS())
        assert [row["path"] for row in rows] == ["knowledges/kept.md"]

    def test_a_concept_needs_no_workspace(self, tmp_path: Path) -> None:
        # The whole point of the OKF library: a plain file is a Concept.
        note = _mount(Note, tmp_path, "idea")
        assert note.path.is_file()
        assert note.frontmatter()["class"] == "Note"
        assert not (tmp_path / "index.md").exists()


class TestNote:
    """``Note`` body + citation edges."""

    def test_ref_threads_role_into_typed_edge(self, tmp_path: Path) -> None:
        note = _mount(Note, tmp_path, "idea")
        ref = _mount(Literature, tmp_path, "smith2024")

        note.ref(ref, role="derived_from")

        typed = note.links()
        assert len(typed) == 1
        assert typed[0].role == "derived_from"
        assert Path(typed[0].target) == ref.path

    def test_a_link_to_a_bare_directory_keeps_its_path(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "runs" / "run-abc123"
        run_dir.mkdir(parents=True)
        note = _mount(Note, tmp_path, "idea")
        append_link(note, run_dir, role="references")
        assert note.links() == [(str(run_dir), "references")]

    def test_tags_and_status_round_trip(self, tmp_path: Path) -> None:
        note = _mount(Note, tmp_path, "idea")
        note.write(tags=["analysis", "rdf"])
        note.write(fields={"status": "retired"})
        assert note.tags() == ["analysis", "rdf"]
        assert note.status() == "retired"

    def test_set_tags_preserves_status(self, tmp_path: Path) -> None:
        note = _mount(Note, tmp_path, "idea")
        note.write(fields={"status": "retired"})
        note.write(tags=["x"])
        assert note.status() == "retired"

    def test_bare_marker_reads_back_with_additive_defaults(self, tmp_path: Path) -> None:
        # A legacy note whose meta.json is only {type, id} — no migration needed.
        note = _mount(Note, tmp_path, "idea")
        assert note.tags() == []
        assert note.status() == "proposed"

    def test_a_status_outside_the_lifecycle_is_refused(self, tmp_path: Path) -> None:
        note = _mount(Note, tmp_path, "idea")
        with pytest.raises(ValueError, match="status"):
            note.write(fields={"status": "draft"})
        assert note.status() == "proposed"


class TestLiterature:
    """``Literature`` typed meta + citation text."""

    def test_write_ref_meta_alias_is_gone(self, tmp_path: Path) -> None:
        # The short spelling was removed; only write remains.
        ref = _mount(Literature, tmp_path, "smith2024")
        assert not hasattr(ref, "write_ref_meta")
