"""``WorkspaceReadModel`` — when a view is rebuilt, and what it costs (P3-3b).

The container's whole job is deciding *when*: the builders are already tested
in ``tests/test_workspace/test_read_model_runs.py``. What matters here is that
an unchanged sweep reads nothing, that a change made by another process is
still noticed, and that the ticker thread never outlives the model.
"""

from __future__ import annotations

import time

import pytest

from molexp.services.workspace_read_model import RefreshPolicy, WorkspaceReadModel
from molexp.workspace import Workspace
from molexp.workspace.run_ops import RunStatus
from tests.support.counting_fs import CountingFileSystem


@pytest.fixture
def seeded(tmp_path):
    ws = Workspace(root=tmp_path / "lab", name="lab")
    experiment = ws.add_project("proj").add_experiment("exp")
    for i in range(3):
        experiment.add_run(params={"i": i})
    return ws


@pytest.fixture
def counting(seeded: Workspace, tmp_path):
    fs = CountingFileSystem(seeded.fs.__class__())
    return Workspace(root=tmp_path / "lab", fs=fs), fs


def _model(ws: Workspace, **policy: object) -> WorkspaceReadModel:
    return WorkspaceReadModel(ws, policy=RefreshPolicy(**policy))  # type: ignore[arg-type]


class TestFirstRead:
    def test_first_read_builds_and_later_reads_serve_the_same_object(
        self, seeded: Workspace
    ) -> None:
        model = _model(seeded)
        try:
            first = model.runs()
            assert len(first.rows) == 3
            assert model.runs() is first
        finally:
            model.stop()

    def test_versions_report_every_view(self, seeded: Workspace) -> None:
        model = _model(seeded)
        try:
            model.runs()
            model.assets()
            model.knowledge()
            assert set(model.versions()) == {"runs", "assets", "knowledge"}
        finally:
            model.stop()


class TestSweepCost:
    def test_unchanged_full_sweep_opens_no_files(self, counting) -> None:
        ws, fs = counting
        model = _model(ws, full_sweep_interval=0.0)
        try:
            model.runs()
            fs.reset()
            model.refresh("runs", block=True)
            assert fs.opens() == 0, dict(fs.calls)
            assert fs.stats() > 0, "a sweep must still validate by stat"
        finally:
            model.stop()

    def test_sweep_within_the_interval_skips_the_walk(self, counting) -> None:
        """Inside ``full_sweep_interval`` only the container probe runs."""
        ws, fs = counting
        model = _model(ws, full_sweep_interval=3600.0)
        try:
            model.runs()
            fs.reset()
            model.refresh("runs", block=True)
            assert fs.opens() == 0, dict(fs.calls)
            assert fs.stats() <= 4, dict(fs.calls)
        finally:
            model.stop()


class TestChangeDetection:
    def test_status_written_by_another_instance_is_picked_up(self, seeded: Workspace) -> None:
        """The cross-process case: a CLI verb writes, the server must notice."""
        model = _model(seeded, full_sweep_interval=0.0)
        try:
            first = model.runs()
            run_id = first.rows[0].run_id
            other = Workspace(root=seeded.resolve())
            other_run = other.get_project("proj").get_experiment("exp").get_run(run_id)
            other_run.update_ops(lambda s: s.model_copy(update={"status": RunStatus.FAILED}))

            model.invalidate("runs")
            second = model.runs()
            assert second.by_id[run_id].status == "failed"
            assert second.version > first.version
        finally:
            model.stop()

    def test_invalidate_forces_a_rebuild(self, seeded: Workspace) -> None:
        model = _model(seeded, full_sweep_interval=3600.0)
        try:
            first = model.runs()
            seeded.get_project("proj").get_experiment("exp").add_run(params={"i": 42})
            model.invalidate("runs")
            assert len(model.runs().rows) == 4
            assert model.runs().version > first.version
        finally:
            model.stop()


class TestPinnedMode:
    def test_pinned_snapshot_is_trusted_until_the_generation_moves(self, seeded: Workspace) -> None:
        """A remote mirror answers from cache — re-statting over SSH buys nothing."""

        class _Pinned:
            generation = 0

            def __init__(self, inner) -> None:
                self._inner = inner

            def __getattr__(self, name: str):
                return getattr(self._inner, name)

        fs = _Pinned(seeded.fs)
        ws = Workspace(root=seeded.resolve(), fs=fs)  # type: ignore[arg-type]
        model = WorkspaceReadModel(ws, policy=RefreshPolicy(mode="pinned"))
        try:
            first = model.runs()
            ws.get_project("proj").get_experiment("exp").add_run(params={"i": 7})
            assert model.runs() is first, "a pinned view must not re-scan on its own"

            fs.generation = 1
            model.refresh("runs", block=True)
            assert len(model.runs().rows) == 4
        finally:
            model.stop()


class TestLifecycle:
    def test_stop_joins_the_ticker_thread(self, seeded: Workspace) -> None:
        model = _model(seeded, tick_interval=0.01)
        model.runs()
        model.start()
        time.sleep(0.05)
        model.stop()
        assert model._ticker is None


class TestMetricsSummary:
    def test_fold_is_memoized_and_extends_incrementally(self, seeded: Workspace) -> None:
        from molexp.workspace.metrics import MetricsWriter

        run = seeded.get_project("proj").get_experiment("exp").list_runs()[0]
        writer = MetricsWriter(run.run_dir)
        writer.scalar("loss", 1.0, step=1)
        model = _model(seeded)
        try:
            assert model.metrics_summary(run.run_dir)["loss"] == 1.0
            # Unchanged file → served from the memo.
            assert model.metrics_summary(run.run_dir)["loss"] == 1.0
            writer.scalar("loss", 0.5, step=2)
            assert model.metrics_summary(run.run_dir)["loss"] == 0.5
        finally:
            model.stop()

    def test_missing_metrics_file_is_empty(self, seeded: Workspace) -> None:
        run = seeded.get_project("proj").get_experiment("exp").list_runs()[0]
        model = _model(seeded)
        try:
            assert model.metrics_summary(run.run_dir) == {}
        finally:
            model.stop()
