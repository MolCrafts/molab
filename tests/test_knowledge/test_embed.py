"""The document-embed verb: ``append_link`` to a live entity, and its read side.

- ``link_target`` — a document is its path, a project / experiment / run /
  asset is its ``molab:`` reference;
- ``default_role_for`` — the per-kind default from the frozen vocabulary;
- ``summarize_entity`` — a pure read projection, with all three ``title``
  branches plus the ``Asset`` branch, each pinned by its own test.

Missing preconditions (an ``Asset`` with no root, no record dir, a foreign
target) raise — never a silent fallback.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from molab.knowledge import Literature, Note
from molab.knowledge.concept import append_link, link_target
from molab.knowledge.embed import EntitySummary, default_role_for, summarize_entity
from molab.workspace.domain import Asset
from molab.workspace.refs import ref_of


@pytest.fixture
def asset(lab: Any, experiment: Any, tmp_path: Path) -> Asset:
    """A user ``DataAsset`` in the experiment scope, with a real record dir."""
    source = tmp_path / "input.txt"
    source.write_text("payload-bytes")
    return experiment.assets.import_asset("mydata", source)


@pytest.fixture
def note(experiment: Any) -> Note:
    return Note.mount(experiment, "My Note", body="# My Note\n\nbody")


class TestLinkTarget:
    def test_a_concept_resolves_to_its_own_path(self, note: Note) -> None:
        assert link_target(note) == str(note.path)

    def test_a_folder_resolves_to_its_ref(self, experiment: Any) -> None:
        assert link_target(experiment) == str(ref_of(experiment))

    def test_an_asset_resolves_to_its_ref(self, asset: Asset) -> None:
        assert link_target(asset) == str(ref_of(asset))

    def test_a_foreign_target_is_rejected(self) -> None:
        with pytest.raises(TypeError):
            link_target(object())  # ty: ignore[invalid-argument-type]


class TestDefaultRoleFor:
    def test_run_and_experiment_record(self, run: Any, experiment: Any) -> None:
        assert default_role_for(run) == "records"
        assert default_role_for(experiment) == "records"

    def test_a_literature_cites(self, experiment: Any) -> None:
        lit = Literature(experiment, "Smith 2024")
        lit.write(fields={"title": "Smith 2024", "year": 2024})

        assert default_role_for(lit) == "cites"

    def test_an_asset_references(self, asset: Asset) -> None:
        assert default_role_for(asset) == "references"

    def test_a_foreign_target_is_rejected(self) -> None:
        with pytest.raises(TypeError):
            default_role_for("not-an-entity")  # ty: ignore[invalid-argument-type]


class TestSummarizeEntity:
    def test_a_folder_projects_its_id_not_its_directory_name(
        self, run: Any, experiment: Any, lab: Any
    ) -> None:
        summary = summarize_entity(run)

        assert isinstance(summary, EntitySummary)
        assert (summary.id, summary.kind, summary.title) == (run.id, "workspace.run", "seed=1")
        assert summary.id != run.name, "the dir name is a label, the id is the identity"
        assert summarize_entity(experiment).kind == "workspace.experiment"
        assert summarize_entity(experiment).title == "e"

    def test_a_concept_projects_its_directory_name(self, note: Note) -> None:
        summary = summarize_entity(note)

        assert (summary.id, summary.kind, summary.title) == (
            str(note.path),
            "Note",
            "My Note",
        )

    def test_a_reference_kind_title_comes_from_the_head(self, tmp_path: Path) -> None:
        document = Literature(tmp_path / "abstract-1")
        document.write(fields={"title": "Head Title"})

        summary = summarize_entity(document)

        assert (summary.id, summary.kind, summary.title) == (
            str(document.path),
            "Literature",
            "Head Title",
        )

    def test_a_literature_falls_back_to_its_bib_title(self, experiment: Any) -> None:
        lit = Literature(experiment, "Smith 2024")
        lit.write(fields={"title": "Smith 2024", "year": 2024})

        summary = summarize_entity(lit)

        assert (summary.id, summary.kind, summary.title) == (
            str(lit.path),
            "Literature",
            "Smith 2024",
        )

    def test_a_document_title_is_its_h1_else_its_name(self, experiment: Any) -> None:
        titled = Note.mount(experiment, "Titled", body="# A Real Title\n")
        untitled = Note.mount(experiment, "Untitled")

        assert summarize_entity(titled).title == "A Real Title"
        assert summarize_entity(untitled).title == "Untitled"

    def test_a_folder_title_prefers_its_index_h1(self, run: Any) -> None:
        run.write_index("# Nice Run Title\n\nnotes")

        assert summarize_entity(run).title == "Nice Run Title"

    def test_an_asset_projects_its_own_fields(self, asset: Asset, lab: Any) -> None:
        summary = summarize_entity(asset)

        assert (summary.id, summary.kind, summary.title) == (asset.id, "asset", "mydata")

    def test_a_foreign_target_is_rejected(self) -> None:
        with pytest.raises(TypeError):
            summarize_entity(object())  # ty: ignore[invalid-argument-type]


class TestEmbed:
    def test_a_run_is_linked_by_its_ref_with_the_given_role(self, note: Note, run: Any) -> None:
        append_link(note, run, role="derived_from")

        assert [(e.target, e.role) for e in note.links()] == [(str(ref_of(run)), "derived_from")]
        assert f"]({ref_of(run)})" in note.path.read_text()

    def test_a_concept_target_round_trips_through_its_own_path(
        self, note: Note, experiment: Any
    ) -> None:
        other = Note.mount(experiment, "Background")

        append_link(note, other, role="cites")

        assert [(Path(e.target).name, e.role) for e in note.links()] == [("background.md", "cites")]
