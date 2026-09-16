"""Folder-family listing cost locks — one ``scandir`` per directory.

``test_folder.py`` and ``test_list_runs_cache.py`` own *what* the listing
verbs return. This module owns *how much* they cost, and in particular the
property that made them cheap: the directory listing itself reports which
entries are directories, so no verb pays a per-entry ``is_dir`` / ``exists``
probe, and a sibling *file* (``workspace.json``, ``meta.yaml``, a stray
``.DS_Store``) never costs a doomed ``metadata.json`` open.

The counts are asserted as exact equalities on purpose: a regression here is
silent — it costs syscalls per entry on a workspace with thousands of runs
and nothing else changes — so an inequality would let it back in.
"""

from __future__ import annotations

import pytest

from molexp.workspace import Workspace
from molexp.workspace.fs_local import LocalFileSystem
from molexp.workspace.project import Project
from tests.support.counting_fs import CountingFileSystem

N_PROJECTS = 6


@pytest.fixture
def populated(tmp_path):
    """A workspace with several projects and loose files beside them."""
    ws = Workspace(root=tmp_path, name="lab")
    for i in range(N_PROJECTS):
        ws.add_project(f"p{i}")
    # Loose files next to the project dirs: the walkers must skip these
    # without spending a call on each.
    (tmp_path / "projects" / "README.md").write_text("not a project")
    (tmp_path / "projects" / ".DS_Store").write_text("junk")
    (tmp_path / "stray.txt").write_text("junk")
    return tmp_path


def _reopen(root):
    fs = CountingFileSystem(LocalFileSystem())
    return Workspace(root=root, fs=fs), fs


class TestListFoldersCost:
    def test_generic_listing_is_one_scandir_and_skips_loose_files(self, populated) -> None:
        ws, fs = _reopen(populated)
        fs.reset()
        found = ws.list_folders()
        # ``projects/`` is the only child dir of the root; the loose
        # ``stray.txt`` is not opened looking for a ``metadata.json``.
        assert fs.calls["scandir"] == 1
        assert fs.calls["listdir"] == 0
        assert fs.probes() == 0, dict(fs.calls)
        assert all(f.kind for f in found)

    def test_sync_folders_is_one_scandir_plus_one_open_per_child(self, populated) -> None:
        ws, fs = _reopen(populated)
        fs.reset()
        ws.sync_folders(cls=Project)
        assert fs.calls["scandir"] == 1
        assert fs.calls["listdir"] == 0
        assert fs.probes() == 0, dict(fs.calls)
        # Exactly the real project dirs are opened — the two loose files in
        # ``projects/`` cost nothing.
        assert fs.opens() == N_PROJECTS

    def test_rebuilt_index_still_lists_every_project(self, populated) -> None:
        """Cheapness must not change the answer: the index round-trips."""
        ws, _fs = _reopen(populated)
        ws.sync_folders(cls=Project)
        assert {p.id for p in ws.list_projects()} == {f"p{i}" for i in range(N_PROJECTS)}


class TestScandirSkipsNonDirectories:
    def test_a_file_named_like_a_run_is_not_listed_as_one(self, tmp_path) -> None:
        """``run-`` prefix is not enough — the entry has to be a directory."""
        ws = Workspace(root=tmp_path, name="lab")
        experiment = ws.add_project("p").add_experiment("e")
        real = experiment.add_run(params={"k": 1})
        (tmp_path / "projects" / "p" / "experiments" / "e" / "runs" / "run-decoy").write_text("x")

        fs = CountingFileSystem(LocalFileSystem())
        reopened = Workspace(root=tmp_path, fs=fs).get_project("p").get_experiment("e")
        fs.reset()
        runs = reopened.list_runs()

        assert [r.id for r in runs] == [real.id]
        assert fs.calls["scandir"] == 1
        # The decoy is rejected from the listing, not by a failed open.
        assert fs.opens() == 1
        assert fs.probes() == 0, dict(fs.calls)
