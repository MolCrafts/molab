"""The OKF ``Note`` + ``ReferenceConcept`` concept types.

Notes and references are ``Concept`` subclasses — directories whose path is
their identity, mountable anywhere and usable with no workspace at all. A note's
body lives in ``index.md`` and its citations are markdown links (resolved by
``out_edges``); a reference's structured bib fields live in ``meta.yaml``
(``ReferenceMeta``). Each is its own Concept directory, reconstructed from its
``meta.yaml`` ``type`` via the shared concept-type registry.
"""

from __future__ import annotations

from pathlib import Path

from molexp.fs import LocalFileSystem
from molexp.knowledge.concept import Concept, concept_from_dir
from molexp.knowledge.concepts import Note, ReferenceConcept
from molexp.knowledge.reference_meta import ReferenceMeta


def _mount[C: Concept](cls: type[C], root: Path, name: str) -> C:
    """Materialize a Concept of *cls* named *name* directly under *root*."""
    concept = cls(root / name)
    concept.write_meta()
    return concept


class TestReferenceMeta:
    """The typed bib payload (``reference_meta``)."""

    def test_yaml_round_trip_preserves_bib_fields(self) -> None:
        m = ReferenceMeta(
            title="Deep Learning", authors=("LeCun", "Bengio"), year=2015, doi="10.1/x"
        )
        assert m.type == "reference"
        assert m.source == "manual"
        back = ReferenceMeta.from_yaml(m.to_yaml())
        assert isinstance(back, ReferenceMeta)
        assert back.title == "Deep Learning"
        assert back.authors == ("LeCun", "Bengio")
        assert back.year == 2015
        assert back.doi == "10.1/x"


class TestConceptRegistry:
    """``@concept_type`` registration + ``concept_from_dir`` reconstruction."""

    def test_mount_writes_the_registered_type_marker(self, tmp_path: Path) -> None:
        note = _mount(Note, tmp_path, "idea")
        ref = _mount(ReferenceConcept, tmp_path, "smith2024")
        assert note.read_meta()["type"] == "note.note"
        assert ref.read_meta()["type"] == "reference.reference"

    def test_concept_from_dir_rebuilds_typed_subclass(self, tmp_path: Path) -> None:
        note = _mount(Note, tmp_path, "idea")
        ref = _mount(ReferenceConcept, tmp_path, "smith2024")
        fs = LocalFileSystem()
        assert isinstance(concept_from_dir(note.path, fs=fs), Note)
        assert isinstance(concept_from_dir(ref.path, fs=fs), ReferenceConcept)

    def test_a_concept_needs_no_workspace(self, tmp_path: Path) -> None:
        # The whole point of the OKF library: a plain directory is a Concept.
        note = _mount(Note, tmp_path, "idea")
        assert note.path.is_dir()
        assert (note.path / "meta.yaml").is_file()
        assert not (tmp_path / "workspace.json").exists()


class TestNote:
    """``Note`` body + citation edges."""

    def test_body_and_cite_round_trip(self, tmp_path: Path) -> None:
        note = _mount(Note, tmp_path, "idea")
        ref = _mount(ReferenceConcept, tmp_path, "smith2024")

        note.set_body("# Idea\n\nbuilds on prior work\n")
        assert "builds on prior work" in note.body()

        note.cite(ref)
        assert "smith2024" in note.read_index()  # citation is a markdown link
        assert ref.path in {Path(p) for p in note.out_edges()}

    def test_cite_threads_role_into_typed_edge(self, tmp_path: Path) -> None:
        note = _mount(Note, tmp_path, "idea")
        ref = _mount(ReferenceConcept, tmp_path, "smith2024")

        note.cite(ref, role="derived_from")

        typed = note.typed_out_edges()
        assert len(typed) == 1
        assert typed[0].role == "derived_from"
        assert Path(typed[0].target) == ref.path

    def test_cite_accepts_a_bare_directory(self, tmp_path: Path) -> None:
        # A note cites something outside the OKF family (a workspace Run) by path.
        run_dir = tmp_path / "runs" / "run-abc123"
        run_dir.mkdir(parents=True)
        note = _mount(Note, tmp_path, "idea")
        note.cite(run_dir, role="records")
        assert note.typed_out_edges() == [(str(run_dir), "records")]

    def test_tags_and_status_round_trip(self, tmp_path: Path) -> None:
        note = _mount(Note, tmp_path, "idea")
        note.set_tags(["analysis", "rdf"])
        note.set_status("draft")
        assert note.tags() == ["analysis", "rdf"]
        assert note.status() == "draft"

    def test_set_tags_preserves_status(self, tmp_path: Path) -> None:
        note = _mount(Note, tmp_path, "idea")
        note.set_status("draft")
        note.set_tags(["x"])
        assert note.status() == "draft"

    def test_bare_marker_reads_back_with_additive_defaults(self, tmp_path: Path) -> None:
        # A legacy note whose meta.yaml is only {type, id} — no migration needed.
        note = _mount(Note, tmp_path, "idea")
        assert note.tags() == []
        assert note.status() == "active"


class TestReferenceConcept:
    """``ReferenceConcept`` typed meta + citation text."""

    def test_typed_meta_and_citation_round_trip(self, tmp_path: Path) -> None:
        ref = _mount(ReferenceConcept, tmp_path, "smith2024")

        ref.write_reference_meta(ReferenceMeta(title="T", doi="10.1/x", year=2024))
        got = ref.read_ref_meta()
        assert isinstance(got, ReferenceMeta)
        assert got.title == "T"
        assert got.doi == "10.1/x"
        assert got.year == 2024

        ref.set_citation("Smith et al. 2024")
        assert ref.citation() == "Smith et al. 2024"

    def test_written_meta_keeps_the_registered_dotted_type(self, tmp_path: Path) -> None:
        # ReferenceMeta.type defaults to the bare "reference" bib payload, but the
        # on-disk marker must stay the registered dotted type so reconstruction works.
        ref = _mount(ReferenceConcept, tmp_path, "smith2024")
        ref.write_reference_meta(ReferenceMeta(title="T", year=2024))
        assert ref.read_meta()["type"] == "reference.reference"
        assert isinstance(concept_from_dir(ref.path, fs=LocalFileSystem()), ReferenceConcept)

    def test_write_ref_meta_alias_is_gone(self, tmp_path: Path) -> None:
        # The short spelling was removed; only write_reference_meta remains.
        ref = _mount(ReferenceConcept, tmp_path, "smith2024")
        assert not hasattr(ref, "write_ref_meta")
