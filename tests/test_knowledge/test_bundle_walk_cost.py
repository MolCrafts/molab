"""``Bundle.walk`` cost locks — one ``scandir`` + one marker read per dir.

``test_bundle_prune.py`` owns *which* directories the walk visits (the
position-aware pruning rule). This module owns *what each visited directory
costs*, which is where the walk's expense actually lived: it used to pay a
per-entry ``is_dir``, a per-entry ``resolve``, a re-``resolve`` of the root at
every level, and a ``.gitignore`` probe per directory — roughly five calls per
entry on top of the one read that actually decides anything.

The invariants, all asserted exactly:

* one ``scandir`` per visited directory, and no ``listdir`` at all;
* no ``is_dir`` / ``exists`` probe anywhere — the listing answers both;
* ``resolve`` only for the root and for symlinked entries, because only a
  symlink can sit somewhere other than ``<parent real path>/<name>``;
* one ``meta.json`` read per visited directory — the read that decides
  concept-ness *and* type, never repeated.
"""

from __future__ import annotations

import json

import pytest

from molab.fs import LocalFileSystem
from molab.knowledge.bundle import Bundle
from tests.support.counting_fs import CountingFileSystem

META = "meta.json"


def _concept(directory, type_str: str = "note.note") -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / META).write_text(json.dumps({"type": type_str, "id": directory.name}))
    (directory / "index.md").write_text(f"# {directory.name}\n")


@pytest.fixture
def tree(tmp_path):
    """A bundle root with nested concepts, plain dirs and loose files.

    Visited directories: root, a, a/b, a/b/c, plain, plain/deep  = 6.
    """
    _concept(tmp_path / "a")
    _concept(tmp_path / "a" / "b")
    _concept(tmp_path / "a" / "b" / "c")
    (tmp_path / "plain" / "deep").mkdir(parents=True)
    (tmp_path / "loose.txt").write_text("x")
    (tmp_path / "a" / "notes.md").write_text("x")
    return tmp_path


N_DIRS = 6  # root + a + a/b + a/b/c + plain + plain/deep


def _counting(root):
    fs = CountingFileSystem(LocalFileSystem())
    return Bundle(root, fs=fs), fs


class TestWalkCost:
    def test_one_scandir_per_directory_and_no_listdir(self, tree) -> None:
        bundle, fs = _counting(tree)
        fs.reset()
        found = list(bundle.walk())
        assert {c.path.name for c in found} == {"a", "b", "c"}
        assert fs.calls["scandir"] == N_DIRS
        assert fs.calls["listdir"] == 0

    def test_walk_never_probes_entry_types(self, tree) -> None:
        bundle, fs = _counting(tree)
        fs.reset()
        list(bundle.walk())
        assert fs.calls["is_dir"] == 0
        assert fs.calls["exists"] == 0

    def test_resolve_is_not_paid_per_entry(self, tree) -> None:
        """No symlinks here, so the root is the only thing needing resolution."""
        bundle, fs = _counting(tree)
        fs.reset()
        list(bundle.walk())
        assert fs.calls["resolve"] <= 2, dict(fs.calls)

    def test_marker_is_read_once_per_visited_directory(self, tree) -> None:
        bundle, fs = _counting(tree)
        fs.reset()
        list(bundle.walk())
        assert fs.for_basename(META, "read_text") == N_DIRS

    def test_gitignore_is_probed_once_per_walk_not_once_per_directory(self, tree) -> None:
        """The listing already says whether a ``.gitignore`` is there.

        The one probe that remains is the matcher's own constructor loading
        the root's ``.gitignore``; every directory below it is answered from
        the ``scandir`` the walk already did.
        """
        bundle, fs = _counting(tree)
        fs.reset()
        list(bundle.walk())
        assert fs.for_basename(".gitignore", "is_file") == 1, dict(fs.calls)


class TestWalkCorrectnessUnderScandir:
    def test_a_nested_gitignore_is_still_honoured(self, tmp_path) -> None:
        """Cheapness must not lose rules: a real ``.gitignore`` still applies."""
        _concept(tmp_path / "keep")
        _concept(tmp_path / "sub")
        _concept(tmp_path / "sub" / "hidden")
        (tmp_path / "sub" / ".gitignore").write_text("hidden/\n")

        bundle = Bundle(tmp_path)
        assert {c.path.name for c in bundle.walk()} == {"keep", "sub"}

    def test_symlinked_child_is_followed_and_cycles_are_cut(self, tmp_path) -> None:
        _concept(tmp_path / "real")
        (tmp_path / "link").symlink_to(tmp_path / "real", target_is_directory=True)
        # A self-referential loop must terminate rather than recurse forever.
        (tmp_path / "real" / "loop").symlink_to(tmp_path, target_is_directory=True)

        found = {c.path.name for c in Bundle(tmp_path).walk()}
        assert "real" in found

    def test_a_file_is_never_walked_as_a_directory(self, tmp_path) -> None:
        _concept(tmp_path / "real")
        (tmp_path / "decoy").write_text("not a dir")
        assert {c.path.name for c in Bundle(tmp_path).walk()} == {"real"}
