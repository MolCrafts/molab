"""``Run`` hot-state and identity reads share one parse each.

``status`` / ``finished_at`` / ``execution_history`` / ``is_retryable`` /
``current_execution_id`` on one instance parse ``_ops/run.json`` once;
``context_results`` / ``sync_metadata`` read the ``run.json`` document once
(seeded by ``from_disk``); the response builders inherit that.
"""

from __future__ import annotations

import pytest

from molexp.fs import LocalFileSystem
from molexp.workspace import Workspace
from tests.support.counting_fs import CountingFileSystem


def _ops_opens(fs: CountingFileSystem) -> int:
    return sum(
        1 for m, p, _ in fs.log if m in {"open", "read_text", "read_bytes"} and "/_ops/" in p
    )


def _run_json_opens(fs: CountingFileSystem) -> int:
    return sum(
        1
        for m, p, _ in fs.log
        if m in {"open", "read_text", "read_bytes"}
        and p.endswith("/run.json")
        and "/_ops/" not in p
    )


@pytest.fixture
def counted(tmp_path):
    fs = CountingFileSystem(LocalFileSystem())
    ws = Workspace(root=tmp_path, name="Counted Lab", fs=fs)
    experiment = ws.add_project("p").add_experiment("e", params={"lr": 1e-4})
    run = experiment.add_run(params={"lr": 1e-4})
    run.update_ops(lambda s: s)
    return ws, experiment, run, fs


class TestRunOpsMemo:
    def test_run_properties_share_one_parse(self, counted) -> None:
        _ws, _e, run, fs = counted
        fs.reset()
        _ = (
            run.status,
            run.finished_at,
            run.execution_history,
            run.is_retryable,
            run.current_execution_id,
        )
        assert _ops_opens(fs) == 1
        assert fs.probes() == 0
        fs.reset()
        _ = (run.status, run.finished_at)
        assert _ops_opens(fs) == 0
        assert fs.calls["stat"] == 2

    def test_absent_sidecar_reads_default_without_probe(self, tmp_path) -> None:
        fs = CountingFileSystem(LocalFileSystem())
        ws = Workspace(root=tmp_path, name="L", fs=fs)
        run = ws.add_project("p").add_experiment("e").add_run(params={"a": 1})
        fs.reset()
        assert run.status == "pending"
        assert fs.probes() == 0

    def test_entity_document_serves_context_results(self, counted) -> None:
        _ws, _e, run, _fs = counted
        assert run.context_results == {}
        with run.start() as ctx:
            ctx.set_result("energy", -1.5)
        assert run.context_results == {"energy": -1.5}

    def test_from_disk_seeds_document_memo(self, counted, tmp_path) -> None:
        _ws, _e, run, _fs = counted
        fs = CountingFileSystem(LocalFileSystem())
        reopened = Workspace(root=tmp_path, fs=fs).get_project("p").get_experiment("e")
        [loaded] = reopened.list_runs()
        assert loaded.id == run.id
        fs.reset()
        assert loaded.context_results == {}
        assert loaded.sync_metadata() is False
        assert _run_json_opens(fs) == 0
        assert fs.calls["stat"] == 2

    def test_sync_metadata_reloads_changed_run_json(self, counted, tmp_path) -> None:
        _ws, _e, run, _fs = counted
        other = Workspace(root=tmp_path).get_project("p").get_experiment("e").get_run(run.id)
        other._update_metadata(target="cluster-a")
        assert run.metadata.target is None
        assert run.sync_metadata() is True
        assert run.metadata.target == "cluster-a"
        assert run.sync_metadata() is False

    def test_own_save_then_sync_is_a_hit(self, counted) -> None:
        _ws, _e, run, fs = counted
        run._update_metadata(script="train.py")
        run.sync_metadata()  # reload after own write (memo was dropped)
        fs.reset()
        assert run.sync_metadata() is False
        assert _run_json_opens(fs) == 0

    def test_rmw_sees_foreign_write_before_applying(self, counted, tmp_path) -> None:
        _ws, _e, run, _fs = counted
        run.sync_metadata()  # warm the document memo
        other = Workspace(root=tmp_path).get_project("p").get_experiment("e").get_run(run.id)
        other._update_metadata(target="cluster-a")
        run._update_metadata(script="train.py")  # must not clobber target
        fresh = Workspace(root=tmp_path).get_project("p").get_experiment("e").get_run(run.id)
        assert fresh.metadata.target == "cluster-a"
        assert fresh.metadata.script == "train.py"


class TestResponseBuildersReadOnce:
    def test_run_response_parses_ops_once_and_run_json_zero_times(self, counted) -> None:
        from molexp.server.schemas.responses import RunResponse

        _ws, _e, run, fs = counted
        run.sync_metadata()
        fs.reset()
        resp = RunResponse.from_model(run)
        assert resp.status == "pending"
        assert _ops_opens(fs) <= 1
        assert _run_json_opens(fs) == 0
        assert fs.probes() == 0

    def test_experiment_response_one_ops_parse_per_run(self, counted) -> None:
        from molexp.server.schemas.responses import ExperimentResponse

        _ws, experiment, _r, fs = counted
        runs = experiment.list_runs()
        fs.reset()
        resp = ExperimentResponse.from_model(experiment, runs=runs)
        assert len(resp.runs) == 1
        assert _ops_opens(fs) <= 1

    def test_workspace_run_row_one_ops_parse(self, counted) -> None:
        from molexp.server.schemas.workspace_runs import WorkspaceRunRow

        _ws, _e, run, fs = counted
        run.read_ops()
        fs.reset()
        row = WorkspaceRunRow.from_run(run, project_name="p", experiment_name="e")
        assert row.status == "pending"
        assert _ops_opens(fs) == 0
        assert fs.calls["stat"] <= 1
