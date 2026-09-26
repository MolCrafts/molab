"""Execution creation, operational state, and sealing.

One attempt is one directory — ``executions/e01``, ``executions/e02`` — and
one file inside it, ``execution.json``, holds the whole attempt: status,
executor, environment, emitted artifacts, evidence, error, and (once
terminal) the seal. Nothing about an attempt is stored anywhere else.

Lock order. Every read-modify-write of ``execution.json`` holds the
per-execution *state* lock. ``seal`` additionally holds the per-execution
*seal* lock, and always takes it first: seal -> state, never the reverse. No
code path holds the state lock and then asks for the seal lock. Locks are
``file_lock`` (flock / O_EXCL) and are not reentrant, so code already holding
the state lock calls the lock-free ``_transition_locked`` kernel instead of
``transition``. History (``_record``) runs outside the state lock, so git never
blocks a writer of the record.

Sealed records are immutable. *Sealing* is how a finished attempt is frozen:
it is two writes. ``seal`` sets ``sealed_at`` and the terminal fields, then,
once history has committed, stamps ``sealed_commit`` exactly once, still under
the seal lock. After that there is one exception, ``_POST_SEAL_FIELDS``: the
prune stamp ``pruned_at`` / ``pruned_dirs``, written only by ``mark_pruned``.
Every other field is never rewritten after ``sealed_at``. *Pruning* deletes a
sealed attempt's bulk directories (reproducible bytes such as ``out/``) to
free disk space while keeping its record. The stamp is how the record says
which directories are gone. ``mark_pruned`` takes only the state lock. It
never needs the seal lock, because it refuses an unsealed record, and a
sealed record cannot be sealed again.
"""

from __future__ import annotations

import builtins
import hashlib
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from molab._typing import JSONValue

from ._file_lock import file_lock
from .artifact_repository import ArtifactRepository
from .domain import (
    ACTIVE_EXECUTION_STATUSES,
    TERMINAL_EXECUTION_STATUSES,
    Artifact,
    EvidenceRef,
    Execution,
    ExecutionMode,
    ExecutionStatus,
    RunStatusSummary,
)
from .execution_dirs import prunable_dirs
from .fs import FileSystem, PathArg
from .fs_local import LocalFileSystem
from .history import AgentRef, EntityRef, GitHistory, Relation
from .naming import execution_slug
from .schema_version import read_versioned_json, write_versioned_json

_ALLOWED_TRANSITIONS: dict[ExecutionStatus, frozenset[ExecutionStatus]] = {
    ExecutionStatus.QUEUED: frozenset(
        {
            ExecutionStatus.RUNNING,
            ExecutionStatus.FAILED,
            ExecutionStatus.CANCELLED,
            ExecutionStatus.INTERRUPTED,
        }
    ),
    ExecutionStatus.RUNNING: frozenset(
        {
            ExecutionStatus.FINALIZING,
            ExecutionStatus.CANCELLED,
            ExecutionStatus.INTERRUPTED,
        }
    ),
    ExecutionStatus.FINALIZING: TERMINAL_EXECUTION_STATUSES,
    ExecutionStatus.SUCCEEDED: frozenset(),
    ExecutionStatus.FAILED: frozenset(),
    ExecutionStatus.CANCELLED: frozenset(),
    ExecutionStatus.INTERRUPTED: frozenset(),
}

_POST_SEAL_FIELDS: frozenset[str] = frozenset({"pruned_at", "pruned_dirs"})
"""Fields of a sealed Execution that may still be written.

The prune stamp is the single named exception to "sealed means immutable".
``mark_pruned`` is the only writer of these keys, and it writes nothing else.
``transition`` and ``update_operational`` both raise ``ValueError`` when an
update names one of them, so the keys are never set on an open attempt.
"""

_EVIDENCE_FILES = {
    "runtime": "run.log",
    "workflow": "workflow.json",
    "results": "results.json",
}


class ExecutionRepository:
    """Own each Execution independently; never mutates Run history."""

    def __init__(
        self,
        workspace_root: PathArg,
        run_dir: PathArg,
        *,
        run_id: str,
        project_id: str,
        fs: FileSystem | None = None,
        history: GitHistory | None = None,
        artifacts: ArtifactRepository | None = None,
    ) -> None:
        self.workspace_root = str(workspace_root)
        self.run_dir = str(run_dir)
        self.run_id = run_id
        self.project_id = project_id
        self.fs = fs or LocalFileSystem()
        self.history = history or GitHistory(self.workspace_root)
        self.artifacts = artifacts or ArtifactRepository(
            self.workspace_root, fs=self.fs, history=self.history
        )

    # ── layout ───────────────────────────────────────────────────────────

    @property
    def executions_dir(self) -> str:
        return self.fs.join(self.run_dir, "executions")

    def execution_dir(self, execution_id: str) -> str:
        """An attempt's directory. Its id *is* its directory name (``e01``)."""
        return self.fs.join(self.executions_dir, execution_id)

    def state_path(self, execution_id: str) -> str:
        return self.fs.join(self.execution_dir(execution_id), "execution.json")

    # ── create ───────────────────────────────────────────────────────────

    def create(
        self,
        *,
        mode: ExecutionMode = ExecutionMode.INITIAL,
        created_by: AgentRef,
        execution_id: str | None = None,
        based_on_execution_id: str | None = None,
        checkpoint_artifact_id: str | None = None,
        executor: dict[str, JSONValue] | None = None,
        environment: dict[str, JSONValue] | None = None,
    ) -> Execution:
        """Allocate the next attempt after validating retry/resume semantics."""
        self.fs.mkdir(self.executions_dir, parents=True, exist_ok=True)
        with file_lock(self._create_lock()):
            prior = self.list()
            predecessor = self._validate_creation(
                mode,
                prior,
                based_on_execution_id=based_on_execution_id,
                checkpoint_artifact_id=checkpoint_artifact_id,
            )
            now = datetime.now(UTC)
            seq = max((item.seq for item in prior), default=0) + 1
            state = Execution(
                id=execution_id or execution_slug(seq),
                seq=seq,
                run_id=self.run_id,
                project_id=self.project_id,
                mode=mode,
                status=ExecutionStatus.QUEUED,
                created_at=now,
                created_by=created_by,
                based_on_execution_id=predecessor.id if predecessor else None,
                checkpoint_artifact_id=checkpoint_artifact_id,
                executor=executor or {},
                environment=environment or {},
            )
            if self.fs.exists(self.state_path(state.id)):
                raise FileExistsError(f"Execution {state.id!r} already exists")
            self._write_state(state)
            self._record("ExecutionCreated", state, when=now)
            return state

    # ── read ─────────────────────────────────────────────────────────────

    def get(self, execution_id: str) -> Execution:
        path = self.state_path(execution_id)
        if not self.fs.exists(path):
            raise KeyError(f"Execution {execution_id!r} not found under Run {self.run_id!r}")
        state = Execution.model_validate(read_versioned_json(path, fs=self.fs))
        if state.run_id != self.run_id:
            raise ValueError(f"Execution {execution_id!r} belongs to another Run")
        return state

    def list(self) -> builtins.list[Execution]:
        if not self.fs.exists(self.executions_dir):
            return []
        states = [
            Execution.model_validate(read_versioned_json(path, fs=self.fs))
            for path in sorted(self.fs.glob(self.executions_dir, "*/execution.json"))
        ]
        return sorted(states, key=lambda item: item.seq)

    def summary(self) -> RunStatusSummary:
        return RunStatusSummary.from_executions(self.list())

    def record(self, execution_id: str) -> Execution | None:
        """Return the attempt once sealed; ``None`` while it is still open."""
        state = self.get(execution_id)
        return state if state.sealed else None

    # ── transition ───────────────────────────────────────────────────────

    def start(self, execution_id: str) -> Execution:
        current = self.get(execution_id)
        started = self.transition(
            execution_id,
            ExecutionStatus.RUNNING,
            started_at=current.started_at or datetime.now(UTC),
        )
        self._record("ExecutionStarted", started, when=started.started_at)
        return started

    def transition(
        self,
        execution_id: str,
        status: ExecutionStatus,
        **updates: object,
    ) -> Execution:
        """Move the attempt to ``status`` under its state lock.

        Args:
            execution_id: The attempt to move (``e01``).
            status: The target status; must be allowed from the current one.
            **updates: Extra fields written in the same record update.

        Returns:
            The record as written (unchanged when already in ``status``).

        Raises:
            ValueError: The transition is not allowed, or ``updates`` names a
                post-seal field.
        """
        with file_lock(self._state_lock(execution_id)):
            return self._transition_locked(execution_id, status, **updates)

    def _transition_locked(
        self,
        execution_id: str,
        status: ExecutionStatus,
        **updates: object,
    ) -> Execution:
        """Lock-free transition kernel; the caller must hold the state lock.

        Args:
            execution_id: The attempt to move (``e01``).
            status: The target status; must be allowed from the current one.
            **updates: Extra fields written in the same record update.

        Returns:
            The record as written (unchanged when already in ``status``).

        Raises:
            ValueError: The transition is not allowed, or ``updates`` names a
                post-seal field (only ``mark_pruned`` writes those).
        """
        post_seal = _POST_SEAL_FIELDS.intersection(updates)
        if post_seal:
            raise ValueError(f"cannot write post-seal fields in a transition: {sorted(post_seal)}")
        current = self.get(execution_id)
        if status == current.status:
            return current
        if status not in _ALLOWED_TRANSITIONS[current.status]:
            raise ValueError(
                f"invalid Execution transition: {current.status.value} -> {status.value}"
            )
        state = current.model_copy(update={"status": status, **updates})
        self._write_state(state)
        return state

    def add_observed_inputs(self, execution_id: str, entity_ids: tuple[str, ...]) -> Execution:
        with file_lock(self._state_lock(execution_id)):
            current = self.get(execution_id)
            if current.sealed:
                raise ValueError(f"Execution {execution_id!r} is sealed")
            merged = tuple(dict.fromkeys((*current.observed_input_ids, *entity_ids)))
            state = current.model_copy(update={"observed_input_ids": merged})
            self._write_state(state)
            return state

    def add_artifact(self, execution_id: str, artifact: Artifact) -> Execution:
        """Attach an emitted product to the attempt that produced it."""
        with file_lock(self._state_lock(execution_id)):
            current = self.get(execution_id)
            if current.sealed:
                raise ValueError(f"Execution {execution_id!r} is sealed")
            kept = tuple(item for item in current.artifacts if item.id != artifact.id)
            state = current.model_copy(update={"artifacts": (*kept, artifact)})
            self._write_state(state)
            return state

    def update_operational(self, execution_id: str, **updates: object) -> Execution:
        """Update unsealed operational fields without touching identity."""
        with file_lock(self._state_lock(execution_id)):
            current = self.get(execution_id)
            if current.sealed:
                raise ValueError(f"Execution {execution_id!r} is sealed")
            forbidden = {
                "id",
                "seq",
                "run_id",
                "project_id",
                "mode",
                "created_at",
                "created_by",
                *_POST_SEAL_FIELDS,
            }
            overlap = forbidden.intersection(updates)
            if overlap:
                raise ValueError(
                    f"cannot update Execution identity or post-seal fields: {sorted(overlap)}"
                )
            state = current.model_copy(update=updates)
            self._write_state(state)
            return state

    # ── seal ─────────────────────────────────────────────────────────────

    def seal(
        self,
        execution_id: str,
        status: ExecutionStatus,
        *,
        error: dict[str, JSONValue] | None = None,
        declaration_diff: dict[str, JSONValue] | None = None,
    ) -> Execution:
        """Freeze the attempt in place, then record the fact in history.

        Takes the seal lock, then the state lock (fixed order), so the
        read-modify-write of the record cannot interleave with
        ``add_artifact`` / ``add_observed_inputs`` / ``update_operational``:
        a racing writer either lands before the seal reads the record, or is
        refused afterwards because the record is sealed. History is recorded
        after the state lock is released; the ``sealed_commit`` stamp re-takes
        it and applies to a fresh read of the record.
        """
        with file_lock(self._seal_lock(execution_id)):
            with file_lock(self._state_lock(execution_id)):
                sealed, newly_sealed = self._seal_locked(
                    execution_id,
                    status,
                    error=error,
                    declaration_diff=declaration_diff,
                )
            if not newly_sealed:
                return sealed
            commit = self._record("ExecutionSealed", sealed, when=sealed.sealed_at)
            if commit is None:
                return sealed
            with file_lock(self._state_lock(execution_id)):
                latest = self.get(execution_id)
                stamped = latest.model_copy(update={"sealed_commit": commit})
                self._write_state(stamped)
            return stamped

    def _seal_locked(
        self,
        execution_id: str,
        status: ExecutionStatus,
        *,
        error: dict[str, JSONValue] | None = None,
        declaration_diff: dict[str, JSONValue] | None = None,
    ) -> tuple[Execution, bool]:
        """Seal kernel; the caller must hold the seal lock and the state lock.

        Returns:
            The sealed record, and whether this call sealed it (``False`` when
            it was already sealed).
        """
        if status not in TERMINAL_EXECUTION_STATUSES:
            raise ValueError(f"cannot seal non-terminal status {status.value!r}")
        current = self.get(execution_id)
        if current.sealed:
            return current, False
        if current.status is ExecutionStatus.QUEUED and status in {
            ExecutionStatus.FAILED,
            ExecutionStatus.CANCELLED,
            ExecutionStatus.INTERRUPTED,
        }:
            finalizing = current
        elif current.status is ExecutionStatus.RUNNING:
            finalizing = self._transition_locked(execution_id, ExecutionStatus.FINALIZING)
        elif current.status is ExecutionStatus.FINALIZING:
            finalizing = current
        else:
            raise ValueError(f"cannot seal Execution in status {current.status.value!r}")

        finished_at = datetime.now(UTC)
        sealed = finalizing.model_copy(
            update={
                "status": status,
                "started_at": finalizing.started_at or finalizing.created_at,
                "finished_at": finished_at,
                "evidence": tuple(self._collect_evidence(execution_id)),
                "declaration_diff": declaration_diff or {},
                "error": error,
                "sealed_at": finished_at,
            }
        )
        self._write_state(sealed)
        return sealed, True

    # ── post-seal ────────────────────────────────────────────────────────

    def mark_pruned(self, execution_id: str, dirs: Iterable[str]) -> Execution:
        """Stamp a sealed attempt with the bulk directories pruned from it.

        This method only records the prune. It deletes nothing, and the caller
        (``molab.workspace.prune.apply_execution_prune``) removes the bytes.
        It writes only ``_POST_SEAL_FIELDS``, under the state lock:
        ``pruned_dirs`` becomes the sorted union of its previous value and
        ``dirs``, and ``pruned_at`` becomes the current UTC time. Every other
        field of the sealed record is left untouched. Once the record is
        written, an ``ExecutionPruned`` fact is recorded in the workspace's git
        history, outside the lock.

        Args:
            execution_id: The sealed attempt (``e01``).
            dirs: Names of the execution directories that were removed. Each
                must be the name of a directory declared ``prunable`` (see
                ``molab.workspace.execution_dirs.prunable_dirs``).

        Returns:
            The record as written.

        Raises:
            ValueError: A name in ``dirs`` is not a prunable execution
                directory (checked first, before the record is read), or the
                attempt is not sealed.
            KeyError: No attempt ``execution_id`` exists under this Run.
        """
        dirs = tuple(dirs)
        allowed = {d.name for d in prunable_dirs()}
        refused = sorted(set(dirs) - allowed)
        if refused:
            raise ValueError(
                f"not prunable execution dir(s) {refused!r}; prunable: {sorted(allowed)}"
            )
        with file_lock(self._state_lock(execution_id)):
            current = self.get(execution_id)
            if not current.sealed:
                raise ValueError(
                    f"Execution {execution_id!r} is not sealed; only a sealed attempt is pruned"
                )
            update: dict[str, object] = {
                "pruned_dirs": tuple(sorted(set(current.pruned_dirs) | set(dirs))),
                "pruned_at": datetime.now(UTC),
            }
            state = current.model_copy(update=update)
            self._write_state(state)
        self._record("ExecutionPruned", state, when=state.pruned_at)
        return state

    # ── internals ────────────────────────────────────────────────────────

    def _create_lock(self) -> Path:
        return self._lock_dir() / f"{self.run_id}.create.lock"

    def _state_lock(self, execution_id: str) -> Path:
        return self._lock_dir() / f"{self.run_id}.{execution_id}.state.lock"

    def _seal_lock(self, execution_id: str) -> Path:
        return self._lock_dir() / f"{self.run_id}.{execution_id}.seal.lock"

    def _lock_dir(self) -> Path:
        path = Path(self.workspace_root) / ".molab" / "locks"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _record(self, event: str, state: Execution, *, when: datetime | None) -> str | None:
        relations = [
            Relation(predicate="realizationOf", object=EntityRef(id=state.run_id, type="run"))
        ]
        if state.based_on_execution_id:
            relations.append(
                Relation(
                    predicate="wasInformedBy",
                    object=EntityRef(
                        id=f"{state.run_id}:{state.based_on_execution_id}", type="execution"
                    ),
                )
            )
        if state.checkpoint_artifact_id:
            relations.append(
                Relation(
                    predicate="used",
                    object=EntityRef(id=state.checkpoint_artifact_id, type="artifact"),
                )
            )
        relations.extend(
            Relation(predicate="generated", object=EntityRef(id=artifact.id, type="artifact"))
            for artifact in state.artifacts
        )
        run_name = self.fs.basename(self.run_dir)
        return self.history.record(
            event,
            subject=EntityRef(id=f"{state.run_id}:{state.id}", type="execution"),
            agent=state.created_by,
            relations=tuple(relations),
            summary=f"{run_name} {state.id} {state.status.value}",
            paths=(self.run_dir,),
            occurred_at=when,
        )

    def _validate_creation(
        self,
        mode: ExecutionMode,
        prior: builtins.list[Execution],
        *,
        based_on_execution_id: str | None,
        checkpoint_artifact_id: str | None,
    ) -> Execution | None:
        by_id = {item.id: item for item in prior}
        if mode is ExecutionMode.INITIAL:
            if prior:
                raise ValueError("initial Execution is only valid before any attempt exists")
            if based_on_execution_id or checkpoint_artifact_id:
                raise ValueError("initial Execution cannot have a predecessor or checkpoint")
            return None
        if based_on_execution_id is None:
            if mode is ExecutionMode.RERUN:
                return None
            raise ValueError(f"{mode.value} Execution requires based_on_execution_id")
        predecessor = by_id.get(based_on_execution_id)
        if predecessor is None:
            raise KeyError(f"predecessor Execution {based_on_execution_id!r} not found")
        if predecessor.status in ACTIVE_EXECUTION_STATUSES:
            raise ValueError("an active Execution cannot be used as a predecessor")
        if mode is ExecutionMode.RETRY and predecessor.status not in {
            ExecutionStatus.FAILED,
            ExecutionStatus.CANCELLED,
            ExecutionStatus.INTERRUPTED,
        }:
            raise ValueError("retry requires a failed, cancelled, or interrupted predecessor")
        if mode is ExecutionMode.RESUME:
            if checkpoint_artifact_id is None:
                raise ValueError("resume requires checkpoint_artifact_id")
            predecessor.artifact(checkpoint_artifact_id)
        elif checkpoint_artifact_id is not None:
            raise ValueError("checkpoint_artifact_id is only valid for resume")
        if mode is ExecutionMode.REPRODUCE and predecessor.status is not ExecutionStatus.SUCCEEDED:
            raise ValueError("reproduce requires a succeeded predecessor")
        return predecessor

    def _collect_evidence(self, execution_id: str) -> builtins.list[EvidenceRef]:
        execution_dir = self.execution_dir(execution_id)
        result: list[EvidenceRef] = []
        for kind, rel_path in _EVIDENCE_FILES.items():
            path = self.fs.join(execution_dir, rel_path)
            if not self.fs.is_file(path):
                continue
            hasher = hashlib.sha256()
            size = 0
            with self.fs.open(path, "rb") as handle:
                while chunk := handle.read(1024 * 1024):
                    hasher.update(chunk)
                    size += len(chunk)
            result.append(
                EvidenceRef(
                    kind=kind,
                    rel_path=rel_path,
                    digest=f"sha256:{hasher.hexdigest()}",
                    size=size,
                )
            )
        return result

    def _write_state(self, state: Execution) -> None:
        path = self.state_path(state.id)
        self.fs.mkdir(self.fs.dirname(path), parents=True, exist_ok=True)
        write_versioned_json(path, state.model_dump(mode="json"), fs=self.fs)


__all__ = ["ExecutionRepository"]
