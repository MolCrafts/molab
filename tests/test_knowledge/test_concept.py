"""The OKF ``Concept`` — a directory whose path is its identity."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from molab.knowledge.concept import (
    Concept,
    append_link,
    concept_from_dir,
    concept_type_of,
)
from molab.knowledge.concept_meta import ConceptMeta
from molab.knowledge.types import concept_type


def _write(directory: Path, *, type_str: str = "note.note", body: str = "") -> Concept:
    concept = Concept(directory, type=type_str)
    concept.write_meta()
    if body:
        concept.set_body(body)
    return concept


class TestConceptIdentity:
    """Path is identity — no parent chain, no layout replay."""

    def test_path_and_name_come_from_the_directory(self, tmp_path: Path) -> None:
        concept = Concept(tmp_path / "deep" / "nested" / "tg-protocol")
        assert concept.path == tmp_path / "deep" / "nested" / "tg-protocol"
        assert concept.name == "tg-protocol"

    def test_resolve_never_replays_a_container_segment(self, tmp_path: Path) -> None:
        # The workspace Folder family doubles "projects/" when re-anchored; a
        # path-addressed Concept structurally cannot.
        nested = tmp_path / "projects" / "p" / "experiments" / "e" / "note"
        assert Concept(nested).resolve() == nested

    def test_equality_is_directory_equality(self, tmp_path: Path) -> None:
        a = Concept(tmp_path / "n")
        b = Concept(tmp_path / "n", type="knowledge.item")
        assert a == b
        assert len({a, b}) == 1

    def test_differing_directories_are_not_equal(self, tmp_path: Path) -> None:
        assert Concept(tmp_path / "a") != Concept(tmp_path / "b")

    def test_construction_touches_no_disk(self, tmp_path: Path) -> None:
        concept = Concept(tmp_path / "not-yet")
        assert not concept.exists()
        assert list(tmp_path.iterdir()) == []


class TestConceptMetaRoundTrip:
    """``meta.json`` is the typed head; ``type`` and ``id`` are always stamped."""

    def test_write_meta_stamps_type_and_id_from_the_directory(self, tmp_path: Path) -> None:
        _write(tmp_path / "tg-protocol", type_str="note.note")
        loaded = json.loads((tmp_path / "tg-protocol" / "meta.json").read_text())
        assert loaded == {"type": "note.note", "id": "tg-protocol"}

    def test_write_meta_preserves_extra_keys_but_overrides_identity(self, tmp_path: Path) -> None:
        concept = Concept(tmp_path / "doc", type="note.note")
        concept.write_meta(ConceptMeta(type="lies", id="lies", tags=["tg", "退火"]))
        loaded = json.loads((tmp_path / "doc" / "meta.json").read_text())
        assert loaded["type"] == "note.note"
        assert loaded["id"] == "doc"
        assert loaded["tags"] == ["tg", "退火"]

    def test_tags_are_readable_back(self, tmp_path: Path) -> None:
        concept = Concept(tmp_path / "doc", type="note.note")
        concept.write_meta(ConceptMeta(type="note.note", tags=["a", "b"]))
        assert concept.tags() == ["a", "b"]

    def test_absent_meta_reads_as_empty_not_an_error(self, tmp_path: Path) -> None:
        (tmp_path / "bare").mkdir()
        concept = Concept(tmp_path / "bare")
        assert concept.read_meta() == {}
        assert concept.tags() == []

    def test_type_falls_back_to_the_declared_type(self, tmp_path: Path) -> None:
        (tmp_path / "bare").mkdir()
        assert Concept(tmp_path / "bare", type="note.note").type() == "note.note"

    def test_meta_json_keeps_cjk_readable(self, tmp_path: Path) -> None:
        # A group wiki is read by humans in an editor; escaped \uXXXX is not that.
        concept = Concept(tmp_path / "doc", type="note.note")
        concept.write_meta(ConceptMeta(type="note.note", tags=["玻璃化转变"]))
        assert "玻璃化转变" in (tmp_path / "doc" / "meta.json").read_text(encoding="utf-8")


class TestConceptBody:
    """``index.md`` is the narrative."""

    def test_body_round_trip(self, tmp_path: Path) -> None:
        concept = _write(tmp_path / "doc", body="# Title\n\ntext\n")
        assert concept.body() == "# Title\n\ntext\n"

    def test_absent_body_reads_as_empty_string(self, tmp_path: Path) -> None:
        (tmp_path / "bare").mkdir()
        assert Concept(tmp_path / "bare").body() == ""

    def test_set_body_creates_the_directory(self, tmp_path: Path) -> None:
        Concept(tmp_path / "fresh").set_body("hi\n")
        assert (tmp_path / "fresh" / "index.md").read_text() == "hi\n"


class TestConceptEdges:
    """The markdown links in ``index.md`` ARE the knowledge graph."""

    def test_in_tree_link_resolving_to_a_dir_is_an_out_edge(self, tmp_path: Path) -> None:
        src = _write(tmp_path / "src")
        dst = _write(tmp_path / "dst")
        append_link(src, dst, role="cites")
        assert src.out_edges() == [str(dst.path)]

    def test_role_round_trips_through_the_label_channel(self, tmp_path: Path) -> None:
        src = _write(tmp_path / "src")
        dst = _write(tmp_path / "dst")
        append_link(src, dst, role="derived_from")
        edge = src.typed_out_edges()[0]
        assert (edge.target, edge.role) == (str(dst.path), "derived_from")

    def test_default_role_writes_a_bare_label(self, tmp_path: Path) -> None:
        src = _write(tmp_path / "src")
        _write(tmp_path / "dst")
        append_link(src, tmp_path / "dst")
        assert "- [dst](../dst)\n" in src.body()

    def test_untyped_legacy_link_defaults_never_drops(self, tmp_path: Path) -> None:
        _write(tmp_path / "dst")
        src = _write(tmp_path / "src", body="- [dst](../dst)\n")
        assert src.typed_out_edges() == [(str(tmp_path / "dst"), "references")]

    def test_link_to_a_bare_path_needs_no_concept(self, tmp_path: Path) -> None:
        # A Concept cites an out-of-family directory (a workspace Run) by path.
        run_dir = tmp_path / "runs" / "run-abc123"
        run_dir.mkdir(parents=True)
        src = _write(tmp_path / "finding")
        append_link(src, run_dir, role="derived_from")
        assert src.typed_out_edges() == [(str(run_dir), "derived_from")]

    def test_external_links_are_not_edges(self, tmp_path: Path) -> None:
        src = _write(tmp_path / "src", body="[paper](https://example.org/x)\n")
        scan = src.links()
        assert scan.concepts == []
        assert scan.external == ["https://example.org/x"]

    def test_link_to_a_nonexistent_dir_is_not_an_edge(self, tmp_path: Path) -> None:
        src = _write(tmp_path / "src", body="[gone](../gone)\n")
        scan = src.links()
        assert scan.concepts == []
        assert scan.other == ["../gone"]

    def test_trailing_index_md_resolves_to_its_directory(self, tmp_path: Path) -> None:
        _write(tmp_path / "dst")
        src = _write(tmp_path / "src", body="[dst](../dst/index.md)\n")
        assert src.out_edges() == [str(tmp_path / "dst")]

    def test_append_is_additive_and_keeps_the_narrative(self, tmp_path: Path) -> None:
        dst = _write(tmp_path / "dst")
        src = _write(tmp_path / "src", body="# Notes\n\nprose")
        append_link(src, dst)
        assert src.body().startswith("# Notes\n\nprose\n")
        assert src.out_edges() == [str(dst.path)]

    def test_invalid_role_leaves_index_untouched(self, tmp_path: Path) -> None:
        dst = _write(tmp_path / "dst")
        src = _write(tmp_path / "src", body="original\n")
        with pytest.raises(ValueError, match="invalid edge role"):
            append_link(src, dst, role="bogus")  # type: ignore[arg-type]
        assert src.body() == "original\n"


class TestConceptFromDir:
    """Registry-driven reconstruction, filtered to the Concept family."""

    def test_registered_subclass_is_rebuilt(self, tmp_path: Path) -> None:
        @concept_type("test-concept-rebuild")
        class Rebuilt(Concept):
            DEFAULT_TYPE = "test-concept-rebuild"

        _write(tmp_path / "doc", type_str="test-concept-rebuild")
        rebuilt = concept_from_dir(tmp_path / "doc", fs=Concept(tmp_path).fs)
        assert isinstance(rebuilt, Rebuilt)
        assert rebuilt.path == tmp_path / "doc"

    def test_unknown_type_falls_back_to_base_concept(self, tmp_path: Path) -> None:
        _write(tmp_path / "doc", type_str="nobody.registered.this")
        rebuilt = concept_from_dir(tmp_path / "doc", fs=Concept(tmp_path).fs)
        assert type(rebuilt) is Concept
        assert rebuilt.type() == "nobody.registered.this"

    def test_foreign_family_class_is_never_returned(self, tmp_path: Path) -> None:
        # A workspace Folder subclass registered under the same global registry
        # must not be handed to the Concept reconstructor — it has a different
        # constructor entirely.
        from molab.workspace.run import Run

        _write(tmp_path / "run-abc", type_str="workspace.run")
        rebuilt = concept_from_dir(tmp_path / "run-abc", fs=Concept(tmp_path).fs)
        assert type(rebuilt) is Concept
        assert not isinstance(rebuilt, Run)

    def test_directory_without_meta_json_reports_no_type(self, tmp_path: Path) -> None:
        (tmp_path / "plain").mkdir()
        assert concept_type_of(tmp_path / "plain", fs=Concept(tmp_path).fs) == ""
