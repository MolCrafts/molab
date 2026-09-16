"""Knowledge tools for InteractiveLoop (mirrors ``interactive/knowledge_tools.py``).

The knowledge→agent channel's agent-side contract: ``search_knowledge`` /
``read_knowledge`` wrap the workspace ``Bundle`` verbs (body-aware search,
path-as-identity read, edges + backlinks), confined to the workspace root with
the same escape rejection as the file tools. Loop tool binding is owned by
``ops/test_ops_surface.py`` + ``loops/interactive/test_loop.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from molexp.agent.loops.interactive.knowledge_tools import knowledge_tools
from molexp.workspace import Workspace, knowledge_mount
from molexp.workspace.knowledge_item import KnowledgeMeta, SourceRef

NEEDLE = "sigma-scan diverged at 0.25nm"


def _seed_workspace(tmp_path: Path) -> Workspace:
    ws = Workspace(tmp_path / "lab", name="lab")
    ws.materialize()
    exp = ws.add_project("p").add_experiment("e")
    run = exp.add_run(params={"sigma": 0.25})
    item, _ = knowledge_mount.mount_knowledge_item(exp, "failure-sigma")
    item.write_knowledge_meta(
        KnowledgeMeta(
            kind="FailureAnalysis",
            sources=[SourceRef(kind="run", ref=run.id)],
            created_by="test",
        )
    )
    item.write_index(f"# Sigma failure\n\nThe {NEEDLE} — grid too coarse.\n")
    item.cite(run.resolve(), role="derived_from")
    return ws


class TestSearchKnowledge:
    def test_body_match_returns_row_with_snippet(self, tmp_path: Path) -> None:
        ws = _seed_workspace(tmp_path)
        search, _sources, _read = knowledge_tools(Path(ws.resolve()))
        out = search("diverged")
        assert "failure-sigma" in out
        assert NEEDLE in out  # the snippet line rides along

    def test_truncated_hint_appended(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import molexp.agent.loops.interactive.knowledge_tools as kt

        ws = _seed_workspace(tmp_path)
        exp = ws.get_project("p").get_experiment("e")
        run = exp.list_runs()[0]
        for i in range(3):
            item, _ = knowledge_mount.mount_knowledge_item(exp, f"finding-{i}")
            item.write_knowledge_meta(
                KnowledgeMeta(
                    kind="Finding",
                    sources=[SourceRef(kind="run", ref=run.id)],
                    created_by="test",
                )
            )
            item.write_index("shared needle body\n")
        monkeypatch.setattr(kt, "_MAX_SEARCH_ROWS", 2)
        search, _sources, _read = knowledge_tools(Path(ws.resolve()))
        out = search("shared needle")
        assert "showing the top 2" in out
        assert "refine the query" in out


class TestReadKnowledge:
    def test_renders_meta_body_edges_and_backlinks(self, tmp_path: Path) -> None:
        ws = _seed_workspace(tmp_path)
        _search, _sources, read = knowledge_tools(Path(ws.resolve()))
        out = read("projects/p/experiments/e/failure-sigma")
        assert "kind: FailureAnalysis" in out
        assert "status: active" in out
        assert "created_by: test" in out
        assert "sources:" in out and "run:" in out
        assert NEEDLE in out  # body
        assert "## cites (out-edges)" in out and "derived_from" in out
        assert "## cited by (backlinks)" in out

    def test_missing_path_raises_with_search_hint(self, tmp_path: Path) -> None:
        ws = _seed_workspace(tmp_path)
        _search, _sources, read = knowledge_tools(Path(ws.resolve()))
        with pytest.raises(ValueError, match="search_knowledge"):
            read("projects/p/experiments/e/no-such-item")

    def test_rejects_path_escape(self, tmp_path: Path) -> None:
        ws = _seed_workspace(tmp_path)
        _search, _sources, read = knowledge_tools(Path(ws.resolve()))
        with pytest.raises(ValueError, match=r"escape|\.\.|outside"):
            read("../outside")
        with pytest.raises(ValueError, match=r"escape|outside"):
            read("/etc/passwd")


class TestExternalKnowledgeSources:
    """An agent reaches the group wiki, not just the workspace it stands in."""

    @pytest.fixture
    def wiki(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        from molexp.knowledge import Note
        from molexp.knowledge.sources import KnowledgeSourceStore, WikiSource

        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr(Path, "home", classmethod(lambda _cls: home))
        import molexp.knowledge.sources as sources_mod

        monkeypatch.setattr(sources_mod, "USER_DIR", home / ".molexp")

        root = tmp_path / "lab-wiki"
        note = Note(root / "tg-protocol")
        note.write_meta()
        note.set_body("# 玻璃化转变温度 Tg 的模拟流程\n\n## 降温速率的选择\n以 1 K/ns 降温。\n")
        KnowledgeSourceStore().add(WikiSource(name="lab-wiki", root=str(root)))
        return root

    def test_search_reaches_a_registered_wiki(self, tmp_path: Path, wiki: Path) -> None:
        ws = _seed_workspace(tmp_path)
        search, _sources, _read = knowledge_tools(Path(ws.resolve()))
        out = search("降温速率怎么选")
        assert "lab-wiki:tg-protocol" in out
        assert "source=lab-wiki" in out

    def test_read_accepts_a_source_qualified_ref(self, tmp_path: Path, wiki: Path) -> None:
        ws = _seed_workspace(tmp_path)
        _search, _sources, read = knowledge_tools(Path(ws.resolve()))
        out = read("lab-wiki:tg-protocol")
        assert "1 K/ns 降温" in out

    def test_unknown_source_lists_the_registered_ones(self, tmp_path: Path, wiki: Path) -> None:
        # The model must be able to correct itself in one turn.
        ws = _seed_workspace(tmp_path)
        _search, _sources, read = knowledge_tools(Path(ws.resolve()))
        with pytest.raises(ValueError, match="lab-wiki"):
            read("ghost-wiki:whatever")

    def test_listing_shows_the_workspace_and_every_wiki(self, tmp_path: Path, wiki: Path) -> None:
        ws = _seed_workspace(tmp_path)
        _search, list_sources, _read = knowledge_tools(Path(ws.resolve()))
        out = list_sources()
        assert "(workspace)" in out
        assert "lab-wiki" in out

    def test_a_bare_path_is_still_confined_to_the_workspace(
        self, tmp_path: Path, wiki: Path
    ) -> None:
        # Registering a wiki must not open a path-traversal door.
        ws = _seed_workspace(tmp_path)
        _search, _sources, read = knowledge_tools(Path(ws.resolve()))
        with pytest.raises(ValueError, match=r"escape|outside"):
            read(str(wiki / "tg-protocol"))
