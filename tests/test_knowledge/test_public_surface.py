"""Public surface of ``molab.knowledge`` after the Knowledge-handle unification.

``Bundle`` / ``Concept`` / ``ReferenceConcept`` / ``KnowledgeItem`` /
``ConceptNotFoundError`` are shims, not ``__all__``. The names a caller is
allowed to import are pinned below (see :class:`TestPublicAll` and
:class:`TestTheNamesMolmcpImports`).
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

import molab.knowledge as knowledge
from molab.knowledge import Note
from molab.knowledge.sources import KnowledgeSourceStore, WikiSource, search_sources

#: ``module path`` → the attribute a caller imports from it.
MOLMCP_IMPORTS: tuple[tuple[str, str], ...] = (
    ("molab.knowledge.sources", "KnowledgeSourceStore"),
    ("molab.knowledge.sources", "search_sources"),
    ("molab.knowledge.sources", "SourceNotFoundError"),
    ("molab.knowledge", "Knowledge"),
    ("molab.knowledge.errors", "KnowledgeNotFoundError"),
)

REQUIRED_PUBLIC: tuple[str, ...] = (
    "Knowledge",
    "Note",
    "Literature",
    "Report",
    "Finding",
    "Plan",
    "Observation",
    "SourceRef",
    "KnowledgeNotFoundError",
    "folder",
    # The write verbs a workspace host needs, plus the layout name and the
    # class-name entry point the redirects (04-07) import from here.
    "write_knowledge",
    "mount_note",
    "normalize_sources",
    "harvest_run",
    "parse_knowledge_class",
    "PLAN_BOOK_NAME",
)

SHIM_NOT_PUBLIC: tuple[str, ...] = (
    "Bundle",
    "Concept",
    "ReferenceConcept",
    "KnowledgeItem",
    "ConceptNotFoundError",
    "Backlink",
    "BundleIndex",
    "ConceptIndexEntry",
    "LinkScan",
    "knowledge_filename",
    "extract_title",
    "NoteMeta",
)


@pytest.fixture
def wiki(tmp_path: Path) -> Path:
    """A one-note bundle, registered as the named source ``lab``."""
    root = tmp_path / "wiki"
    note = Note(root / "tg-cooling")
    note.write("# Cooling rate\n\nQuench at 10 K/ns to reach Tg.\n")
    return root


class TestTheNamesMolmcpImports:
    @pytest.mark.parametrize(("module", "name"), MOLMCP_IMPORTS)
    def test_the_name_resolves_at_the_path_molmcp_spells(self, module: str, name: str) -> None:
        # An alias counts: molmcp imports by path, so a rename must leave one.
        assert hasattr(importlib.import_module(module), name)

    def test_not_found_is_a_lookup_error(self) -> None:
        # The server maps LookupError to 404. A bare Exception here turns every
        # "no such document" into a 500 for every consumer at once.
        from molab.knowledge.errors import KnowledgeNotFoundError

        assert issubclass(KnowledgeNotFoundError, LookupError)


class TestTheRefFormat:
    """``"<source>:<ref>"`` is how molmcp addresses a document across turns."""

    def test_a_named_source_prefixes_its_name(self, tmp_path: Path, wiki: Path) -> None:
        store = KnowledgeSourceStore(tmp_path / "ws", user_dir=tmp_path / "user")
        store.add(WikiSource(name="lab", root=str(wiki)))

        hits = search_sources("cooling", store=store, include_workspace=False)

        assert [h.ref for h in hits] == ["lab:tg-cooling"]

    def test_the_active_workspace_is_the_unnamed_source(self, wiki: Path) -> None:
        # A bare ref (no prefix) means "the workspace" — molmcp's read() relies
        # on this to accept a workspace-relative path with no source.
        hits = search_sources("cooling", workspace_root=wiki, include_workspace=True)

        assert [h.ref for h in hits] == ["tg-cooling"]

    def test_a_ref_round_trips_back_to_its_document(self, wiki: Path) -> None:
        [hit] = search_sources("cooling", workspace_root=wiki, include_workspace=True)
        source, _, rel = hit.ref.partition(":") if ":" in hit.ref else ("", "", hit.ref)

        assert source == ""
        assert Note(wiki / rel).exists()


class TestTheSearchHitFieldsMolmcpReads:
    def test_every_field_the_search_tool_emits_is_present(self, wiki: Path) -> None:
        # Mirrors the dict built at molmcp knowledge.py:131-138.
        [hit] = search_sources("cooling", workspace_root=wiki, include_workspace=True)

        assert hit.ref and hit.source == "" and hit.rank == 1
        assert hit.hit.entry.title == "Cooling rate"
        assert hit.hit.entry.type == "note"
        assert isinstance(hit.hit.entry.tags, tuple)
        assert hit.hit.score > 0
        assert hit.hit.snippet  # the reason the model was given this hit


class TestTheInformationARefMustYield:
    """What molmcp needs off a resolved document, however it comes to be spelled.

    The accessors are named once, here. The refactor replaces these seven method
    calls with attribute reads on an eager value; when it does, this is the only
    test that should need touching, and the assertions below — the *information* —
    must all still hold.
    """

    def test_a_resolved_document_yields_what_the_read_tool_reports(self, wiki: Path) -> None:
        doc = Note(wiki / "tg-cooling")

        title = doc.read_meta().get("title") or doc.name  # → doc.title
        type_ = doc.type()  # → doc.type
        tags = doc.tags()  # → doc.tags
        body = doc.read()
        edges = doc.links()  # → doc.edges
        openable = Path(doc.path) / "index.md"  # → doc.origin.body_path

        assert title == "tg-cooling"
        assert type_ == "note"
        assert tuple(tags) == ()
        assert "Quench at 10 K/ns" in body
        assert edges == []
        assert openable.is_file(), "the path handed to the model must be openable"


class TestPublicAll:
    """``molab.knowledge.__all__`` is the Knowledge handle plus six subclasses."""

    @pytest.mark.parametrize("name", REQUIRED_PUBLIC)
    def test_name_is_exported(self, name: str) -> None:
        assert name in knowledge.__all__

    @pytest.mark.parametrize("name", SHIM_NOT_PUBLIC)
    def test_shim_name_is_not_exported(self, name: str) -> None:
        assert name not in knowledge.__all__
