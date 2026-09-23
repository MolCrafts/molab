"""``Bundle`` walk cost + pruning + read-only search (P1-1f).

Locks three properties of the OKF bundle façade:

- **pruning** — ``prune_dirs`` names subtrees the walk never enters, and
  ``_ops`` is always pruned;
- **one read per Concept** — the walk reads each ``meta.json`` exactly once
  and never probes with ``exists``; ``partition()`` / ``scan_index()`` hand
  that read back instead of repeating it;
- **a search never writes** — only the explicit ``build_index`` verb produces
  ``index.json`` / ``INDEX.md``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from molab.fs import LocalFileSystem
from molab.knowledge import Note, ReferenceMeta
from molab.knowledge.bundle import Bundle
from molab.knowledge.bundle_index import INDEX_JSON_FILENAME, INDEX_MD_FILENAME
from molab.knowledge.concept import META_JSON_FILENAME, Concept
from molab.knowledge.concepts import Literature
from molab.knowledge.knowledge_item import KnowledgeItem, KnowledgeMeta, SourceRef
from tests.support.counting_fs import CountingFileSystem


def _note(root: Path, rel: str, body: str = "") -> Note:
    note = Note(root / rel)
    note.write_meta()
    note.write(body or f"# {rel}\n\nbody of {rel}\n")
    return note


def _max_reads_per_path(fs: CountingFileSystem, basename: str) -> int:
    """The most times any single file named *basename* was read."""
    from collections import Counter

    per_path = Counter(
        path for name, path, _ in fs.log if name == "read_text" and path.endswith(basename)
    )
    return max(per_path.values(), default=0)


def _plant_marker(directory: Path, type_str: str = "note.note") -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / META_JSON_FILENAME).write_text(
        json.dumps({"type": type_str, "id": directory.name})
    )
    (directory / "index.md").write_text(f"# decoy {directory.name}\n")


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """A small bundle with knowledge at several depths plus decoy markers.

    Layout::

        root/
          alpha/                    note
          group/beta/               note (under a plain organizational dir)
          group/ref/                reference
          group/finding/            knowledge item
          run/                      note-typed marker (stands in for an entity)
          run/executions/e1/        DECOY marker — inside a prunable subtree
          run/artifacts/a1/         DECOY marker — inside a prunable subtree
          run/_ops/fake/            DECOY marker — the sidecar is always pruned
    """
    root = tmp_path / "bundle"
    root.mkdir()
    _note(root, "alpha")
    (root / "group").mkdir()
    _note(root, "group/beta")
    ref = Literature(root / "group" / "ref")
    ref.write(ReferenceMeta(title="A paper", authors=["Someone"], year=2020))
    item = KnowledgeItem(root / "group" / "finding")
    item.write_knowledge_meta(
        KnowledgeMeta(
            kind="Finding",
            sources=[SourceRef(kind="run", ref="run-1")],
            created_by="tester",
        )
    )
    item.write("# Finding\n\nsomething learned\n")
    _note(root, "run")
    _plant_marker(root / "run" / "executions" / "e1")
    _plant_marker(root / "run" / "artifacts" / "a1")
    _plant_marker(root / "run" / "_ops" / "fake")
    return root


PRUNE = frozenset({"executions", "artifacts"})


class TestPruneDirs:
    def test_unpruned_walk_sees_the_decoys(self, tree: Path) -> None:
        rels = {Bundle(tree).rel_path(c) for c in Bundle(tree).walk()}
        assert "run/executions/e1" in rels
        assert "run/artifacts/a1" in rels

    def test_pruned_walk_skips_the_named_subtrees_at_any_depth(self, tree: Path) -> None:
        b = Bundle(tree, prune_dirs=PRUNE)
        rels = {b.rel_path(c) for c in b.walk()}
        assert rels == {"alpha", "group/beta", "group/ref", "group/finding", "run"}

    def test_ops_sidecar_is_always_pruned(self, tree: Path) -> None:
        for b in (Bundle(tree), Bundle(tree, prune_dirs=PRUNE)):
            assert "_ops" in b.prune_dirs
            assert not any(b.rel_path(c).startswith("run/_ops") for c in b.walk())

    def test_pruned_subtree_is_never_listed(self, tree: Path) -> None:
        fs = CountingFileSystem(LocalFileSystem())
        list(Bundle(tree, fs=fs, prune_dirs=PRUNE).walk())
        listed = {path for name, path, _ in fs.log if name == "listdir"}
        assert not any(p.endswith(("/executions", "/artifacts", "/e1", "/a1")) for p in listed)


class TestOneReadPerConcept:
    def test_walk_reads_each_meta_once_and_never_probes(self, tree: Path) -> None:
        fs = CountingFileSystem(LocalFileSystem())
        b = Bundle(tree, fs=fs, prune_dirs=PRUNE)
        concepts = list(b.walk())
        assert len(concepts) == 5
        # One try-read of ``meta.json`` per directory visited: the 5 Concepts
        # plus the organizational ``group/`` dir, whose read *fails* — that
        # failure IS the "not a concept" answer, so no ``exists`` probe is ever
        # issued, and no marker is read twice (the type comes from the same read).
        # Plus one for the root itself, whose type decides which of its own
        # children are prunable (a Bundle may be rooted at a run) — once per
        # walk, not per directory.
        assert fs.for_basename(META_JSON_FILENAME, "read_text") == 6 + 1
        assert fs.calls["exists"] == 0
        assert _max_reads_per_path(fs, META_JSON_FILENAME) == 1

    def test_walk_reconstructs_typed_subclasses_from_that_one_read(self, tree: Path) -> None:
        by_rel = {Bundle(tree).rel_path(c): c for c in Bundle(tree, prune_dirs=PRUNE).walk()}
        assert isinstance(by_rel["alpha"], Note)
        assert isinstance(by_rel["group/ref"], Literature)
        assert isinstance(by_rel["group/finding"], KnowledgeItem)

    def test_walk_with_meta_hands_back_the_parsed_marker(self, tree: Path) -> None:
        b = Bundle(tree, prune_dirs=PRUNE)
        metas = {b.rel_path(c): meta for c, meta in b.walk_with_meta()}
        assert metas["group/ref"]["title"] == "A paper"
        assert metas["group/finding"]["kind"] == "Finding"
        assert metas["alpha"] == {"type": "note.note", "id": "alpha"}

    def test_get_reads_meta_once_without_probing(self, tree: Path) -> None:
        fs = CountingFileSystem(LocalFileSystem())
        concept = Bundle(tree, fs=fs).get("group/ref")
        assert isinstance(concept, Literature)
        assert fs.for_basename(META_JSON_FILENAME, "read_text") == 1
        assert fs.calls["exists"] == 0

    def test_partition_is_one_walk_with_typed_views_and_metas(self, tree: Path) -> None:
        fs = CountingFileSystem(LocalFileSystem())
        b = Bundle(tree, fs=fs, prune_dirs=PRUNE)
        part = b.partition()
        # notes / references / items from the same walk …
        assert {b.rel_path(n) for n in part.notes} == {"alpha", "group/beta", "run"}
        assert [b.rel_path(r) for r in part.references] == ["group/ref"]
        assert [b.rel_path(i) for i in part.items] == ["group/finding"]
        # … with each marker read exactly once and handed back.
        assert _max_reads_per_path(fs, META_JSON_FILENAME) == 1
        assert fs.calls["exists"] == 0
        assert set(part.metas) == {"alpha", "group/beta", "group/ref", "group/finding", "run"}
        assert part.metas["group/ref"]["year"] == 2020

    def test_notes_and_references_still_answer_alone(self, tree: Path) -> None:
        b = Bundle(tree, prune_dirs=PRUNE)
        assert {b.rel_path(n) for n in b.notes()} == {"alpha", "group/beta", "run"}
        assert [b.rel_path(r) for r in b.references()] == ["group/ref"]
        assert [b.rel_path(i) for i in b.items()] == ["group/finding"]

    def test_concepts_by_type_groups_by_declared_type(self, tree: Path) -> None:
        b = Bundle(tree, prune_dirs=PRUNE)
        grouped = b.concepts_by_type()
        assert {b.rel_path(c) for c in grouped["note.note"]} == {"alpha", "group/beta", "run"}
        assert all(isinstance(c, Concept) for group in grouped.values() for c in group)

    def test_scan_index_reads_each_body_and_meta_once(self, tree: Path) -> None:
        fs = CountingFileSystem(LocalFileSystem())
        index, bodies, metas = Bundle(tree, fs=fs, prune_dirs=PRUNE).scan_index()
        assert {e.path for e in index.entries} == set(bodies) == set(metas)
        assert _max_reads_per_path(fs, META_JSON_FILENAME) == 1
        assert _max_reads_per_path(fs, "index.md") == 1
        assert fs.for_basename("index.md", "read_text") == 5


class TestSearchNeverWrites:
    def test_search_creates_no_index_files(self, tree: Path) -> None:
        result = Bundle(tree).search("body")
        assert result.hits
        assert not (tree / INDEX_JSON_FILENAME).exists()
        assert not (tree / INDEX_MD_FILENAME).exists()

    def test_search_issues_zero_writes(self, tree: Path) -> None:
        fs = CountingFileSystem(LocalFileSystem())
        Bundle(tree, fs=fs).search("body", rebuild=True)
        Bundle(tree, fs=fs).search("body", rebuild=False)  # no index.json → in-memory scan
        assert fs.count("atomic_write_json", "atomic_write_text", "write_text", "write_bytes") == 0

    def test_build_index_is_the_one_verb_that_writes_both_files(self, tree: Path) -> None:
        Bundle(tree).build_index()
        assert (tree / INDEX_JSON_FILENAME).is_file()
        assert (tree / INDEX_MD_FILENAME).is_file()

    def test_search_reads_bodies_once_per_query(self, tree: Path) -> None:
        fs = CountingFileSystem(LocalFileSystem())
        Bundle(tree, fs=fs, prune_dirs=PRUNE).search("body")
        assert fs.for_basename("index.md", "read_text") == 5


class TestRankThenFilter:
    def test_filters_narrow_the_ranked_list(self, tree: Path) -> None:
        b = Bundle(tree, prune_dirs=PRUNE)
        everything = b.search("body")
        only_group = b.search("body", scope="group")
        assert {h.entry.path for h in only_group.hits} < {h.entry.path for h in everything.hits}
        assert all(h.entry.path.startswith("group/") for h in only_group.hits)

    def test_a_document_scores_the_same_under_any_filter(self, tree: Path) -> None:
        # IDF is that of the whole bundle, so the filter a hit was found under
        # cannot change its score — one ranking corpus serves every filter.
        b = Bundle(tree, prune_dirs=PRUNE)
        unfiltered = {h.entry.path: h.score for h in b.search("body").hits}
        scoped = {h.entry.path: h.score for h in b.search("body", scope="group").hits}
        assert scoped
        for path, score in scoped.items():
            assert score == pytest.approx(unfiltered[path])

    def test_truncated_counts_only_hits_that_pass_the_filters(self, tree: Path) -> None:
        b = Bundle(tree, prune_dirs=PRUNE)
        # "body" is in alpha, group/beta and run — three hits unscoped …
        assert len(b.search("body", limit=10).hits) == 3
        assert b.search("body", limit=2).truncated is True
        # … but only one under group/, so the same limit is not a cut there:
        # truncation is judged after the filters, not on the raw ranking.
        scoped = b.search("body", scope="group", limit=2)
        assert [h.entry.path for h in scoped.hits] == ["group/beta"]
        assert scoped.truncated is False


class TestPositionAwarePruning:
    """A declared subtree is skipped only among *that type's own* children.

    The knowledge layer learns a host's layout from the concept-type registry
    (``NON_CONCEPT_SUBDIRS`` on the registered class), never from a global list
    of names. A bare name means different things in different places, so a
    name-based denylist would hide a real Concept that merely happens to be
    called ``logs``. These tests pin the scoping with a registered stand-in
    type, so the rule holds without any workspace import.
    """

    @pytest.fixture
    def registered_host(self) -> str:
        """A concept type declaring ``logs``/``out`` as its own non-Concept subdirs."""
        from molab.knowledge.types import _REGISTRY, register_concept_type

        type_str = "test.host_with_output"

        class _Host:
            NON_CONCEPT_SUBDIRS = frozenset({"logs", "out"})

        register_concept_type(type_str, _Host)
        try:
            yield type_str
        finally:
            _REGISTRY.pop(type_str, None)

    @staticmethod
    def _marker(directory: Path, type_str: str) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / META_JSON_FILENAME).write_text(
            json.dumps({"type": type_str, "id": directory.name})
        )
        (directory / "index.md").write_text(f"# {directory.name}\n")

    def test_declared_subdir_is_pruned_under_its_own_type(
        self, tmp_path: Path, registered_host: str
    ) -> None:
        root = tmp_path / "b"
        self._marker(root / "host", registered_host)
        self._marker(root / "host" / "logs", "note.note")
        rels = {Bundle(root).rel_path(c) for c in Bundle(root).walk()}
        assert "host" in rels
        assert "host/logs" not in rels

    def test_the_same_name_survives_under_any_other_parent(
        self, tmp_path: Path, registered_host: str
    ) -> None:
        root = tmp_path / "b"
        self._marker(root / "logs", "note.note")  # at the bundle root
        self._marker(root / "plain", "note.note")
        self._marker(root / "plain" / "logs", "note.note")  # under an ordinary Concept
        rels = {Bundle(root).rel_path(c) for c in Bundle(root).walk()}
        assert {"logs", "plain", "plain/logs"} <= rels

    def test_pruning_applies_when_the_bundle_is_rooted_at_the_host(
        self, tmp_path: Path, registered_host: str
    ) -> None:
        # The root's own type is read once per walk, so opening a bundle
        # directly on a host still skips that host's output.
        root = tmp_path / "host"
        self._marker(root, registered_host)
        self._marker(root / "out", "note.note")
        self._marker(root / "kept", "note.note")
        rels = {Bundle(root).rel_path(c) for c in Bundle(root).walk()}
        assert rels == {"kept"}

    def test_an_unregistered_or_markerless_parent_prunes_nothing(self, tmp_path: Path) -> None:
        root = tmp_path / "b"
        self._marker(root / "unknown", "nobody.registered.this")
        self._marker(root / "unknown" / "logs", "note.note")
        self._marker(root / "bare" / "logs", "note.note")  # ``bare/`` has no marker
        rels = {Bundle(root).rel_path(c) for c in Bundle(root).walk()}
        assert {"unknown", "unknown/logs", "bare/logs"} <= rels
