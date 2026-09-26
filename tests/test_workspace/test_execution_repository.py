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
import json
import threading
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pydantic
import pytest

from molab.workspace import Run
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
from molab.workspace.schema_version import MOLAB_SCHEMA_VERSION, read_versioned_json

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


# ── arch-own-02a-record ──────────────────────────────────────────────────
#
# The record carries creation-time vs start-time provenance. ``create``
# persists ``bypass_cache`` / ``source``; ``start`` admits only a QUEUED record
# under the state lock and merges start-time facts without overwriting
# creation-time ones; ``update_operational`` refuses the union of identity,
# post-seal and provenance fields; ``fold_legacy_attempt`` builds a
# current-schema record through the model. Symbols introduced by 02a are
# imported inside each test so every test fails for its own reason.

_SCHEMA_V4 = 4
_LEGACY_AGENT = {"id": "molab", "type": "system", "name": "Molab"}
_LEGACY_CREATED = "2026-09-04T22:09:31.925482Z"


def _run_repo(run: Run) -> ExecutionRepository:
    return run._execution_repository()


def _raw_state(repo: ExecutionRepository, execution_id: str) -> dict[str, object]:
    return json.loads(Path(repo.state_path(execution_id)).read_text(encoding="utf-8"))


class TestExecutionRepositoryCreate:
    def test_persists_bypass_cache_and_source(self, run: Run) -> None:
        from molab.workspace.domain import SourceFile, SourceManifest

        source = SourceManifest(
            entrypoint="wf.py",
            locator="/abs/wf.py",
            files=(SourceFile(name="wf.py", sha256="sha256:" + "b" * 64),),
            captured_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        repo = _run_repo(run)
        repo.create(created_by=_TEST_AGENT, bypass_cache=True, source=source)

        got = repo.get("e01")
        assert got.bypass_cache is True
        assert got.source == source

    def test_raw_schema_version_is_4(self, run: Run) -> None:
        repo = _run_repo(run)
        repo.create(created_by=_TEST_AGENT)
        assert _raw_state(repo, "e01")["schema_version"] == _SCHEMA_V4


class TestExecutionRepositoryStart:
    def test_merges_start_facts_without_overwriting_creation_facts(self, run: Run) -> None:
        repo = _run_repo(run)
        state = repo.create(
            created_by=_TEST_AGENT,
            environment={"script": "a"},
            executor={"backend": "molq"},
        )

        started = repo.start(
            state.id,
            environment={"script": "b", "host": "h"},
            executor={"backend": "x", "pid": 7},
        )

        assert started.environment == {"script": "a", "host": "h"}
        assert started.executor == {"backend": "molq", "pid": 7}
        assert started.status is ExecutionStatus.RUNNING
        assert started.started_at is not None
        assert repo.get(state.id) == started

    def test_records_workflow_digest(self, run: Run) -> None:
        repo = _run_repo(run)
        state = repo.create(created_by=_TEST_AGENT)

        started = repo.start(state.id, workflow_digest="sha256:d")

        assert started.workflow_digest == "sha256:d"
        assert repo.get(state.id).workflow_digest == "sha256:d"

    def test_second_start_raises(self, run: Run) -> None:
        repo = _run_repo(run)
        state = repo.create(created_by=_TEST_AGENT)
        repo.start(state.id)
        first = repo.get(state.id)

        with pytest.raises(ValueError, match="not queued"):
            repo.start(state.id)
        with pytest.raises(ValueError, match="not queued"):
            repo.start(state.id, environment={"k": 1})

        after = repo.get(state.id)
        assert after.started_at == first.started_at
        assert after.environment == first.environment

    def test_concurrent_start_has_one_winner(self, run: Run) -> None:
        repo = _run_repo(run)
        state = repo.create(created_by=_TEST_AGENT)
        barrier = threading.Barrier(2)
        results: list[Execution] = []
        errors: list[BaseException] = []
        guard = threading.Lock()

        def starter() -> None:
            mine = _run_repo(run)
            barrier.wait(timeout=10)
            try:
                started = mine.start(state.id)
            except BaseException as exc:
                with guard:
                    errors.append(exc)
                return
            with guard:
                results.append(started)

        threads = [threading.Thread(target=starter) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        assert not any(thread.is_alive() for thread in threads)

        assert len(results) == 1, f"results={results!r} errors={errors!r}"
        assert results[0].status is ExecutionStatus.RUNNING
        assert len(errors) == 1
        assert isinstance(errors[0], ValueError)

    def test_start_on_sealed_raises(self, run: Run) -> None:
        repo = _run_repo(run)
        state = repo.create(created_by=_TEST_AGENT)
        repo.start(state.id)
        sealed = repo.seal(state.id, ExecutionStatus.SUCCEEDED)

        with pytest.raises(ValueError, match="not queued"):
            repo.start(state.id)
        assert repo.get(state.id) == sealed

    def test_positional_start_still_works(self, run: Run) -> None:
        repo = _run_repo(run)
        repo.create(created_by=_TEST_AGENT)

        started = repo.start("e01")

        assert started.id == "e01"
        assert started.status is ExecutionStatus.RUNNING


class TestExecutionRepositoryUpdateOperational:
    @pytest.mark.parametrize(
        "updates",
        [
            {"bypass_cache": True},
            {"environment": {}},
            {"source": None},
            {"workflow_digest": "x"},
            {"started_at": datetime.now(UTC)},
            {"based_on_execution_id": "e00"},
            {"checkpoint_artifact_id": "a"},
            {"pruned_at": datetime.now(UTC)},
            {"pruned_dirs": ("out",)},
        ],
        ids=lambda updates: next(iter(updates)),
    )
    def test_refuses_identity_or_provenance_field(
        self, run: Run, updates: dict[str, object]
    ) -> None:
        repo = _run_repo(run)
        state = repo.create(created_by=_TEST_AGENT, environment={"script": "a"})
        before = _raw_state(repo, state.id)

        with pytest.raises(ValueError, match="identity or provenance"):
            repo.update_operational(state.id, **updates)

        assert _raw_state(repo, state.id) == before

    def test_executor_stays_mutable(self, run: Run) -> None:
        repo = _run_repo(run)
        state = repo.create(created_by=_TEST_AGENT)

        repo.update_operational(state.id, executor={"job_id": "j1"})

        assert repo.get(state.id).executor == {"job_id": "j1"}

    def test_mark_pruned_writes_schema_version_4(self, run: Run) -> None:
        repo = _run_repo(run)
        state = repo.create(created_by=_TEST_AGENT)
        repo.start(state.id)
        repo.seal(state.id, ExecutionStatus.SUCCEEDED)

        repo.mark_pruned(state.id, ["out"])

        assert _raw_state(repo, state.id)["schema_version"] == _SCHEMA_V4

    def test_immutable_fields_compose_named_sets(self) -> None:
        from molab.workspace.execution_repository import (
            _IDENTITY_FIELDS,
            _IMMUTABLE_FIELDS,
            _POST_SEAL_FIELDS,
            _PROVENANCE_FIELDS,
        )

        assert _POST_SEAL_FIELDS <= _IMMUTABLE_FIELDS
        assert _IMMUTABLE_FIELDS == _IDENTITY_FIELDS | _POST_SEAL_FIELDS | _PROVENANCE_FIELDS


def _write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _legacy_src(tmp_path: Path) -> Path:
    """A legacy attempt dir: state + environment + exception sidecars."""
    src = tmp_path / "old"
    src.mkdir()
    _write(
        src / "execution.json",
        {
            "schema_version": 2,
            "id": "old-exec",
            "run_id": "old-run",
            "project_id": "old-p",
            "mode": "initial",
            "status": "failed",
            "created_at": _LEGACY_CREATED,
            "finished_at": "2026-09-04T22:10:21.113655Z",
            "created_by": _LEGACY_AGENT,
        },
    )
    _write(src / "environment.json", {"schema_version": 2, "environment": {"host": "n226"}})
    _write(src / "exception.json", {"type": "ImportError", "message": "boom"})
    return src


def _legacy_artifact() -> dict[str, object]:
    return {
        "schema_version": 2,
        "id": "a1",
        "execution_id": "old-exec",
        "run_id": "old-run",
        "project_id": "old-p",
        "name": "metrics.jsonl",
        "content": {"digest": "sha256:" + "c" * 64, "size": 9, "kind": "file"},
        "created_at": "2026-09-04T22:10:20.775525Z",
        "created_by": _LEGACY_AGENT,
        "source_path": "work/metrics.jsonl",
    }


def _dst(root: Path) -> Path:
    """The target attempt dir; the CLI has created it (and linked bytes) before folding."""
    dst = root / "runs" / "dp=5" / "executions" / "e01"
    dst.mkdir(parents=True)
    return dst


class TestFoldLegacyAttempt:
    def test_folds_to_current_schema(self, tmp_path: Path) -> None:
        from molab.workspace.execution_repository import (
            fold_legacy_attempt,
        )

        src = _legacy_src(tmp_path)
        root = tmp_path / "lab"
        dst = _dst(root)
        _write(dst / "artifacts" / "metrics.jsonl", {"loss": 1})

        ex = fold_legacy_attempt(
            src,
            dst,
            workspace_root=root,
            seq=1,
            run_id="r1",
            project_id="p1",
            artifacts=[(_legacy_artifact(), "artifacts/metrics.jsonl")],
        )

        raw = json.loads((dst / "execution.json").read_text(encoding="utf-8"))
        assert raw["schema_version"] == MOLAB_SCHEMA_VERSION == _SCHEMA_V4
        assert Execution.model_validate(read_versioned_json(dst / "execution.json")) == ex

        # hard-coded golden: HEAD 56d5b466 cli/migrate_cmd.py fold rules
        assert (ex.id, ex.seq, ex.run_id, ex.project_id) == ("e01", 1, "r1", "p1")
        assert ex.mode is ExecutionMode.INITIAL
        assert ex.status is ExecutionStatus.FAILED
        created = datetime(2026, 9, 4, 22, 9, 31, 925482, tzinfo=UTC)
        finished = datetime(2026, 9, 4, 22, 10, 21, 113655, tzinfo=UTC)
        assert ex.created_at == ex.started_at == created
        assert ex.sealed_at == ex.finished_at == finished
        assert ex.environment == {"host": "n226"}
        assert ex.error == {"type": "ImportError", "message": "boom"}
        assert ex.executor == {}
        assert ex.based_on_execution_id is None

        assert len(ex.artifacts) == 1
        art = ex.artifacts[0]
        # arch-own-05b changes this to "artifacts/metrics.jsonl".
        assert art.path == "runs/dp=5/executions/e01/artifacts/metrics.jsonl"
        assert art.execution_id == "e01"
        assert art.run_id == "r1"
        assert art.project_id == "p1"
        assert art.source_path == "work/metrics.jsonl"

    def test_missing_state_is_interrupted(self, tmp_path: Path) -> None:
        from molab.workspace.execution_repository import (
            fold_legacy_attempt,
        )

        src = tmp_path / "old"
        src.mkdir()
        root = tmp_path / "lab"
        dst = _dst(root)

        ex = fold_legacy_attempt(src, dst, workspace_root=root, seq=2, run_id="r1", project_id="p1")

        assert ex.status is ExecutionStatus.INTERRUPTED
        assert ex.mode is ExecutionMode.RERUN
        assert ex.sealed_at is None
        assert ex.based_on_execution_id is None
        assert ex.artifacts == ()
        raw = json.loads((dst / "execution.json").read_text(encoding="utf-8"))
        assert raw["schema_version"] == _SCHEMA_V4

    def test_rejected_record_writes_nothing(self, tmp_path: Path) -> None:
        from molab.workspace.execution_repository import (
            fold_legacy_attempt,
        )

        src = _legacy_src(tmp_path)
        state = json.loads((src / "execution.json").read_text(encoding="utf-8"))
        state["status"] = "exploded"
        _write(src / "execution.json", state)
        root = tmp_path / "lab"
        dst = _dst(root)

        with pytest.raises(pydantic.ValidationError):
            fold_legacy_attempt(src, dst, workspace_root=root, seq=1, run_id="r1", project_id="p1")

        assert (dst / "execution.json").exists() is False


class TestLegacyAttemptCreatedAt:
    def test_reads_legacy_created_at(self, tmp_path: Path) -> None:
        from molab.workspace.execution_repository import (
            legacy_attempt_created_at,
        )

        src = _legacy_src(tmp_path)
        assert legacy_attempt_created_at(src) == _LEGACY_CREATED

    def test_empty_dir_is_empty_string(self, tmp_path: Path) -> None:
        from molab.workspace.execution_repository import (
            legacy_attempt_created_at,
        )

        empty = tmp_path / "empty"
        empty.mkdir()
        assert legacy_attempt_created_at(empty) == ""


# ── arch-own-02a-record review fixes ─────────────────────────────────────
#
# ``start`` is the only way into RUNNING and the only writer of start-time
# provenance; ``update_operational`` writes ``executor`` and nothing else.


class TestExecutionRepositoryTransition:
    def test_transition_to_running_raises(self, run: Run) -> None:
        repo = _run_repo(run)
        state = repo.create(created_by=_TEST_AGENT)
        before = _raw_state(repo, state.id)

        with pytest.raises(ValueError, match=r"start\(\)"):
            repo.transition(state.id, ExecutionStatus.RUNNING)

        assert _raw_state(repo, state.id) == before

    @pytest.mark.parametrize(
        "updates",
        [
            {"environment": {}},
            {"source": None},
            {"bypass_cache": True},
            {"workflow_digest": "x"},
            {"started_at": _FIXED_TIME},
            {"id": "e99"},
            {"created_by": _TEST_AGENT},
        ],
        ids=lambda updates: next(iter(updates)),
    )
    def test_transition_refuses_identity_or_provenance_update(
        self, run: Run, updates: dict[str, object]
    ) -> None:
        repo = _run_repo(run)
        state = repo.create(created_by=_TEST_AGENT, environment={"script": "a"})
        repo.start(state.id)
        before = _raw_state(repo, state.id)

        with pytest.raises(ValueError, match=next(iter(updates))):
            repo.transition(state.id, ExecutionStatus.FINALIZING, **updates)

        assert _raw_state(repo, state.id) == before


class TestUpdateOperationalAllowList:
    @pytest.mark.parametrize(
        "updates",
        [
            {"status": "running"},
            {"sealed_at": _FIXED_TIME},
            {"sealed_commit": "abc"},
            {"finished_at": _FIXED_TIME},
            {"error": {"type": "X"}},
            {"evidence": ()},
            {"artifacts": ()},
            {"observed_input_ids": ("x",)},
            {"declaration_diff": {}},
        ],
        ids=lambda updates: next(iter(updates)),
    )
    def test_refuses_lifecycle_field(self, run: Run, updates: dict[str, object]) -> None:
        repo = _run_repo(run)
        state = repo.create(created_by=_TEST_AGENT)
        before = _raw_state(repo, state.id)

        with pytest.raises(ValueError, match="only updates executor"):
            repo.update_operational(state.id, **updates)

        assert _raw_state(repo, state.id) == before


class TestFoldLegacyAttemptReview:
    def test_non_dict_state_folds_as_missing(self, tmp_path: Path) -> None:
        from molab.workspace.execution_repository import fold_legacy_attempt

        src = tmp_path / "old"
        src.mkdir()
        (src / "execution.json").write_text("[]", encoding="utf-8")
        root = tmp_path / "lab"
        dst = _dst(root)

        ex = fold_legacy_attempt(src, dst, workspace_root=root, seq=1, run_id="r1", project_id="p1")

        assert ex.status is ExecutionStatus.INTERRUPTED
        assert ex.sealed_at is None

    def test_accepts_filesystem(self, tmp_path: Path) -> None:
        from molab.workspace.execution_repository import fold_legacy_attempt
        from molab.workspace.fs_local import LocalFileSystem

        src = _legacy_src(tmp_path)
        root = tmp_path / "lab"
        dst = _dst(root)

        ex = fold_legacy_attempt(
            src,
            dst,
            workspace_root=root,
            seq=1,
            run_id="r1",
            project_id="p1",
            fs=LocalFileSystem(),
        )

        assert ex.status is ExecutionStatus.FAILED
        assert (dst / "execution.json").is_file()
