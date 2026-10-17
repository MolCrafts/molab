"""Execution identity.

An attempt is identified by its position in its Run: ``e01``, ``e02``, …
allocated by
:meth:`~molab.workspace.execution_repository.ExecutionRepository.create`.
The id *is* the directory name, so a path leads to an attempt and an attempt
leads back to its path with no lookup. Global uniqueness comes from the pair
``(run_id, execution_id)`` — a Run's id is the UUIDv7.
"""

from __future__ import annotations

from molab.workspace.domain import ExecutionMode, ExecutionStatus
from molab.workspace.execution_repository import ExecutionRepository
from molab.workspace.history import AgentRef

_TEST_AGENT = AgentRef(id="test", type="person", name="test")


def _repo(run) -> ExecutionRepository:
    ws = run.experiment.project.workspace
    return ExecutionRepository(
        ws.root,
        run.run_dir,
        run_id=run.id,
        project_id=run.experiment.project.id,
        fs=ws.fs,
    )


def test_execution_repository_numbers_attempts_in_order(run) -> None:
    run.materialize()
    repo = _repo(run)
    first = repo.create(mode=ExecutionMode.INITIAL, created_by=_TEST_AGENT)
    repo.seal("e01", ExecutionStatus.CANCELLED)
    second = repo.create(mode=ExecutionMode.RERUN, created_by=_TEST_AGENT)
    assert (first.id, first.seq) == ("e01", 1)
    assert (second.id, second.seq) == ("e02", 2)


def test_execution_id_is_its_directory_name(run) -> None:
    run.materialize()
    repo = _repo(run)
    state = repo.create(mode=ExecutionMode.INITIAL, created_by=_TEST_AGENT)
    assert repo.execution_dir(state.id).endswith(f"/executions/{state.id}")


def test_two_execution_repository_creates_get_distinct_ids(run) -> None:
    run.materialize()
    repo = _repo(run)
    first = repo.create(mode=ExecutionMode.INITIAL, created_by=_TEST_AGENT).id
    repo.seal("e01", ExecutionStatus.CANCELLED)
    second = repo.create(mode=ExecutionMode.RERUN, created_by=_TEST_AGENT).id
    assert first != second


class TestTimestampsStayComparable:
    """A record read back must be orderable against every other record.

    Attempts written by different molab generations disagreed about whether
    a timestamp carries a zone. Comparing a naive one with an aware one
    raises, which took out anything that sorts attempts or asks a Run when it
    finished — so the model normalizes naive timestamps to UTC on read.
    """

    def test_naive_and_aware_attempts_sort_together(self, run) -> None:
        run.materialize()
        repo = _repo(run)
        repo.create(mode=ExecutionMode.INITIAL, created_by=_TEST_AGENT)
        repo.seal("e01", ExecutionStatus.CANCELLED)
        repo.create(mode=ExecutionMode.RERUN, created_by=_TEST_AGENT)

        # Rewrite one attempt the way an older molab wrote it: no zone.
        import json
        from pathlib import Path

        state_path = Path(repo.state_path("e01"))
        raw = json.loads(state_path.read_text(encoding="utf-8"))
        raw["created_at"] = "2026-09-01T12:00:00"
        raw["finished_at"] = "2026-09-01T18:00:00"
        raw["status"] = "failed"
        state_path.write_text(json.dumps(raw), encoding="utf-8")

        attempts = repo.list()
        assert [item.id for item in attempts] == ["e01", "e02"]
        assert all(item.created_at.tzinfo is not None for item in attempts)
        assert run.finished_at is None  # latest attempt (e02) is still queued
