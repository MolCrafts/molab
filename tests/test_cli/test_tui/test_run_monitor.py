"""Run watching reuses the workspace tree and reconciles off the render path."""

from __future__ import annotations

import threading

from molab.cli.tui.run_monitor import RunMonitor
from molab.cli.tui.tree_model import build_tree
from molab.workspace import Workspace


def test_watch_reuses_the_tree_with_only_selected_runs(tmp_path, monkeypatch):
    workspace = Workspace(tmp_path / "workspace")
    experiment = workspace.add_project("project").add_experiment("experiment")
    selected = experiment.add_run(params={"seed": 1})
    other = experiment.add_run(params={"seed": 2})
    reconciled = threading.Event()
    frames = []

    class Viewer:
        def __init__(self, *, run_ids, **_kwargs: object):
            self.run_ids = run_ids

        def watch(self, ws):
            assert reconciled.wait(2)
            frames.append(build_tree(ws, run_ids=self.run_ids))
            return []

    def reconcile(self, runs):
        assert runs == [selected]
        reconciled.set()

    monkeypatch.setattr("molab.cli.tui.run_monitor.TreeMonitor", Viewer)
    monkeypatch.setattr(RunMonitor, "_reconcile_pass", reconcile)
    RunMonitor(reconcile_interval=3600).watch([selected])
    shown = frames[0].children[0].children[0].children
    assert len(shown) == 1 and shown[0].ref.id == selected.id
    assert shown[0].ref.id != other.id
    assert not any(thread.name == "molab-run-monitor-reconcile" for thread in threading.enumerate())


def test_reconcile_failures_are_retained_without_stopping_other_runs(monkeypatch):
    class Run:
        def __init__(self, identifier):
            self.id = identifier

    monitor = RunMonitor()
    monkeypatch.setattr(
        monitor,
        "_reconcile_one",
        lambda run: ("e01", "connection failed") if run.id == "failed" else None,
    )
    monitor._reconcile_pass([Run("failed"), Run("healthy")])
    assert monitor._reconcile_errors == {"failed": ("e01", "connection failed")}


def test_empty_watch_does_not_open_a_viewer(monkeypatch):
    monkeypatch.setattr(
        "molab.cli.tui.run_monitor.TreeMonitor",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("opened")),
    )
    RunMonitor().watch([])
