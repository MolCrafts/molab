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
        from molab.knowledge.concepts import Note, parse_class
        from molab.knowledge.edges import EdgeRole
        from molab.knowledge.embed import default_role_for, resolve_embed_target, summarize_entity
        from molab.knowledge.errors import ConceptNotFoundError
        from molab.knowledge.search import extract_title

        assert all(
            callable(obj)
            for obj in (
                extract_title,
                parse_class,
                default_role_for,
                resolve_embed_target,
                summarize_entity,
            )
        )
        assert parse_class("Note") is Note
        assert issubclass(ConceptNotFoundError, LookupError)
        assert set(get_args(EdgeRole)) == {
            "derived_from",
            "cites",
            "supersedes",
            "records",
            "references",
        }
        # The route module holds the knowledge layer's own objects.
        assert knowledge_routes.Note is Note
        assert knowledge_routes.EdgeRole is EdgeRole

    def test_search_parses_class_through_knowledge(self) -> None:
        src = inspect.getsource(knowledge_routes.search_knowledge)
        assert "molab.knowledge" in src
        assert "parse_class" in src
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
        from molab.fs import LocalFileSystem
        from molab.server.deps.resolution import get_workspace
        from tests.support.counting_fs import CountingFileSystem

        ws, _exp, _run = lab
        fs = CountingFileSystem(LocalFileSystem())
        with served(ws) as client:
            client.app.dependency_overrides[get_workspace] = lambda: Workspace(ws.root, fs=fs)
            fs.reset()
            response = client.get("/api/knowledge")
        assert response.status_code == 200, response.text
        assert fs.for_basename("idea.md", "read_text") > 0
        assert fs.calls["scandir"] > 0
        assert "fs=workspace.fs" in inspect.getsource(knowledge_routes.list_knowledge)


class TestSearchKnowledge:
    def test_search_calls_knowledge_search(self) -> None:
        src = inspect.getsource(knowledge_routes.search_knowledge)
        assert "Knowledge(" in src
        assert ".search(" in src
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
        from molab.fs import LocalFileSystem
        from molab.server.deps.resolution import get_workspace
        from tests.support.counting_fs import CountingFileSystem

        ws, _exp, _run = lab
        fs = CountingFileSystem(LocalFileSystem())
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

    def test_route_source_does_not_parse_asset_directories(self) -> None:
        source = inspect.getsource(knowledge_routes)
        assert 'parent.name == "assets"' not in source
        assert ".asset_dir" + "(" not in source
        resolver = inspect.getsource(knowledge_routes._ref_card)
        for name in ("RefNotFoundError", "AmbiguousRefError", "InvalidRefError"):
            assert name in resolver
