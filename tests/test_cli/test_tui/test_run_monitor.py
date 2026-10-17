"""Unit tests for ``molab.cli.tui.run_monitor.RunMonitor`` (the dashboard poll).

Spec arch-own-02d §1e-prime: terminal handling of a molq submission is
level-triggered. Every poll of the run dashboard (shared by ``molab run
--block`` and ``molab monitor``) calls
``molab.plugins.submit_molq.submit.reconcile_submission`` for each run's
newest attempt that is still active and was submitted through molq — and for
nothing else. The molq dashboard is replaced by a fake that polls once, and
``reconcile_submission`` by a recorder; no scheduler or terminal is involved.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from molq.dashboard import DashboardState, JobRow

from molab.cli.tui.run_monitor import RunMonitor
from molab.profile import ProfileConfig
from molab.workspace import Workspace
from molab.workspace.domain import ExecutionMode
from molab.workspace.execution_repository import ExecutionRepository
from molab.workspace.experiment import Experiment
from molab.workspace.run import Run

_MOLQ_EXECUTOR = {"backend": "molq", "target": None, "scheduler": "local", "job_id": "job-x"}


@dataclass
class PollSpy:
    """One dashboard poll: the states it built and the reconcile calls it made."""

    states: list[DashboardState] = field(default_factory=list)
    reconciled: list[tuple[str, str]] = field(default_factory=list)


def _install_single_poll(monkeypatch: pytest.MonkeyPatch) -> PollSpy:
    """Make ``RunMonitor.watch`` poll exactly once and record reconcile calls.

    ``molq.dashboard.RunDashboard`` is replaced by a fake whose ``watch``
    calls the data function once; ``reconcile_submission`` on
    ``molab.plugins.submit_molq.submit`` is replaced by a recorder that
    returns the record unchanged, with no error.
    """
    from molab.plugins.submit_molq.submit import ReconcileOutcome

    spy = PollSpy()

    class SinglePollDashboard:
        def watch(
            self, data_fn: Callable[[], DashboardState], *, refresh_interval: float = 2.0
        ) -> None:
            del refresh_interval
            spy.states.append(data_fn())

    def recording_reconcile(mol_run: Run, execution_id: str) -> ReconcileOutcome:
        spy.reconciled.append((mol_run.id, execution_id))
        return ReconcileOutcome(record=mol_run.execution(execution_id))

    monkeypatch.setattr("molq.dashboard.RunDashboard", SinglePollDashboard)
    monkeypatch.setattr(
        "molab.plugins.submit_molq.submit.reconcile_submission",
        recording_reconcile,
        raising=False,
    )
    return spy


def _experiment(root: Path) -> Experiment:
    ws = Workspace(root)
    ws.materialize()
    return ws.add_project("p").add_experiment("e", params={})


def _repository(run: Run) -> ExecutionRepository:
    ws = run.experiment.project.workspace
    return ExecutionRepository(
        ws.root, run.run_dir, run_id=run.id, project_id=run.experiment.project.id, fs=ws.fs
    )


class TestRunMonitorReconcile:
    def test_poll_reconciles_latest_active_molq_attempt_only(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        experiment = _experiment(tmp_path)

        queued_molq = experiment.add_run(params={"seed": 1})
        queued_molq._create_execution(executor=dict(_MOLQ_EXECUTOR))

        queued_local = experiment.add_run(params={"seed": 2})
        queued_local._create_execution()

        sealed_molq = experiment.add_run(params={"seed": 3})
        sealed_molq._create_execution(executor=dict(_MOLQ_EXECUTOR))
        sealed_molq.cancel("e01")

        retried_molq = experiment.add_run(params={"seed": 4})
        retried_molq._create_execution(executor=dict(_MOLQ_EXECUTOR))
        retried_molq.cancel("e01")
        retried_molq._create_execution(
            mode=ExecutionMode.RERUN,
            predecessor="e01",
            executor=dict(_MOLQ_EXECUTOR),
        )

        running_molq = experiment.add_run(params={"seed": 5})
        running_molq._create_execution(executor=dict(_MOLQ_EXECUTOR))
        _repository(running_molq).start("e01")

        never_submitted = experiment.add_run(params={"seed": 6})

        runs = [
            queued_molq,
            queued_local,
            sealed_molq,
            retried_molq,
            running_molq,
            never_submitted,
        ]
        spy = _install_single_poll(monkeypatch)

        RunMonitor(title="t").watch(runs)

        assert len(spy.states) == 1
        assert spy.states[0].total == len(runs)
        assert spy.reconciled == [
            (queued_molq.id, "e01"),
            (retried_molq.id, "e02"),
        ]

    def test_poll_without_molq_attempts_reconciles_nothing(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        experiment = _experiment(tmp_path)
        local = experiment.add_run(params={"seed": 1})
        local._create_execution()
        sealed_molq = experiment.add_run(params={"seed": 2})
        sealed_molq._create_execution(executor=dict(_MOLQ_EXECUTOR))
        sealed_molq.cancel("e01")
        spy = _install_single_poll(monkeypatch)

        RunMonitor(title="t").watch([local, sealed_molq])

        assert len(spy.states) == 1
        assert spy.reconciled == []


# ----------------------------------------------------------------------
# Reconciliation runs off the render path (spec §1e-prime review)


def _install_outcome_reconcile(
    monkeypatch: pytest.MonkeyPatch,
    *,
    errors: dict[str, str] | None = None,
    raises: dict[str, Exception] | None = None,
) -> list[tuple[str, str]]:
    """Replace ``reconcile_submission`` with a recorder returning an outcome.

    Args:
        monkeypatch: The test's monkeypatch.
        errors: Run id → ``ReconcileOutcome.error`` to report for that run.
        raises: Run id → exception the recorder raises for that run.

    Returns:
        The ``(run id, execution id)`` pairs reconciled, in call order.
    """
    from molab.plugins.submit_molq.submit import ReconcileOutcome

    calls: list[tuple[str, str]] = []

    def recording_reconcile(mol_run: Run, execution_id: str) -> ReconcileOutcome:
        calls.append((mol_run.id, execution_id))
        if raises and mol_run.id in raises:
            raise raises[mol_run.id]
        return ReconcileOutcome(
            record=mol_run.execution(execution_id),
            error=(errors or {}).get(mol_run.id),
        )

    monkeypatch.setattr(
        "molab.plugins.submit_molq.submit.reconcile_submission", recording_reconcile
    )
    return calls


def _install_polls(monkeypatch: pytest.MonkeyPatch, polls: int) -> list[DashboardState]:
    """Make ``RunDashboard.watch`` call the data function *polls* times."""
    states: list[DashboardState] = []

    class MultiPollDashboard:
        def watch(
            self, data_fn: Callable[[], DashboardState], *, refresh_interval: float = 2.0
        ) -> None:
            del refresh_interval
            for _ in range(polls):
                states.append(data_fn())

    monkeypatch.setattr("molq.dashboard.RunDashboard", MultiPollDashboard)
    return states


def _queued_molq(experiment: Experiment, seed: int) -> Run:
    run = experiment.add_run(params={"seed": seed})
    run._create_execution(executor=dict(_MOLQ_EXECUTOR))
    return run


def _row(state: DashboardState, run: Run) -> JobRow:
    return next(row for row in state.jobs if row.run_id == run.id)


class TestRunMonitorReconcileOffRenderPath:
    def test_pass_skips_running_molq_attempt(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        experiment = _experiment(tmp_path)
        queued = _queued_molq(experiment, 1)
        running = _queued_molq(experiment, 2)
        _repository(running).start("e01")
        calls = _install_outcome_reconcile(monkeypatch)

        RunMonitor(title="t")._reconcile_pass([queued, running])

        assert calls == [(queued.id, "e01")]

    def test_build_state_does_not_reconcile(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        experiment = _experiment(tmp_path)
        queued = _queued_molq(experiment, 1)
        calls = _install_outcome_reconcile(monkeypatch)

        state = RunMonitor(title="t")._build_state([queued])

        assert calls == []
        assert state.total == 1

    def test_reconcile_error_shown_in_row_message(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        experiment = _experiment(tmp_path)
        failing = _queued_molq(experiment, 1)
        fine = _queued_molq(experiment, 2)
        message = f"could not reconcile run {failing.id} attempt e01: TransportError: down"
        _install_outcome_reconcile(monkeypatch, errors={failing.id: message})
        monitor = RunMonitor(title="t")

        monitor._reconcile_pass([failing, fine])
        state = monitor._build_state([failing, fine])

        assert message in (_row(state, failing).message or "")
        assert _row(state, fine).message is None

    def test_unexpected_reconcile_exception_becomes_row_message(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        experiment = _experiment(tmp_path)
        broken = _queued_molq(experiment, 1)
        fine = _queued_molq(experiment, 2)
        calls = _install_outcome_reconcile(monkeypatch, raises={broken.id: RuntimeError("boom")})
        monitor = RunMonitor(title="t")

        monitor._reconcile_pass([broken, fine])
        state = monitor._build_state([broken, fine])

        assert calls == [(broken.id, "e01"), (fine.id, "e01")]
        assert "RuntimeError: boom" in (_row(state, broken).message or "")
        assert _row(state, fine).message is None

    def test_watch_reconciles_at_most_once_per_interval_and_stops_worker(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        experiment = _experiment(tmp_path)
        queued = _queued_molq(experiment, 1)
        calls = _install_outcome_reconcile(monkeypatch)
        states = _install_polls(monkeypatch, 3)

        RunMonitor(title="t", reconcile_interval=3600.0).watch([queued])

        assert len(states) == 3
        assert calls == [(queued.id, "e01")]
        assert not any(
            t.name == "molab-run-monitor-reconcile" and t.is_alive() for t in threading.enumerate()
        )


# ----------------------------------------------------------------------
# Rows read the latest Execution (spec arch-own-02e-readers)

_RUN_LEVEL_PROVENANCE = ("profile", "config_hash", "script", "executor_info")


def _run_with_record(root: Path) -> Run:
    """A run whose only provenance is the QUEUED e01 execution record."""
    ws = Workspace(root / "lab", name="Lab")
    ws.materialize()
    run = ws.add_project("p").add_experiment("e").add_run(params={"x": 1})
    run._create_execution(
        profile_config=ProfileConfig({"nodes": 2}, name="cpu"),
        environment={"script": "/lab/s.py"},
        executor={"backend": "molq", "scheduler": "slurm", "scheduler_job_id": "4242"},
    )
    raw = json.loads((run.run_dir / "run.json").read_text())
    assert not any(key in raw for key in _RUN_LEVEL_PROVENANCE)
    return run


def _sealed_run(root: Path, *, fail: bool) -> Run:
    """A run whose single attempt e01 was started and sealed in-process."""
    ws = Workspace(root / "lab", name="Lab")
    ws.materialize()
    run = ws.add_project("p").add_experiment("e").add_run(params={"x": 1})
    if fail:
        with pytest.raises(RuntimeError), run.start():
            raise RuntimeError("boom")
    else:
        with run.start():
            pass
    return run


def _single_state(monkeypatch: pytest.MonkeyPatch, runs: list[Run]) -> DashboardState:
    spy = _install_single_poll(monkeypatch)
    RunMonitor(title="t").watch(runs)
    assert len(spy.states) == 1
    return spy.states[0]


class TestRunMonitor:
    def test_row_state_is_latest_attempt_status(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        run = _run_with_record(tmp_path)

        state = _single_state(monkeypatch, [run])

        assert state.jobs[0].state == "queued"

    def test_row_scheduler_id_from_latest_executor(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        run = _run_with_record(tmp_path)

        state = _single_state(monkeypatch, [run])

        assert state.jobs[0].scheduler_id == "4242"

    def test_row_profile_from_latest_environment(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        run = _run_with_record(tmp_path)

        state = _single_state(monkeypatch, [run])

        assert ("profile", "cpu") in state.jobs[0].extras

    def test_queued_counts_as_pending(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        run = _run_with_record(tmp_path)

        state = _single_state(monkeypatch, [run])

        assert state.pending == 1
        assert state.running == 0

    def test_sealed_failed_attempt_shows_failed_and_counts(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        run = _sealed_run(tmp_path, fail=True)

        state = _single_state(monkeypatch, [run])

        assert state.jobs[0].state == "failed"
        assert state.failed == 1
        assert state.pending == 0
        assert state.done == 0

    def test_sealed_succeeded_attempt_counts_as_done(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        run = _sealed_run(tmp_path, fail=False)

        state = _single_state(monkeypatch, [run])

        assert state.jobs[0].state == "succeeded"
        assert state.done == 1
        assert state.pending == 0

    def test_failed_row_carries_execution_error(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        ws = Workspace(tmp_path / "lab", name="Lab")
        ws.materialize()
        run = ws.add_project("p").add_experiment("e").add_run(params={"x": 1})
        with pytest.raises(RuntimeError), run.start():
            raise RuntimeError("oom-marker")

        state = _single_state(monkeypatch, [run])

        assert state.jobs[0].message == "oom-marker"
