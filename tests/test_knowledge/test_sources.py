"""The named knowledge-source registry and cross-source search."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from molab.knowledge import Note
from molab.knowledge.sources import (
    KnowledgeScope,
    KnowledgeSourceStore,
    SourceNotFoundError,
    WikiSource,
    open_source,
    resolve_source,
    search_sources,
)


@pytest.fixture
def store(tmp_path: Path) -> KnowledgeSourceStore:
    return KnowledgeSourceStore(tmp_path / "ws", user_dir=tmp_path / "user")


def _wiki(root: Path, name: str, title: str, body: str) -> Path:
    note = Note(root / name)
    note.write_meta()
    note.write(f"# {title}\n\n{body}\n")
    return root


class TestWikiSource:
    def test_name_must_be_path_safe(self) -> None:
        # Names become JSON keys, CLI args and "<source>:<path>" ref prefixes.
        with pytest.raises(ValueError, match="invalid knowledge source name"):
            WikiSource(name="Lab Wiki!", root="/x")

    def test_home_is_expanded_so_a_config_stays_portable(self) -> None:
        source = WikiSource(name="w", root="~/notes")
        assert source.path() == Path.home() / "notes"
        assert source.root == "~/notes"  # stored verbatim


class TestKnowledgeSourceStore:
    def test_add_then_get_round_trips(self, store: KnowledgeSourceStore) -> None:
        store.add(WikiSource(name="lab-wiki", root="/data/wiki", description="ours"))
        got = store.get("lab-wiki")
        assert (got.root, got.description) == ("/data/wiki", "ours")

    def test_unknown_name_raises(self, store: KnowledgeSourceStore) -> None:
        with pytest.raises(SourceNotFoundError, match="lab-wiki"):
            store.get("lab-wiki")

    def test_workspace_entry_fully_replaces_the_user_one(self, store: KnowledgeSourceStore) -> None:
        # Full replacement, not a per-field merge — the MCP store's rule.
        store.add(WikiSource(name="w", root="/user", description="from user"))
        store.add(WikiSource(name="w", root="/ws"), scope=KnowledgeScope.WORKSPACE)
        got = store.get("w")
        assert got.root == "/ws"
        assert got.description == ""

    def test_list_reports_the_winning_scope(self, store: KnowledgeSourceStore) -> None:
        store.add(WikiSource(name="a", root="/a"))
        store.add(WikiSource(name="b", root="/b"), scope=KnowledgeScope.WORKSPACE)
        assert [(s.name, scope) for s, scope in store.list()] == [
            ("a", KnowledgeScope.USER),
            ("b", KnowledgeScope.WORKSPACE),
        ]

    def test_listing_is_name_sorted(self, store: KnowledgeSourceStore) -> None:
        for name in ("zeta", "alpha", "mid"):
            store.add(WikiSource(name=name, root=f"/{name}"))
        assert [s.name for s, _ in store.list()] == ["alpha", "mid", "zeta"]

    def test_empty_store_lists_nothing(self, store: KnowledgeSourceStore) -> None:
        assert store.list() == []

    def test_remove_drops_the_entry(self, store: KnowledgeSourceStore) -> None:
        store.add(WikiSource(name="w", root="/w"))
        store.remove("w")
        assert store.list() == []

    def test_removing_an_absent_name_raises(self, store: KnowledgeSourceStore) -> None:
        # Loud, so removing a *shadowed* user entry from the wrong scope says so.
        with pytest.raises(SourceNotFoundError):
            store.remove("nope")

    def test_shorthand_string_form_is_accepted(self, tmp_path: Path) -> None:
        # {"lab-wiki": "/data/wiki"} is the form a human types by hand.
        cfg = tmp_path / "user" / "knowledge.json"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(json.dumps({"sources": {"lab-wiki": "/data/wiki"}}))
        store = KnowledgeSourceStore(user_dir=tmp_path / "user")
        assert store.get("lab-wiki").root == "/data/wiki"

    def test_a_corrupt_config_does_not_break_every_command(self, tmp_path: Path) -> None:
        cfg = tmp_path / "user" / "knowledge.json"
        cfg.parent.mkdir(parents=True)
        cfg.write_text("{not json at all")
        assert KnowledgeSourceStore(user_dir=tmp_path / "user").list() == []

    def test_one_bad_entry_does_not_hide_the_good_ones(self, tmp_path: Path) -> None:
        cfg = tmp_path / "user" / "knowledge.json"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(json.dumps({"sources": {"Bad Name!": "/x", "good": "/g"}}))
        store = KnowledgeSourceStore(user_dir=tmp_path / "user")
        assert [s.name for s, _ in store.list()] == ["good"]

    def test_workspace_scope_needs_a_workspace_root(self, tmp_path: Path) -> None:
        store = KnowledgeSourceStore(user_dir=tmp_path / "user")
        with pytest.raises(ValueError, match="workspace_root"):
            store.config_path(KnowledgeScope.WORKSPACE)

    def test_workspace_config_lands_in_the_hidden_molab_dir(
        self, store: KnowledgeSourceStore, tmp_path: Path
    ) -> None:
        assert store.config_path(KnowledgeScope.WORKSPACE) == (
            tmp_path / "ws" / ".molab" / "knowledge.json"
        )


class TestASourceDeclaresWhichBackendReadsIt:
    """``kind`` exists so an unreadable source fails loudly instead of quietly.

    ``WikiSource`` ignores unknown keys, and the config loader splats whatever
    the JSON holds into it. Without a declared ``kind``, a config written by a
    later molab (``kind: obsidian``) loses the key on load, the vault opens as
    OKF, the walk finds no ``meta.json`` anywhere, and the user gets an empty
    result with nothing to explain it. Declaring the field now — while ``okf`` is
    still the only value — is what makes that impossible later.
    """

    def test_a_plain_source_is_okf(self) -> None:
        assert WikiSource(name="lab", root="/x").kind == "okf"

    def test_the_kind_survives_a_config_round_trip(self, store: KnowledgeSourceStore) -> None:
        store.add(WikiSource(name="vault", root="/x", kind="obsidian"))

        assert store.get("vault").kind == "obsidian"

    def test_backend_options_survive_a_config_round_trip(self, store: KnowledgeSourceStore) -> None:
        # Opaque here; only the backend named by *kind* reads them.
        store.add(
            WikiSource(name="docs", root="/x", kind="docs", options={"config": "zensical.toml"})
        )

        assert store.get("docs").options == {"config": "zensical.toml"}

    def test_a_kind_that_is_not_an_identifier_is_refused(self) -> None:
        # Caught at the boundary: *kind* names a registered reader, so a value
        # that cannot be one is a config error, not a lookup miss.
        with pytest.raises(ValueError, match="invalid knowledge source kind"):
            WikiSource(name="lab", root="/x", kind="Obsidian Vault!")

    def test_an_unreadable_kind_is_still_listable(self, store: KnowledgeSourceStore) -> None:
        # No backend answers to "obsidian" yet. Listing must still work: a
        # machine missing one source's reader has to keep using the others.
        store.add(WikiSource(name="vault", root="/x", kind="obsidian"))
        store.add(WikiSource(name="lab", root="/y"))

        assert [source.name for source, _ in store.list()] == ["lab", "vault"]


class TestAHitNeedNotOfferAFile:
    """``abs_path`` is a convenience, and some sources have nothing to offer.

    A bibliographic record with no attached PDF has no file to open. Fabricating
    a path there hands a model something to read that is not on disk, so the
    field admits ``None`` and the ``ref`` stays the thing that always works.
    """

    def test_abs_path_accepts_none(self) -> None:
        from molab.knowledge.bundle_index import ConceptIndexEntry, SearchHit
        from molab.knowledge.sources import SourcedHit

        hit = SourcedHit(
            source="papers",
            hit=SearchHit(entry=ConceptIndexEntry(path="A1B2C3D4", type="reference.reference")),
            abs_path=None,
            rank=1,
        )

        assert hit.abs_path is None
        assert hit.ref == "papers:A1B2C3D4"  # the ref still addresses it


class TestOpenBundle:
    def test_resolves_and_opens_a_registered_wiki(self, tmp_path: Path) -> None:
        wiki = tmp_path / "wiki"
        wiki.mkdir()
        _wiki(wiki, "n", "Title", "body text")
        store = KnowledgeSourceStore(tmp_path / "ws", user_dir=tmp_path / "user")
        store.add(WikiSource(name="w", root=str(wiki)))

        assert resolve_source("w", store=store) == wiki
        assert [c.name for c in open_source("w", store=store).walk()] == ["n"]

    def test_opening_an_unregistered_name_raises(self, tmp_path: Path) -> None:
        store = KnowledgeSourceStore(tmp_path / "ws", user_dir=tmp_path / "user")
        with pytest.raises(SourceNotFoundError):
            open_source("nope", store=store)


class TestSearchSources:
    """Cross-source retrieval, fused by rank."""

    def _two_wikis(self, tmp_path: Path) -> KnowledgeSourceStore:
        a = tmp_path / "wiki-a"
        b = tmp_path / "wiki-b"
        a.mkdir()
        b.mkdir()
        _wiki(a, "tg", "降温速率的选择", "以 1 K/ns 降温至 200 K")
        _wiki(b, "rdf", "RDF conventions", "integration bounds for rdf")
        store = KnowledgeSourceStore(tmp_path / "ws", user_dir=tmp_path / "user")
        store.add(WikiSource(name="wiki-a", root=str(a)))
        store.add(WikiSource(name="wiki-b", root=str(b)))
        return store

    def _search(self, tmp_path: Path, query: str, **kw: object) -> list:
        store = self._two_wikis(tmp_path)
        return search_sources(
            query,
            workspace_root=tmp_path / "ws",
            include_workspace=False,
            store=store,
            **kw,  # type: ignore[arg-type]
        )

    def test_finds_a_hit_in_the_right_source(self, tmp_path: Path) -> None:
        hits = self._search(tmp_path, "降温速率")
        assert [h.source for h in hits] == ["wiki-a"]

    def test_hit_carries_the_absolute_markdown_path(self, tmp_path: Path) -> None:
        # This is what lets a caller hand over the whole document.
        hit = self._search(tmp_path, "降温速率")[0]
        assert Path(hit.abs_path).is_file()
        assert Path(hit.abs_path).name == "index.md"
        assert "1 K/ns" in Path(hit.abs_path).read_text(encoding="utf-8")

    def test_ref_is_source_qualified(self, tmp_path: Path) -> None:
        assert self._search(tmp_path, "降温速率")[0].ref == "wiki-a:tg"

    def test_ranks_are_one_based_and_contiguous(self, tmp_path: Path) -> None:
        hits = self._search(tmp_path, "rdf 降温")
        assert [h.rank for h in hits] == list(range(1, len(hits) + 1))

    def test_restricting_to_one_source_excludes_the_other(self, tmp_path: Path) -> None:
        hits = self._search(tmp_path, "rdf", sources=["wiki-a"])
        assert hits == []

    def test_an_unmounted_source_is_skipped_not_an_error(self, tmp_path: Path) -> None:
        store = self._two_wikis(tmp_path)
        store.add(WikiSource(name="gone", root=str(tmp_path / "does-not-exist")))
        hits = search_sources(
            "降温速率",
            workspace_root=tmp_path / "ws",
            include_workspace=False,
            store=store,
        )
        assert [h.source for h in hits] == ["wiki-a"]

    def test_the_active_workspace_searches_as_an_unnamed_source(self, tmp_path: Path) -> None:
        ws = tmp_path / "ws"
        ws.mkdir(parents=True, exist_ok=True)
        _wiki(ws, "local", "Local note", "降温速率 mentioned locally")
        store = self._two_wikis(tmp_path)
        hits = search_sources("降温速率", workspace_root=ws, include_workspace=True, store=store)
        assert "" in {h.source for h in hits}
        assert next(h for h in hits if h.source == "").ref == "local"


class TestWorkspaceSearcherSeam:
    """``workspace_searcher`` replaces the workspace's own search, nothing else."""

    def test_the_workspace_is_searched_through_the_seam_when_given(self, tmp_path: Path) -> None:
        from molab.knowledge.bundle_index import ConceptIndexEntry, SearchHit, SearchResult

        ws = tmp_path / "ws"
        ws.mkdir()
        _wiki(ws, "local", "Local note", "降温速率 mentioned locally")
        calls = 0

        def searcher() -> SearchResult:
            nonlocal calls
            calls += 1
            entry = ConceptIndexEntry(path="injected", type="note.note", title="Injected")
            return SearchResult(hits=(SearchHit(entry=entry, score=1.0),), truncated=False)

        hits = search_sources(
            "降温速率",
            workspace_root=ws,
            include_workspace=True,
            store=KnowledgeSourceStore(ws, user_dir=tmp_path / "user"),
            workspace_searcher=searcher,
        )
        assert calls == 1
        assert [h.ref for h in hits] == ["injected"]  # the seam's answer, not a fresh Bundle

    def test_registered_sources_still_search_per_query(self, tmp_path: Path) -> None:
        from molab.knowledge.bundle_index import SearchResult

        ws = tmp_path / "ws"
        ws.mkdir()
        wiki = _wiki(tmp_path / "wiki-a", "tg", "Tg protocol", "降温速率 in the wiki")
        store = KnowledgeSourceStore(ws, user_dir=tmp_path / "user")
        store.add(WikiSource(name="wiki-a", root=str(wiki)))
        hits = search_sources(
            "降温速率",
            workspace_root=ws,
            include_workspace=True,
            store=store,
            workspace_searcher=lambda: SearchResult(hits=(), truncated=False),
        )
        assert [h.source for h in hits] == ["wiki-a"]

    def test_without_the_seam_the_workspace_is_a_plain_bundle(self, tmp_path: Path) -> None:
        ws = tmp_path / "ws"
        ws.mkdir()
        _wiki(ws, "local", "Local note", "降温速率 mentioned locally")
        hits = search_sources(
            "降温速率",
            workspace_root=ws,
            include_workspace=True,
            store=KnowledgeSourceStore(ws, user_dir=tmp_path / "user"),
        )
        assert [h.ref for h in hits] == ["local"]
