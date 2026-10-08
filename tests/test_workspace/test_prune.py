"""Two-phase execution pruning — ``molab.workspace.prune``.

The ONE prune core behind the CLI (``molab runs prune``):
``plan_execution_prune`` turns a selection (explicit ids /
statuses / everything) into a frozen, reviewable ``ExecutionPrunePlan``;
``apply_execution_prune`` removes exactly the bulk directories the plan lists.

Contract points under test (arch-own-01-cleanup):

* planning is read-only; each entry names the *prunable* directories
  (``execution_dirs.prunable_dirs()``) present at plan time, sorted;
* refusal lives at PLAN time — selecting a queued, running or finalizing
  Execution raises ``LivePruneRefusedError``;
* apply removes only those bulk directories. ``execution.json``, the node
  journal (``workflow.json``), ``run.log`` and ``artifacts/`` are kept, the
  record is stamped ``pruned_at`` / ``pruned_dirs``, and execution ids are
  never reused.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from molab.workspace import Workspace
from molab.workspace.domain import ExecutionMode, ExecutionStatus
from molab.workspace.execution_repository import ExecutionRepository
from molab.workspace.history import AgentRef
from molab.workspace.prune import (
    ExecutionPruneEntry,
    ExecutionPrunePlan,
    LivePruneRefusedError,
    apply_execution_prune,
    plan_execution_prune,
)
from molab.workspace.run import Run

_TEST_AGENT = AgentRef(id="test", type="person", name="test")

# Every attempt carries bulk (out/, work/) next to what must survive a prune.
_BULK = {"out/x": "x", "work/y": "y"}
_KEPT = {"workflow.json": "{}", "run.log": "log\n", "artifacts/z": "z"}


def _repo(run: Run) -> ExecutionRepository:
    ws = run.experiment.project.workspace
    return ExecutionRepository(
        ws.root,
        run.run_dir,
        run_id=run.id,
        project_id=run.experiment.project.id,
        fs=ws.fs,
    )


def _exec_dir(run: Run, execution_id: str) -> Path:
    return Path(str(run.run_dir)) / "executions" / execution_id


def _write_payload(run: Run, execution_id: str) -> None:
    for rel, text in {**_BULK, **_KEPT}.items():
        path = _exec_dir(run, execution_id) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _seed_executions(run: Run, statuses: tuple[str, ...]) -> list[str]:
    """Seed one sealed Execution per status, each with bulk + kept files."""
    repo = _repo(run)
    ids: list[str] = []
    for i, status in enumerate(statuses):
        mode = ExecutionMode.INITIAL if i == 0 else ExecutionMode.RERUN
        state = repo.create(mode=mode, created_by=_TEST_AGENT)
        repo.start(state.id)
        _write_payload(run, state.id)
        repo.seal(state.id, ExecutionStatus(status))
        ids.append(state.id)
    return ids


@pytest.fixture
def seeded(tmp_path: Path) -> Run:
    """A run with e01 succeeded, e02 failed, e03 failed."""
    ws = Workspace(root=tmp_path, name="prune-lab")
    exp = ws.add_project("proj-a").add_experiment("exp-x", params={})
    run = exp.add_run(params={"seed": 1})
    assert _seed_executions(run, ("succeeded", "failed", "failed")) == ["e01", "e02", "e03"]
    return run


def _snapshot(run: Run) -> list[str]:
    """Every file / directory under the run's executions/, relative."""
    root = Path(str(run.run_dir)) / "executions"
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))


def _live(run: Run, status: ExecutionStatus) -> str:
    """Add a fourth attempt left in an active *status*; return its id."""
    repo = _repo(run)
    state = repo.create(mode=ExecutionMode.RERUN, created_by=_TEST_AGENT)
    if status is not ExecutionStatus.QUEUED:
        repo.start(state.id)
    if status is ExecutionStatus.FINALIZING:
        repo.transition(state.id, ExecutionStatus.FINALIZING)
    assert repo.get(state.id).status is status
    return state.id


class TestPlanExecutionPrune:
    def test_statuses_filter_selects_failed_with_their_bulk_dirs(self, seeded: Run) -> None:
        plan = plan_execution_prune(seeded, statuses=["failed"])
        assert plan.run_id == seeded.id
        assert [entry.execution_id for entry in plan.entries] == ["e02", "e03"]
        assert [entry.status for entry in plan.entries] == ["failed", "failed"]
        assert [entry.dirs for entry in plan.entries] == [("out", "work"), ("out", "work")]

    def test_explicit_execution_ids_win(self, seeded: Run) -> None:
        plan = plan_execution_prune(seeded, execution_ids=["e01"], statuses=["failed"])
        assert [entry.execution_id for entry in plan.entries] == ["e01"]

    def test_unknown_execution_id_raises_key_error(self, seeded: Run) -> None:
        with pytest.raises(KeyError):
            plan_execution_prune(seeded, execution_ids=["e99"])

    def test_no_filters_selects_every_attempt(self, seeded: Run) -> None:
        plan = plan_execution_prune(seeded)
        assert [entry.execution_id for entry in plan.entries] == ["e01", "e02", "e03"]

    def test_no_match_yields_an_empty_plan(self, seeded: Run) -> None:
        plan = plan_execution_prune(seeded, statuses=["cancelled"])
        assert plan.entries == ()

    def test_planning_touches_no_disk_state(self, seeded: Run) -> None:
        before_files = _snapshot(seeded)
        before_records = [rec.model_dump() for rec in seeded.executions]
        plan_execution_prune(seeded, statuses=["failed"])
        assert _snapshot(seeded) == before_files
        assert [rec.model_dump() for rec in seeded.executions] == before_records

    @pytest.mark.parametrize(
        "status",
        [ExecutionStatus.QUEUED, ExecutionStatus.RUNNING, ExecutionStatus.FINALIZING],
        ids=["queued", "running", "finalizing"],
    )
    def test_selecting_an_active_execution_refuses(
        self, seeded: Run, status: ExecutionStatus
    ) -> None:
        live_id = _live(seeded, status)
        assert live_id == "e04"
        with pytest.raises(LivePruneRefusedError):
            plan_execution_prune(seeded, execution_ids=[live_id])
        assert len(seeded.executions) == 4

    def test_selecting_a_terminal_unsealed_execution_refuses(self, seeded: Run) -> None:
        # A terminal status with no seal is real: ``molab migrate layout``
        # writes ``status="interrupted"`` with ``sealed_at`` possibly None.
        # ``mark_pruned`` needs a seal, so plan must refuse before apply
        # could remove the bytes.
        repo = _repo(seeded)
        state = repo.create(mode=ExecutionMode.RERUN, created_by=_TEST_AGENT)
        repo.start(state.id)
        _write_payload(seeded, state.id)
        unsealed = repo.get(state.id).model_copy(update={"status": ExecutionStatus.INTERRUPTED})
        repo._write_state(unsealed)
        assert repo.get(state.id).status is ExecutionStatus.INTERRUPTED
        assert repo.get(state.id).sealed_at is None
        before = _snapshot(seeded)

        with pytest.raises(LivePruneRefusedError, match="not sealed"):
            plan_execution_prune(seeded, execution_ids=[state.id])

        assert _snapshot(seeded) == before
        assert (_exec_dir(seeded, state.id) / "out" / "x").is_file()
        assert repo.get(state.id).pruned_at is None


class TestApplyExecutionPrune:
    def test_returns_removed_dir_count(self, seeded: Run) -> None:
        plan = plan_execution_prune(seeded, statuses=["failed"])
        assert apply_execution_prune(seeded, plan) == 4

    def test_keeps_records_journal_logs_and_artifacts(self, seeded: Run) -> None:
        plan = plan_execution_prune(seeded, statuses=["failed"])
        apply_execution_prune(seeded, plan)
        for execution_id in ("e02", "e03"):
            d = _exec_dir(seeded, execution_id)
            assert (d / "execution.json").is_file()
            assert (d / "workflow.json").is_file()
            assert (d / "run.log").is_file()
            assert (d / "artifacts" / "z").is_file()
            assert not (d / "out").exists()
            assert not (d / "work").exists()
        untouched = _exec_dir(seeded, "e01")
        assert (untouched / "out" / "x").is_file()
        assert (untouched / "work" / "y").is_file()

    def test_execution_ids_are_kept(self, seeded: Run) -> None:
        plan = plan_execution_prune(seeded, statuses=["failed"])
        apply_execution_prune(seeded, plan)
        assert [rec.id for rec in seeded.executions] == ["e01", "e02", "e03"]

    def test_stamps_pruned_record(self, seeded: Run) -> None:
        plan = plan_execution_prune(seeded, statuses=["failed"])
        apply_execution_prune(seeded, plan)
        repo = _repo(seeded)
        e02 = repo.get("e02")
        assert e02.pruned_dirs == ("out", "work")
        assert e02.pruned_at is not None
        assert repo.get("e01").pruned_at is None

    def test_next_execution_id_is_never_reused(self, seeded: Run) -> None:
        plan = plan_execution_prune(seeded, statuses=["failed"])
        apply_execution_prune(seeded, plan)
        nxt = _repo(seeded).create(mode=ExecutionMode.RERUN, created_by=_TEST_AGENT)
        assert nxt.id == "e04"

    def test_dir_removed_since_planning_is_not_counted(self, seeded: Run) -> None:
        plan = plan_execution_prune(seeded, statuses=["failed"])
        shutil.rmtree(_exec_dir(seeded, "e02") / "out")
        assert apply_execution_prune(seeded, plan) == 3
        assert _repo(seeded).get("e02").pruned_dirs == ("out", "work")

    def test_refuses_an_unsealed_entry_before_touching_bytes(self, seeded: Run) -> None:
        # A plan is data; apply re-checks the seal so a hand-built or stale
        # plan can never remove bulk it cannot then stamp.
        repo = _repo(seeded)
        state = repo.create(mode=ExecutionMode.RERUN, created_by=_TEST_AGENT)
        repo.start(state.id)
        _write_payload(seeded, state.id)
        repo._write_state(
            repo.get(state.id).model_copy(update={"status": ExecutionStatus.INTERRUPTED})
        )
        forged = ExecutionPrunePlan(
            run_id=seeded.id,
            entries=(
                ExecutionPruneEntry(
                    execution_id=state.id, status="interrupted", dirs=("out", "work")
                ),
            ),
        )
        with pytest.raises(ValueError, match="not sealed"):
            apply_execution_prune(seeded, forged)
        assert (_exec_dir(seeded, state.id) / "out" / "x").is_file()
        assert (_exec_dir(seeded, state.id) / "work" / "y").is_file()

    def test_refuses_non_prunable_dir_before_touching_bytes(self, seeded: Run) -> None:
        # ``ExecutionPruneEntry`` is public, so a hand-built entry can name a
        # directory that is not bulk. Apply must refuse it before removing
        # anything, not after the bytes are gone.
        forged = ExecutionPrunePlan(
            run_id=seeded.id,
            entries=(
                ExecutionPruneEntry(execution_id="e01", status="succeeded", dirs=("artifacts",)),
            ),
        )
        with pytest.raises(ValueError, match="artifacts"):
            apply_execution_prune(seeded, forged)
        assert (_exec_dir(seeded, "e01") / "artifacts" / "z").is_file()
        assert _repo(seeded).get("e01").pruned_at is None

    def test_refuses_a_plan_built_for_another_run(self, seeded: Run) -> None:
        foreign = ExecutionPrunePlan(run_id="someone-else", entries=())
        with pytest.raises(ValueError, match="someone-else"):
            apply_execution_prune(seeded, foreign)
