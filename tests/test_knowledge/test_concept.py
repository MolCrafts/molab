"""The OKF ``Concept`` — a directory whose path is its identity."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from molab.fs import LocalFileSystem
from molab.knowledge.concept import (
    Concept,
    Knowledge,
    append_link,
)
from molab.knowledge.concepts import Literature, Note
from molab.knowledge.errors import KnowledgeNotFoundError
from molab.knowledge.location import folder
from molab.workspace import Experiment, Workspace
from molab.workspace.workspace import set_cli_root_override


@pytest.fixture
def experiment(tmp_path: Path) -> Experiment:
    """A real workspace Experiment — the Folder-family host."""
    workspace = Workspace(root=tmp_path / "lab")
    workspace.materialize()
    return workspace.add_project("p").add_experiment("e")


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
        assert src.links() == [(str(tmp_path / "planned.md"), "references")]

    def test_a_run_directory_object_is_rejected(self, tmp_path: Path) -> None:
        coordinate = Concept(_run_dir(tmp_path))
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


class TestKnowledgeAlias:
    """``Concept`` is ``Knowledge``; the not-found error is the same object."""

    def test_concept_is_knowledge(self) -> None:
        from molab.knowledge.concept import Knowledge

        assert Concept is Knowledge

    def test_concept_not_found_error_is_knowledge_not_found_error(self) -> None:
        from molab.knowledge.errors import ConceptNotFoundError, KnowledgeNotFoundError

        assert ConceptNotFoundError is KnowledgeNotFoundError


class TestHostConstruction:
    """``Concept(host, name)`` — the host supplies path and filesystem."""

    def test_a_file_document_lands_on_the_host_markdown_golden(
        self, experiment: Experiment
    ) -> None:
        note = Note(experiment, "Tg Cooling")

        assert note.path == Path(str(experiment.resolve())) / "knowledges" / "tg-cooling.md"

    def test_a_bare_class_is_not_a_document(self, experiment: Experiment) -> None:
        with pytest.raises(TypeError, match="not a knowledge document"):
            Concept(experiment, "records")

    def test_construction_touches_no_disk(self, experiment: Experiment) -> None:
        with pytest.raises(TypeError):
            Knowledge(experiment, "x")

        assert not (Path(str(experiment.resolve())) / "knowledges").exists()

    def test_the_hosts_own_disk_is_adopted(self, experiment: Experiment) -> None:
        assert Note(experiment, "x").fs is experiment.fs

    def test_a_path_host_yields_the_local_filesystem(self, tmp_path: Path) -> None:
        assert isinstance(Note(tmp_path / "wiki", "x").fs, LocalFileSystem)

    def test_an_explicit_fs_wins_over_the_hosts_disk(self, tmp_path: Path) -> None:
        disk = LocalFileSystem()

        assert Note(tmp_path / "wiki", "x", fs=disk).fs is disk

    def test_an_unrecognised_host_fast_fails(self, tmp_path: Path) -> None:
        class Coordinate:
            """A resolve()-only stand-in — not a host, and never a local fallback."""

            def resolve(self) -> Path:
                return tmp_path

        with pytest.raises(TypeError, match="Folder"):
            Note(Coordinate(), "x")

    def test_the_host_is_not_retained(self, experiment: Experiment) -> None:
        note = Note(experiment, "x")
        twin = Knowledge(folder(experiment, "x", Note))

        assert not hasattr(note, "_host")
        assert note == twin
        assert hash(note) == hash(twin)

    def test_the_single_argument_path_form_is_unchanged(self) -> None:
        assert Knowledge("/wiki/cooling").path == Path("/wiki/cooling")
        assert Concept("/wiki/cooling").path == Path("/wiki/cooling")

    def test_the_first_ref_lands_the_bytes_at_the_host_path(self, experiment: Experiment) -> None:
        note = Note(experiment, "idea")
        literature = Literature(experiment, "smith")
        literature.write("Smith et al. 2024\n")

        note.ref(literature, role="cites")

        assert note.path.is_file()
        assert "@cites" in note.path.read_text()

    def test_the_first_write_lands_the_bytes_at_the_host_path(self, experiment: Experiment) -> None:
        note = Note(experiment, "plan")
        assert not note.path.exists()

        note.write("# Plan\n")

        assert note.path.read_text().endswith("# Plan\n")


def _workspace(tmp_path: Path, name: str = "lab") -> Workspace:
    workspace = Workspace(tmp_path / name, name=name)
    workspace.materialize()
    return workspace


class TestConceptWalk:
    def test_a_workspace_root_yields_only_host_documents(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        project = ws.add_project("p")
        experiment = project.add_experiment("e")
        run = experiment.add_run(params={"seed": 1})
        Note(ws, "lab-note").write("# Lab\n")
        Note(experiment, "finding").write("# Finding\n")
        Note(run, "log").write("# Log\n")
        decoy = Path(experiment.resolve()) / "pinn-src" / "knowledges"
        decoy.mkdir(parents=True)
        (decoy / "noise.md").write_text("---\nclass: Note\n---\n\n# Noise\n")
        campaign = Path(project.resolve()) / "campaign" / "knowledges"
        campaign.mkdir(parents=True)
        (campaign / "old.md").write_text("---\nclass: Note\n---\n\n# Old\n")
        out = Path(run.resolve()) / "executions" / "e01" / "out" / "knowledges"
        out.mkdir(parents=True)
        (out / "x.md").write_text("---\nclass: Note\n---\n\n# X\n")
        (Path(ws.root) / "stray.md").write_text("---\nclass: Note\n---\n\n# Stray\n")
        legacy = Path(ws.root) / "knowledges" / "legacy"
        legacy.mkdir(parents=True)
        (legacy / "note.json").write_text("{}\n")

        assert {item.name for item in Knowledge(ws.root).walk()} == {"lab-note", "finding", "log"}

    def test_a_non_workspace_directory_is_the_container(self, tmp_path: Path) -> None:
        wiki = tmp_path / "wiki"
        wiki.mkdir()
        Note(wiki / "tg").write("# Tg\n")
        hidden = wiki / "knowledges"
        hidden.mkdir()
        (hidden / "hidden.md").write_text("---\nclass: Note\n---\n\n# Hidden\n")

        assert [item.name for item in Knowledge(wiki).walk()] == ["tg"]

    def test_a_directory_inside_a_workspace_is_a_container(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        pinn = Path(ws.root) / "pinn-src"
        pinn.mkdir()
        Note(pinn / "a").write("# A\n")

        assert [item.name for item in Knowledge(pinn).walk()] == ["a"]

    def test_a_missing_root_yields_nothing(self, tmp_path: Path) -> None:
        assert list(Knowledge(tmp_path / "nope").walk()) == []

    def test_a_symlinked_root_keeps_the_link_spelling(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        Note(ws, "lab-note").write("# Cooling\n\ncooling schedule\n")
        link = tmp_path / "link"
        link.symlink_to(ws.root, target_is_directory=True)

        assert all(str(item.path).startswith(str(link)) for item in Knowledge(link).walk())
        hits = Knowledge(link).search("cooling")
        assert hits.hits[0].entry.path == "knowledges/lab-note.md"

    def test_the_cli_root_override_does_not_redirect_the_walk(self, tmp_path: Path) -> None:
        ws_a = _workspace(tmp_path, "a")
        ws_b = _workspace(tmp_path, "b")
        Note(ws_a, "a-note").write("# A note\n")
        Note(ws_b, "b-note").write("# B note\n")
        set_cli_root_override(ws_a.root, explicit=True)
        try:
            names = [item.name for item in Knowledge(ws_b.root).walk()]
            hits = Knowledge(ws_b.root).search("note")
        finally:
            set_cli_root_override(None)

        assert names == ["b-note"]
        assert hits.hits[0].entry.path == "knowledges/b-note.md"


class TestConceptSearch:
    def test_of_filters_by_class(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        Note(ws, "cooling").write("# Cooling rate\n\ncool the sample\n", tags=["Tg"])
        Literature(ws, "paper").write("# Paper\n\ncooling in the literature\n")

        notes = Knowledge(ws.root).search("cooling", of=Note)
        papers = Knowledge(ws.root).search("cooling", of=Literature)

        assert {hit.entry.path for hit in notes.hits} == {"knowledges/cooling.md"}
        assert {hit.entry.path for hit in papers.hits} == {"knowledges/paper.md"}

    def test_entry_type_and_title_come_from_the_document(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        Note(ws, "cooling").write("# Cooling rate\n\ncool the sample\n")

        hit = Knowledge(ws.root).search("cooling").hits[0]

        assert hit.entry.type == "Note"
        assert hit.entry.title == "Cooling rate"

    def test_tag_keeps_only_tagged_documents(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        Note(ws, "cooling").write("# Cooling rate\n\ncool\n", tags=["Tg"])
        Note(ws, "other").write("# Cooling other\n\ncool\n", tags=["misc"])

        hits = Knowledge(ws.root).search("cooling", tag="Tg")

        assert {hit.entry.path for hit in hits.hits} == {"knowledges/cooling.md"}


def _pair(ws: Workspace) -> tuple[Note, Note]:
    cited = Note(ws, "a")
    cited.write("# A\n")
    reader = Note(ws, "reader")
    reader.write("# Reader\n")
    append_link(reader, cited, role="cites")
    return cited, reader


class TestConceptRename:
    def test_rename_rewrites_the_inbound_link(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        cited, reader = _pair(ws)

        cited.rename("Renamed Notes", within=ws.root)

        assert cited.path.name == "renamed-notes.md"
        assert [Path(edge.target).name for edge in reader.links()] == ["renamed-notes.md"]
        assert reader.links()[0].role == "cites"

    def test_an_existing_destination_is_refused(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        cited, _reader = _pair(ws)
        Note(ws, "taken").write("# Taken\n")

        with pytest.raises(FileExistsError):
            cited.rename("taken", within=ws.root)

    def test_the_same_name_is_a_no_op(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        cited, reader = _pair(ws)
        before = cited.path

        cited.rename("a", within=ws.root)

        assert cited.path == before
        assert reader.links()[0].target == str(before)


class TestConceptMoveTo:
    def test_move_keeps_outbound_links_and_rewrites_inbound(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        experiment = ws.add_project("p").add_experiment("e")
        cited, reader = _pair(ws)
        append_link(cited, reader, role="cites")

        cited.move_to(experiment, within=ws.root)

        assert cited.path == Path(experiment.resolve()) / "knowledges" / "a.md"
        assert cited.links()[0].target == str(reader.path)
        assert reader.links()[0].target == str(cited.path)

    def test_a_document_host_is_rejected(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        cited, reader = _pair(ws)

        with pytest.raises(TypeError, match="Folder"):
            cited.move_to(reader, within=ws.root)

    def test_an_existing_destination_is_refused(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        experiment = ws.add_project("p").add_experiment("e")
        cited, _reader = _pair(ws)
        Note(experiment, "a").write("# Already\n")

        with pytest.raises(FileExistsError):
            cited.move_to(experiment, within=ws.root)

    def test_a_move_leaves_a_run_reference_verbatim(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        experiment = ws.add_project("p").add_experiment("e")
        note = Note(ws, "a")
        ref = "molab:experiment/E1/run/R1#L3-L9"
        note.write(f"- [@derived_from R1]({ref})\n")

        note.move_to(experiment, within=ws.root)

        assert f"]({ref})" in note.path.read_text(encoding="utf-8")

    def test_stem_is_kept_and_relink_false_is_a_pure_move(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        experiment = ws.add_project("p").add_experiment("e")
        note = Note(ws, "a")
        note.write("# A\n[b](b.md)\n")
        original = note.path.read_bytes()
        reader = Note(ws, "reader")
        reader.write(f"[a]({note.path.name})\n")
        reader_before = reader.path.read_bytes()

        note.move_to(experiment, stem="Mixed_Case.v2", relink=False)

        assert note.path == Path(experiment.resolve()) / "knowledges" / "Mixed_Case.v2.md"
        assert note.path.read_bytes() == original
        assert reader.path.read_bytes() == reader_before

    def test_a_bad_stem_is_refused(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        experiment = ws.add_project("p").add_experiment("e")
        note = Note(ws, "a")
        note.write("# A\n")

        with pytest.raises(ValueError):
            note.move_to(experiment, stem="a/b", relink=False)
        with pytest.raises(ValueError):
            note.move_to(experiment, stem="..", relink=False)
        with pytest.raises(ValueError):
            note.move_to(experiment, stem="", relink=False)

    def test_an_existing_stem_destination_is_refused(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        experiment = ws.add_project("p").add_experiment("e")
        note = Note(ws, "a")
        note.write("# A\n")
        dest = Path(experiment.resolve()) / "knowledges" / "Mixed_Case.v2.md"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("# there\n")

        with pytest.raises(FileExistsError):
            note.move_to(experiment, stem="Mixed_Case.v2", relink=False)

    def test_omitted_within_matches_the_workspace_root(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        cited, reader = _pair(ws)

        cited.rename("Renamed Notes")

        assert cited.path.name == "renamed-notes.md"
        assert [Path(edge.target).name for edge in reader.links()] == ["renamed-notes.md"]

    def test_a_plain_wiki_requires_within(self, tmp_path: Path) -> None:
        wiki = tmp_path / "wiki"
        wiki.mkdir()
        page = Note(wiki / "a")
        page.write("# A\n")

        with pytest.raises(ValueError, match="pass within="):
            page.rename("b")
        with pytest.raises(ValueError, match="pass within="):
            page.move_to(wiki, within=None)
        with pytest.raises(ValueError, match="pass within="):
            page.backlinks()

    def test_a_non_host_document_inside_a_workspace_requires_within(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        wiki = Path(ws.root) / "wiki"
        wiki.mkdir()
        page = Note(wiki / "a")
        page.write("# A\n")

        with pytest.raises(ValueError, match="pass within="):
            page.rename("b")
        with pytest.raises(ValueError, match="pass within="):
            page.move_to(wiki)
        with pytest.raises(ValueError, match="pass within="):
            page.backlinks()

        page.rename("renamed", within=wiki)
        assert page.path.name == "renamed.md"


class TestConceptDelete:
    def test_delete_removes_the_file_from_the_walk(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        cited, _reader = _pair(ws)

        cited.delete()

        assert not cited.path.exists()
        assert cited.name not in {item.name for item in Knowledge(ws.root).walk()}


class TestConceptBacklinks:
    def test_inbound_edges_exclude_a_self_link(self, tmp_path: Path) -> None:
        from molab.knowledge.edges import Backlink

        ws = _workspace(tmp_path)
        cited, reader = _pair(ws)
        append_link(cited, cited, role="cites")

        found = cited.backlinks(within=ws.root)

        assert found == [Backlink(source=reader, role="cites")]


class TestConceptExport:
    def test_export_is_the_narrative(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        note = Note(ws, "lab")
        note.write("# Lab Notes\n")

        assert note.export() == note.read()
        assert "---" not in note.export()


class TestConceptImportZotero:
    def test_import_lands_markdown_and_is_idempotent(self, tmp_path: Path) -> None:
        from tests.test_workspace.test_zotero_concepts import _make_zotero_db

        ws = _workspace(tmp_path)
        experiment = ws.add_project("p").add_experiment("e")
        zot = tmp_path / "zot"
        zot.mkdir()
        db = _make_zotero_db(zot)

        Knowledge(ws.root).import_zotero(db)
        landed = list(Path(ws.root).glob("knowledges/*.md"))
        assert len(landed) == 2
        assert not (Path(ws.root) / "references").exists()

        Knowledge(ws.root).import_zotero(db)
        assert len(list(Path(ws.root).glob("knowledges/*.md"))) == 2

        wiki = tmp_path / "wiki"
        wiki.mkdir()
        Knowledge(wiki).import_zotero(db)
        assert len(list(wiki.glob("*.md"))) == 2
        assert not (wiki / "knowledges").exists()

        Knowledge(ws.root).import_zotero(db, under=experiment)
        assert len(list((Path(experiment.resolve()) / "knowledges").glob("*.md"))) == 2


class TestConceptLinks:
    def test_ref_missing_other_and_external(self, tmp_path: Path) -> None:
        note = Note(tmp_path / "docs" / "n")
        note.write(
            "- [@derived_from R1](molab:experiment/E1/run/R1)\n"
            "- [gone](../gone.md)\n"
            "- [m](mailto:a@b)\n"
            "[p](https://example.org/x)\n"
        )

        scan = note.scan_links(note.read())

        assert scan.refs == ["molab:experiment/E1/run/R1"]
        assert scan.missing == [str(tmp_path / "gone.md")]
        assert scan.other == ["mailto:a@b"]
        assert scan.external == ["https://example.org/x"]
        assert scan.typed_concepts == [
            ("molab:experiment/E1/run/R1", "derived_from"),
            (str(tmp_path / "gone.md"), "references"),
        ]

    def test_a_cites_https_edge_stays_typed(self, tmp_path: Path) -> None:
        note = Note(tmp_path / "n")
        note.write("- [@cites p](https://doi.org/10.1/x)\n")

        assert note.links() == [("https://doi.org/10.1/x", "cites")]


class TestAppendLink:
    def test_a_ref_string_is_written_verbatim(self, tmp_path: Path) -> None:
        src = Note(tmp_path / "src")
        src.write("# S\n")

        append_link(src, "molab:experiment/E1/run/R1", role="derived_from")

        assert src.read().endswith("- [@derived_from R1](molab:experiment/E1/run/R1)\n")

    def test_a_molab_ref_is_written_verbatim(self, tmp_path: Path) -> None:
        from molab.workspace.refs import MolabRef

        src = Note(tmp_path / "src")
        src.write("# S\n")

        append_link(src, MolabRef(experiment_id="E1", run_id="R1"), role="derived_from")

        assert src.read().endswith("- [@derived_from R1](molab:experiment/E1/run/R1)\n")


class TestConceptWrite:
    def test_finding_write_renders_the_source_link_once(self, tmp_path: Path) -> None:
        from molab.knowledge.concepts import Finding
        from molab.knowledge.knowledge_item import SourceRef

        finding = Finding(
            tmp_path / "f",
            sources=[SourceRef(kind="run", ref="molab:experiment/E1/run/R1")],
        )

        finding.write("# F\n")

        text = finding.path.read_text()
        assert "sources:" not in text
        assert finding.read() == "# F\n- [@derived_from R1](molab:experiment/E1/run/R1)\n"

        finding.write("# G\n")

        body = finding.read()
        assert body.startswith("# G\n")
        assert body.count("- [@derived_from R1](molab:experiment/E1/run/R1)") == 1

    def test_a_legacy_disk_file_keeps_its_sources_key(self, tmp_path: Path) -> None:
        path = tmp_path / "old.md"
        path.write_text("---\nclass: Finding\nsources:\n- kind: run\n  ref: R1\n---\n\n# Old\n")

        opened = Knowledge.open(path)
        opened.write(tags=["t"])

        assert "sources:" in path.read_text()


class TestBacklinksTo:
    def test_a_ref_link_is_found(self, tmp_path: Path) -> None:
        from molab.knowledge.concept import backlinks_to

        ws = Workspace(tmp_path / "lab", name="Lab")
        ws.materialize()
        note = Note(Path(ws.root) / "knowledges" / "a")
        note.write("- [@derived_from R1](molab:experiment/E1/run/R1)\n")

        found = backlinks_to(
            ["molab:experiment/E1/run/R1"],
            within=ws.root,
            fs=LocalFileSystem(),
        )

        assert [(link.source.path, link.role) for link in found] == [(note.path, "derived_from")]
        assert note.backlinks() == []

    def test_concept_backlinks_drop_self_edges(self, tmp_path: Path) -> None:
        from molab.knowledge.concept import backlinks_to

        ws = Workspace(tmp_path / "lab", name="Lab")
        ws.materialize()
        note = Note(Path(ws.root) / "knowledges" / "a")
        note.write("# A\n")
        append_link(note, note, role="cites")

        found = backlinks_to([str(note.path)], within=ws.root, fs=LocalFileSystem())

        assert len(found) == 1
        assert note.backlinks() == []

    def test_a_spanned_ref_matches_the_canonical_target(self, tmp_path: Path) -> None:
        from molab.knowledge.concept import backlinks_to

        ws = Workspace(tmp_path / "lab", name="Lab")
        ws.materialize()
        note = Note(Path(ws.root) / "knowledges" / "a")
        note.write("- [@derived_from R1](molab:experiment/E1/run/R1#L3-L9)\n")

        found = backlinks_to(
            ["molab:experiment/E1/run/R1"],
            within=ws.root,
            fs=LocalFileSystem(),
        )

        assert [(link.source.path, link.role) for link in found] == [(note.path, "derived_from")]


class TestRetargetLinks:
    def test_replaces_the_target_and_keeps_the_label(self) -> None:
        from molab.knowledge.concept import retarget_links

        new, count = retarget_links(
            "[@derived_from run](../runs/seed=1)",
            lambda _target, _image: "X",
        )

        assert new == "[@derived_from run](X)"
        assert count == 1

    def test_image_flag_distinguishes_images(self) -> None:
        from molab.knowledge.concept import retarget_links

        seen: list[tuple[str, bool]] = []

        def _rewrite(target: str, image: bool) -> None:
            seen.append((target, image))

        retarget_links("![f](a.png)\n[a](b.md)\n", _rewrite)

        assert seen == [("a.png", True), ("b.md", False)]

    def test_none_or_the_same_target_keeps_the_text(self) -> None:
        from molab.knowledge.concept import retarget_links

        text = "[a](b.md)"

        assert retarget_links(text, lambda _target, _image: None) == (text, 0)
        assert retarget_links(text, lambda target, _image: target) == (text, 0)

    def test_a_fenced_link_is_offered(self) -> None:
        from molab.knowledge.concept import retarget_links

        seen: list[str] = []
        retarget_links("```\n[a](b.md)\n```\n", lambda target, _image: seen.append(target))

        assert seen == ["b.md"]

    def test_the_private_wrapper_delegates(self) -> None:
        import inspect

        from molab.knowledge.concept import _retarget_links

        assert "retarget_links(" in inspect.getsource(_retarget_links)


class TestAppendSourceLinks:
    def test_qualified_sources_append_once_each(self) -> None:
        from molab.knowledge.concept import append_source_links
        from molab.knowledge.knowledge_item import SourceRef
        from molab.workspace.refs import MolabRef

        run_ref = str(MolabRef(experiment_id="E", run_id="R"))
        experiment_ref = str(MolabRef(experiment_id="E"))
        sources = [
            SourceRef(kind="run", ref=run_ref),
            SourceRef(kind="experiment", ref=experiment_ref),
        ]

        body, appended = append_source_links("", sources, base_dir="/w")

        assert appended == 2
        assert body == (f"- [@derived_from R]({run_ref})\n- [@derived_from E]({experiment_ref})\n")

    def test_an_existing_link_is_not_duplicated(self) -> None:
        from molab.knowledge.concept import append_source_links
        from molab.knowledge.knowledge_item import SourceRef
        from molab.workspace.refs import MolabRef

        run_ref = str(MolabRef(experiment_id="E", run_id="R"))
        experiment_ref = str(MolabRef(experiment_id="E"))
        body = f"- [@derived_from R]({run_ref})\n"

        new, appended = append_source_links(
            body,
            [
                SourceRef(kind="run", ref=run_ref),
                SourceRef(kind="experiment", ref=experiment_ref),
            ],
            base_dir="/w",
        )

        assert appended == 1
        assert new.count(run_ref) == 1
        assert experiment_ref in new

    def test_duplicate_inputs_append_once(self) -> None:
        from molab.knowledge.concept import append_source_links
        from molab.knowledge.knowledge_item import SourceRef
        from molab.workspace.refs import MolabRef

        source = SourceRef(kind="run", ref=str(MolabRef(experiment_id="E", run_id="R")))

        _body, appended = append_source_links("", [source, source], base_dir="/w")

        assert appended == 1

    def test_a_reference_source_uses_cites(self) -> None:
        from molab.knowledge.concept import append_source_links
        from molab.knowledge.knowledge_item import SourceRef

        body, appended = append_source_links(
            "",
            [SourceRef(kind="reference", ref="https://doi.org/10.1/x")],
            base_dir="/w",
        )

        assert appended == 1
        assert "@cites" in body

    def test_a_bare_run_id_raises(self) -> None:
        from molab.knowledge.concept import append_source_links
        from molab.knowledge.knowledge_item import SourceRef

        with pytest.raises(ValueError):
            append_source_links("", [SourceRef(kind="run", ref="R")], base_dir="/w")

    def test_the_line_comes_from_source_ref_and_one_formatter(self) -> None:
        import ast
        import inspect

        import molab.knowledge as knowledge
        from molab.knowledge import concept as concept_mod

        assert "link_line" in inspect.getsource(concept_mod.append_source_links)
        for name in ("retarget_links", "append_source_links", "remove_legacy_files"):
            assert name in concept_mod.__all__
            assert name not in knowledge.__all__
        offenders: list[str] = []
        root = Path("src/molab/knowledge")
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.JoinedStr):
                    continue
                literal = "".join(
                    part.value
                    if isinstance(part, ast.Constant) and isinstance(part.value, str)
                    else ""
                    for part in node.values
                )
                if "- [" in literal and "](" in literal:
                    offenders.append(f"{path}:{node.lineno}")
        assert offenders == ["src/molab/knowledge/edges.py:96"]


class TestConceptWriteReplace:
    def test_replace_persists_the_text_and_drops_sources(self, tmp_path: Path) -> None:
        from molab.knowledge.concepts import Finding

        path = tmp_path / "f.md"
        path.write_text("---\nclass: Finding\nsources:\n- kind: run\n  ref: R1\n---\n\n# F\n")
        finding = Finding._from_disk(str(path))
        text = "---\nclass: Finding\n---\n\n# F\n"

        finding.write(text, replace=True)

        assert path.read_text(encoding="utf-8") == text

    def test_a_class_mismatch_or_non_str_is_refused(self, tmp_path: Path) -> None:
        from molab.knowledge.concepts import Finding

        path = tmp_path / "f.md"
        original = "---\nclass: Finding\n---\n\n# F\n"
        path.write_text(original)
        finding = Finding._from_disk(str(path))

        with pytest.raises(ValueError):
            finding.write("---\nclass: Note\n---\n\n# N\n", replace=True)
        with pytest.raises(TypeError):
            finding.write({"class": "Finding"}, replace=True)

        assert path.read_text(encoding="utf-8") == original

    def test_equal_bytes_are_not_rewritten(self, tmp_path: Path) -> None:
        from molab.knowledge.concepts import Finding

        path = tmp_path / "f.md"
        text = "---\nclass: Finding\n---\n\n# F\n"
        path.write_text(text)
        finding = Finding._from_disk(str(path))
        before = path.stat().st_mtime_ns

        finding.write(text, replace=True)

        assert path.stat().st_mtime_ns == before


class TestConceptWriteDocument:
    def test_a_legacy_observation_is_persisted_verbatim(self, tmp_path: Path) -> None:
        text = "---\nclass: Observation\nsources:\n- kind: run\n  ref: R\n---\n\n# obs\n"
        path = tmp_path / "knowledges" / "obs-1.md"

        handle = Concept.write_document(path, text)

        assert type(handle).__name__ == "Observation"
        assert path.read_text(encoding="utf-8") == text

    def test_a_missing_or_unknown_class_writes_nothing(self, tmp_path: Path) -> None:
        missing = tmp_path / "missing.md"
        unknown = tmp_path / "unknown.md"

        with pytest.raises(ValueError):
            Concept.write_document(missing, "# hi\n")
        with pytest.raises(ValueError):
            Concept.write_document(unknown, "---\nclass: Widget\n---\n\n")

        assert not missing.exists()
        assert not unknown.exists()


class TestRemoveLegacyFiles:
    def test_named_files_go_and_an_attachment_stays(self, tmp_path: Path) -> None:
        from molab.knowledge.concept import remove_legacy_files

        directory = tmp_path / "obs-1"
        directory.mkdir()
        (directory / "observation.json").write_text("{}\n")
        (directory / "index.md").write_text("# i\n")
        (directory / "fig.png").write_bytes(b"PNG")

        left = remove_legacy_files(
            directory,
            ["observation.json", "index.md"],
            fs=LocalFileSystem(),
        )

        assert left == ["fig.png"]
        assert directory.is_dir()
        assert (directory / "fig.png").read_bytes() == b"PNG"
        assert not (directory / "index.md").exists()

    def test_an_empty_directory_is_removed(self, tmp_path: Path) -> None:
        from molab.knowledge.concept import remove_legacy_files

        directory = tmp_path / "obs-1"
        directory.mkdir()
        (directory / "index.md").write_text("x")

        assert remove_legacy_files(directory, ["index.md"], fs=LocalFileSystem()) == []
        assert not directory.exists()

    def test_absent_names_are_ignored(self, tmp_path: Path) -> None:
        from molab.knowledge.concept import remove_legacy_files

        directory = tmp_path / "d"
        directory.mkdir()
        (directory / "a.txt").write_text("a")

        assert remove_legacy_files(directory, ["missing.txt"], fs=LocalFileSystem()) == ["a.txt"]

    def test_a_slash_in_the_name_is_refused(self, tmp_path: Path) -> None:
        from molab.knowledge.concept import remove_legacy_files

        directory = tmp_path / "d"
        directory.mkdir()

        with pytest.raises(ValueError):
            remove_legacy_files(directory, ["a/b"], fs=LocalFileSystem())

    def test_a_subdirectory_is_kept(self, tmp_path: Path) -> None:
        from molab.knowledge.concept import remove_legacy_files

        directory = tmp_path / "d"
        (directory / "nested").mkdir(parents=True)
        (directory / "nested" / "x").write_text("x")

        left = remove_legacy_files(directory, ["nested"], fs=LocalFileSystem())

        assert left == ["nested"]
        assert (directory / "nested" / "x").is_file()


class TestConceptOpen:
    def test_a_directory_is_not_a_document(self, tmp_path: Path) -> None:
        directory = tmp_path / "note"
        directory.mkdir()
        (directory / "note.json").write_text("{}\n")
        (directory / "index.md").write_text("# Old\n")

        with pytest.raises(KnowledgeNotFoundError):
            Knowledge.open(directory)

    def test_frontmatter_class_selects_the_subclass(self, tmp_path: Path) -> None:
        path = tmp_path / "knowledges" / "f.md"
        path.parent.mkdir()
        path.write_text("---\nclass: Finding\n---\n\n# F\n")

        assert type(Knowledge.open(path)).__name__ == "Finding"

    def test_an_unknown_class_opens_as_note(self, tmp_path: Path) -> None:
        path = tmp_path / "knowledges" / "x.md"
        path.parent.mkdir()
        path.write_text("---\nclass: Widget\n---\n\n# X\n")

        assert type(Knowledge.open(path)).__name__ == "Note"

    def test_a_suffixless_path_opens_the_markdown_file(self, tmp_path: Path) -> None:
        path = tmp_path / "knowledges" / "f.md"
        path.parent.mkdir()
        path.write_text("---\nclass: Note\n---\n\n# F\n")

        opened = Knowledge.open(path.with_suffix(""))

        assert opened.path == path


class TestKnowledgeRootHandle:
    def test_document_verbs_are_refused(self, tmp_path: Path) -> None:
        handle = Knowledge(tmp_path)

        for verb in ("write", "read", "tags", "frontmatter"):
            with pytest.raises(TypeError, match="root handle"):
                getattr(handle, verb)("x") if verb == "write" else getattr(handle, verb)()
        with pytest.raises(TypeError, match="root handle"):
            handle.delete()
        with pytest.raises(TypeError, match="root handle"):
            handle.rename("x")
        assert tmp_path.is_dir()

        assert handle.type() == "concept"
        for name in ("read_meta", "write_meta", "read_index", "write_index", "_persist"):
            assert not hasattr(Concept, name)

    def test_a_note_type_does_not_read_the_file(self, tmp_path: Path) -> None:
        from molab.fs.local import LocalFileSystem

        class _Counting(LocalFileSystem):
            def __init__(self) -> None:
                self.reads = 0

            def read_text(self, path, encoding="utf-8"):  # type: ignore[no-untyped-def]
                self.reads += 1
                return super().read_text(path, encoding=encoding)

        disk = _Counting()
        note = Note(tmp_path / "a.md", fs=disk)

        assert note.type() == "note.note"
        assert disk.reads == 0
