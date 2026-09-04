"""Unit tests for ``molexp.plugins.submit_molq.cancel.classify``.

``classify`` is pure inspection: it maps a run's active Execution to a
:class:`CancelPlan` without executing anything. One test per branch of the
classification contract (molq / local-same-host / uncancellable reasons).
"""

from __future__ import annotations

import platform

import pytest

from molexp.plugins.submit_molq.cancel import classify
from molexp.workspace import Workspace
from molexp.workspace.domain import ACTIVE_EXECUTION_STATUSES, ExecutionMode, ExecutionStatus
from molexp.workspace.execution_repository import ExecutionRepository
from molexp.workspace.scientific_repository import SYSTEM_AGENT


def _repo(run) -> ExecutionRepository:
    ws = run.experiment.project.workspace
    return ExecutionRepository(
        ws.root,
        run.run_dir,
        run_id=run.id,
        project_id=run.experiment.project.id,
        fs=ws.fs,
    )


def _active_execution(run):
    return [ex for ex in run.executions if ex.status in ACTIVE_EXECUTION_STATUSES][-1]


def _set_executor(run, **executor: object) -> None:
    """Overwrite the active Execution's ``executor`` info in place."""
    repo = _repo(run)
    ex = _active_execution(run)
    repo.update_operational(ex.id, executor=dict(executor))


@pytest.fixture
def running_run(tmp_path):
    """A Run with one live (running) Execution whose ``executor`` is empty."""
    ws = Workspace(root=tmp_path, name="lab")
    ws.materialize()
    project = ws.add_project("p")
    experiment = project.add_experiment("e", workflow_source="s.py", params={})
    run = experiment.add_run(params={"seed": 1})
    repo = _repo(run)
    state = repo.create(mode=ExecutionMode.INITIAL, created_by=SYSTEM_AGENT)
    repo.start(state.id)
    return run


class TestClassify:
    def test_molq_backend_with_job_id_classifies_molq(self, running_run):
        _set_executor(
            running_run,
            backend="molq",
            scheduler="slurm",
            cluster_name="hpc",
            job_id="abc-uuid-123",
            scheduler_job_id="88001",
        )
        plan = classify(running_run)
        assert plan.kind == "molq"
        assert plan.detail == "hpc"
        assert plan.job_id == "abc-uuid-123"

    def test_local_pid_same_host_classifies_local(self, running_run):
        _set_executor(running_run, pid=12345, host=platform.node())
        plan = classify(running_run)
        assert plan.kind == "local"
        assert plan.detail == "12345"

    def test_pid_on_different_host_is_uncancellable(self, running_run):
        _set_executor(running_run, pid=12345, host="some-other-host.example")
        plan = classify(running_run)
        assert plan.kind == "none"
        assert "different host" in plan.detail

    def test_terminal_status_is_uncancellable(self, running_run):
        repo = _repo(running_run)
        ex = _active_execution(running_run)
        repo.seal(ex.id, ExecutionStatus.SUCCEEDED)
        plan = classify(running_run)
        assert plan.kind == "none"
        assert plan.detail == "already terminal"

    def test_no_pid_or_scheduler_info_is_uncancellable(self, running_run):
        plan = classify(running_run)
        assert plan.kind == "none"
