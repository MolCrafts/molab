"""Tests for the in-memory bundle index + its index-level search filters.

``Bundle.scan_index()`` walks the whole Concept tree (``meta.json`` +
markdown-link graph) into an in-memory :class:`BundleIndex` and returns it with
the bodies and heads it read. Nothing is persisted: there is no ``index.json``
or ``INDEX.md`` (arch-own-01-cleanup removed the derived sibling files), so a
query always sees the tree as it is on disk. ``search()``'s index-level filters
(type / tag / text AND semantics) live here; its body-aware retrieval is owned
by ``test_bundle_search.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

from molab.knowledge.bundle import Bundle
from molab.workspace import Folder, Workspace

CONCEPT_KIND = "bundle.concept"


def _hierarchy(tmp_path: Path) -> Path:
    ws = Workspace(root=tmp_path / "lab")
    ws.materialize()
    ws.add_project("p").add_experiment("e").add_run(id="r")
    return tmp_path


def _run_rel(root: Path) -> str:
    """The run's bundle-relative identity — its directory is named by its params."""
    b = Bundle(root)
    return next(p for p in (b.rel_path(c) for c in b.walk()) if "/runs/" in p)


def _concept(name: str, root_path: Path) -> Folder:
    folder = Folder(name=name, kind=CONCEPT_KIND, root_path=str(root_path))
    folder.materialize()
    folder.write_meta()
    return folder


class TestScanIndex:
    """``Bundle.scan_index`` — the in-memory rollup; it writes nothing."""

    def test_entries_equal_walk_set_with_typed_rows(self, tmp_path: Path) -> None:
        root = _hierarchy(tmp_path)
        b = Bundle(root)
        idx, _bodies, _metas = b.scan_index()
        assert {e.path for e in idx.entries} == {b.rel_path(f) for f in b.walk()}
        by_path = {e.path: e for e in idx.entries}
        assert by_path["lab"].type == "workspace.root"
        assert by_path[_run_rel(root)].type == "workspace.run"

    def test_persists_no_index_files(self, tmp_path: Path) -> None:
        root = _hierarchy(tmp_path)
        b = Bundle(root)
        b.scan_index()
        assert not (root / "index.json").exists()
        assert not (root / "INDEX.md").exists()
        assert all(not b.rel_path(f).endswith(".json") for f in b.walk())
        assert all(not b.rel_path(f).endswith(".md") for f in b.walk())

    def test_title_from_h1_else_name_and_resolves_links(self, tmp_path: Path) -> None:
        root = tmp_path / "bundle"
        root.mkdir()
        a = _concept("alpha", root)
        b_concept = _concept("beta", root)
        a.write_index("# Alpha Title\n\nbody\n- [to-b](../beta)\n")
        bundle = Bundle(root)
        idx, bodies, _metas = bundle.scan_index()
        by_path = {e.path: e for e in idx.entries}
        assert by_path["alpha"].title == "Alpha Title"
        assert by_path["beta"].title == "beta"  # no H1 → concept name
        assert by_path["beta"].path == bundle.rel_path(b_concept)
        # link resolves to beta as bundle-relative posix
        assert "beta" in by_path["alpha"].links
        assert bodies["alpha"].startswith("# Alpha Title")

    def test_rescan_reflects_new_concept(self, tmp_path: Path) -> None:
        root = _hierarchy(tmp_path)
        b = Bundle(root)
        before, _bodies, _metas = b.scan_index()
        assert "lab/projects/q" not in {e.path for e in before.entries}
        Workspace(root=root / "lab").add_project("q")
        after, _bodies, _metas = b.scan_index()
        assert "lab/projects/q" in {e.path for e in after.entries}


class TestSearchFilters:
    """``Bundle.search`` index-level filters (body-aware match: see
    ``test_bundle_search.py``)."""

    def test_filter_by_type(self, tmp_path: Path) -> None:
        b = Bundle(_hierarchy(tmp_path))
        runs = b.search(concept_type="workspace.run")
        assert [h.entry.path for h in runs.hits] == [_run_rel(b.root)]
        assert runs.truncated is False

    def test_filter_by_tag(self, tmp_path: Path) -> None:
        root = tmp_path / "bundle"
        root.mkdir()
        tagged = _concept("tagged", root)
        # tags live in meta.json; write_meta() only stores type+id, so add tags directly
        (Path(tagged.resolve()) / "meta.json").write_text(
            json.dumps({"type": CONCEPT_KIND, "id": "tagged", "tags": ["important"]})
        )
        _concept("plain", root)
        b = Bundle(root)
        result = b.search(tag="important")
        assert [h.entry.path for h in result.hits] == ["tagged"]

    def test_text_and_type_use_and_semantics(self, tmp_path: Path) -> None:
        b = Bundle(_hierarchy(tmp_path))
        paths = {h.entry.path for h in b.search("p").hits}
        assert {"lab/projects/p", "lab/projects/p/experiments/e"} <= paths
        # AND: text + type
        assert [h.entry.path for h in b.search("lab", concept_type="workspace.run").hits] == [
            _run_rel(b.root)
        ]

    def test_search_reflects_new_concept(self, tmp_path: Path) -> None:
        root = _hierarchy(tmp_path)
        b = Bundle(root)
        b.search()
        Workspace(root=root / "lab").add_project("q")
        assert any(h.entry.path == "lab/projects/q" for h in b.search().hits)
