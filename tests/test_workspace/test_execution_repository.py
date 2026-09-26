"""Unit tests for ``molab.workspace.execution_repository`` (``ExecutionRepository``).

Execution creation, operational state and sealing: one attempt is one
directory (``executions/e01``) and one file inside it (``execution.json``).

Chain-owned test module: created by arch-own-01-cleanup; later arch-own specs
extend it (add classes / tests here rather than creating sibling files).

arch-own-01 pins two contracts:

* ``seal`` takes the per-execution locks in the fixed order seal -> state and
  holds the state lock across its read-modify-write, so a racing
  ``add_artifact`` either lands in the sealed record or is refused as sealed —
  never "returned success, then silently overwritten".
* ``mark_pruned`` is the single writer of the post-seal field set
  ``_POST_SEAL_FIELDS`` (``pruned_at`` / ``pruned_dirs``); every other field of
  a sealed record is frozen, and ``update_operational`` refuses those fields.
"""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from molab.workspace import execution_repository as repo_mod
from molab.workspace.domain import (
    Artifact,
    ContentRef,
    EvidenceRef,
    Execution,
    ExecutionMode,
    ExecutionStatus,
)
from molab.workspace.execution_repository import ExecutionRepository
from molab.workspace.history import AgentRef

_TEST_AGENT = AgentRef(id="test", type="person", name="test")
_FIXED_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def _repo(tmp_path: Path) -> ExecutionRepository:
    """A repository on a bare tmp workspace root (no ``.git`` → history is a no-op)."""
    run_dir = tmp_path / "projects" / "p" / "experiments" / "e" / "runs" / "seed=1"
    run_dir.mkdir(parents=True)
    return ExecutionRepository(tmp_path, run_dir, run_id="run-1", project_id="proj-1")


def _running(repo: ExecutionRepository) -> Execution:
    state = repo.create(mode=ExecutionMode.INITIAL, created_by=_TEST_AGENT)
    return repo.start(state.id)


def _sealed(repo: ExecutionRepository) -> Execution:
    state = _running(repo)
    return repo.seal(state.id, ExecutionStatus.SUCCEEDED)


def _artifact(execution_id: str) -> Artifact:
    return Artifact(
        id="a-race",
        execution_id=execution_id,
        run_id="run-1",
        project_id="proj-1",
        name="race.json",
        content=ContentRef(digest="sha256:" + "0" * 64, size=2),
        created_at=_FIXED_TIME,
        created_by=_TEST_AGENT,
        path="projects/p/experiments/e/runs/seed=1/executions/e01/artifacts/race.json",
        source_path="out/race.json",
    )


def _lock_suffix(path: Path) -> str:
    """``run-1.e01.seal.lock`` -> ``.seal.lock``."""
    return "." + ".".join(Path(path).name.split(".")[-2:])


class TestExecutionRepositorySeal:
    def test_concurrent_add_artifact_is_never_lost(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = _repo(tmp_path)
        state = _running(repo)
        original = ExecutionRepository._collect_evidence
        outcome: dict[str, BaseException | Execution] = {}
        threads: list[threading.Thread] = []

        def racer() -> None:
            try:
                outcome["result"] = repo.add_artifact(state.id, _artifact(state.id))
            except BaseException as exc:
                outcome["error"] = exc

        def collect_then_race(self: ExecutionRepository, execution_id: str) -> list[EvidenceRef]:
            # Seal has already read the record it is about to freeze.
            if not threads:
                thread = threading.Thread(target=racer)
                threads.append(thread)
                thread.start()
                thread.join(timeout=0.5)
            return original(self, execution_id)

        monkeypatch.setattr(ExecutionRepository, "_collect_evidence", collect_then_race)

        sealed = repo.seal(state.id, ExecutionStatus.SUCCEEDED)
        assert threads, "seal never collected evidence"
        threads[0].join(timeout=15)
        assert not threads[0].is_alive()

        landed = "a-race" in sealed.artifact_ids
        error = outcome.get("error")
        refused = isinstance(error, ValueError) and "sealed" in str(error)
        assert landed != refused, (
            f"exactly one of landed={landed} / refused={refused} must hold; "
            f"racer outcome={outcome!r}"
        )

    def test_seal_takes_seal_lock_then_state_lock(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = _repo(tmp_path)
        state = _running(repo)
        real_lock = repo_mod.file_lock
        acquired: list[str] = []
        held: list[str] = []
        held_at_terminal_write: list[frozenset[str]] = []
        nesting_violations: list[str] = []

        @contextlib.contextmanager
        def recording_lock(path: Path, *args: object, **kwargs: object) -> Iterator[None]:
            suffix = _lock_suffix(path)
            if suffix == ".seal.lock" and ".state.lock" in held:
                nesting_violations.append("seal acquired while state held")
            with real_lock(path, *args, **kwargs):  # type: ignore[arg-type]
                acquired.append(suffix)
                held.append(suffix)
                try:
                    yield
                finally:
                    held.remove(suffix)

        original_write = ExecutionRepository._write_state

        def recording_write(self: ExecutionRepository, written: Execution) -> None:
            if written.sealed:
                held_at_terminal_write.append(frozenset(held))
            original_write(self, written)

        monkeypatch.setattr(repo_mod, "file_lock", recording_lock)
        monkeypatch.setattr(ExecutionRepository, "_write_state", recording_write)

        repo.seal(state.id, ExecutionStatus.SUCCEEDED)

        assert acquired == [".seal.lock", ".state.lock"]
        assert nesting_violations == []
        # The sealed record is written inside the state lock (read-modify-write
        # under the lock every other writer takes), not after releasing it.
        assert held_at_terminal_write == [frozenset({".seal.lock", ".state.lock"})]

    def test_seal_twice_returns_same_record(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        first = _sealed(repo)
        second = repo.seal(first.id, ExecutionStatus.SUCCEEDED)
        assert first.sealed_at is not None
        assert second.sealed_at == first.sealed_at


class TestExecutionRepositoryMarkPruned:
    def test_stamps_pruned_at_and_sorted_dirs(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        sealed = _sealed(repo)
        pruned = repo.mark_pruned(sealed.id, ["work", "out"])
        assert pruned.pruned_dirs == ("out", "work")
        assert pruned.pruned_at is not None
        reread = repo.get(sealed.id)
        assert reread.pruned_dirs == ("out", "work")
        assert reread.pruned_at is not None

    def test_merges_dirs(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        sealed = _sealed(repo)
        repo.mark_pruned(sealed.id, ["work", "out"])
        merged = repo.mark_pruned(sealed.id, ["checkpoints"])
        assert merged.pruned_dirs == ("checkpoints", "out", "work")
        assert repo.get(sealed.id).pruned_dirs == ("checkpoints", "out", "work")

    def test_only_post_seal_fields_change(self, tmp_path: Path) -> None:
        from molab.workspace.execution_repository import _POST_SEAL_FIELDS

        assert frozenset({"pruned_at", "pruned_dirs"}) == _POST_SEAL_FIELDS
        repo = _repo(tmp_path)
        sealed = _sealed(repo)
        before = repo.get(sealed.id)
        repo.mark_pruned(sealed.id, ["out"])
        after = repo.get(sealed.id)
        excluded = set(_POST_SEAL_FIELDS)
        assert before.model_dump(exclude=excluded) == after.model_dump(exclude=excluded)
        assert after.sealed_at == before.sealed_at

    def test_refuses_unsealed(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        queued = repo.create(mode=ExecutionMode.INITIAL, created_by=_TEST_AGENT)
        with pytest.raises(ValueError):
            repo.mark_pruned(queued.id, ["out"])
        assert repo.get(queued.id).sealed_at is None

    def test_update_operational_refuses_prune_fields(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        queued = repo.create(mode=ExecutionMode.INITIAL, created_by=_TEST_AGENT)
        with pytest.raises(ValueError, match="pruned_at"):
            repo.update_operational(queued.id, pruned_at=_FIXED_TIME)
        with pytest.raises(ValueError, match="pruned_dirs"):
            repo.update_operational(queued.id, pruned_dirs=("out",))

    def test_transition_refuses_prune_fields(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        queued = repo.create(mode=ExecutionMode.INITIAL, created_by=_TEST_AGENT)
        with pytest.raises(ValueError, match="pruned_at"):
            repo.transition(queued.id, ExecutionStatus.RUNNING, pruned_at=_FIXED_TIME)
        with pytest.raises(ValueError, match="pruned_dirs"):
            repo.transition(queued.id, ExecutionStatus.RUNNING, pruned_dirs=("out",))
        after = repo.get(queued.id)
        assert after.status is ExecutionStatus.QUEUED
        assert after.pruned_at is None
        assert after.pruned_dirs == ()

    def test_refuses_non_prunable_dir(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        sealed = _sealed(repo)
        before = repo.get(sealed.id)
        with pytest.raises(ValueError, match="artifacts"):
            repo.mark_pruned(sealed.id, ["artifacts"])
        assert repo.get(sealed.id) == before
