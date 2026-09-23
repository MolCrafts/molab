"""Tests for the ``Bundle`` docs/notes CRUD surface (knowledge-docs-01).

Covers the bundle-owned document verbs on :class:`molab.knowledge.bundle.Bundle`
(``create_note`` / ``rename_note`` / ``move_note`` / ``delete_note`` /
``backlinks`` / ``export_markdown``) plus the :class:`Backlink` reverse-edge
wrapper. These are the shared CRUD path CLI and server both call (the
Python==UI invariant). The base graph verbs (``walk`` / ``get`` / ``put`` /
``link``) are owned by ``test_bundle.py``.

``TestBundleDocs`` still pins the pre-file-document *directory* model (a note as
``<name>/meta.json`` + ``index.md``); those assertions are stale against the
landed ``FILE_DOCUMENT`` layout and are carried here unchanged for the chain that
owns the migration. ``TestFileDocumentVerbs`` is the landed coverage.
"""

from __future__ import annotations

from pathlib import Path
from typing import IO

import pytest

from molab.fs import LocalFileSystem, PathArg
from molab.knowledge import KnowledgeNotFoundError, Note
from molab.knowledge.bundle import Bundle
from molab.knowledge.concept import Concept


@pytest.fixture
def bundle_root(tmp_path: Path) -> Path:
    """An empty on-disk bundle root (no concepts yet)."""
    root = tmp_path / "bundle"
    root.mkdir()
    return root


class RecordingFileSystem(LocalFileSystem):
    """A ``LocalFileSystem`` that logs every write entry point before delegating.

    Overriding the atomic writers + ``open`` lets a test prove a ``Note``'s body
    and ``meta.json`` were written through the *atomic* writers, and that NO
    write-mode bare ``open()`` was used for any file.
    """

    def __init__(self) -> None:
        self.atomic_text_writes: list[str] = []
        self.atomic_json_writes: list[str] = []
        self.write_opens: list[tuple[str, str]] = []

    def atomic_write_text(self, path: PathArg, content: str, *, encoding: str = "utf-8") -> None:
        self.atomic_text_writes.append(str(path))
        super().atomic_write_text(path, content, encoding=encoding)

    def atomic_write_json(self, path: PathArg, data: object) -> None:
        self.atomic_json_writes.append(str(path))
        super().atomic_write_json(path, data)

    def open(self, path: PathArg, mode: str = "r", encoding: str = "utf-8") -> IO[str]:
        if any(flag in mode for flag in ("w", "a", "x", "+")):
            self.write_opens.append((str(path), mode))
        return super().open(path, mode=mode, encoding=encoding)


class TestBundleDocs:
    """The document CRUD verbs on :class:`Bundle`."""

    def test_create_note_slugifies_dir_and_writes_meta_and_body(self, bundle_root: Path) -> None:
        b = Bundle(bundle_root)
        note = b.create_note("Design Doc", body="hi")

        assert isinstance(note, Note)
        assert b.rel_path(note) == "design-doc"
        assert (bundle_root / "design-doc").is_dir()
        assert note.read_meta()["type"] == "note.note"
        assert note.read() == "hi"

    def test_create_note_is_idempotent_on_slug(self, bundle_root: Path) -> None:
        b = Bundle(bundle_root)
        first = b.create_note("Design Doc", body="hi")
        count_before = len(list(b.walk()))

        second = b.create_note("Design Doc", body="hi")

        assert b.rel_path(second) == b.rel_path(first) == "design-doc"
        assert len(list(b.walk())) == count_before
        rels = [b.rel_path(f) for f in b.walk()]
        assert rels.count("design-doc") == 1

    def test_create_note_child_nests_under_parent(self, bundle_root: Path) -> None:
        b = Bundle(bundle_root)
        parent = b.create_note("Parent")
        child = b.create_note("Child", parent=parent)

        assert b.rel_path(parent) == "parent"
        assert b.rel_path(child) == "parent/child"
        assert (bundle_root / "parent" / "child").is_dir()
        assert b.get("parent/child").read_meta()["type"] == "note.note"

    def test_create_note_writes_body_and_meta_through_atomic_writers(
        self, bundle_root: Path
    ) -> None:
        rec = RecordingFileSystem()
        b = Bundle(bundle_root, fs=rec)

        note = b.create_note("Design Doc", body="hello world")

        assert note.read() == "hello world"
        assert any(p.endswith("design-doc/index.md") for p in rec.atomic_text_writes)
        assert any(p.endswith("design-doc/meta.json") for p in rec.atomic_text_writes)

    def test_rename_note_preserves_body_and_resolves_at_new_identity(
        self, bundle_root: Path
    ) -> None:
        b = Bundle(bundle_root)
        note = b.create_note("Design Doc", body="ORIGINAL BODY")

        b.rename_note(note, "Renamed")

        renamed = b.get("renamed")
        assert renamed.read_meta()["type"] == "note.note"
        assert renamed.read_index() == "ORIGINAL BODY"
        with pytest.raises(KnowledgeNotFoundError):
            b.get("design-doc")

    def test_move_note_resolves_under_new_parent(self, bundle_root: Path) -> None:
        b = Bundle(bundle_root)
        home = b.create_note("Home", body="H")
        note = b.create_note("Roamer", body="R")

        b.move_note(note, home)

        assert b.get("home/roamer").read_index() == "R"
        with pytest.raises(KnowledgeNotFoundError):
            b.get("roamer")

    def test_delete_note_removes_dir_and_walk_drops_it(self, bundle_root: Path) -> None:
        b = Bundle(bundle_root)
        note = b.create_note("Design Doc", body="hi")
        note_dir = bundle_root / "design-doc"
        assert note_dir.is_dir()

        b.delete_note(note)

        assert not note_dir.exists()
        assert "design-doc" not in {b.rel_path(f) for f in b.walk()}

    def test_backlinks_returns_typed_sources_excluding_unrelated(self, bundle_root: Path) -> None:
        b = Bundle(bundle_root)
        dst = b.create_note("Target", body="T")
        src1 = b.create_note("Src One", body="1")
        src2 = b.create_note("Src Two", body="2")
        other = b.create_note("Unrelated", body="U")

        b.link(src1, dst, role="cites")
        b.link(src2, dst)  # default role == references
        b.link(other, src1)  # unrelated edge — must NOT surface as a backlink of dst

        got = {(b.rel_path(bl.source), bl.role) for bl in b.backlinks(dst)}
        assert got == {("src-one", "cites"), ("src-two", "references")}
        assert all(isinstance(bl.source, Concept) for bl in b.backlinks(dst))

    def test_backlinks_persists_no_reverse_index_file(self, bundle_root: Path) -> None:
        # One-source-of-truth: backlinks is a derived recompute; no reverse index
        # is ever written to disk.
        b = Bundle(bundle_root)
        dst = b.create_note("Target", body="T")
        src = b.create_note("Src One", body="1")
        b.link(src, dst, role="cites")

        before = {p.name for p in bundle_root.iterdir()}
        _ = b.backlinks(dst)
        after = {p.name for p in bundle_root.iterdir()}

        assert before == after
        assert not (bundle_root / "backlinks.json").exists()

    def test_export_markdown_includes_children_in_document_order(self, bundle_root: Path) -> None:
        b = Bundle(bundle_root)
        note = b.create_note("Parent", body="PARENT")
        b.create_note("Child", parent=note, body="CHILD")

        out = b.export_markdown(note, include_children=True)

        assert isinstance(out, str)
        assert "PARENT" in out
        assert "CHILD" in out
        assert out.index("PARENT") < out.index("CHILD")

    def test_export_markdown_excludes_children_when_flag_false(self, bundle_root: Path) -> None:
        b = Bundle(bundle_root)
        note = b.create_note("Parent", body="PARENT")
        b.create_note("Child", parent=note, body="CHILD")

        out = b.export_markdown(note, include_children=False)

        assert "PARENT" in out
        assert "CHILD" not in out


class TestFileDocumentVerbs:
    """``create_note`` and friends under the landed file-document layout.

    A ``Note`` is a ``FILE_DOCUMENT``: it lands as one markdown file
    (``<host>/<slug>.md``) whose head is its frontmatter. ``create_note`` used to
    build a *directory* at ``<host>/<slug>`` and then call ``write_meta()``,
    which ``mkdir``-ed a directory at the document's own ``.md`` path — every
    create died with ``IsADirectoryError``, and so did ``POST /api/knowledge/doc``.
    """

    def test_create_note_lands_one_markdown_file(self, bundle_root: Path) -> None:
        b = Bundle(bundle_root)

        note = b.create_note("Design Doc", body="hi")

        assert isinstance(note, Note)
        assert note.path == bundle_root / "design-doc.md"
        assert note.path.is_file()
        assert not (bundle_root / "design-doc").exists()  # never a directory
        assert not (bundle_root / "design-doc.md").is_dir()
        assert note.read().strip() == "hi"

    def test_create_note_materializes_an_empty_body(self, bundle_root: Path) -> None:
        note = Bundle(bundle_root).create_note("Parent")

        assert note.path.is_file()
        assert note.read() == ""

    def test_create_note_is_idempotent_and_never_truncates(self, bundle_root: Path) -> None:
        b = Bundle(bundle_root)
        first = b.create_note("Design Doc", body="ORIGINAL")

        second = b.create_note("Design Doc")

        assert second.path == first.path
        assert second.read().strip() == "ORIGINAL"
        assert sorted(p.name for p in bundle_root.iterdir()) == ["design-doc.md"]

    def test_create_note_child_lands_beside_a_document_parent(self, bundle_root: Path) -> None:
        b = Bundle(bundle_root)
        parent = b.create_note("Parent")
        child = b.create_note("Child", parent=parent)

        # a file has no interior: nesting under a document nests beside it
        assert child.path == bundle_root / "child.md"
        assert child.path.is_file()
        assert parent.path.is_file()

    def test_create_note_writes_through_the_atomic_writer(self, bundle_root: Path) -> None:
        rec = RecordingFileSystem()

        note = Bundle(bundle_root, fs=rec).create_note("Design Doc", body="hello world")

        assert note.read().strip() == "hello world"
        assert rec.atomic_text_writes == [str(bundle_root / "design-doc.md")]
        assert rec.write_opens == []

    def test_rename_note_keeps_the_markdown_suffix(self, bundle_root: Path) -> None:
        b = Bundle(bundle_root)
        note = b.create_note("Design Doc", body="ORIGINAL BODY")

        b.rename_note(note, "Renamed")

        renamed = bundle_root / "renamed.md"
        assert renamed.is_file()
        assert "ORIGINAL BODY" in renamed.read_text()
        assert not (bundle_root / "design-doc.md").exists()
        assert not (bundle_root / "renamed").exists()

    def test_move_note_keeps_the_markdown_suffix(self, bundle_root: Path) -> None:
        b = Bundle(bundle_root)
        home = b.create_note("Home", body="H")
        note = b.create_note("Roamer", body="R")

        b.move_note(note, home)

        assert (bundle_root / "roamer.md").is_file()
        assert not (bundle_root / "roamer").exists()
        assert home.path.is_file()

    def test_delete_note_removes_the_file(self, bundle_root: Path) -> None:
        b = Bundle(bundle_root)
        note = b.create_note("Design Doc", body="hi")

        b.delete_note(note)

        assert not (bundle_root / "design-doc.md").exists()
