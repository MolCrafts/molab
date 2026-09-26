"""The OKF ``Note`` + ``Literature`` concept types.

Notes and references are ``Concept`` subclasses — directories whose path is
their identity, mountable anywhere and usable with no workspace at all. A note's
body lives in ``index.md`` and its citations are markdown links (resolved by
``out_edges``); a reference's structured bib fields live in ``meta.json``
(``ReferenceMeta``). Each is its own Concept directory, reconstructed from its
``meta.json`` ``type`` via the shared concept-type registry.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from molab.fs import LocalFileSystem
from molab.knowledge.concept import Concept, concept_from_dir
from molab.knowledge.concepts import Literature, Note
from molab.knowledge.reference_meta import ReferenceMeta


def _mount[C: Concept](cls: type[C], root: Path, name: str) -> C:
    """Materialize a Concept of *cls* named *name* directly under *root*.

    A Knowledge is one file: writing it stamps the ``class`` frontmatter marker
    ``Concept.open`` reconstructs the subclass from.
    """
    concept = cls(root / name)
    concept.write()
    return concept


class TestReferenceMeta:
    """The typed bib payload (``reference_meta``)."""

    def test_json_round_trip_preserves_bib_fields(self) -> None:
        m = ReferenceMeta(
            title="Deep Learning", authors=("LeCun", "Bengio"), year=2015, doi="10.1/x"
        )
        assert m.type == "reference"
        assert m.source == "manual"
        back = ReferenceMeta.from_json(m.to_json())
        assert isinstance(back, ReferenceMeta)
        assert back.title == "Deep Learning"
        assert back.authors == ("LeCun", "Bengio")
        assert back.year == 2015
        assert back.doi == "10.1/x"


class TestConceptRegistry:
    """``@concept_type`` registration + ``concept_from_dir`` reconstruction."""

    def test_mount_writes_the_registered_type_marker(self, tmp_path: Path) -> None:
        note = _mount(Note, tmp_path, "idea")
        ref = _mount(Literature, tmp_path, "smith2024")
        assert note.frontmatter()["class"] == "Note"
        assert ref.frontmatter()["class"] == "Literature"

    def test_concept_from_dir_rebuilds_typed_subclass(self, tmp_path: Path) -> None:
        note = _mount(Note, tmp_path, "idea")
        ref = _mount(Literature, tmp_path, "smith2024")
        fs = LocalFileSystem()
        assert isinstance(concept_from_dir(note.path, fs=fs), Note)
        assert isinstance(concept_from_dir(ref.path, fs=fs), Literature)

    def test_a_concept_needs_no_workspace(self, tmp_path: Path) -> None:
        # The whole point of the OKF library: a plain file is a Concept.
        note = _mount(Note, tmp_path, "idea")
        assert note.path.is_file()
        assert note.frontmatter()["class"] == "Note"
        assert not (tmp_path / "workspace.json").exists()


class TestNote:
    """``Note`` body + citation edges."""

    def test_cite_threads_role_into_typed_edge(self, tmp_path: Path) -> None:
        note = _mount(Note, tmp_path, "idea")
        ref = _mount(Literature, tmp_path, "smith2024")

        note.cite(ref, role="derived_from")

        typed = note.links()
        assert len(typed) == 1
        assert typed[0].role == "derived_from"
        assert Path(typed[0].target) == ref.path

    def test_cite_delegates_to_ref_for_a_knowledge_target(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A Knowledge target takes the canonical verb; a bare directory does not.
        note = _mount(Note, tmp_path, "idea")
        ref = _mount(Literature, tmp_path, "smith2024")
        delegations: list[tuple[object, dict[str, object]]] = []

        def spy(_self: Concept, target: object, **kwargs: object) -> None:
            delegations.append((target, kwargs))

        monkeypatch.setattr(Note, "ref", spy)

        note.cite(ref, role="derived_from")
        note.cite(tmp_path / "runs" / "run-abc123", role="records")

        assert delegations == [(ref, {"text": None, "role": "derived_from"})]

    def test_cite_accepts_a_bare_directory(self, tmp_path: Path) -> None:
        # A note cites something outside the OKF family (a workspace Run) by path.
        run_dir = tmp_path / "runs" / "run-abc123"
        run_dir.mkdir(parents=True)
        note = _mount(Note, tmp_path, "idea")
        note.cite(run_dir, role="records")
        assert note.links() == [(str(run_dir), "records")]

    def test_tags_and_status_round_trip(self, tmp_path: Path) -> None:
        note = _mount(Note, tmp_path, "idea")
        note.write(tags=["analysis", "rdf"])
        note.write(status="draft")
        assert note.tags() == ["analysis", "rdf"]
        assert note.status() == "draft"

    def test_set_tags_preserves_status(self, tmp_path: Path) -> None:
        note = _mount(Note, tmp_path, "idea")
        note.write(status="draft")
        note.write(tags=["x"])
        assert note.status() == "draft"

    def test_bare_marker_reads_back_with_additive_defaults(self, tmp_path: Path) -> None:
        # A legacy note whose meta.json is only {type, id} — no migration needed.
        note = _mount(Note, tmp_path, "idea")
        assert note.tags() == []
        assert note.status() == "active"


class TestLiterature:
    """``Literature`` typed meta + citation text."""

    def test_write_ref_meta_alias_is_gone(self, tmp_path: Path) -> None:
        # The short spelling was removed; only write remains.
        ref = _mount(Literature, tmp_path, "smith2024")
        assert not hasattr(ref, "write_ref_meta")
