"""Public surface of ``molab.knowledge`` after the knowledge/workspace flip.

A public name is defined **in** ``molab.knowledge``: no name is handed over from
``molab.workspace``. Retired product names and ``ConceptNotFoundError`` are that layer's own internal
parts, not ``__all__``. The names a caller is allowed to import are pinned below
(see :class:`TestPublicAll` and :class:`TestTheNamesMolmcpImports`).
"""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path

import pytest

import molab.knowledge as knowledge
from molab.knowledge import Knowledge, Note
from molab.knowledge.search import ConceptIndexEntry, SearchHit
from molab.knowledge.sources import (
    SourcedHit,
    search_sources,
)
from molab.workspace import Workspace

#: ``module path`` → the attribute a caller imports from it.
MOLMCP_IMPORTS: tuple[tuple[str, str], ...] = (
    ("molab.knowledge.sources", "KnowledgeSourceStore"),
    ("molab.knowledge.sources", "search_sources"),
    ("molab.knowledge.sources", "SourceNotFoundError"),
    ("molab.knowledge", "Knowledge"),
    ("molab.knowledge.errors", "KnowledgeNotFoundError"),
)

#: The names a caller must be able to import by name.
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
)

#: The whole exported surface, pinned — so a name added by 01-03 is not handed
#: out silently (a subset assertion would miss it).
PINNED_ALL: frozenset[str] = frozenset(
    {
        "Edge",
        "EdgeRole",
        "Finding",
        "Knowledge",
        "KnowledgeNotFoundError",
        "KnowledgeScope",
        "KnowledgeSourceStore",
        "Literature",
        "Note",
        "Observation",
        "Plan",
        "ReferenceMeta",
        "Report",
        "SearchHit",
        "SearchResult",
        "SourceKind",
        "SourceNotFoundError",
        "SourceRef",
        "SourcedHit",
        "WikiSource",
        "ZoteroItem",
        "folder",
        "parse_class",
        "read_zotero",
        "resolve_source",
        "search_sources",
    }
)

#: This layer's own internals: real classes a caller reaches through a public
#: verb, never through ``from molab.knowledge import …``.
INTERNAL_NOT_PUBLIC: tuple[str, ...] = (
    "Concept",
    "ReferenceConcept",
    "ConceptNotFoundError",
    "Backlink",
    "ConceptIndexEntry",
    "LinkScan",
    "extract_title",
)


@pytest.fixture
def wiki(tmp_path: Path) -> Path:
    """A one-note workspace: ``knowledges/tg-cooling.md`` under ``wiki/``."""
    root = tmp_path / "wiki"
    workspace = Workspace(root, name="wiki")
    workspace.materialize()
    Note(workspace, "tg-cooling").write("# Cooling rate\n\nQuench at 10 K/ns to reach Tg.\n")
    return root


def _workspace_hits(root: Path, query: str):
    """The workspace searched through the seam a host with its own scan passes."""
    return search_sources(
        query,
        workspace_root=root,
        include_workspace=True,
        workspace_searcher=lambda: Knowledge(root).search(query),
    )


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

    def test_a_named_source_prefixes_its_name(self) -> None:
        # Pinned at ``SourcedHit.ref`` — the one place the format is defined.
        # Not driven end-to-end: ``search_sources`` searches a *registered*
        # source through the old walker, which descends directories only and so
        # cannot see a ``knowledges/<slug>.md`` file document (the structural
        # gap the document-as-file migration left; owned by no member of this
        # chain). The workspace half below is end-to-end.
        hit = SourcedHit(
            source="lab",
            hit=SearchHit(entry=ConceptIndexEntry(path="knowledges/tg-cooling.md", type="Note")),
            abs_path=None,
            rank=1,
        )

        assert hit.ref == "lab:knowledges/tg-cooling.md"

    def test_the_active_workspace_is_the_unnamed_source(self, wiki: Path) -> None:
        # A bare ref (no prefix) means "the workspace" — molmcp's read() relies
        # on this to accept a workspace-relative path with no source.
        [hit] = _workspace_hits(wiki, "cooling")

        assert [hit.ref] == ["knowledges/tg-cooling.md"]

    def test_a_ref_round_trips_back_to_its_document(self, wiki: Path) -> None:
        [hit] = _workspace_hits(wiki, "cooling")
        source, _, rel = hit.ref.partition(":") if ":" in hit.ref else ("", "", hit.ref)

        assert source == ""
        assert Note(wiki / rel).exists()


class TestTheSearchHitFieldsMolmcpReads:
    def test_every_field_the_search_tool_emits_is_present(self, wiki: Path) -> None:
        # Mirrors the dict built at molmcp knowledge.py:131-138.
        [hit] = Knowledge(wiki).search("cooling").hits

        assert hit.entry.path == "knowledges/tg-cooling.md"
        assert hit.entry.title == "Cooling rate"
        assert hit.entry.type == "Note"
        assert isinstance(hit.entry.tags, tuple)
        assert hit.score > 0
        assert hit.snippet  # the reason the model was given this hit


class TestTheInformationARefMustYield:
    """What molmcp needs off a resolved document, however it comes to be spelled.

    The accessors are named once, here. The refactor replaces these seven method
    calls with attribute reads on an eager value; when it does, this is the only
    test that should need touching, and the assertions below — the *information* —
    must all still hold.
    """

    def test_a_resolved_document_yields_what_the_read_tool_reports(self, wiki: Path) -> None:
        doc = Note(wiki, "tg-cooling")

        title = doc.frontmatter().get("title") or doc.name  # → doc.title
        type_ = doc.type()  # → doc.type
        tags = doc.tags()  # → doc.tags
        body = doc.read()
        edges = doc.links()  # → doc.edges
        openable = doc.path  # → doc.origin.body_path

        assert title == "tg-cooling"
        assert type_ == "note.note"
        assert tuple(tags) == ()
        assert "Quench at 10 K/ns" in body
        assert edges == []
        assert openable.is_file(), "the path handed to the model must be openable"


class TestPublicAll:
    """``molab.knowledge.__all__`` is the Knowledge handle plus six subclasses."""

    @pytest.mark.parametrize("name", REQUIRED_PUBLIC)
    def test_name_is_exported(self, name: str) -> None:
        assert name in knowledge.__all__

    def test_the_whole_all_set_is_pinned(self) -> None:
        assert set(knowledge.__all__) == PINNED_ALL

    @pytest.mark.parametrize("name", INTERNAL_NOT_PUBLIC)
    def test_internal_name_is_not_exported(self, name: str) -> None:
        assert name not in knowledge.__all__

    def test_every_public_name_is_knowledge_defined(self) -> None:
        """No public name is handed over from ``molab.workspace``.

        Only *defined* exports are checked: a typing alias (``EdgeRole`` /
        ``SourceKind``) owns no defining module of its own — it renders as
        ``typing``.
        """
        for name in knowledge.__all__:
            obj = getattr(knowledge, name)
            if not (inspect.isclass(obj) or inspect.isfunction(obj)):
                continue
            module = getattr(obj, "__module__", "")
            assert module.startswith("molab.knowledge"), f"{name} is defined in {module!r}"
