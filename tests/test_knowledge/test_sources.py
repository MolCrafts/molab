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
    search_sources,
)
from molab.workspace import Workspace


@pytest.fixture
def store(tmp_path: Path) -> KnowledgeSourceStore:
    return KnowledgeSourceStore(tmp_path / "ws", user_dir=tmp_path / "user")


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
        assert store.config_path(KnowledgeScope.WORKSPACE) == Path(
            Workspace.machine_dir(tmp_path / "ws") / "knowledge.json"
        )

    def test_workspace_config_ignores_the_cli_root_override(self, tmp_path: Path) -> None:
        from molab.workspace.workspace import set_cli_root_override

        set_cli_root_override(tmp_path / "other", explicit=True)
        try:
            store = KnowledgeSourceStore(tmp_path / "ws", user_dir=tmp_path / "user")
            assert store.config_path(KnowledgeScope.WORKSPACE) == Path(
                Workspace.machine_dir(tmp_path / "ws") / "knowledge.json"
            )
        finally:
            set_cli_root_override(None)

    def test_sources_defines_no_machine_dir_name(self) -> None:
        import molab.knowledge.sources as sources

        assert not hasattr(sources, "MOLAB_DIR")
        assert "MOLAB_DIR" not in sources.__all__


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
        from molab.knowledge.search import ConceptIndexEntry, SearchHit
        from molab.knowledge.sources import SourcedHit

        hit = SourcedHit(
            source="papers",
            hit=SearchHit(entry=ConceptIndexEntry(path="A1B2C3D4", type="reference.reference")),
            abs_path=None,
            rank=1,
        )

        assert hit.abs_path is None
        assert hit.ref == "papers:A1B2C3D4"  # the ref still addresses it


def _wiki(root: Path, name: str, body: str) -> None:
    Note(root / name).write(body)


class TestSearchSources:
    def test_a_wiki_hit_points_at_the_markdown_file(self, tmp_path: Path) -> None:
        wiki = tmp_path / "wiki"
        wiki.mkdir()
        _wiki(wiki, "tg", "# Tg\n\nQuench at 1 K/ns.\n")
        (wiki / "knowledges").mkdir()
        (wiki / "knowledges" / "hidden.md").write_text("---\nclass: Note\n---\n\nhidden\n")
        store = KnowledgeSourceStore(tmp_path / "ws", user_dir=tmp_path / "user")
        store.add(WikiSource(name="wiki-a", root=str(wiki)))

        [hit] = search_sources("quench", sources=["wiki-a"], include_workspace=False, store=store)

        assert hit.ref == "wiki-a:tg.md"
        assert hit.abs_path is not None
        assert Path(hit.abs_path).name == "tg.md"
        assert Path(hit.abs_path).is_file()
        assert "1 K/ns" in Path(hit.abs_path).read_text(encoding="utf-8")

    def test_concept_type_filters_by_class_name(self, tmp_path: Path) -> None:
        wiki = tmp_path / "wiki"
        wiki.mkdir()
        _wiki(wiki, "tg", "# Tg\n\nQuench at 1 K/ns.\n")
        store = KnowledgeSourceStore(tmp_path / "ws", user_dir=tmp_path / "user")
        store.add(WikiSource(name="wiki-a", root=str(wiki)))

        notes = search_sources(
            "quench",
            sources=["wiki-a"],
            include_workspace=False,
            concept_type="Note",
            store=store,
        )
        findings = search_sources(
            "quench",
            sources=["wiki-a"],
            include_workspace=False,
            concept_type="Finding",
            store=store,
        )

        assert [hit.ref for hit in notes] == ["wiki-a:tg.md"]
        assert findings == []
        with pytest.raises(ValueError, match="unknown knowledge class"):
            search_sources(
                "quench",
                sources=["wiki-a"],
                include_workspace=False,
                concept_type="Bogus",
                store=store,
            )

    def test_an_unnamed_workspace_hit_is_the_document_path(self, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "lab", name="Lab")
        ws.materialize()
        Note(ws, "local").write("# Local\n\nhello local\n")
        store = KnowledgeSourceStore(ws.root, user_dir=tmp_path / "user")

        [hit] = search_sources("local", workspace_root=ws.root, store=store)

        assert hit.ref == "knowledges/local.md"


class TestOpenBundle:
    def test_opening_an_unregistered_name_raises(self, tmp_path: Path) -> None:
        store = KnowledgeSourceStore(tmp_path / "ws", user_dir=tmp_path / "user")
        with pytest.raises(SourceNotFoundError):
            open_source("nope", store=store)

    def test_opening_a_registered_wiki_walks_its_markdown(self, tmp_path: Path) -> None:
        wiki = tmp_path / "wiki"
        wiki.mkdir()
        _wiki(wiki, "n", "# N\n")
        store = KnowledgeSourceStore(tmp_path / "ws", user_dir=tmp_path / "user")
        store.add(WikiSource(name="w", root=str(wiki)))

        assert [item.name for item in open_source("w", store=store).walk()] == ["n"]
