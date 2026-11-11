"""Knowledge routes delegate to Knowledge.walk / search / from_dir."""

from __future__ import annotations

import inspect
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, get_args

import pytest
from fastapi.testclient import TestClient

from molab.knowledge import Note
from molab.server.routes import knowledge as knowledge_routes
from molab.workspace import Experiment, Run, Workspace
from molab.workspace.domain import Asset
from molab.workspace.errors import RefNotFoundError
from molab.workspace.refs import REF_SCHEME, InvalidRefError, MolabRef

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
        "molab.workspace.knowledge",
    )

    def test_route_module_imports_knowledge_layer(self) -> None:
        src = inspect.getsource(knowledge_routes)
        for shim in self._WORKSPACE_SHIMS:
            assert shim not in src, shim
        for owned in ("molab.knowledge.errors", "molab.knowledge.embed"):
            assert owned in src, owned
        for gone in (
            "_bundle",
            "Bun" + "dle",
            "_get_entity",
            "read_meta_dict",
            "concept_from_dir",
            "_legacy_path_card",
            "_legacy_entity_dir_targets",
            "qualify_run_id",
        ):
            assert gone not in src, gone

    def test_knowledge_symbols_import(self) -> None:
        from molab.knowledge.concepts import Note, _product
        from molab.knowledge.edges import EdgeRole
        from molab.knowledge.embed import default_role_for, resolve_embed_target, summarize_entity
        from molab.knowledge.errors import ConceptNotFoundError
        from molab.knowledge.search import extract_title

        assert all(
            callable(obj)
            for obj in (
                extract_title,
                _product,
                default_role_for,
                resolve_embed_target,
                summarize_entity,
            )
        )
        assert _product("Note") is Note
        assert issubclass(ConceptNotFoundError, LookupError)
        assert set(get_args(EdgeRole)) == {
            "derived_from",
            "cites",
            "supersedes",
            "supports",
            "contradicts",
            "records",
            "references",
        }
        # The route module holds the knowledge layer's own objects.
        assert knowledge_routes.Note is Note
        assert knowledge_routes.EdgeRole is EdgeRole

    def test_search_parses_class_through_knowledge(self) -> None:
        src = inspect.getsource(knowledge_routes.search_knowledge)
        assert "molab.knowledge" in src
        assert "_product" in src
        assert "Knowledge.parse" not in src
        assert "molab.workspace.knowledge" not in src

    def test_embeddoc_delegates_knowledge_edge_writer(self) -> None:
        src = inspect.getsource(knowledge_routes.embed_doc)
        assert "molab.knowledge.embed" in src
        assert "resolve_embed_target" in src
        assert "append_link(" in src
        assert ".link(" not in src
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

    def test_bundle_only_serves_entity_backlinks(self) -> None:
        src = inspect.getsource(knowledge_routes)
        assert "_resolve_note" not in src
        for name in ("_bundle", "Bun" + "dle", "_get_entity", "read_meta_dict", "concept_from_dir"):
            assert name not in src

    def test_wire_uses_host_path(self) -> None:
        from molab.server.app import create_app

        schemas = create_app(serve_static=False).openapi()["components"]["schemas"]
        for name in ("DocCreateRequest", "DocMoveRequest"):
            props = schemas[name]["properties"]
            assert "hostPath" in props
            assert "parentPath" not in props
        assert "hostPath" in schemas["NoteSummary"]["properties"]


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

    def test_list_reads_the_workspace_disk(self, served: ServedFactory, lab: RunFixture) -> None:
        from molab.fs import LocalFS
        from molab.server.deps.resolution import get_workspace
        from tests.support.counting_fs import CountingFileSystem

        ws, _exp, _run = lab
        fs = CountingFileSystem(LocalFS())
        with served(ws) as client:
            client.app.dependency_overrides[get_workspace] = lambda: Workspace(ws.root, fs=fs)
            fs.reset()
            response = client.get("/api/knowledge")
        assert response.status_code == 200, response.text
        assert fs.for_basename("idea.md", "read_text") > 0
        assert fs.calls["ls"] > 0
        assert "fs=workspace.fs" in inspect.getsource(knowledge_routes.list_knowledge)


class TestSearchKnowledge:
    def test_search_calls_knowledge_search(self) -> None:
        src = inspect.getsource(knowledge_routes.search_knowledge)
        assert "Knowledge(" in src
        assert ".search(" in src
        assert "KnowledgeSourceStore" in src
        assert ("Bun" + "dle") + ".search" not in src
        assert "_bundle(workspace).search" not in src

    def test_search_finds_note(self, served: ServedFactory, lab: RunFixture) -> None:
        ws, _exp, _run = lab
        with served(ws) as client:
            response = client.get("/api/knowledge/search", params={"q": "cooling"})
        assert response.status_code == 200
        hits = response.json()["hits"]
        assert hits

    def test_search_reads_the_workspace_disk(self, served: ServedFactory, lab: RunFixture) -> None:
        from molab.fs import LocalFS
        from molab.server.deps.resolution import get_workspace
        from tests.support.counting_fs import CountingFileSystem

        ws, _exp, _run = lab
        fs = CountingFileSystem(LocalFS())
        with served(ws) as client:
            client.app.dependency_overrides[get_workspace] = lambda: Workspace(ws.root, fs=fs)
            fs.reset()
            response = client.get("/api/knowledge/search", params={"q": "cooling"})
        assert response.status_code == 200, response.text
        hits = response.json()["hits"]
        assert any(row["path"] == "knowledges/idea.md" for row in hits)
        assert fs.for_basename("idea.md", "read_text") == 1
        assert "fs=workspace.fs" in inspect.getsource(knowledge_routes.search_knowledge)


class TestTexManuscripts:
    def test_lists_and_reads_manuscript_without_writing_it(
        self, served: ServedFactory, lab: RunFixture
    ) -> None:
        ws, exp, _run = lab
        project = Path(str(exp.resolve())).parent.parent
        tex = project / "manuscript" / "nve-drift.tex"
        tex.parent.mkdir()
        tex.write_text(
            "\\documentclass{article}\n\\begin{document}drift\\end{document}\n",
            encoding="utf-8",
        )
        figures = tex.parent / "figures"
        figures.mkdir()
        (figures / "tab_drift.tex").write_text("% fragment\n", encoding="utf-8")

        with served(ws) as client:
            listed = client.get("/api/knowledge")
            assert listed.status_code == 200, listed.text
            rows = [row for row in listed.json()["notes"] if str(row["relPath"]).endswith(".tex")]
            assert len(rows) == 1
            row = rows[0]
            assert row["name"] == "nve-drift"
            assert row["cls"] == "Tex"
            assert row["relPath"].endswith("manuscript/nve-drift.tex")
            assert row["hostPath"].endswith(project.name)

            opened = client.get("/api/knowledge/note", params={"path": row["relPath"]})
            assert opened.status_code == 200, opened.text
            assert "drift" in opened.json()["body"]

            edited = client.put(
                "/api/knowledge/doc",
                params={"path": row["relPath"]},
                json={"body": "nope"},
            )
            assert edited.status_code == 405, edited.text
        assert tex.read_text(encoding="utf-8").startswith("\\documentclass")


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
        assert "$x^2$" in Path(finding.path).read_text(encoding="utf-8")


class TestUpdateDocMeta:
    """``update_doc_meta``: tags / status of any of the classes."""

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
        assert Note(Path(str(ws.root)) / "knowledges" / "idea.md").tags() == ["glass"]


def _experiment_host(ws: Workspace, exp: Experiment) -> str:
    return Path(str(exp.resolve())).relative_to(Path(str(ws.root))).as_posix()


class TestCreateDoc:
    """``create_doc``: a new Note document."""

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
        assert response.json()["hostPath"] == ""
        assert "cooling-idea" in names

    def test_create_on_experiment_host(self, served: ServedFactory, lab: RunFixture) -> None:
        ws, exp, _run = lab
        host = _experiment_host(ws, exp)
        with served(ws) as client:
            response = client.post(
                "/api/knowledge/doc",
                json={"name": "Idea 2", "hostPath": host},
            )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["hostPath"] == host
        assert body["relPath"] == f"{host}/knowledges/idea-2.md"
        assert (Path(str(exp.resolve())) / "knowledges" / "idea-2.md").is_file()

    def test_unknown_host_is_404(self, served: ServedFactory, lab: RunFixture) -> None:
        ws, _exp, _run = lab
        with served(ws) as client:
            response = client.post(
                "/api/knowledge/doc",
                json={"name": "Nope", "hostPath": "projects/missing"},
            )
        assert response.status_code == 404, response.text

    def test_omitted_host_lands_at_root(self, served: ServedFactory, lab: RunFixture) -> None:
        ws, _exp, _run = lab
        with served(ws) as client:
            response = client.post("/api/knowledge/doc", json={"name": "Root Note"})
        assert response.status_code == 201, response.text
        assert response.json()["hostPath"] == ""
        assert (Path(str(ws.root)) / "knowledges" / "root-note.md").is_file()

    def test_finding_without_a_source_is_422(self, served: ServedFactory, lab: RunFixture) -> None:
        ws, exp, _run = lab
        host = _experiment_host(ws, exp)
        with served(ws) as client:
            response = client.post(
                "/api/knowledge/doc",
                json={"name": "Tg", "cls": "Finding", "hostPath": host, "body": "# Tg\n"},
            )
        assert response.status_code == 422, response.text
        assert not (Path(str(exp.resolve())) / "knowledges" / "tg.md").exists()

    def test_finding_records_the_run_source(self, served: ServedFactory, lab: RunFixture) -> None:
        from molab.workspace.refs import ref_of

        ws, exp, run = lab
        host = _experiment_host(ws, exp)
        target = str(ref_of(run))
        with served(ws) as client:
            response = client.post(
                "/api/knowledge/doc",
                json={
                    "name": "Tg Result",
                    "cls": "Finding",
                    "hostPath": host,
                    "body": "# Tg rose\n",
                    "sources": [{"kind": "run", "ref": target}],
                },
            )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["cls"] == "Finding"
        assert body["relPath"] == f"{host}/knowledges/tg-result.md"
        text = (Path(str(exp.resolve())) / "knowledges" / "tg-result.md").read_text()
        assert "class: Finding" in text
        assert target in text

    def test_literature_stores_bib_fields(self, served: ServedFactory, lab: RunFixture) -> None:
        from molab.knowledge import Literature

        ws, _exp, _run = lab
        with served(ws) as client:
            response = client.post(
                "/api/knowledge/doc",
                json={
                    "name": "Glass Paper",
                    "cls": "Literature",
                    "title": "Glass transition",
                    "authors": ["Lin"],
                    "year": 2020,
                    "doi": "10.1000/glass",
                },
            )
        assert response.status_code == 201, response.text
        assert response.json()["cls"] == "Literature"
        doc = Literature(Path(str(ws.root)) / "knowledges" / "glass-paper.md")
        assert doc.record.title == "Glass transition"
        assert doc.record.authors == ("Lin",)
        assert doc.record.year == 2020
        assert doc.record.doi == "10.1000/glass"

    def test_roadmap_record_round_trips_on_the_note(
        self, served: ServedFactory, lab: RunFixture
    ) -> None:
        from molab.workspace.refs import ref_of

        ws, _exp, run = lab
        with served(ws) as client:
            plan = client.post(
                "/api/knowledge/doc",
                json={
                    "name": "Overview",
                    "cls": "Plan",
                    "body": "# Overview\n",
                    "sources": [{"kind": "run", "ref": str(ref_of(run))}],
                },
            )
            assert plan.status_code == 201, plan.text
            plan_path = plan.json()["relPath"]
            opened_plan = client.get("/api/knowledge/note", params={"path": plan_path})
            assert opened_plan.status_code == 200, opened_plan.text
            assert opened_plan.json()["record"] == {}

            created = client.post(
                "/api/knowledge/doc",
                json={
                    "name": "Stages",
                    "cls": "Roadmap",
                    "body": "Order of the work.\n",
                    "sources": [{"kind": "file", "ref": plan_path}],
                    "record": {
                        "stages": [
                            {"id": "monomers", "title": "Fragments"},
                            {
                                "id": "equilibrate",
                                "title": "Boxes",
                                "depends_on": ["monomers"],
                            },
                        ]
                    },
                },
            )
            assert created.status_code == 201, created.text
            assert created.json()["cls"] == "Roadmap"
            path = created.json()["relPath"]
            opened = client.get("/api/knowledge/note", params={"path": path})
        assert opened.status_code == 200, opened.text
        stages = opened.json()["record"]["stages"]
        assert stages[0]["id"] == "monomers"
        assert stages[1]["depends_on"] == ["monomers"]
        text = (Path(str(ws.root)) / path).read_text(encoding="utf-8")
        assert "knowledges/knowledges" not in text
        assert plan_path.rsplit("/", 1)[-1] in text

    def test_roadmap_without_stages_is_422(self, served: ServedFactory, lab: RunFixture) -> None:
        from molab.workspace.refs import ref_of

        ws, _exp, run = lab
        with served(ws) as client:
            plan = client.post(
                "/api/knowledge/doc",
                json={
                    "name": "Overview",
                    "cls": "Plan",
                    "sources": [{"kind": "run", "ref": str(ref_of(run))}],
                },
            )
            assert plan.status_code == 201, plan.text
            response = client.post(
                "/api/knowledge/doc",
                json={
                    "name": "Stages",
                    "cls": "Roadmap",
                    "sources": [{"kind": "file", "ref": plan.json()["relPath"]}],
                    "record": {},
                },
            )
        assert response.status_code == 422, response.text

    def test_file_source_must_stay_inside_the_workspace(
        self, served: ServedFactory, lab: RunFixture
    ) -> None:
        ws, _exp, _run = lab
        with served(ws) as client:
            escaped = client.post(
                "/api/knowledge/doc",
                json={
                    "name": "Stages",
                    "cls": "Roadmap",
                    "sources": [{"kind": "file", "ref": "../secret.md"}],
                    "record": {"stages": [{"id": "a", "title": "A"}]},
                },
            )
            missing = client.post(
                "/api/knowledge/doc",
                json={
                    "name": "Stages",
                    "cls": "Roadmap",
                    "sources": [{"kind": "file", "ref": "knowledges/missing.md"}],
                    "record": {"stages": [{"id": "a", "title": "A"}]},
                },
            )
        assert escaped.status_code == 422, escaped.text
        assert "inside this workspace" in escaped.text
        assert missing.status_code == 422, missing.text
        assert "not a file" in missing.text


class TestEmbedDoc:
    """``embed_doc``: one typed link from a document to a live entity."""

    def test_embed_into_markdown_doc(self, served: ServedFactory, lab: RunFixture) -> None:
        from molab.workspace.refs import ref_of

        ws, _exp, run = lab
        target = str(ref_of(run))
        doc = Path(str(ws.root)) / "knowledges" / "idea.md"
        links_before = len(_MD_LINK.findall(doc.read_text()))
        with served(ws) as client:
            response = client.post(
                "/api/knowledge/doc/embed",
                params={"path": "knowledges/idea.md"},
                json={"target_kind": "run", "target": target},
            )
        assert response.status_code == 200, response.text
        assert response.json()["target"] == target
        text = doc.read_text()
        assert len(_MD_LINK.findall(text)) == links_before + 1
        assert text.count(f"]({target})") == 1

    def test_bare_run_id_writes_the_same_ref(self, served: ServedFactory, lab: RunFixture) -> None:
        from molab.workspace.refs import ref_of

        ws, _exp, run = lab
        target = str(ref_of(run))
        doc = Path(str(ws.root)) / "knowledges" / "idea.md"
        with served(ws) as client:
            response = client.post(
                "/api/knowledge/doc/embed",
                params={"path": "knowledges/idea.md"},
                json={"target_kind": "run", "target": run.id},
            )
        assert response.status_code == 422, response.text
        assert target not in doc.read_text()


class TestMoveDoc:
    """``move_doc``: rename a document."""

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

    def test_patch_host_path_moves_the_file(self, served: ServedFactory, lab: RunFixture) -> None:
        ws, exp, _run = lab
        host = _experiment_host(ws, exp)
        with served(ws) as client:
            response = client.patch(
                "/api/knowledge/doc",
                params={"path": "knowledges/idea.md"},
                json={"hostPath": host},
            )
        assert response.status_code == 200, response.text
        assert response.json()["hostPath"] == host
        assert response.json()["relPath"] == f"{host}/knowledges/idea.md"
        assert not (Path(str(ws.root)) / "knowledges" / "idea.md").exists()
        assert (Path(str(exp.resolve())) / "knowledges" / "idea.md").is_file()

    def test_move_onto_existing_document_is_409(
        self, served: ServedFactory, lab: RunFixture
    ) -> None:
        ws, exp, _run = lab
        host = _experiment_host(ws, exp)
        with served(ws) as client:
            created = client.post(
                "/api/knowledge/doc",
                json={"name": "idea", "hostPath": host},
            )
            assert created.status_code == 201, created.text
            response = client.patch(
                "/api/knowledge/doc",
                params={"path": "knowledges/idea.md"},
                json={"hostPath": host},
            )
        assert response.status_code == 409, response.text
        assert (Path(str(ws.root)) / "knowledges" / "idea.md").is_file()


class TestDeleteDoc:
    """``delete_doc``: remove a document."""

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


class TestKnowledgeGraph:
    """``get_knowledge_graph``: every document as a node, every typed link as an edge."""

    @staticmethod
    def _write(ws: Workspace, name: str, body: str) -> None:
        Note(Path(str(ws.root)) / "knowledges" / name).write(body)

    @staticmethod
    def _edges(client: TestClient, source: str) -> list[dict[str, str]]:
        response = client.get("/api/knowledge/graph")
        assert response.status_code == 200, response.text
        return [edge for edge in response.json()["edges"] if edge["source"] == source]

    def test_graph_reuses_the_knowledge_link_scan(self) -> None:
        src = inspect.getsource(knowledge_routes._graph_edges)
        assert ".scan_links(" in src
        assert "re.compile" not in src

    def test_nodes_carry_the_display_title(self, served: ServedFactory, lab: RunFixture) -> None:
        ws, _exp, _run = lab
        self._write(ws, "h-dry-ffv", "# Crosslinking lowers dry FFV\n\nBody.\n")
        self._write(ws, "untitled", "No heading here.\n")
        with served(ws) as client:
            graph = client.get("/api/knowledge/graph").json()
            listed = client.get("/api/knowledge").json()
        titles = {n["name"]: n["title"] for n in graph["nodes"]}
        assert titles["h-dry-ffv"] == "Crosslinking lowers dry FFV"
        assert titles["untitled"] == "untitled"
        assert {n["name"]: n["title"] for n in listed["notes"]} == titles

    def test_nodes_equal_the_listed_notes(self, served: ServedFactory, lab: RunFixture) -> None:
        ws, exp, _run = lab
        self._write(ws, "a", "# A\n\n- [b](b.md)\n")
        self._write(ws, "b", "# B\n")
        Note(exp, "deep").write("# Deep\n")
        with served(ws) as client:
            listed = client.get("/api/knowledge")
            graph = client.get("/api/knowledge/graph")
        assert graph.status_code == 200, graph.text
        assert set(graph.json()) == {"nodes", "edges"}
        assert graph.json()["nodes"] == listed.json()["notes"]
        assert len(graph.json()["nodes"]) >= 4

    def test_typed_link_is_a_document_edge(self, served: ServedFactory, lab: RunFixture) -> None:
        ws, exp, _run = lab
        self._write(ws, "b", "# B\n")
        deep = Note(exp, "deep")
        target = Path(str(ws.root)) / "knowledges" / "b.md"
        link = Path(os.path.relpath(target, Path(str(deep.path)).parent)).as_posix()
        deep.write(f"# Deep\n\n- [@derived_from x]({link}#method)\n")
        with served(ws) as client:
            nodes = {
                row["name"]: row["relPath"] for row in client.get("/api/knowledge").json()["notes"]
            }
            edges = self._edges(client, nodes["deep"])
        assert edges == [
            {
                "source": nodes["deep"],
                "target": nodes["b"],
                "role": "derived_from",
                "kind": "document",
            }
        ]
        assert nodes["b"] == "knowledges/b.md"

    def test_untyped_link_is_references(self, served: ServedFactory, lab: RunFixture) -> None:
        ws, _exp, _run = lab
        self._write(ws, "b", "# B\n")
        self._write(ws, "a", "# A\n\nSee [the other one](b.md).\n")
        with served(ws) as client:
            edges = self._edges(client, "knowledges/a.md")
        assert edges == [
            {
                "source": "knowledges/a.md",
                "target": "knowledges/b.md",
                "role": "references",
                "kind": "document",
            }
        ]

    def test_ref_and_url_keep_their_spelling(self, served: ServedFactory, lab: RunFixture) -> None:
        ws, exp, run = lab
        ref = f"{REF_SCHEME}experiment/{exp.id}/run/{run.id}"
        self._write(
            ws,
            "a",
            "# A\n\n"
            f"- [@records the run]({ref})\n"
            "- [@cites paper](https://doi.org/10.1000/xyz)\n"
            "- [plain](https://example.org/page)\n",
        )
        with served(ws) as client:
            edges = self._edges(client, "knowledges/a.md")
        found = {(edge["target"], edge["role"], edge["kind"]) for edge in edges}
        assert found == {
            (ref, "records", "ref"),
            ("https://doi.org/10.1000/xyz", "cites", "external"),
            ("https://example.org/page", "references", "external"),
        }
        assert len(edges) == 3

    def test_link_to_absent_file_is_missing(self, served: ServedFactory, lab: RunFixture) -> None:
        ws, _exp, _run = lab
        self._write(ws, "a", "# A\n\n- [@supersedes old](gone.md)\n")
        with served(ws) as client:
            edges = self._edges(client, "knowledges/a.md")
        assert edges == [
            {
                "source": "knowledges/a.md",
                "target": "knowledges/gone.md",
                "role": "supersedes",
                "kind": "missing",
            }
        ]

    def test_existing_file_that_is_no_document_is_not_an_edge(
        self, served: ServedFactory, lab: RunFixture
    ) -> None:
        ws, _exp, _run = lab
        (Path(str(ws.root)) / "data.csv").write_text("x\n", encoding="utf-8")
        self._write(ws, "a", "# A\n\n- [table](../data.csv)\n- [here](#top)\n")
        with served(ws) as client:
            edges = self._edges(client, "knowledges/a.md")
        assert edges == []

    def test_repeated_link_is_one_edge(self, served: ServedFactory, lab: RunFixture) -> None:
        ws, _exp, _run = lab
        self._write(ws, "b", "# B\n")
        self._write(ws, "a", "# A\n\n[b](b.md) and [b](b.md#part) and [@cites b](b.md)\n")
        with served(ws) as client:
            edges = self._edges(client, "knowledges/a.md")
        assert [(edge["role"], edge["kind"]) for edge in edges] == [
            ("references", "document"),
            ("cites", "document"),
        ]


class TestExportDoc:
    """``export_doc``: portable markdown of one document."""

    def test_export_markdown_doc(self, served: ServedFactory, lab: RunFixture) -> None:
        ws, _exp, _run = lab
        with served(ws) as client:
            response = client.get(
                "/api/knowledge/doc/export", params={"path": "knowledges/idea.md"}
            )
        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith("text/markdown")
        assert "Cooling rate" in response.text


class TestNoteCards:
    def test_a_live_run_edge(self, served: ServedFactory, lab: RunFixture) -> None:
        from molab.knowledge.concept import append_link
        from molab.workspace.refs import ref_of

        ws, _exp, run = lab
        target = str(ref_of(run))
        note = Note(Path(str(ws.root)) / "knowledges" / "idea")
        append_link(note, target, role="records")
        with served(ws) as client:
            response = client.get("/api/knowledge/note", params={"path": "knowledges/idea.md"})
        assert response.status_code == 200, response.text
        card = next(row for row in response.json()["cards"] if row["ref"] == target)
        assert card["kind"] == "run"
        assert card["id"] == run.id
        assert card["missing"] is False
        assert card["status"] == run.status_label
        if run.parameters:
            assert card["detail"]
            assert next(iter(sorted(run.parameters))) in card["detail"]

    def test_a_missing_run_ref_stays_200(self, served: ServedFactory, lab: RunFixture) -> None:
        from molab.knowledge.concept import append_link
        from molab.workspace.refs import MolabRef

        ws, exp, _run = lab
        target = str(MolabRef(experiment_id=exp.id, run_id="deadbeef"))
        note = Note(Path(str(ws.root)) / "knowledges" / "idea")
        append_link(note, target, role="records")
        with served(ws) as client:
            response = client.get("/api/knowledge/note", params={"path": "knowledges/idea.md"})
        assert response.status_code == 200, response.text
        card = next(row for row in response.json()["cards"] if row["ref"] == target)
        assert card["missing"] is True

    def test_an_ambiguous_ref_is_missing(self, served: ServedFactory, tmp_path: Path) -> None:
        from molab.knowledge.concept import append_link

        ws = Workspace(tmp_path / "ws", name="lab")
        ws.add_project("a").add_experiment("e", id="dup-exp")
        ws.add_project("b").add_experiment("f", id="dup-exp")
        _seed_note(ws)
        target = str(MolabRef(experiment_id="dup-exp"))
        note = Note(Path(str(ws.root)) / "knowledges" / "idea")
        append_link(note, target, role="records")
        with served(ws) as client:
            response = client.get("/api/knowledge/note", params={"path": "knowledges/idea.md"})
        assert response.status_code == 200, response.text
        card = response.json()["cards"][0]
        assert card["missing"] is True
        assert "ambiguous" in card["title"]

    def test_a_legacy_run_directory_is_a_path_card(
        self, served: ServedFactory, lab: RunFixture
    ) -> None:
        from molab.knowledge.concept import append_link

        ws, _exp, run = lab
        note = Note(Path(str(ws.root)) / "knowledges" / "idea")
        append_link(note, str(run.resolve()), role="references")
        with served(ws) as client:
            response = client.get("/api/knowledge/note", params={"path": "knowledges/idea.md"})
        assert response.status_code == 200, response.text
        assert response.json()["cards"] == []

    def test_a_missing_doc_link(self, served: ServedFactory, lab: RunFixture) -> None:
        from molab.knowledge.concept import append_link

        ws, _exp, _run = lab
        note = Note(Path(str(ws.root)) / "knowledges" / "idea")
        append_link(note, str(Path(str(ws.root)) / "gone.md"), role="references")
        with served(ws) as client:
            response = client.get("/api/knowledge/note", params={"path": "knowledges/idea.md"})
        assert response.status_code == 200, response.text
        card = response.json()["cards"][0]
        assert card["kind"] == "document"
        assert card["missing"] is True


class TestEntityBacklinks:
    """``entity_backlinks``: knowledge documents citing a run / experiment."""

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

    def test_a_legacy_run_directory_link_is_listed(
        self, served: ServedFactory, lab: RunFixture
    ) -> None:
        from molab.knowledge.concept import append_link

        ws, exp, run = lab
        note = Note(Path(str(ws.root)) / "knowledges" / "idea")
        append_link(note, str(run.resolve()), role="records")
        with served(ws) as client:
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
        assert response.json()["backlinks"] == []

    def test_a_note_citing_an_asset_is_listed(
        self, served: ServedFactory, lab: RunFixture, tmp_path: Path
    ) -> None:
        ws, exp, _run = lab
        source = tmp_path / "ligands.csv"
        source.write_text("ligand,smiles\nL-001,CCO\n")
        asset = exp.project.import_asset("ligands", source)
        note = Note(Path(str(ws.root)) / "knowledges" / "screen")
        note.write(f"# Screen\n\n[@cites ligands]({MolabRef(asset_id=asset.id)})\n")
        with served(ws) as client:
            response = client.get(
                "/api/knowledge/entity-backlinks",
                params={"kind": "asset", "assetId": asset.id},
            )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["entity"] == f"asset:{asset.id}"
        assert [row["title"] for row in body["backlinks"]] == ["Screen"]

    def test_an_unknown_asset_is_404(self, served: ServedFactory, lab: RunFixture) -> None:
        ws, _exp, _run = lab
        with served(ws) as client:
            response = client.get(
                "/api/knowledge/entity-backlinks",
                params={"kind": "asset", "assetId": "no-such-asset"},
            )
        assert response.status_code == 404, response.text

    def test_kind_asset_requires_asset_id(self, served: ServedFactory, lab: RunFixture) -> None:
        ws, _exp, _run = lab
        with served(ws) as client:
            response = client.get("/api/knowledge/entity-backlinks", params={"kind": "asset"})
        assert response.status_code == 422, response.text


def _seed_note(ws: Workspace) -> None:
    """Same markdown note the ``lab`` fixture writes at ``knowledges/idea.md``."""
    note = Note(Path(str(ws.root)) / "knowledges" / "idea")
    note.write("# Cooling rate\n")


class TestResolveEmbedEntity:
    """``_resolve_embed_entity`` walks references, not private finders."""

    def test_unique_bare_run_id_is_rejected(self, tmp_path: Path) -> None:
        from fastapi import HTTPException

        ws = Workspace(tmp_path / "ws", name="lab")
        ws.add_project("p").add_experiment("e").add_run(id="r1")
        with pytest.raises(HTTPException) as caught:
            knowledge_routes._resolve_embed_entity(ws, "run", "r1")
        assert caught.value.status_code == 422

    def test_qualified_run_ref_picks_that_experiment(self, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "ws", name="lab")
        project = ws.add_project("p")
        exp_a = project.add_experiment("A")
        exp_b = project.add_experiment("B")
        run_a = exp_a.add_run(id="r1")
        exp_b.add_run(id="r1")
        target = str(MolabRef(experiment_id=exp_a.id, run_id="r1"))
        found = knowledge_routes._resolve_embed_entity(ws, "run", target)
        assert isinstance(found, Run)
        assert found.id == run_a.id
        assert found.experiment.id == exp_a.id

    def test_bare_experiment_id(self, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "ws", name="lab")
        experiment = ws.add_project("p").add_experiment("e")
        found = knowledge_routes._resolve_embed_entity(ws, "experiment", experiment.id)
        assert isinstance(found, Experiment)
        assert found.id == experiment.id

    def test_ambiguous_bare_run_id_is_rejected(self, tmp_path: Path) -> None:
        from fastapi import HTTPException

        ws = Workspace(tmp_path / "ws", name="lab")
        project = ws.add_project("p")
        project.add_experiment("A").add_run(id="r1")
        project.add_experiment("B").add_run(id="r1")
        with pytest.raises(HTTPException) as caught:
            knowledge_routes._resolve_embed_entity(ws, "run", "r1")
        assert caught.value.status_code == 422

    def test_missing_run_id_is_rejected(self, tmp_path: Path) -> None:
        from fastapi import HTTPException

        ws = Workspace(tmp_path / "ws", name="lab")
        with pytest.raises(HTTPException) as caught:
            knowledge_routes._resolve_embed_entity(ws, "run", "r1")
        assert caught.value.status_code == 422

    def test_asset_ref_with_run_kind_rejected(self, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "ws", name="lab")
        with pytest.raises(InvalidRefError):
            knowledge_routes._resolve_embed_entity(ws, "run", REF_SCHEME + "asset/x")

    def test_experiment_ref_with_run_kind_rejected(self, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "ws", name="lab")
        with pytest.raises(InvalidRefError):
            knowledge_routes._resolve_embed_entity(ws, "run", "molab:experiment/E")

    def test_private_finders_are_gone(self) -> None:
        assert hasattr(knowledge_routes, "_find_run") is False
        assert hasattr(knowledge_routes, "_find_experiment") is False

    def test_route_module_does_not_spell_the_scheme(self) -> None:
        assert REF_SCHEME not in inspect.getsource(knowledge_routes)


class TestEmbedDocRefErrors:
    """POST ``/api/knowledge/doc/embed`` maps reference failures onto HTTP."""

    def test_ambiguous_bare_run_is_409(self, served: ServedFactory, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "ws", name="lab")
        project = ws.add_project("p")
        project.add_experiment("A").add_run(id="r1")
        project.add_experiment("B").add_run(id="r1")
        _seed_note(ws)
        with served(ws, raise_server_exceptions=False) as client:
            response = client.post(
                "/api/knowledge/doc/embed",
                params={"path": "knowledges/idea.md"},
                json={"target_kind": "run", "target": "r1"},
            )
        assert response.status_code == 422

    def test_unknown_run_is_404(self, served: ServedFactory, lab: RunFixture) -> None:
        ws, _exp, _run = lab
        with served(ws, raise_server_exceptions=False) as client:
            response = client.post(
                "/api/knowledge/doc/embed",
                params={"path": "knowledges/idea.md"},
                json={"target_kind": "run", "target": "missing-run"},
            )
        assert response.status_code == 422, response.text

    def test_asset_ref_as_run_is_422(self, served: ServedFactory, lab: RunFixture) -> None:
        ws, _exp, _run = lab
        with served(ws, raise_server_exceptions=False) as client:
            response = client.post(
                "/api/knowledge/doc/embed",
                params={"path": "knowledges/idea.md"},
                json={"target_kind": "run", "target": REF_SCHEME + "asset/x"},
            )
        assert response.status_code == 422

    def test_bare_experiment_id_with_slash_is_400(
        self, served: ServedFactory, lab: RunFixture
    ) -> None:
        ws, _exp, _run = lab
        with served(ws, raise_server_exceptions=False) as client:
            response = client.post(
                "/api/knowledge/doc/embed",
                params={"path": "knowledges/idea.md"},
                json={"target_kind": "experiment", "target": "a/b"},
            )
        assert response.status_code != 500
        assert response.status_code == 400


class TestEmbedRequestWire:
    def test_response_field_set(self) -> None:
        assert set(knowledge_routes.EmbedResponse.model_fields) == {"srcPath", "target", "role"}

    def test_target_kind_literals(self) -> None:
        annotation = knowledge_routes.EmbedRequest.model_fields["target_kind"].annotation
        assert get_args(annotation) == ("run", "asset", "experiment", "reference")

    def test_field_set(self) -> None:
        assert set(knowledge_routes.EmbedRequest.model_fields) == {
            "target_kind",
            "target",
            "role",
            "text",
        }


class TestAssetEmbedResolution:
    def test_bare_asset_id_is_a_domain_asset(self, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "ws", name="lab")
        source = tmp_path / "mydata.txt"
        source.write_text("payload")
        asset = ws.assets.import_asset("mydata", source)
        found = knowledge_routes._resolve_embed_entity(ws, "asset", asset.id)
        assert isinstance(found, Asset)
        assert found.id == asset.id
        assert found.title == "mydata"

    def test_unknown_asset_id_raises(self, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "ws", name="lab")
        with pytest.raises(RefNotFoundError) as exc:
            knowledge_routes._resolve_embed_entity(ws, "asset", "nope")
        assert exc.value.segment == "asset"

    def test_experiment_ref_under_asset_kind_raises(self, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "ws", name="lab")
        with pytest.raises(InvalidRefError):
            knowledge_routes._resolve_embed_entity(ws, "asset", str(MolabRef(experiment_id="E")))

    def test_unknown_asset_is_404(self, served: ServedFactory, lab: RunFixture) -> None:
        ws, _exp, _run = lab
        with served(ws, raise_server_exceptions=False) as client:
            response = client.post(
                "/api/knowledge/doc/embed",
                params={"path": "knowledges/idea.md"},
                json={"target_kind": "asset", "target": "nope"},
            )
        assert response.status_code == 404, response.text
        assert response.json()["error"]["code"] == "NOT_FOUND"

    def test_experiment_ref_as_asset_is_422(self, served: ServedFactory, lab: RunFixture) -> None:
        ws, _exp, _run = lab
        with served(ws, raise_server_exceptions=False) as client:
            response = client.post(
                "/api/knowledge/doc/embed",
                params={"path": "knowledges/idea.md"},
                json={"target_kind": "asset", "target": str(MolabRef(experiment_id="E"))},
            )
        assert response.status_code == 422, response.text
        assert response.json()["error"]["code"] == "INVALID_REF"

    def test_note_card_for_an_embedded_asset(
        self, served: ServedFactory, lab: RunFixture, tmp_path: Path
    ) -> None:
        from molab.knowledge.embed import embed

        ws, _exp, _run = lab
        source = tmp_path / "mydata.txt"
        source.write_text("payload")
        asset = ws.assets.import_asset("mydata", source)
        note = Note(Path(str(ws.root)) / "knowledges" / "idea")
        embed(note, asset)
        with served(ws) as client:
            response = client.get("/api/knowledge/note", params={"path": "knowledges/idea.md"})
        assert response.status_code == 200, response.text
        card = next(row for row in response.json()["cards"] if row["id"] == asset.id)
        assert card["kind"] == "asset"
        assert card["title"] == "mydata"
        assert card["relPath"] is None
        assert card["detail"] == asset.scope.kind

    def test_route_source_does_not_parse_asset_directories(self) -> None:
        source = inspect.getsource(knowledge_routes)
        assert 'parent.name == "assets"' not in source
        assert ".asset_dir" + "(" not in source
        resolver = inspect.getsource(knowledge_routes._ref_card)
        for name in ("RefNotFoundError", "AmbiguousRefError", "InvalidRefError"):
            assert name in resolver


class TestDocMedia:
    """``upload_doc_media`` writes a figure beside the document."""

    def test_png_lands_under_figs(self, served: ServedFactory, lab: RunFixture) -> None:
        ws, _exp, _run = lab
        png = b"\x89PNG\r\n\x1a\n" + b"x" * 8
        with served(ws) as client:
            response = client.post(
                "/api/knowledge/doc/media",
                params={"path": "knowledges/idea.md"},
                files={"file": ("plot.png", png, "image/png")},
            )
        assert response.status_code == 201, response.text
        assert response.json()["path"] == "figs/plot.png"
        assert (Path(str(ws.root)) / "knowledges" / "figs" / "plot.png").read_bytes() == png

    def test_text_file_is_415(self, served: ServedFactory, lab: RunFixture) -> None:
        ws, _exp, _run = lab
        with served(ws) as client:
            response = client.post(
                "/api/knowledge/doc/media",
                params={"path": "knowledges/idea.md"},
                files={"file": ("notes.txt", b"hello", "text/plain")},
            )
        assert response.status_code == 415, response.text


class TestExportNotebook:
    """``export_notebook`` zips one host's documents and the figures they cite."""

    def test_zip_contains_the_document_its_figure_and_the_embed_list(
        self, served: ServedFactory, lab: RunFixture
    ) -> None:
        import io
        import json
        import zipfile

        from molab.knowledge.concept import append_link
        from molab.workspace.refs import ref_of

        ws, _exp, run = lab
        png = b"\x89PNG\r\n\x1a\n" + b"y" * 4
        note = Note(Path(str(ws.root)) / "knowledges" / "idea")
        append_link(note, str(ref_of(run)), role="records")
        with served(ws) as client:
            uploaded = client.post(
                "/api/knowledge/doc/media",
                params={"path": "knowledges/idea.md"},
                files={"file": ("plot.png", png, "image/png")},
            )
            assert uploaded.status_code == 201, uploaded.text
            current = Path(str(ws.root)).joinpath("knowledges", "idea.md").read_text()
            edited = client.put(
                "/api/knowledge/doc",
                params={"path": "knowledges/idea.md"},
                json={"body": current + "\n![plot](figs/plot.png)\n"},
            )
            assert edited.status_code == 200, edited.text
            response = client.get("/api/knowledge/export")
        assert response.status_code == 200, response.text
        assert response.headers["content-type"] == "application/zip"
        archive = zipfile.ZipFile(io.BytesIO(response.content))
        names = set(archive.namelist())
        assert "knowledges/idea.md" in names
        assert "knowledges/figs/plot.png" in names
        assert archive.read("knowledges/figs/plot.png") == png
        embeds = json.loads(archive.read("embeds.json"))
        idea = next(row for row in embeds if row["path"] == "knowledges/idea.md")
        assert any(card["id"] == run.id for card in idea["cards"])


class TestDelegationRecordRoutes:
    """Create a Delegation over HTTP, read its record, replace it with ``ifMatch``."""

    @staticmethod
    def _create(client: TestClient, exp: Experiment, host: str) -> dict[str, object]:
        response = client.post(
            "/api/knowledge/doc",
            json={
                "name": "Cooling study",
                "cls": "Delegation",
                "hostPath": host,
                "createdBy": "tack",
                "sources": [{"kind": "experiment", "ref": exp.id}],
                "record": {
                    "goal": "Is Tg rate-dependent?",
                    "scope": f"molab:experiment/{exp.id}",
                    "actions": ["read", "start_execution"],
                },
            },
        )
        assert response.status_code == 201, response.text
        return response.json()

    def test_create_get_and_replace(self, served: ServedFactory, lab: RunFixture) -> None:
        ws, exp, _run = lab
        host = _experiment_host(ws, exp)
        with served(ws) as client:
            created = self._create(client, exp, host)
            assert created["cls"] == "Delegation"
            path = created["relPath"]
            got = client.get("/api/knowledge/doc/record", params={"path": path})
            assert got.status_code == 200, got.text
            record = got.json()["record"]
            assert record["goal"] == "Is Tg rate-dependent?"
            replaced = client.patch(
                "/api/knowledge/doc/record",
                params={"path": path},
                json={
                    "record": {**record, "state": "waiting"},
                    "ifMatch": got.json()["digest"],
                    "body": "## Status\n\nwaiting\n",
                },
            )
            assert replaced.status_code == 200, replaced.text
            assert replaced.json()["record"]["state"] == "waiting"
            assert replaced.json()["digest"] != got.json()["digest"]
            stale = client.patch(
                "/api/knowledge/doc/record",
                params={"path": path},
                json={"record": record, "ifMatch": got.json()["digest"]},
            )
            assert stale.status_code == 409, stale.text
        text = (Path(str(ws.root)) / path).read_text(encoding="utf-8")
        assert "created_by: tack" in text
        assert "## Status" in text

    def test_invalid_record_is_422(self, served: ServedFactory, lab: RunFixture) -> None:
        ws, exp, _run = lab
        with served(ws) as client:
            created = self._create(client, exp, _experiment_host(ws, exp))
            response = client.patch(
                "/api/knowledge/doc/record",
                params={"path": created["relPath"]},
                json={"record": {"goal": "g", "scope": "s", "state": "sleeping"}},
            )
        assert response.status_code == 422, response.text

    def test_an_approval_is_recorded_at_a_known_gate(
        self, served: ServedFactory, lab: RunFixture
    ) -> None:
        ws, exp, _run = lab
        approval = {
            "gate": "dry_run",
            "target": f"molab:experiment/{exp.id}",
            "by": "roykid",
            "at": "2026-11-04T10:05:00+00:00",
            "note": "Waves look right.",
        }
        with served(ws) as client:
            created = self._create(client, exp, _experiment_host(ws, exp))
            path = created["relPath"]
            record = client.get("/api/knowledge/doc/record", params={"path": path}).json()
            approved = client.patch(
                "/api/knowledge/doc/record",
                params={"path": path},
                json={
                    "record": {**record["record"], "approvals": [approval]},
                    "ifMatch": record["digest"],
                },
            )
            assert approved.status_code == 200, approved.text
            assert approved.json()["record"]["approvals"] == [approval]
            unknown_gate = client.patch(
                "/api/knowledge/doc/record",
                params={"path": path},
                json={"record": {**record["record"], "approvals": [{**approval, "gate": "merge"}]}},
            )
        assert unknown_gate.status_code == 422, unknown_gate.text
        assert "approvals" in unknown_gate.json()["detail"]

    def test_create_without_goal_is_422(self, served: ServedFactory, lab: RunFixture) -> None:
        ws, exp, _run = lab
        with served(ws) as client:
            response = client.post(
                "/api/knowledge/doc",
                json={
                    "name": "Empty",
                    "cls": "Delegation",
                    "sources": [{"kind": "experiment", "ref": exp.id}],
                    "record": {"actions": ["read"]},
                },
            )
        assert response.status_code == 422, response.text

    def test_note_record_cannot_be_replaced(self, served: ServedFactory, lab: RunFixture) -> None:
        ws, _exp, _run = lab
        with served(ws) as client:
            response = client.patch(
                "/api/knowledge/doc/record",
                params={"path": "knowledges/idea.md"},
                json={"record": {"x": 1}},
            )
        assert response.status_code == 422, response.text


class TestHtmlDocumentsAndTimes:
    """An HTML document over the wire, and the ``format`` / ``createdAt`` / ``updatedAt`` fields."""

    _BODY = (
        "<molab-markdown>\n# Page\n\nGlass forms on cooling.\n</molab-markdown>\n"
        '<molab-chart series="rho"></molab-chart>\n'
    )

    def _create(self, client: TestClient, **extra: object) -> dict[str, object]:
        response = client.post(
            "/api/knowledge/doc",
            json={"name": "page", "body": self._BODY, "format": "html", **extra},
        )
        assert response.status_code == 201, response.text
        return response.json()

    def test_create_lists_and_reads_an_html_document(
        self, served: ServedFactory, lab: RunFixture
    ) -> None:
        from datetime import datetime

        ws, _exp, _run = lab
        with served(ws) as client:
            created = self._create(client)
            listed = client.get("/api/knowledge").json()["notes"]
            detail = client.get("/api/knowledge/note", params={"path": "knowledges/page.html"})
        assert created["relPath"] == "knowledges/page.html"
        assert created["format"] == "html"
        assert isinstance(created["createdAt"], str)
        datetime.fromisoformat(created["createdAt"])
        rows = {row["relPath"]: row for row in listed}
        page = rows["knowledges/page.html"]
        assert page["format"] == "html"
        assert page["createdAt"] == created["createdAt"]
        assert datetime.fromisoformat(page["updatedAt"]).utcoffset().total_seconds() == 0
        assert "<molab" not in page["excerpt"]
        assert "Glass forms on cooling." in page["excerpt"]
        idea = rows["knowledges/idea.md"]
        assert idea["format"] == "md"
        assert idea["createdAt"] is None
        assert isinstance(idea["updatedAt"], str)
        assert detail.status_code == 200, detail.text
        body = detail.json()
        assert body["body"] == self._BODY
        assert body["format"] == "html"
        assert body["createdAt"] == created["createdAt"]
        assert isinstance(body["updatedAt"], str)

    def test_markdown_create_carries_created_at(
        self, served: ServedFactory, lab: RunFixture
    ) -> None:
        ws, _exp, _run = lab
        with served(ws) as client:
            response = client.post("/api/knowledge/doc", json={"name": "plain", "body": "x"})
        assert response.status_code == 201, response.text
        assert response.json()["format"] == "md"
        assert isinstance(response.json()["createdAt"], str)

    def test_create_refuses_the_other_format(self, served: ServedFactory, lab: RunFixture) -> None:
        ws, _exp, _run = lab
        with served(ws) as client:
            response = client.post(
                "/api/knowledge/doc", json={"name": "idea", "body": "<p>x</p>", "format": "html"}
            )
        assert response.status_code == 422, response.text
        assert "already exists" in response.text

    def test_edit_keeps_the_html_form(self, served: ServedFactory, lab: RunFixture) -> None:
        ws, _exp, _run = lab
        with served(ws) as client:
            self._create(client)
            edited = client.put(
                "/api/knowledge/doc",
                params={"path": "knowledges/page.html"},
                json={"body": "<p>rewritten</p>"},
            )
        assert edited.status_code == 200, edited.text
        assert edited.json()["body"] == "<p>rewritten</p>"
        text = Path(str(ws.root)).joinpath("knowledges", "page.html").read_text()
        assert text.startswith("<!doctype html>")
        assert "<body>\n<p>rewritten</p>\n</body>" in text

    def test_export_is_text_html_with_an_html_filename(
        self, served: ServedFactory, lab: RunFixture
    ) -> None:
        ws, _exp, _run = lab
        with served(ws) as client:
            self._create(client)
            response = client.get(
                "/api/knowledge/doc/export", params={"path": "knowledges/page.html"}
            )
        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith("text/html")
        assert 'filename="page.html"' in response.headers["content-disposition"]
        assert response.text == Path(str(ws.root)).joinpath("knowledges", "page.html").read_text()

    def test_notebook_export_carries_an_img_figure(
        self, served: ServedFactory, lab: RunFixture
    ) -> None:
        import io
        import zipfile

        ws, _exp, _run = lab
        png = b"\x89PNG\r\n\x1a\n" + b"z" * 4
        with served(ws) as client:
            self._create(client)
            uploaded = client.post(
                "/api/knowledge/doc/media",
                params={"path": "knowledges/page.html"},
                files={"file": ("plot.png", png, "image/png")},
            )
            assert uploaded.status_code == 201, uploaded.text
            client.put(
                "/api/knowledge/doc",
                params={"path": "knowledges/page.html"},
                json={"body": self._BODY + '<img src="figs/plot.png" alt="plot">\n'},
            )
            response = client.get("/api/knowledge/export")
        archive = zipfile.ZipFile(io.BytesIO(response.content))
        assert "knowledges/page.html" in archive.namelist()
        assert archive.read("knowledges/figs/plot.png") == png


class TestHypothesisAndDecision:
    """``Hypothesis`` and ``Decision`` over HTTP: create, list, graph, and the evidence roles."""

    @pytest.mark.parametrize(
        ("cls", "record"),
        [
            ("Hypothesis", {"verdict": "refuted"}),
            ("Hypothesis", {"verdict": "supported"}),
            ("Hypothesis", {"verdict": "unsettled"}),
            ("Decision", {"status": "open"}),
            ("Decision", {"status": "made"}),
        ],
    )
    def test_note_detail_preserves_the_reasoning_record(
        self, served: ServedFactory, lab: RunFixture, cls: str, record: dict[str, str]
    ) -> None:
        ws, _exp, run = lab
        with served(ws) as client:
            created = self._create(client, run, cls, "Reasoning", record)
            assert created.status_code == 201, created.text
            path = created.json()["relPath"]
            detail = client.get("/api/knowledge/note", params={"path": path})
            canonical = client.get("/api/knowledge/doc/record", params={"path": path})
        assert detail.status_code == 200, detail.text
        assert detail.json()["record"] == canonical.json()["record"] == record

    @staticmethod
    def _create(
        client: TestClient, run: Run, cls: str, name: str, record: dict[str, str] | None = None
    ) -> Any:
        from molab.workspace.refs import ref_of

        payload: dict[str, object] = {
            "name": name,
            "cls": cls,
            "body": f"# {name}\n",
            "sources": [{"kind": "run", "ref": str(ref_of(run))}],
        }
        if record is not None:
            payload["record"] = record
        return client.post("/api/knowledge/doc", json=payload)

    def test_the_create_request_accepts_both_classes(self) -> None:
        names = get_args(knowledge_routes.DocCreateRequest.model_fields["cls"].annotation)
        assert {"Hypothesis", "Decision"} <= set(names)
        from molab.knowledge.concepts import _PRODUCTS

        assert set(names) == set(_PRODUCTS)

    @pytest.mark.parametrize("cls", ["Hypothesis", "Decision"])
    def test_a_source_is_required(self, served: ServedFactory, lab: RunFixture, cls: str) -> None:
        ws, _exp, _run = lab
        with served(ws) as client:
            response = client.post("/api/knowledge/doc", json={"name": "x", "cls": cls})
        assert response.status_code == 422, response.text

    def test_defaults_are_open_and_made(self, served: ServedFactory, lab: RunFixture) -> None:
        from molab.knowledge import Decision, Hypothesis

        ws, _exp, run = lab
        with served(ws) as client:
            hypothesis = self._create(client, run, "Hypothesis", "Tg rises")
            decision = self._create(client, run, "Decision", "Use OPLS")
        assert hypothesis.status_code == 201, hypothesis.text
        assert decision.status_code == 201, decision.text
        assert hypothesis.json()["cls"] == "Hypothesis"
        assert decision.json()["cls"] == "Decision"
        root = Path(str(ws.root))
        assert "class: Hypothesis" in (root / hypothesis.json()["relPath"]).read_text()
        assert Hypothesis(root / hypothesis.json()["relPath"]).verdict() == "open"
        assert Decision(root / decision.json()["relPath"]).status() == "made"

    def test_explicit_values_round_trip_on_the_record(
        self, served: ServedFactory, lab: RunFixture
    ) -> None:
        ws, _exp, run = lab
        with served(ws) as client:
            hypothesis = self._create(client, run, "Hypothesis", "Tg", {"verdict": "unsettled"})
            decision = self._create(client, run, "Decision", "FF", {"status": "open"})
            assert hypothesis.status_code == 201, hypothesis.text
            assert decision.status_code == 201, decision.text
            h_path, d_path = hypothesis.json()["relPath"], decision.json()["relPath"]
            h_record = client.get("/api/knowledge/doc/record", params={"path": h_path})
            d_record = client.get("/api/knowledge/doc/record", params={"path": d_path})
            assert h_record.json()["record"]["verdict"] == "unsettled"
            assert d_record.json()["record"]["status"] == "open"
            settled = client.patch(
                "/api/knowledge/doc/record",
                params={"path": h_path},
                json={"record": {"verdict": "refuted"}, "ifMatch": h_record.json()["digest"]},
            )
            made = client.patch(
                "/api/knowledge/doc/record",
                params={"path": d_path},
                json={"record": {"status": "made"}, "ifMatch": d_record.json()["digest"]},
            )
            bad = client.patch(
                "/api/knowledge/doc/record",
                params={"path": h_path},
                json={"record": {"verdict": "true"}},
            )
        assert settled.status_code == 200, settled.text
        assert settled.json()["record"]["verdict"] == "refuted"
        assert made.status_code == 200, made.text
        assert made.json()["record"]["status"] == "made"
        assert bad.status_code == 422, bad.text

    @pytest.mark.parametrize(
        ("cls", "record"),
        [("Hypothesis", {"verdict": "maybe"}), ("Decision", {"status": "pending"})],
    )
    def test_an_unknown_value_is_422_and_nothing_lands(
        self, served: ServedFactory, lab: RunFixture, cls: str, record: dict[str, str]
    ) -> None:
        ws, _exp, run = lab
        with served(ws) as client:
            response = self._create(client, run, cls, "Bad one", record)
            names = _listed_names(client)
        assert response.status_code == 422, response.text
        assert next(iter(record.values())) in response.text
        assert "Bad one" not in names
        assert not (Path(str(ws.root)) / "knowledges" / "bad-one.md").exists()

    def test_the_meta_patch_cannot_store_an_unknown_decision_status(
        self, served: ServedFactory, lab: RunFixture
    ) -> None:
        from molab.knowledge import Decision

        ws, _exp, run = lab
        with served(ws) as client:
            path = self._create(client, run, "Decision", "FF", {"status": "open"}).json()["relPath"]
            bad = client.patch(
                "/api/knowledge/doc/meta", params={"path": path}, json={"status": "active"}
            )
            good = client.patch(
                "/api/knowledge/doc/meta", params={"path": path}, json={"status": "made"}
            )
        assert bad.status_code == 400, bad.text
        assert "active" in bad.text
        assert good.status_code == 200, good.text
        assert Decision(Path(str(ws.root)) / path).status() == "made"

    def test_both_are_listed_and_are_graph_nodes(
        self, served: ServedFactory, lab: RunFixture
    ) -> None:
        ws, _exp, run = lab
        with served(ws) as client:
            hypothesis = self._create(client, run, "Hypothesis", "Tg rises").json()["relPath"]
            decision = self._create(client, run, "Decision", "Use OPLS").json()["relPath"]
            notes = client.get("/api/knowledge").json()["notes"]
            graph = client.get("/api/knowledge/graph").json()["nodes"]
        listed = {row["relPath"]: row["cls"] for row in notes}
        nodes = {row["relPath"]: row["cls"] for row in graph}
        assert listed[hypothesis] == nodes[hypothesis] == "Hypothesis"
        assert listed[decision] == nodes[decision] == "Decision"

    @pytest.mark.parametrize("role", ["supports", "contradicts"])
    def test_an_embed_with_an_evidence_role_is_a_graph_edge(
        self, served: ServedFactory, lab: RunFixture, role: str
    ) -> None:
        from molab.workspace.refs import ref_of

        ws, _exp, run = lab
        target = str(ref_of(run))
        with served(ws) as client:
            embedded = client.post(
                "/api/knowledge/doc/embed",
                params={"path": "knowledges/idea.md"},
                json={"target_kind": "run", "target": target, "role": role},
            )
            graph = client.get("/api/knowledge/graph")
        assert embedded.status_code == 200, embedded.text
        assert embedded.json()["role"] == role
        text = (Path(str(ws.root)) / "knowledges" / "idea.md").read_text()
        assert f"- [@{role} " in text
        assert f"]({target})" in text
        edges = [e for e in graph.json()["edges"] if e["source"] == "knowledges/idea.md"]
        assert edges == [
            {"source": "knowledges/idea.md", "target": target, "role": role, "kind": "ref"}
        ]

    @pytest.mark.parametrize("role", ["supports", "contradicts"])
    def test_a_finding_to_hypothesis_link_is_a_document_edge(
        self, served: ServedFactory, lab: RunFixture, role: str
    ) -> None:
        ws, _exp, run = lab
        with served(ws) as client:
            hypothesis = self._create(client, run, "Hypothesis", "Tg rises").json()["relPath"]
            finding = self._create(client, run, "Finding", "Tg result").json()["relPath"]
            path = Path(str(ws.root)) / finding
            link = Path(hypothesis).name
            path.write_text(path.read_text() + f"\n- [@{role} h]({link})\n")
            edges = client.get("/api/knowledge/graph").json()["edges"]
        assert {
            "source": finding,
            "target": hypothesis,
            "role": role,
            "kind": "document",
        } in edges

    def test_an_unknown_embed_role_is_422(self, served: ServedFactory, lab: RunFixture) -> None:
        from molab.workspace.refs import ref_of

        ws, _exp, run = lab
        with served(ws) as client:
            response = client.post(
                "/api/knowledge/doc/embed",
                params={"path": "knowledges/idea.md"},
                json={"target_kind": "run", "target": str(ref_of(run)), "role": "proves"},
            )
        assert response.status_code == 422, response.text
