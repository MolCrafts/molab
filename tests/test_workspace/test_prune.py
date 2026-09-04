"""Two-phase execution pruning — ``molexp.workspace.prune`` (v2).

The ONE prune core the CLI (``molexp runs prune``) and the harness lifecycle
capability share: ``plan_execution_prune`` turns a selection (explicit ids /
statuses / everything) into a frozen, reviewable ``ExecutionPrunePlan``;
``apply_execution_prune`` removes exactly the retained workspace bytes the
plan lists. Provenance is immutable, so apply never rewrites history — the
derived ``run.executions`` view shrinks only because the removed
``execution.json`` files are gone.

Contract points under test:

* planning is read-only and refusal lives at PLAN time — a ``running``
  Execution on an actively-running run raises ``LivePruneRefusedError``;
* terminal Executions prune normally;
* apply removes exactly the planned dirs; run params / other attempts are
  untouched, and an already-removed dir is tolerated (idempotent).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from molexp.workspace import Workspace
from molexp.workspace.domain import ExecutionMode, ExecutionStatus
from molexp.workspace.execution_repository import ExecutionRepository
from molexp.workspace.provenance import AgentRef
from molexp.workspace.prune import (
    ExecutionPrunePlan,
    LivePruneRefusedError,
    apply_execution_prune,
    plan_execution_prune,
)
from molexp.workspace.run import Run

_TEST_AGENT = AgentRef(id="test", type="person", name="test")


def _repo(run: Run) -> ExecutionRepository:
    ws = run.experiment.project.workspace
    return ExecutionRepository(
        ws.root,
        run.run_dir,
        run_id=run.id,
        project_id=run.experiment.project.id,
        fs=ws.fs,
    )


def _seed_executions(run: Run, statuses: tuple[str, ...]) -> list[str]:
    """Seed one physical Execution per status; return their ids."""
    repo = _repo(run)
    ids: list[str] = []
    for i, status in enumerate(statuses):
        mode = ExecutionMode.INITIAL if i == 0 else ExecutionMode.RERUN
        state = repo.create(mode=mode, created_by=_TEST_AGENT)
        repo.start(state.id)
        repo.seal(state.id, ExecutionStatus(status))
        ids.append(state.id)
    return ids


@pytest.fixture
def seeded(tmp_path: Path) -> tuple[Path, Run, list[str]]:
    """A run with three attempts: one succeeded + two failed."""
    ws = Workspace(root=tmp_path, name="prune-lab")
    exp = ws.add_project("proj-a").add_experiment("exp-x", workflow_source="s.py", params={})
    run = exp.add_run(params={"seed": 1})
    run.materialize()
    exec_ids = _seed_executions(run, ("succeeded", "failed", "failed"))
    return tmp_path, run, exec_ids


def _reloaded_ids(ws_path: Path, run: Run) -> list[str]:
    """Execution ids read back through a FRESH workspace (disk truth)."""
    reloaded = Workspace.load(ws_path).get_project("proj-a").get_experiment("exp-x").get_run(run.id)
    return [rec.id for rec in reloaded.executions]


# ── plan: selection semantics ────────────────────────────────────────────────


class TestPlanSelection:
    def test_statuses_filter_selects_only_matching_attempts(self, seeded) -> None:
        _, run, exec_ids = seeded
        plan = plan_execution_prune(run, statuses=["failed"])
        assert plan.run_id == run.id
        assert [entry.execution_id for entry in plan.entries] == exec_ids[1:]
        assert all(entry.status == "failed" for entry in plan.entries)
        assert all(entry.dir_exists for entry in plan.entries)

    def test_explicit_execution_ids_win(self, seeded) -> None:
        _, run, exec_ids = seeded
        plan = plan_execution_prune(run, execution_ids=[exec_ids[1]])
        assert [entry.execution_id for entry in plan.entries] == [exec_ids[1]]

    def test_unknown_execution_id_raises_key_error(self, seeded) -> None:
        _, run, _ = seeded
        with pytest.raises(KeyError):
            plan_execution_prune(run, execution_ids=["exec-nope"])

    def test_no_filters_selects_every_attempt(self, seeded) -> None:
        _, run, exec_ids = seeded
        plan = plan_execution_prune(run)
        assert [entry.execution_id for entry in plan.entries] == exec_ids

    def test_no_match_yields_an_empty_plan(self, seeded) -> None:
        _, run, _ = seeded
        plan = plan_execution_prune(run, statuses=["cancelled"])
        assert plan.entries == ()


class TestPlanIsReadOnlyAndFrozen:
    def test_planning_touches_no_disk_state(self, seeded) -> None:
        _, run, exec_ids = seeded
        plan_execution_prune(run, statuses=["failed"])
        exec_root = Path(str(run.run_dir)) / "executions"
        assert sorted(p.name for p in exec_root.iterdir() if p.is_dir()) == sorted(exec_ids)
        assert [rec.id for rec in run.executions] == exec_ids


# ── plan: live-record refusal (typed, at PLAN time) ──────────────────────────


class TestLiveRecordRefusal:
    @staticmethod
    def _live_run(tmp_path: Path) -> Run:
        ws = Workspace(root=tmp_path, name="live-lab")
        exp = ws.add_project("proj-a").add_experiment("exp-x", workflow_source="s.py", params={})
        run = exp.add_run(params={})
        run.materialize()
        state = _repo(run).create(mode=ExecutionMode.INITIAL, created_by=_TEST_AGENT)
        _repo(run).start(state.id)
        return run

    def test_running_record_on_active_run_refuses_at_plan_time(self, tmp_path: Path) -> None:
        run = self._live_run(tmp_path)
        with pytest.raises(LivePruneRefusedError):
            plan_execution_prune(run)
        assert len(run.executions) == 1

    def test_terminal_execution_prunes_normally(self, tmp_path: Path) -> None:
        """A terminal Execution is prunable history, never a refusal."""
        run = self._live_run(tmp_path)
        execution_id = run.executions[-1].id
        _repo(run).seal(execution_id, ExecutionStatus.FAILED)
        plan = plan_execution_prune(run, statuses=["failed"])
        assert [entry.execution_id for entry in plan.entries] == [execution_id]
        apply_execution_prune(run, plan)
        assert run.executions == []


# ── apply: exact deletion ────────────────────────────────────────────────────


class TestApply:
    def test_apply_removes_exactly_the_planned_dirs(self, seeded) -> None:
        _, run, exec_ids = seeded
        plan = plan_execution_prune(run, statuses=["failed"])
        removed = apply_execution_prune(run, plan)
        assert removed == 2
        exec_root = Path(str(run.run_dir)) / "executions"
        assert [p.name for p in exec_root.iterdir() if p.is_dir()] == [exec_ids[0]]

    def test_apply_shrinks_the_derived_executions_view(self, seeded) -> None:
        ws_path, run, exec_ids = seeded
        plan = plan_execution_prune(run, statuses=["failed"])
        apply_execution_prune(run, plan)
        assert _reloaded_ids(ws_path, run) == [exec_ids[0]]

    def test_apply_leaves_run_params_and_other_attempts_alone(self, seeded) -> None:
        _, run, _ = seeded
        plan = plan_execution_prune(run, statuses=["failed"])
        apply_execution_prune(run, plan)
        assert run.parameters == {"seed": 1}
        assert run.executions[-1].status is ExecutionStatus.SUCCEEDED

    def test_apply_tolerates_an_already_removed_dir(self, seeded) -> None:
        _, run, exec_ids = seeded
        plan = plan_execution_prune(run, execution_ids=[exec_ids[0]])
        exec_root = Path(str(run.run_dir)) / "executions"
        shutil.rmtree(exec_root / exec_ids[0])
        removed = apply_execution_prune(run, plan)
        assert removed == 0
        assert [rec.id for rec in run.executions] == exec_ids[1:]

    def test_apply_refuses_a_plan_built_for_another_run(self, seeded, tmp_path: Path) -> None:
        _, run, _ = seeded
        foreign = ExecutionPrunePlan(run_id="someone-else", entries=())
        with pytest.raises(ValueError, match="someone-else"):
            apply_execution_prune(run, foreign)
