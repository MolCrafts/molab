"""Knowledge routes delegate to Knowledge.walk / search / from_dir."""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import get_args

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


class TestKnowledgeRouteRedirect:
    """The route reaches knowledge through ``molab.knowledge``, never workspace shims."""

    _WORKSPACE_SHIMS = (
        "molab.workspace.bundle",
        "molab.workspace.edges",
        "molab.workspace.concepts",
        "molab.workspace.doc_embed",
        "molab.workspace.bundle_index",
        "molab.workspace.knowledge",
    )

    def test_route_module_imports_knowledge_layer(self) -> None:
        src = inspect.getsource(knowledge_routes)
        for shim in self._WORKSPACE_SHIMS:
            assert shim not in src, shim
        for owned in ("molab.knowledge.bundle", "molab.knowledge.errors", "molab.knowledge.embed"):
            assert owned in src, owned

    def test_knowledge_symbols_import(self) -> None:
        from molab.knowledge.bundle import Bundle
        from molab.knowledge.bundle_index import extract_title
        from molab.knowledge.concepts import Note, parse_knowledge_class
        from molab.knowledge.edges import EdgeRole
        from molab.knowledge.embed import default_role_for, resolve_embed_target, summarize_entity
        from molab.knowledge.errors import ConceptNotFoundError

        assert all(
            callable(obj)
            for obj in (
                extract_title,
                parse_knowledge_class,
                default_role_for,
                resolve_embed_target,
                summarize_entity,
            )
        )
        assert parse_knowledge_class("Note") is Note
        assert issubclass(ConceptNotFoundError, LookupError)
        assert set(get_args(EdgeRole)) == {
            "derived_from",
            "cites",
            "supersedes",
            "records",
            "references",
        }
        # The route module holds the knowledge layer's own objects.
        assert knowledge_routes.Bundle is Bundle
        assert knowledge_routes.Note is Note
        assert knowledge_routes.EdgeRole is EdgeRole

    def test_search_parses_class_through_knowledge(self) -> None:
        src = inspect.getsource(knowledge_routes.search_knowledge)
        assert "molab.knowledge" in src
        assert "parse_knowledge_class" in src
        assert "molab.workspace.knowledge" not in src

    def test_embeddoc_delegates_knowledge_edge_writer(self) -> None:
        src = inspect.getsource(knowledge_routes.embed_doc)
        assert "molab.knowledge.embed" in src
        assert "resolve_embed_target" in src
        assert ".link(" in src
        assert "bundle.embed(" not in src

    def test_missing_note_is_404(self, tmp_path: Path) -> None:
        client, _ws = _client(tmp_path)
        with client:
            response = client.get("/api/knowledge/note", params={"path": "knowledges/nope"})
        set_workspace_path_override(None)
        assert response.status_code == 404

    def test_missing_backlink_target_is_404(self, tmp_path: Path) -> None:
        client, _ws = _client(tmp_path)
        with client:
            response = client.get("/api/knowledge/backlinks", params={"path": "knowledges/nope"})
        set_workspace_path_override(None)
        assert response.status_code == 404


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
