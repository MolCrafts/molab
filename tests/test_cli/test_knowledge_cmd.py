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

    def test_init_with_title_writes_child_note(self, tmp_path: Path) -> None:
        target = tmp_path / "wiki"
        result = CliRunner().invoke(knowledge_app, ["init", str(target), "--title", "Cooling"])
        assert result.exit_code == 0
        note = Note(target / "cooling")
        assert (note.path / "note.json").is_file()
        assert "Cooling" in note.read()
        assert not (note.path / "meta.json").exists()


class TestKnowledgeSearch:
    def test_search_uses_knowledge_handle(self) -> None:
        from molab.cli import knowledge_cmd

        search_src = inspect.getsource(knowledge_cmd.knowledge_search)
        assert "Knowledge(ws_root).search" in search_src
        assert "Bundle" not in inspect.getsource(knowledge_cmd)


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


class TestImportZotero:
    def test_import_uses_knowledge_not_bundle(self) -> None:
        from molab.cli import knowledge_cmd

        src = inspect.getsource(knowledge_cmd.import_zotero)
        assert "Knowledge(" in src
        assert "import_zotero" in src
        assert "Bundle" not in src
        assert "ReferenceConcept" not in src
