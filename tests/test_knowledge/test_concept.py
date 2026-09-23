"""The OKF ``Concept`` — a directory whose path is its identity."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from molab.fs import LocalFileSystem
from molab.knowledge.concept import (
    Concept,
    append_link,
    concept_from_dir,
    concept_type_of,
)
from molab.knowledge.concept_meta import ConceptMeta
from molab.knowledge.concepts import Literature, Note
from molab.knowledge.errors import KnowledgeNotFoundError
from molab.knowledge.types import concept_type


def _write(directory: Path, *, type_str: str = "note.note", body: str = "") -> Concept:
    concept = Concept(directory, type=type_str)
    concept.write_meta()
    if body:
        concept.write(body)
    return concept


def _run_dir(root: Path) -> Path:
    """A workspace run directory: an entity record, no Knowledge head."""
    run_dir = root / "runs" / "run-abc123"
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(json.dumps({"type": "workspace.run", "id": "abc"}) + "\n")
    return run_dir


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
        assert concept.read() == "# Title\n\ntext\n"

    def test_absent_body_reads_as_empty_string(self, tmp_path: Path) -> None:
        (tmp_path / "bare").mkdir()
        assert Concept(tmp_path / "bare").read() == ""

    def test_write_creates_the_directory(self, tmp_path: Path) -> None:
        Concept(tmp_path / "fresh").write("hi\n")
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
        edge = src.links()[0]
        assert (edge.target, edge.role) == (str(dst.path), "derived_from")

    def test_default_role_writes_a_bare_label(self, tmp_path: Path) -> None:
        src = _write(tmp_path / "src")
        _write(tmp_path / "dst")
        append_link(src, tmp_path / "dst")
        assert "- [dst](../dst)\n" in src.read()

    def test_untyped_legacy_link_defaults_never_drops(self, tmp_path: Path) -> None:
        _write(tmp_path / "dst")
        src = _write(tmp_path / "src", body="- [dst](../dst)\n")
        assert src.links() == [(str(tmp_path / "dst"), "references")]

    def test_link_to_a_bare_path_needs_no_concept(self, tmp_path: Path) -> None:
        # A Concept cites an out-of-family directory (a workspace Run) by path.
        run_dir = tmp_path / "runs" / "run-abc123"
        run_dir.mkdir(parents=True)
        src = _write(tmp_path / "finding")
        append_link(src, run_dir, role="derived_from")
        assert src.links() == [(str(run_dir), "derived_from")]

    def test_external_links_are_not_edges(self, tmp_path: Path) -> None:
        src = _write(tmp_path / "src", body="[paper](https://example.org/x)\n")
        scan = src.scan_links(src.read())
        assert scan.concepts == []
        assert scan.external == ["https://example.org/x"]

    def test_link_to_a_nonexistent_dir_is_not_an_edge(self, tmp_path: Path) -> None:
        src = _write(tmp_path / "src", body="[gone](../gone)\n")
        scan = src.scan_links(src.read())
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
        assert src.read().startswith("# Notes\n\nprose\n")
        assert src.out_edges() == [str(dst.path)]

    def test_invalid_role_leaves_index_untouched(self, tmp_path: Path) -> None:
        dst = _write(tmp_path / "dst")
        src = _write(tmp_path / "src", body="original\n")
        with pytest.raises(ValueError, match="invalid edge role"):
            append_link(src, dst, role="bogus")  # type: ignore[arg-type]
        assert src.read() == "original\n"


class TestConceptRef:
    """``.ref`` — the strict cross-reference verb: knowledge → knowledge only."""

    def test_ref_by_object_appends_the_typed_golden_line(self, tmp_path: Path) -> None:
        src = Note(tmp_path / "idea")
        dst = Literature(tmp_path / "smith2024")
        dst.write("Smith et al. 2024\n")

        src.ref(dst, text="smith2024", role="derived_from")

        assert (
            (tmp_path / "idea.md")
            .read_text()
            .endswith("- [@derived_from smith2024](smith2024.md)\n")
        )
        assert src.links() == [(str(dst.path), "derived_from")]

    def test_ref_by_path_and_str_path_match_the_object_form(self, tmp_path: Path) -> None:
        dst = Literature(tmp_path / "smith2024")
        dst.write("Smith et al. 2024\n")

        for index, form in enumerate((dst, dst.path, str(dst.path))):
            src = Note(tmp_path / f"note{index}")
            src.write("# Idea\n")

            src.ref(form, text="smith2024", role="derived_from")

            assert src.links() == [(str(dst.path), "derived_from")]
            assert (
                (tmp_path / f"note{index}.md")
                .read_text()
                .endswith("- [@derived_from smith2024](smith2024.md)\n")
            )

    def test_default_role_writes_a_bare_label(self, tmp_path: Path) -> None:
        src = Note(tmp_path / "idea")
        dst = Literature(tmp_path / "smith2024")
        src.write("# Idea\n")
        dst.write("Smith et al. 2024\n")

        src.ref(dst)

        text = (tmp_path / "idea.md").read_text()
        assert text.endswith("- [smith2024.md](smith2024.md)\n")
        assert "@references" not in text

    def test_ref_starts_a_source_that_has_no_narrative_yet(self, tmp_path: Path) -> None:
        src = Note(tmp_path / "idea")  # construction touches no disk
        dst = Literature(tmp_path / "smith2024")
        dst.write("Smith et al. 2024\n")

        src.ref(dst, role="cites")

        assert (tmp_path / "idea.md").read_text() == (
            "---\nclass: Note\n---\n- [@cites smith2024.md](smith2024.md)\n"
        )

    def test_ref_accepts_a_target_that_is_not_written_yet(self, tmp_path: Path) -> None:
        # Construction touches no disk, so an edge may point at a document that
        # does not exist yet — the raw markdown carries it, links() cannot
        # resolve it (nothing is there to resolve to).
        src = Note(tmp_path / "idea")
        dst = Note(tmp_path / "planned")

        src.ref(dst)

        assert not dst.exists()
        assert (tmp_path / "idea.md").read_text().endswith("- [planned.md](planned.md)\n")
        assert src.links() == []

    def test_a_run_directory_object_is_rejected(self, tmp_path: Path) -> None:
        # concept_from_dir hands back the bare base class for a workspace
        # entity — that is not a Knowledge, and .ref says so.
        coordinate = concept_from_dir(_run_dir(tmp_path), fs=LocalFileSystem())
        assert type(coordinate) is Concept

        src = Note(tmp_path / "idea")
        src.write("# Idea\n")
        before = (tmp_path / "idea.md").read_text()

        with pytest.raises(TypeError):
            src.ref(coordinate)

        assert (tmp_path / "idea.md").read_text() == before

    def test_a_run_directory_path_is_rejected_in_the_path_branch(self, tmp_path: Path) -> None:
        run_dir = _run_dir(tmp_path)
        src = Note(tmp_path / "idea")
        src.write("# Idea\n")
        before = (tmp_path / "idea.md").read_text()

        for form in (run_dir, str(run_dir)):
            with pytest.raises(TypeError) as caught:
                src.ref(form)
            assert isinstance(caught.value.__cause__, KnowledgeNotFoundError)

        assert (tmp_path / "idea.md").read_text() == before

    def test_non_knowledge_objects_are_rejected(self, tmp_path: Path) -> None:
        class Coordinate:
            """Stand-in for a project / experiment / run coordinate."""

            def resolve(self) -> Path:
                return tmp_path

        src = Note(tmp_path / "idea")
        src.write("# Idea\n")
        before = (tmp_path / "idea.md").read_text()

        for bad in (Coordinate(), 42, "projects/p/experiments/e"):
            with pytest.raises(TypeError):
                src.ref(bad)

        assert (tmp_path / "idea.md").read_text() == before

    def test_invalid_role_raises_before_any_write(self, tmp_path: Path) -> None:
        src = Note(tmp_path / "idea")
        dst = Literature(tmp_path / "smith2024")
        src.write("# Idea\n")
        before = (tmp_path / "idea.md").read_text()

        with pytest.raises(ValueError, match="invalid edge role"):
            src.ref(dst, role="bogus")  # type: ignore[arg-type]

        assert (tmp_path / "idea.md").read_text() == before


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


class TestKnowledgeAlias:
    """``Concept`` is ``Knowledge``; the not-found error is the same object."""

    def test_concept_is_knowledge(self) -> None:
        from molab.knowledge.concept import Knowledge

        assert Concept is Knowledge

    def test_concept_not_found_error_is_knowledge_not_found_error(self) -> None:
        from molab.knowledge.errors import ConceptNotFoundError, KnowledgeNotFoundError

        assert ConceptNotFoundError is KnowledgeNotFoundError
