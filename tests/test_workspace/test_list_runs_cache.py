"""``Experiment.list_runs`` reuses the children cache and never probes.

Cold: one ``scandir`` + one ``run.json`` open per run (no ``is_dir`` /
``exists`` — the listing already reports which entries are directories).
Warm: one ``scandir`` + one ``stat`` per run (``sync=False``: just the
``scandir``). Identity is stable across calls; runs that vanish are
evicted; stray entries are skipped; concurrent listing is safe.
"""

from __future__ import annotations

import shutil
import threading

import pytest

from molexp.fs import LocalFileSystem
from molexp.workspace import Workspace
from tests.support.counting_fs import CountingFileSystem

N_RUNS = 200


@pytest.fixture(scope="module")
def populated(tmp_path_factory):
    root = tmp_path_factory.mktemp("ws")
    ws = Workspace(root=root, name="Big Lab")
    experiment = ws.add_project("p").add_experiment("e", params={"i": 0})
    for i in range(N_RUNS):
        experiment.add_run(params={"i": i})
    return root


def _reopen(root):
    fs = CountingFileSystem(LocalFileSystem())
    experiment = Workspace(root=root, fs=fs).get_project("p").get_experiment("e")
    return experiment, fs


class TestListRunsCache:
    def test_cold_listing_is_scandir_plus_one_open_per_run(self, populated) -> None:
        experiment, fs = _reopen(populated)
        fs.reset()
        runs = experiment.list_runs()
        assert len(runs) == N_RUNS
        assert fs.calls["scandir"] == 1
        assert fs.calls["listdir"] == 0
        assert fs.opens() == N_RUNS
        assert fs.probes() == 0, dict(fs.calls)

    def test_warm_listing_is_scandir_plus_one_stat_per_run(self, populated) -> None:
        experiment, fs = _reopen(populated)
        first = experiment.list_runs()
        fs.reset()
        second = experiment.list_runs()
        assert fs.calls["scandir"] == 1
        assert fs.calls["listdir"] == 0
        assert fs.opens() == 0
        assert fs.calls["stat"] == N_RUNS
        assert fs.probes() == 0
        assert all(a is b for a, b in zip(first, second, strict=True))

    def test_warm_listing_without_sync_is_just_scandir(self, populated) -> None:
        experiment, fs = _reopen(populated)
        experiment.list_runs()
        fs.reset()
        experiment.list_runs(sync=False)
        # Path math (``join``) is counted too — assert on the I/O calls only.
        assert fs.calls["scandir"] == 1
        assert fs.calls["listdir"] == 0
        assert fs.opens() == 0
        assert fs.stats() == 0
        assert fs.probes() == 0

    def test_evicts_removed_runs(self, tmp_path) -> None:
        ws = Workspace(root=tmp_path, name="L")
        experiment = ws.add_project("p").add_experiment("e")
        a = experiment.add_run(params={"k": "a"})
        b = experiment.add_run(params={"k": "b"})
        assert {r.id for r in experiment.list_runs()} == {a.id, b.id}
        shutil.rmtree(str(b.run_dir))
        assert {r.id for r in experiment.list_runs()} == {a.id}
        assert b.id not in experiment._children_cache

    def test_skips_stray_entries(self, tmp_path) -> None:
        ws = Workspace(root=tmp_path, name="L")
        experiment = ws.add_project("p").add_experiment("e")
        run = experiment.add_run(params={"k": 1})
        runs_dir = tmp_path / "projects" / "p" / "experiments" / "e" / "runs"
        (runs_dir / "run-stray").mkdir()  # dir without run.json
        (runs_dir / "run-file").write_text("not a dir")
        (runs_dir / "notes.txt").write_text("loose file")
        assert [r.id for r in experiment.list_runs()] == [run.id]

    def test_picks_up_runs_added_by_another_handle(self, tmp_path) -> None:
        ws = Workspace(root=tmp_path, name="L")
        experiment = ws.add_project("p").add_experiment("e")
        experiment.add_run(params={"k": 1})
        assert len(experiment.list_runs()) == 1
        Workspace(root=tmp_path).get_project("p").get_experiment("e").add_run(params={"k": 2})
        assert len(experiment.list_runs()) == 2

    def test_concurrent_listing_while_adding_is_safe(self, tmp_path) -> None:
        ws = Workspace(root=tmp_path, name="L")
        experiment = ws.add_project("p").add_experiment("e")
        for i in range(20):
            experiment.add_run(params={"i": i})
        errors: list[BaseException] = []
        stop = threading.Event()

        def lister() -> None:
            try:
                while not stop.is_set():
                    experiment.list_runs()
            except BaseException as exc:
                errors.append(exc)

        threads = [threading.Thread(target=lister) for _ in range(2)]
        for t in threads:
            t.start()
        try:
            for i in range(20, 40):
                experiment.add_run(params={"i": i})
        finally:
            stop.set()
            for t in threads:
                t.join(timeout=10)
        assert errors == []
        assert len(experiment.list_runs()) == 40
