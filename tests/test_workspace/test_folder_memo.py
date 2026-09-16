"""``Folder`` read paths are stat-validated memos with try-read semantics.

Locks the P1 contract: a repeat ``read_meta`` / ``read_index`` /
``read_ops_json`` / children-index read is one ``stat`` and zero opens; no
read path issues ``exists`` / ``is_dir`` / ``mkdir`` probes; a foreign write
(another ``Workspace`` handle, i.e. another process) is seen on the next
read; a writer on the same instance drops its own memo.
"""

from __future__ import annotations

import pytest

from molexp.fs import LocalFileSystem
from molexp.workspace import Workspace
from tests.support.counting_fs import CountingFileSystem


@pytest.fixture
def counted(tmp_path):
    fs = CountingFileSystem(LocalFileSystem())
    ws = Workspace(root=tmp_path, name="Counted Lab", fs=fs)
    project = ws.add_project("p")
    experiment = project.add_experiment("e", params={"lr": 1e-4})
    run = experiment.add_run(params={"lr": 1e-4})
    return ws, project, experiment, run, fs


class TestFolderMemo:
    def test_read_ops_json_hits_memo_with_one_stat(self, counted) -> None:
        _ws, _p, _e, run, fs = counted
        run.update_ops(lambda s: s)  # ensure _ops/run.json exists
        run.read_ops_json("run")
        fs.reset()
        assert run.read_ops_json("run") is not None
        assert fs.calls["stat"] == 1
        assert fs.opens() == 0
        assert fs.probes() == 0

    def test_read_meta_and_read_index_memoized(self, counted) -> None:
        _ws, project, _e, _r, fs = counted
        project.write_index("# hello\n")
        project.read_meta()
        project.read_index()
        fs.reset()
        assert project.read_meta()["type"] == "workspace.project"
        assert project.read_index() == "# hello\n"
        assert fs.opens() == 0
        assert fs.calls["stat"] == 2
        assert fs.probes() == 0

    def test_read_meta_returns_a_copy(self, counted) -> None:
        _ws, project, _e, _r, _fs = counted
        first = project.read_meta()
        first["type"] = "mutated"
        assert project.read_meta()["type"] == "workspace.project"

    def test_missing_files_read_as_empty_with_no_probe(self, counted) -> None:
        _ws, project, _e, _r, fs = counted
        fs.reset()
        assert project.read_index() == ""
        assert project.read_ops_json("nothing") is None
        assert fs.probes() == 0

    def test_external_write_seen_by_other_handle(self, counted, tmp_path) -> None:
        _ws, _p, _e, run, _fs = counted
        run.update_ops(lambda s: s)
        assert run.status == "pending"
        other = Workspace(root=tmp_path).get_project("p").get_experiment("e").get_run(run.id)
        assert other is not run
        other.cancel()
        assert run.status == "cancelled"  # stat key changed → reload

    def test_writer_drops_own_memo(self, counted) -> None:
        _ws, project, _e, _r, _fs = counted
        project.write_index("v1\n")
        assert project.read_index() == "v1\n"
        project.write_index("v2\n")
        assert project.read_index() == "v2\n"
        project.write_ops_json("x", {"n": 1})
        assert project.read_ops_json("x") == {"n": 1}
        project.write_ops_json("x", {"n": 2})
        assert project.read_ops_json("x") == {"n": 2}

    def test_update_ops_reads_fresh_and_invalidates(self, counted) -> None:
        _ws, _p, _e, run, _fs = counted
        run.update_ops(lambda s: s)
        run.read_ops()  # warm the typed memo
        state = run.update_ops(lambda s: s.model_copy(update={"owner_host": "h1"}))
        assert state.owner_host == "h1"
        assert run.read_ops().owner_host == "h1"

    def test_read_json_does_no_dir_probe(self, counted) -> None:
        _ws, project, _e, _r, fs = counted
        project.write_json("extra.json", {"k": 1})
        fs.reset()
        assert project.read_json("extra.json") == {"k": 1}
        assert fs.calls["is_dir"] == 0
        assert fs.calls["mkdir"] == 0

    def test_path_probes_dir_once_per_instance(self, counted) -> None:
        _ws, project, _e, _r, fs = counted
        project.path()
        fs.reset()
        project.path()
        project.path()
        assert fs.calls["is_dir"] == 0
        assert fs.calls["mkdir"] == 0

    def test_list_folders_second_call_is_one_stat_zero_opens(self, counted) -> None:
        ws, _p, _e, _r, fs = counted
        ws.list_projects()
        fs.reset()
        assert [p.id for p in ws.list_projects()] == ["p"]
        assert fs.opens() == 0
        assert fs.calls["stat"] == 1  # the children index
        assert fs.probes() == 0

    def test_list_folders_cold_uses_no_probes(self, tmp_path) -> None:
        Workspace(root=tmp_path, name="L").add_project("p1")
        fs = CountingFileSystem(LocalFileSystem())
        ws = Workspace(root=tmp_path, fs=fs)
        fs.reset()
        assert [p.id for p in ws.list_projects()] == ["p1"]
        assert fs.calls["is_dir"] == 0
        assert fs.calls["exists"] == 0

    def test_list_folders_sees_index_rewritten_by_other_handle(self, counted, tmp_path) -> None:
        ws, _p, _e, _r, _fs = counted
        assert len(ws.list_projects()) == 1
        Workspace(root=tmp_path).add_project("p2")
        assert {p.id for p in ws.list_projects()} == {"p", "p2"}

    def test_from_disk_and_concept_from_dir_use_no_probes(self, counted) -> None:
        from molexp.workspace.folder import concept_from_dir

        ws, project, _e, _r, fs = counted
        fs.reset()
        loaded = concept_from_dir(project.resolve(), ws)
        assert loaded.id == "p"
        assert fs.calls["exists"] == 0
        assert fs.calls["is_dir"] == 0
