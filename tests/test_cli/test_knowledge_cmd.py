"""CLI knowledge commands open trees with Knowledge(root)."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from typer.testing import CliRunner

from molab.cli.knowledge_cmd import knowledge_app
from molab.knowledge import Note


class TestKnowledgeInit:
    def test_init_root_has_no_meta_or_note_json(self, tmp_path: Path) -> None:
        target = tmp_path / "wiki"
        result = CliRunner().invoke(knowledge_app, ["init", str(target)])
        assert result.exit_code == 0
        assert target.is_dir()
        assert not (target / "meta.json").exists()
        assert not (target / "note.json").exists()

    def test_init_wiki_title_lands_at_the_wiki_root(self, tmp_path: Path) -> None:
        target = tmp_path / "wiki"
        result = CliRunner().invoke(knowledge_app, ["init", str(target), "--title", "Cooling"])
        assert result.exit_code == 0, result.output
        assert (target / "cooling.md").is_file()
        assert not (target / "knowledges").exists()

    def test_init_workspace_root_lands_in_knowledges(self, tmp_path: Path) -> None:
        from molab.workspace import Workspace

        ws = Workspace(tmp_path / "lab", name="lab")
        ws.materialize()
        result = CliRunner().invoke(knowledge_app, ["init", str(ws.root), "--title", "Cooling"])
        assert result.exit_code == 0, result.output
        assert (Path(str(ws.root)) / "knowledges" / "cooling.md").is_file()

    def test_init_inside_a_workspace_exits(self, tmp_path: Path) -> None:
        from molab.workspace import Workspace

        ws = Workspace(tmp_path / "lab", name="lab")
        ws.materialize()
        experiment = ws.add_project("p").add_experiment("e")
        before = {path for path in Path(str(experiment.resolve())).rglob("*") if path.is_file()}
        result = CliRunner().invoke(
            knowledge_app, ["init", str(experiment.resolve()), "--title", "Cooling"]
        )
        assert result.exit_code == 1
        assert "lives on a host" in result.output
        after = {path for path in Path(str(experiment.resolve())).rglob("*") if path.is_file()}
        assert after == before


class TestKnowledgeSearch:
    def test_search_uses_knowledge_handle(self) -> None:
        from molab.cli import knowledge_cmd

        search_src = inspect.getsource(knowledge_cmd.knowledge_search)
        assert "Knowledge(ws_root).search" in search_src
        assert "Bun" + "dle" not in inspect.getsource(knowledge_cmd)
        assert "class name" in search_src
        assert '"workspace.json"' not in inspect.getsource(knowledge_cmd)


class TestKnowledgeRead:
    def test_read_uses_open(self) -> None:
        from molab.cli import knowledge_cmd

        read_src = inspect.getsource(knowledge_cmd.knowledge_read)
        assert "_open_document" in read_src
        assert "_open_document(root / rel" in read_src

    def test_read_prints_note_body(self, tmp_path: Path) -> None:
        from molab.workspace import Workspace

        ws = Workspace(tmp_path / "ws", name="lab")
        ws.materialize()
        note = Note(Path(str(ws.root)) / "idea")
        note.write("# Cooling rate\n")
        result = CliRunner().invoke(knowledge_app, ["read", "idea", "--path", str(ws.root)])
        assert result.exit_code == 0
        assert "Cooling rate" in result.stdout

    def test_read_prints_the_markdown_file(self, tmp_path: Path) -> None:
        from molab.workspace import Workspace

        ws = Workspace(tmp_path / "ws", name="lab")
        ws.materialize()
        note = Note(Path(str(ws.root)) / "knowledges" / "idea")
        note.write("# Cooling rate\n")
        result = CliRunner().invoke(
            knowledge_app, ["read", "knowledges/idea.md", "--path", str(ws.root)]
        )
        assert result.exit_code == 0, result.output
        assert f"file: {note.path}" in result.stdout
        assert str(note.path).endswith("knowledges/idea.md")
        assert "index.md" not in result.stdout


class TestKnowledgeWrite:
    def test_write_lands_a_note_on_the_run(self, tmp_path: Path) -> None:
        from molab.workspace import Workspace

        ws = Workspace(tmp_path / "lab", name="lab")
        ws.materialize()
        run = ws.add_project("p").add_experiment("e").add_run(params={"seed": 1})
        result = CliRunner().invoke(
            knowledge_app,
            [
                "write",
                "rdf",
                "5 ns later the RDF converged",
                "--on",
                run.id,
                "--path",
                str(ws.root),
            ],
        )
        assert result.exit_code == 0, result.output
        landed = Path(str(run.resolve())) / "knowledges" / "rdf.md"
        assert landed.is_file()
        assert "RDF converged" in landed.read_text(encoding="utf-8")
        assert "knowledges/rdf.md" in result.stdout

    def test_write_format_html_lands_an_html_document(self, tmp_path: Path) -> None:
        from molab.workspace import Workspace

        ws = Workspace(tmp_path / "lab", name="lab")
        ws.materialize()
        args = ["write", "page", "<p>hello</p>", "--path", str(ws.root)]
        result = CliRunner().invoke(knowledge_app, [*args, "--format", "html"])
        assert result.exit_code == 0, result.output
        landed = Path(str(ws.root)) / "knowledges" / "page.html"
        assert landed.read_text(encoding="utf-8").startswith("<!doctype html>")
        assert "knowledges/page.html" in result.stdout

        again = CliRunner().invoke(knowledge_app, [*args, "--format", "md"])
        assert again.exit_code == 1
        assert "already exists" in again.output
        bad = CliRunner().invoke(knowledge_app, [*args, "--format", "rst"])
        assert bad.exit_code == 1
        assert "--format" in bad.output

    def test_write_plan_records_a_file_and_a_doi(self, tmp_path: Path) -> None:
        from molab.workspace import Workspace

        ws = Workspace(tmp_path / "lab", name="lab")
        ws.materialize()
        brief = tmp_path / "brief.pdf"
        brief.write_text("plan", encoding="utf-8")
        doi = "10.1021/jp409664d"
        result = CliRunner().invoke(
            knowledge_app,
            [
                "write",
                "PBIX plan",
                "The question.",
                "--class",
                "Plan",
                "--source",
                str(brief),
                "--source",
                doi,
                "--path",
                str(ws.root),
            ],
        )
        assert result.exit_code == 0, result.output
        text = (Path(str(ws.root)) / "knowledges" / "pbix-plan.md").read_text(encoding="utf-8")
        assert "brief.pdf" in text
        assert "https://doi.org/10.1021/jp409664d" in text
        assert "class: Plan" in text

    def test_write_roadmap_record_cites_the_plan(self, tmp_path: Path) -> None:
        from molab.knowledge import Plan, campaign_of, check_campaign
        from molab.workspace import Workspace

        ws = Workspace(tmp_path / "lab", name="lab")
        ws.materialize()
        root = str(ws.root)
        brief = tmp_path / "brief.pdf"
        brief.write_text("plan", encoding="utf-8")
        plan = CliRunner().invoke(
            knowledge_app,
            [
                "write",
                "PBIX plan",
                "The question.",
                "--class",
                "Plan",
                "--source",
                str(brief),
                "--path",
                root,
            ],
        )
        assert plan.exit_code == 0, plan.output
        plan_path = Path(root) / "knowledges" / "pbix-plan.md"
        record = tmp_path / "roadmap.json"
        record.write_text(
            '{"stages": [{"id": "monomers", "title": "Fragments", "experiment": "monomers"}]}',
            encoding="utf-8",
        )
        roadmap = CliRunner().invoke(
            knowledge_app,
            [
                "write",
                "PBIX roadmap",
                "The order.",
                "--class",
                "Roadmap",
                "--source",
                str(plan_path),
                "--record",
                str(record),
                "--path",
                root,
            ],
        )
        assert roadmap.exit_code == 0, roadmap.output
        text = (Path(root) / "knowledges" / "pbix-roadmap.md").read_text(encoding="utf-8")
        assert "class: Roadmap" in text
        assert "monomers" in text
        campaign = campaign_of(Plan(plan_path))
        check_campaign(campaign)
        assert campaign.roadmaps[0].stages()[0].id == "monomers"

    def test_list_rename_and_delete(self, tmp_path: Path) -> None:
        from molab.workspace import Workspace

        ws = Workspace(tmp_path / "lab", name="lab")
        ws.materialize()
        root = str(ws.root)
        wrote = CliRunner().invoke(knowledge_app, ["write", "idea", "cooling", "--path", root])
        assert wrote.exit_code == 0, wrote.output
        listed = CliRunner().invoke(knowledge_app, ["list", "--path", root])
        assert listed.exit_code == 0, listed.output
        assert "Note\tknowledges/idea.md" in listed.stdout
        renamed = CliRunner().invoke(
            knowledge_app, ["rename", "knowledges/idea.md", "cooling", "--path", root]
        )
        assert renamed.exit_code == 0, renamed.output
        assert (Path(root) / "knowledges" / "cooling.md").is_file()
        deleted = CliRunner().invoke(
            knowledge_app, ["delete", "knowledges/cooling.md", "--path", root]
        )
        assert deleted.exit_code == 0, deleted.output
        assert not (Path(root) / "knowledges" / "cooling.md").exists()

    @pytest.mark.parametrize("level", ["project", "experiment"])
    @pytest.mark.parametrize("container", ["", "/knowledges", "/knowledges/"])
    def test_write_on_a_relative_host_directory(
        self, tmp_path: Path, level: str, container: str
    ) -> None:
        """A workspace-relative ``--on`` (the host or its knowledges/) is that host."""
        from molab.workspace import Workspace
        from molab.workspace.refs import ref_of

        ws = Workspace(tmp_path / "lab", name="lab")
        ws.materialize()
        project = ws.add_project("membranes")
        host = project if level == "project" else project.add_experiment("sweep")
        host_dir = Path(str(host.resolve()))
        rel = host_dir.relative_to(Path(str(ws.root))).as_posix()
        (host_dir / "knowledges").mkdir(exist_ok=True)
        record = tmp_path / "record.json"
        record.write_text('{"tags": ["membrane"]}', encoding="utf-8")
        for name, extra in (("plain", []), ("recorded", ["--record", str(record)])):
            result = CliRunner().invoke(
                knowledge_app,
                [
                    "write", name, "Water uptake plateaus.",
                    "--on", rel + container,
                    "--class", "Observation",
                    "--created-by", "tack",
                    *extra,
                    "--path", str(ws.root),
                ],
            )  # fmt: skip
            assert result.exit_code == 0, result.output
            landed = host_dir / "knowledges" / f"{name}.md"
            assert landed.is_file()
            assert str(ref_of(host)) in landed.read_text(encoding="utf-8")
        assert not (host_dir / "knowledges" / "knowledges").exists()
        assert "membrane" in (host_dir / "knowledges" / "recorded.md").read_text(encoding="utf-8")

    def test_write_on_a_non_host_directory_exits(self, tmp_path: Path) -> None:
        from molab.workspace import Workspace

        ws = Workspace(tmp_path / "lab", name="lab")
        ws.materialize()
        project = ws.add_project("membranes")
        assets = Path(str(project.resolve())) / "assets"
        assets.mkdir(exist_ok=True)
        rel = assets.relative_to(Path(str(ws.root))).as_posix()
        result = CliRunner().invoke(
            knowledge_app,
            ["write", "obs", "text", "--on", rel, "--class", "Observation",
             "--path", str(ws.root)],
        )  # fmt: skip
        assert result.exit_code == 1
        assert "is not a project" in result.output
        assert not (assets / "knowledges").exists()


class TestSourcesAdd:
    def test_a_legacy_directory_holds_no_documents(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr("molab.knowledge.sources.USER_DIR", tmp_path / "user")
        root = tmp_path / "wiki"
        (root / "x").mkdir(parents=True)
        (root / "x" / "note.json").write_text("{}\n", encoding="utf-8")

        result = CliRunner().invoke(knowledge_app, ["sources", "add", "lab-wiki", str(root)])

        assert result.exit_code == 0, result.output
        # Click wraps the note when the path is wider than the terminal.
        assert "holds no knowledge documents yet" in " ".join(result.stdout.split())

    def test_a_markdown_file_is_a_document(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr("molab.knowledge.sources.USER_DIR", tmp_path / "user")
        root = tmp_path / "wiki"
        root.mkdir()
        (root / "a.md").write_text("# A\n", encoding="utf-8")

        result = CliRunner().invoke(knowledge_app, ["sources", "add", "lab-wiki", str(root)])

        assert result.exit_code == 0, result.output
        assert "holds no knowledge documents yet" not in result.stdout

    def test_the_command_does_not_name_a_legacy_head(self) -> None:
        from molab.cli import knowledge_cmd

        assert "note.json" not in inspect.getsource(knowledge_cmd)


class TestImportZotero:
    def test_import_uses_knowledge_not_bundle(self) -> None:
        from molab.cli import knowledge_cmd

        src = inspect.getsource(knowledge_cmd.import_zotero)
        assert "Knowledge(" in src
        assert "import_zotero" in src
        assert "under=ws" in src
        assert "Bun" + "dle" not in src
        assert "ReferenceConcept" not in src

    def test_import_lands_markdown_under_knowledges(self, tmp_path: Path) -> None:
        from molab.workspace import Workspace
        from tests.test_workspace.test_zotero_concepts import _make_zotero_db

        ws = Workspace(tmp_path / "lab", name="lab")
        ws.materialize()
        zot = tmp_path / "zot"
        zot.mkdir()
        db = _make_zotero_db(zot)
        result = CliRunner().invoke(
            knowledge_app, ["import-zotero", str(db), "--dest", str(ws.root)]
        )
        assert result.exit_code == 0, result.output
        landed = list((Path(str(ws.root)) / "knowledges").glob("*.md"))
        assert len(landed) == 2
        assert not (Path(str(ws.root)) / "references").exists()
