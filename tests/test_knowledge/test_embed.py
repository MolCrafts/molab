"""``molab.knowledge.embed`` — the document-embed adapter.

Covers the three read/write halves of the embed verb:

- ``resolve_embed_target`` — a ``Concept`` / ``Folder`` target is its own
  directory, an ``Asset`` is resolved to its in-tree record dir
  ``<scope_dir>/assets/<asset_id>/`` (pointed at, never copied);
- ``default_role_for`` — the per-kind default from the frozen vocabulary;
- ``summarize_entity`` — a pure read projection, with all three ``title``
  branches plus the ``Asset`` branch, each pinned by its own test.

Missing preconditions (an ``Asset`` with no root, no record dir, a foreign
target) raise — never a silent fallback.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from molab.knowledge import Literature, Note, ReferenceMeta
from molab.knowledge.concept import Concept
from molab.knowledge.embed import (
    EntitySummary,
    asset_record_dir,
    default_role_for,
    embed,
    resolve_embed_target,
    summarize_entity,
)
from molab.knowledge.write import mount_note
from molab.workspace.assets.base import Asset


@pytest.fixture
def asset(lab: Any, experiment: Any, tmp_path: Path) -> Asset:
    """A user ``DataAsset`` in the experiment scope, with a real record dir."""
    source = tmp_path / "input.txt"
    source.write_text("payload-bytes")
    return experiment.data_assets.import_asset("mydata", source)


@pytest.fixture
def note(experiment: Any) -> Note:
    return mount_note(experiment, "My Note", body="# My Note\n\nbody")


class TestResolveEmbedTarget:
    def test_a_concept_resolves_to_its_own_path(self, note: Note, lab: Any) -> None:
        assert resolve_embed_target(note, root=lab.root) == note.path

    def test_a_folder_resolves_to_its_own_directory(self, experiment: Any, lab: Any) -> None:
        assert resolve_embed_target(experiment, root=lab.root) == experiment.resolve()

    def test_an_asset_resolves_to_its_record_dir_without_copying(
        self, asset: Asset, lab: Any
    ) -> None:
        record_dir = asset_record_dir(asset, lab.root)
        before = sorted(p.name for p in Path(record_dir).iterdir())

        resolved = resolve_embed_target(asset, root=lab.root)

        assert resolved == record_dir
        assert Path(resolved).parent.name == "assets"
        assert Path(resolved).name == asset.asset_id
        assert sorted(p.name for p in Path(record_dir).iterdir()) == before

    def test_a_foreign_target_is_rejected(self, lab: Any) -> None:
        with pytest.raises(TypeError):
            resolve_embed_target("not-an-entity", root=lab.root)  # ty: ignore[invalid-argument-type]


class TestDefaultRoleFor:
    def test_run_and_experiment_record(self, run: Any, experiment: Any) -> None:
        assert default_role_for(run) == "records"
        assert default_role_for(experiment) == "records"

    def test_a_literature_cites(self, experiment: Any) -> None:
        lit = Literature(experiment, "Smith 2024")
        lit.write(ReferenceMeta(title="Smith 2024", year=2024))

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
        summary = summarize_entity(run, root=lab.root)

        assert isinstance(summary, EntitySummary)
        assert (summary.id, summary.kind, summary.title) == (run.id, "workspace.run", "seed=1")
        assert summary.id != run.name, "the dir name is a label, the id is the identity"
        assert summarize_entity(experiment).kind == "workspace.experiment"
        assert summarize_entity(experiment).title == "e"

    def test_a_concept_projects_its_directory_name(self, note: Note) -> None:
        summary = summarize_entity(note)

        assert (summary.id, summary.kind, summary.title) == ("my-note", "note.note", "My Note")

    def test_a_reference_kind_title_comes_from_the_head(self, tmp_path: Path) -> None:
        document = Concept(tmp_path / "abstract-1", type="reference.reference")
        document.write_meta({"title": "Head Title"})

        summary = summarize_entity(document)

        assert (summary.id, summary.kind, summary.title) == (
            "abstract-1",
            "reference.reference",
            "Head Title",
        )

    def test_a_literature_falls_back_to_its_bib_title(self, experiment: Any) -> None:
        lit = Literature(experiment, "Smith 2024")
        lit.write(ReferenceMeta(title="Smith 2024", year=2024))

        summary = summarize_entity(lit)

        assert (summary.id, summary.kind, summary.title) == (
            "smith-2024",
            "reference.reference",
            "Smith 2024",
        )

    def test_a_document_title_falls_back_to_its_h1_then_its_name(self, experiment: Any) -> None:
        titled = mount_note(experiment, "Titled", body="# A Real Title\n")
        untitled = mount_note(experiment, "Untitled")

        assert summarize_entity(titled).title == "A Real Title"
        assert summarize_entity(untitled).title == "untitled"

    def test_a_folder_title_prefers_its_index_h1(self, run: Any) -> None:
        run.write_index("# Nice Run Title\n\nnotes")

        assert summarize_entity(run).title == "Nice Run Title"

    def test_an_asset_projects_its_own_fields(self, asset: Asset, lab: Any) -> None:
        summary = summarize_entity(asset, root=lab.root)

        assert (summary.id, summary.kind, summary.title) == (asset.asset_id, "data", "mydata")

    def test_a_foreign_target_is_rejected(self) -> None:
        with pytest.raises(TypeError):
            summarize_entity(object())  # ty: ignore[invalid-argument-type]


class TestAssetRecordDir:
    def test_a_missing_root_is_refused(self, asset: Asset) -> None:
        with pytest.raises(ValueError):
            asset_record_dir(asset, None)

    def test_a_missing_record_dir_is_refused(self, asset: Asset, lab: Any) -> None:
        ghost = asset.model_copy(update={"asset_id": "does-not-exist-0000"})

        with pytest.raises(FileNotFoundError):
            asset_record_dir(ghost, lab.root)


class TestEmbed:
    def test_one_relative_typed_edge_uses_the_per_kind_default(
        self, note: Note, run: Any, lab: Any
    ) -> None:
        embed(note, run, root=lab.root)

        assert [(e.target, e.role) for e in note.links()] == [(str(run.resolve()), "records")]
        relative = os.path.relpath(str(run.resolve()), str(note.path.parent))
        assert f"]({Path(relative).as_posix()})" in note.path.read_text()
        assert not Path(relative).is_absolute()

    def test_an_explicit_role_overrides_the_default(self, note: Note, run: Any, lab: Any) -> None:
        embed(note, run, root=lab.root, role="derived_from")

        assert [(e.target, e.role) for e in note.links()] == [(str(run.resolve()), "derived_from")]

    def test_a_concept_target_round_trips_through_its_own_path(
        self, note: Note, experiment: Any
    ) -> None:
        other = mount_note(experiment, "Background")

        embed(note, other, root=experiment.resolve(), role="cites")

        assert [(Path(e.target).name, e.role) for e in note.links()] == [("background.md", "cites")]
