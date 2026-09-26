"""Knowledge routes delegate to Knowledge.walk / search / from_dir."""

from __future__ import annotations

import inspect
import re
from collections.abc import Callable
from pathlib import Path
from typing import get_args

import pytest
from fastapi.testclient import TestClient

from molab.knowledge import Knowledge, Note
from molab.server.routes import knowledge as knowledge_routes
from molab.workspace import Experiment, Run, Workspace

ServedFactory = Callable[..., TestClient]
RunFixture = tuple[Workspace, Experiment, Run]

_MD_LINK = re.compile(r"\[[^\]]*\]\([^)]+\)")


@pytest.fixture
def lab(fresh_run: RunFixture) -> RunFixture:
    """A workspace holding one run and the markdown note ``knowledges/idea.md``."""
    ws, _exp, _run = fresh_run
    note = Note(Path(str(ws.root)) / "knowledges" / "idea")
    note.write("# Cooling rate\n")
    return fresh_run


def _listed_names(client: TestClient) -> list[str]:
    response = client.get("/api/knowledge")
    assert response.status_code == 200, response.text
    return [row["name"] for row in response.json()["notes"]]


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

    def test_missing_note_is_404(self, served: ServedFactory, lab: RunFixture) -> None:
        ws, _exp, _run = lab
        with served(ws) as client:
            response = client.get("/api/knowledge/note", params={"path": "knowledges/nope"})
        assert response.status_code == 404

    def test_missing_backlink_target_is_404(self, served: ServedFactory, lab: RunFixture) -> None:
        ws, _exp, _run = lab
        with served(ws) as client:
            response = client.get("/api/knowledge/backlinks", params={"path": "knowledges/nope"})
        assert response.status_code == 404


class TestListKnowledge:
    def test_list_calls_walk(self) -> None:
        src = inspect.getsource(knowledge_routes.list_knowledge)
        assert "Knowledge(" in src
        assert ".walk()" in src
        assert "bundle.notes" not in src

    def test_list_returns_note(self, served: ServedFactory, lab: RunFixture) -> None:
        ws, _exp, _run = lab
        with served(ws) as client:
            response = client.get("/api/knowledge")
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

    def test_search_finds_note(self, served: ServedFactory, lab: RunFixture) -> None:
        ws, _exp, _run = lab
        with served(ws) as client:
            response = client.get("/api/knowledge/search", params={"q": "cooling"})
        assert response.status_code == 200
        hits = response.json()["hits"]
        assert hits


class TestGetNote:
    def test_get_uses_open(self) -> None:
        src = inspect.getsource(knowledge_routes.get_note)
        assert "open" in src

    def test_get_returns_body(self, served: ServedFactory, lab: RunFixture) -> None:
        ws, _exp, _run = lab
        with served(ws) as client:
            response = client.get("/api/knowledge/note", params={"path": "knowledges/idea.md"})
        assert response.status_code == 200
        assert "Cooling rate" in response.json()["body"]


class TestEditDoc:
    def test_edit_writes_finding_body(self, served: ServedFactory, lab: RunFixture) -> None:
        from molab.knowledge import Finding, SourceRef

        ws, _exp, _run = lab
        finding = Finding(
            Path(str(ws.root)) / "knowledges" / "tg",
            sources=[SourceRef(kind="file", ref="index.md")],
        )
        finding.write("# Tg\n")
        with served(ws) as client:
            response = client.put(
                "/api/knowledge/doc",
                params={"path": "knowledges/tg.md"},
                json={"body": "$x^2$\n"},
            )
        assert response.status_code == 200, response.text
        assert "$x^2$" in response.json()["body"]
        assert "$x^2$" in Path(finding.path).read_text()


class TestUpdateDocMeta:
    """``update_doc_meta``: tags / status of any of the six classes."""

    def test_meta_patch_updates_markdown_doc_tags(
        self, served: ServedFactory, lab: RunFixture
    ) -> None:
        ws, _exp, _run = lab
        with served(ws) as client:
            response = client.patch(
                "/api/knowledge/doc/meta",
                params={"path": "knowledges/idea.md"},
                json={"tags": ["glass"]},
            )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["relPath"] == "knowledges/idea.md"
        assert body["tags"] == ["glass"]
        assert Knowledge.open(Path(str(ws.root)) / "knowledges" / "idea.md").tags() == ["glass"]


class TestCreateDoc:
    """``create_doc``: a new Note document."""

    @pytest.mark.xfail(
        strict=True,
        raises=AssertionError,
        reason=(
            "arch-own-06: POST /api/knowledge/doc — a created document lands at "
            "knowledges/<name>.md and is listed"
        ),
    )
    def test_create_lands_under_knowledges(self, served: ServedFactory, lab: RunFixture) -> None:
        ws, _exp, _run = lab
        with served(ws) as client:
            response = client.post(
                "/api/knowledge/doc",
                json={"name": "cooling-idea", "body": "# Cooling idea\n"},
            )
            names = _listed_names(client)
        assert response.status_code == 201, response.text
        assert response.json()["relPath"] == "knowledges/cooling-idea.md"
        assert "cooling-idea" in names


class TestEmbedDoc:
    """``embed_doc``: one typed link from a document to a live entity."""

    @pytest.mark.xfail(
        strict=True,
        raises=AssertionError,
        reason=(
            "arch-own-06: POST /api/knowledge/doc/embed — embedding a run into a "
            "markdown document appends exactly one markdown link"
        ),
    )
    def test_embed_into_markdown_doc(self, served: ServedFactory, lab: RunFixture) -> None:
        ws, _exp, run = lab
        doc = Path(str(ws.root)) / "knowledges" / "idea.md"
        links_before = len(_MD_LINK.findall(doc.read_text()))
        with served(ws) as client:
            response = client.post(
                "/api/knowledge/doc/embed",
                params={"path": "knowledges/idea.md"},
                json={"target_kind": "run", "target": run.id},
            )
        assert response.status_code == 200, response.text
        assert response.json()["target"] == run.id
        assert len(_MD_LINK.findall(doc.read_text())) == links_before + 1


class TestMoveDoc:
    """``move_doc``: rename a document."""

    @pytest.mark.xfail(
        strict=True,
        raises=AssertionError,
        reason=(
            "arch-own-06: PATCH /api/knowledge/doc — renaming a markdown document "
            "moves knowledges/<old>.md to knowledges/<new>.md"
        ),
    )
    def test_rename_markdown_doc(self, served: ServedFactory, lab: RunFixture) -> None:
        ws, _exp, _run = lab
        with served(ws) as client:
            response = client.patch(
                "/api/knowledge/doc",
                params={"path": "knowledges/idea.md"},
                json={"name": "idea-renamed"},
            )
        assert response.status_code == 200, response.text
        assert response.json()["relPath"] == "knowledges/idea-renamed.md"
        assert not (Path(str(ws.root)) / "knowledges" / "idea.md").exists()


class TestDeleteDoc:
    """``delete_doc``: remove a document."""

    @pytest.mark.xfail(
        strict=True,
        raises=AssertionError,
        reason=(
            "arch-own-06: DELETE /api/knowledge/doc — a markdown document is "
            "deleted and no longer listed"
        ),
    )
    def test_delete_markdown_doc(self, served: ServedFactory, lab: RunFixture) -> None:
        ws, _exp, _run = lab
        with served(ws) as client:
            response = client.delete("/api/knowledge/doc", params={"path": "knowledges/idea.md"})
            names = _listed_names(client)
        assert response.status_code == 200, response.text
        assert not (Path(str(ws.root)) / "knowledges" / "idea.md").exists()
        assert "idea" not in names


class TestGetBacklinks:
    """``get_backlinks``: every document linking at one document."""

    @pytest.mark.xfail(
        strict=True,
        raises=AssertionError,
        reason=(
            "arch-own-06: GET /api/knowledge/backlinks — a markdown document's "
            "backlinks list the markdown documents citing it"
        ),
    )
    def test_backlinks_of_markdown_doc(self, served: ServedFactory, lab: RunFixture) -> None:
        ws, _exp, _run = lab
        root = Path(str(ws.root))
        a = Note(root / "knowledges" / "a")
        a.write("# A\n")
        b = Note(root / "knowledges" / "b")
        b.write("# B\n")
        a.cite(b)
        with served(ws) as client:
            response = client.get("/api/knowledge/backlinks", params={"path": "knowledges/b.md"})
        assert response.status_code == 200, response.text
        assert [row["relPath"] for row in response.json()["backlinks"]] == ["knowledges/a.md"]


class TestExportDoc:
    """``export_doc``: portable markdown of one document."""

    @pytest.mark.xfail(
        strict=True,
        raises=AssertionError,
        reason=(
            "arch-own-06: GET /api/knowledge/doc/export — a markdown document "
            "exports as text/markdown"
        ),
    )
    def test_export_markdown_doc(self, served: ServedFactory, lab: RunFixture) -> None:
        ws, _exp, _run = lab
        with served(ws) as client:
            response = client.get(
                "/api/knowledge/doc/export", params={"path": "knowledges/idea.md"}
            )
        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith("text/markdown")
        assert "Cooling rate" in response.text


class TestEntityBacklinks:
    """``entity_backlinks``: knowledge documents citing a run / experiment."""

    @pytest.mark.xfail(
        strict=True,
        raises=AssertionError,
        reason=(
            "arch-own-06: GET /api/knowledge/entity-backlinks — a Finding harvested "
            "from a run is listed as that run's backlink"
        ),
    )
    def test_harvested_finding_backlinks_run(
        self, served: ServedFactory, terminal_run: RunFixture
    ) -> None:
        ws, exp, run = terminal_run
        with served(ws) as client:
            harvest = client.post(
                f"/api/projects/{exp.project.id}/experiments/{exp.id}/runs/{run.id}/harvest",
                json={"cls": "Finding", "narrative": "Tg rose with cooling rate."},
            )
            assert harvest.status_code == 200, harvest.text
            response = client.get(
                "/api/knowledge/entity-backlinks",
                params={
                    "kind": "run",
                    "projectId": exp.project.id,
                    "experimentId": exp.id,
                    "runId": run.id,
                },
            )
        assert response.status_code == 200, response.text
        rows = response.json()["backlinks"]
        assert len(rows) == 1
        assert rows[0]["path"].endswith(harvest.json()["name"] + ".md")
