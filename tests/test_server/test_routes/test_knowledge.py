"""Knowledge routes delegate to Knowledge.walk / search / from_dir."""

from __future__ import annotations

import inspect
from pathlib import Path

from fastapi.testclient import TestClient

from molab.knowledge import Note
from molab.server.app import create_app
from molab.server.dependencies import set_workspace_path_override
from molab.server.routes import knowledge as knowledge_routes
from molab.workspace import Workspace


def _client(tmp_path: Path) -> tuple[TestClient, Workspace]:
    ws = Workspace(tmp_path / "ws", name="lab")
    ws.materialize()
    note = Note(Path(str(ws.root)) / "knowledges" / "idea")
    note.write("# Cooling rate\n")
    set_workspace_path_override(Path(str(ws.root)))
    app = create_app(serve_static=False)
    return TestClient(app), ws


class TestListKnowledge:
    def test_list_calls_walk(self) -> None:
        src = inspect.getsource(knowledge_routes.list_knowledge)
        assert "Knowledge(" in src
        assert ".walk()" in src
        assert "bundle.notes" not in src

    def test_list_returns_note(self, tmp_path: Path) -> None:
        client, _ws = _client(tmp_path)
        with client:
            response = client.get("/api/knowledge")
        set_workspace_path_override(None)
        assert response.status_code == 200
        body = response.json()
        assert body["total"] >= 1
        assert any(row["name"] == "idea" and row.get("cls") == "Note" for row in body["notes"])


class TestSearchKnowledge:
    def test_search_calls_knowledge_search(self) -> None:
        src = inspect.getsource(knowledge_routes.search_knowledge)
        assert "Knowledge(" in src
        assert ".search(" in src
        assert "Bundle.search" not in src
        assert "_bundle(workspace).search" not in src

    def test_search_finds_note(self, tmp_path: Path) -> None:
        client, _ws = _client(tmp_path)
        with client:
            response = client.get("/api/knowledge/search", params={"q": "cooling"})
        set_workspace_path_override(None)
        assert response.status_code == 200
        hits = response.json()["hits"]
        assert hits


class TestGetNote:
    def test_get_uses_open(self) -> None:
        src = inspect.getsource(knowledge_routes.get_note)
        assert "open" in src

    def test_get_returns_body(self, tmp_path: Path) -> None:
        client, _ws = _client(tmp_path)
        with client:
            response = client.get("/api/knowledge/note", params={"path": "knowledges/idea.md"})
        set_workspace_path_override(None)
        assert response.status_code == 200
        assert "Cooling rate" in response.json()["body"]


class TestEditDoc:
    def test_edit_writes_finding_body(self, tmp_path: Path) -> None:
        from molab.knowledge import Finding, SourceRef

        client, ws = _client(tmp_path)
        finding = Finding(
            Path(str(ws.root)) / "knowledges" / "tg",
            sources=[SourceRef(kind="file", ref="index.md")],
        )
        finding.write("# Tg\n")
        with client:
            response = client.put(
                "/api/knowledge/doc",
                params={"path": "knowledges/tg.md"},
                json={"body": "$x^2$\n"},
            )
        set_workspace_path_override(None)
        assert response.status_code == 200, response.text
        assert "$x^2$" in response.json()["body"]
        assert "$x^2$" in Path(finding.path).read_text()
