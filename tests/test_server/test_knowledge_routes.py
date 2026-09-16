"""``/api/knowledge`` — ranked search and the knowledge-source listing.

The server is pure exposure: ranking, tokenization and cross-source fusion all
live in :mod:`molexp.knowledge`. These tests check that the wire shape carries
what a UI needs (which source a hit came from, and a ref it can follow) and that
the route reaches registered wikis, not only the active workspace.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from molexp.knowledge import Note
from molexp.knowledge.sources import KnowledgeSourceStore, WikiSource


@pytest.fixture(autouse=True)
def _isolated_sources(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Never read or write the developer's real ``~/.molexp/knowledge.json``."""
    home = tmp_path / "_home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: home))
    import molexp.knowledge.sources as sources_mod

    monkeypatch.setattr(sources_mod, "USER_DIR", home / ".molexp")


@pytest.fixture
def wiki(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A registered group wiki living OUTSIDE the workspace.

    Outside matters: the ``workspace`` fixture roots the workspace at
    ``tmp_path``, so a wiki nested under it would also be found by the
    workspace's own bundle walk and these tests would pass for the wrong reason.
    """
    root = tmp_path_factory.mktemp("lab_wiki")
    note = Note(root / "tg-protocol")
    note.write_meta({"tags": ["Tg"]})
    note.set_body("# 玻璃化转变温度 Tg 的模拟流程\n\n## 降温速率的选择\n以 1 K/ns 降温。\n")
    KnowledgeSourceStore().add(
        WikiSource(name="lab-wiki", root=str(root), description="group wiki")
    )
    return root


class TestKnowledgeSourcesRoute:
    def test_lists_a_registered_source(self, client, wiki: Path) -> None:
        body = client.get("/api/knowledge/sources").json()
        assert [s["name"] for s in body["sources"]] == ["lab-wiki"]
        assert body["sources"][0]["description"] == "group wiki"
        assert body["sources"][0]["available"] is True

    def test_reports_an_unavailable_source_rather_than_hiding_it(
        self, client, tmp_path: Path
    ) -> None:
        KnowledgeSourceStore().add(
            WikiSource(name="offline", root=str(tmp_path / "not-mounted-today"))
        )
        body = client.get("/api/knowledge/sources").json()
        assert body["sources"][0]["available"] is False

    def test_empty_when_nothing_registered(self, client) -> None:
        assert client.get("/api/knowledge/sources").json()["sources"] == []


class TestKnowledgeSearchRoute:
    def test_a_chinese_question_reaches_the_registered_wiki(self, client, wiki: Path) -> None:
        body = client.get(
            "/api/knowledge/search", params={"q": "计算Tg的时候升降温怎么选择"}
        ).json()
        assert body["hits"], "the question must not come back empty"
        top = body["hits"][0]
        assert top["source"] == "lab-wiki"
        assert top["ref"] == "lab-wiki:tg-protocol"
        assert top["score"] > 0

    def test_hits_carry_the_snippet_that_earned_them(self, client, wiki: Path) -> None:
        body = client.get("/api/knowledge/search", params={"q": "降温速率"}).json()
        assert "降温速率" in body["hits"][0]["snippet"]

    def test_source_filter_restricts_the_search(self, client, wiki: Path) -> None:
        body = client.get(
            "/api/knowledge/search", params={"q": "降温速率", "source": ["elsewhere"]}
        ).json()
        assert body["hits"] == []

    def test_no_match_is_an_empty_result_not_an_error(self, client, wiki: Path) -> None:
        response = client.get("/api/knowledge/search", params={"q": "quantum chromodynamics"})
        assert response.status_code == 200
        assert response.json()["hits"] == []

    def test_limit_is_validated_at_the_boundary(self, client) -> None:
        assert client.get("/api/knowledge/search", params={"q": "x", "limit": 0}).status_code == 422

    def test_workspace_notes_are_searched_too(self, client, workspace) -> None:
        note = Note(Path(str(workspace.resolve())) / "local-note")
        note.write_meta()
        note.set_body("# Local\n\nthe sigma scan diverged\n")
        body = client.get("/api/knowledge/search", params={"q": "sigma scan"}).json()
        assert [h["ref"] for h in body["hits"]] == ["local-note"]
        assert body["hits"][0]["source"] == ""


class TestKnowledgeReadsAreCheap:
    """The read endpoints walk once and never write (P1-1f)."""

    def test_list_knowledge_walks_the_bundle_exactly_once(
        self, client, workspace, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from molexp.knowledge.bundle import Bundle as KnowledgeBundle

        root = Path(str(workspace.resolve()))
        for name in ("alpha", "beta"):
            note = Note(root / name)
            note.write_meta()
            note.set_body(f"# {name}\n\nbody\n")

        walks = 0
        original = KnowledgeBundle.walk_with_meta

        def counting_walk(self):
            nonlocal walks
            walks += 1
            return original(self)

        monkeypatch.setattr(KnowledgeBundle, "walk_with_meta", counting_walk)
        body = client.get("/api/knowledge").json()
        assert {n["relPath"] for n in body["notes"]} == {"alpha", "beta"}
        # notes + references used to be two independent walks.
        assert walks == 1

    def test_list_knowledge_reads_each_marker_once(self, client, workspace) -> None:
        root = Path(str(workspace.resolve()))
        note = Note(root / "tagged")
        note.write_meta({"tags": ["important"], "status": "stale"})
        note.set_body("# Tagged\n\nbody\n")
        body = client.get("/api/knowledge", params={"tag": "important"}).json()
        assert [n["relPath"] for n in body["notes"]] == ["tagged"]
        assert body["notes"][0]["tags"] == ["important"]
        assert body["notes"][0]["status"] == "stale"
        assert client.get("/api/knowledge", params={"status": "active"}).json()["notes"] == []

    def test_search_get_leaves_the_tree_untouched(self, client, workspace) -> None:
        from molexp.knowledge.bundle_index import INDEX_JSON_FILENAME, INDEX_MD_FILENAME

        root = Path(str(workspace.resolve()))
        note = Note(root / "local-note")
        note.write_meta()
        note.set_body("# Local\n\nthe sigma scan diverged\n")
        before = {p: p.stat().st_mtime_ns for p in root.rglob("*")}

        body = client.get("/api/knowledge/search", params={"q": "sigma scan"}).json()
        assert [h["ref"] for h in body["hits"]] == ["local-note"]

        # A GET is a read: no derived index files appear and nothing changed.
        assert not (root / INDEX_JSON_FILENAME).exists()
        assert not (root / INDEX_MD_FILENAME).exists()
        assert {p: p.stat().st_mtime_ns for p in root.rglob("*")} == before

    def test_search_skips_run_output_subtrees(self, client, workspace) -> None:
        # A marker planted inside a run's ``executions/`` is never a hit: the
        # route searches the workspace through its layout-pruned bundle.
        root = Path(str(workspace.resolve()))
        project = workspace.add_project("p")
        run = project.add_experiment("e").add_run(params={})
        decoy = Path(str(run.resolve())) / "executions" / "exec-1" / "decoy"
        decoy.mkdir(parents=True)
        (decoy / "meta.yaml").write_text("type: note.note\nid: decoy\n")
        (decoy / "index.md").write_text("# Decoy\n\nthe sigma scan diverged\n")
        real = Note(root / "real-note")
        real.write_meta()
        real.set_body("# Real\n\nthe sigma scan diverged\n")

        body = client.get("/api/knowledge/search", params={"q": "sigma scan"}).json()
        assert [h["ref"] for h in body["hits"]] == ["real-note"]


class TestKnowledgeListSeesNotesNamedLikeRunOutput:
    """``GET /api/knowledge`` must not lose a Note because of its directory name.

    Regression: layout pruning once matched a bare directory name at any depth,
    so a Note mounted as ``logs`` / ``source`` / ``artifacts`` was on disk but
    absent from the API, the tree and search. Pruning is now scoped to a Run's
    own children, so only genuine run output is skipped.
    """

    @pytest.fixture
    def notes_named_like_output(self, workspace):
        from molexp.workspace.knowledge_mount import mount_note

        project = workspace.add_project("p")
        experiment = project.add_experiment("e")
        experiment.add_run(params={"x": 1})
        for host in (workspace, project, experiment):
            for name in ("logs", "source", "artifacts"):
                mount_note(host, name, body=f"# {name}\n\nreal knowledge\n")
        return workspace

    def test_route_returns_them_at_every_level(self, client, notes_named_like_output) -> None:
        paths = {n["relPath"] for n in client.get("/api/knowledge").json()["notes"]}
        for name in ("logs", "source", "artifacts"):
            assert name in paths, f"root-level {name!r} note missing from /api/knowledge"
            assert f"projects/p/{name}" in paths
            assert f"projects/p/experiments/e/{name}" in paths
