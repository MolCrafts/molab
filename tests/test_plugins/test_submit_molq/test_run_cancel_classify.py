"""Unit tests for ``molab.plugins.submit_molq.cancel.classify``.

``classify`` is pure inspection: it maps a run's active Execution to a
:class:`CancelPlan` without executing anything. One test per branch of the
classification contract (molq / local-same-host / uncancellable reasons).
"""

from __future__ import annotations

import platform

import pytest

from molab.plugins.submit_molq.cancel import classify
from molab.workspace import Workspace
from molab.workspace.domain import ACTIVE_EXECUTION_STATUSES, ExecutionMode, ExecutionStatus
from molab.workspace.execution_repository import ExecutionRepository
from molab.workspace.scientific_repository import SYSTEM_AGENT


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


def _run(tmp_path):
    """A Run with no Execution yet."""
    ws = Workspace(root=tmp_path, name="lab")
    ws.materialize()
    project = ws.add_project("p")
    experiment = project.add_experiment("e", params={})
    return experiment.add_run(params={"seed": 1})


@pytest.fixture
def start_run(tmp_path):
    """Factory: a Run whose one Execution was created QUEUED, then started.

    ``executor`` keys are the start-time facts the worker writes (``host`` /
    ``pid``) or the scheduler facts molq would have recorded; they are seeded
    through ``ExecutionRepository.start`` on the fresh QUEUED record, never
    through ``update_operational`` (which refuses start-time keys).
    """

    def _start(**executor: object):
        run = _run(tmp_path)
        repo = _repo(run)
        state = repo.create(mode=ExecutionMode.INITIAL, created_by=SYSTEM_AGENT)
        repo.start(state.id, executor=dict(executor))
        return run

    return _start


@pytest.fixture
def running_run(start_run):
    """A Run with one live (running) Execution whose ``executor`` is empty."""
    return start_run()


class TestClassify:
    def test_molq_backend_with_job_id_classifies_molq(self, start_run):
        run = start_run(
            backend="molq",
            scheduler="slurm",
            cluster_name="hpc",
            job_id="abc-uuid-123",
            scheduler_job_id="88001",
        )
        plan = classify(run)
        assert plan.kind == "molq"
        assert plan.detail == "hpc"
        assert plan.job_id == "abc-uuid-123"

    def test_local_pid_same_host_classifies_local(self, start_run):
        run = start_run(pid=12345, host=platform.node())
        plan = classify(run)
        assert plan.kind == "local"
        assert plan.detail == "12345"

    def test_pid_on_different_host_is_uncancellable(self, start_run):
        run = start_run(pid=12345, host="some-other-host.example")
        plan = classify(run)
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
