"""CLI knowledge commands open trees with Knowledge(root)."""

from __future__ import annotations

import inspect
from pathlib import Path

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
        assert "Knowledge.open" in read_src
        assert "open(root / rel" in read_src

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


class TestSourcesAdd:
    def test_a_legacy_directory_holds_no_documents(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr("molab.knowledge.sources.USER_DIR", tmp_path / "user")
        root = tmp_path / "wiki"
        (root / "x").mkdir(parents=True)
        (root / "x" / "note.json").write_text("{}\n", encoding="utf-8")

        result = CliRunner().invoke(knowledge_app, ["sources", "add", "lab-wiki", str(root)])

        assert result.exit_code == 0, result.output
        assert "holds no knowledge documents yet" in result.stdout

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
