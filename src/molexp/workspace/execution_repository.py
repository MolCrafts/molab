"""Execution creation, operational state, and immutable sealing."""

from __future__ import annotations

import builtins
import hashlib
from datetime import UTC, datetime
from pathlib import Path

from molexp._typing import JSONValue
from molexp.ids import generate_uuid7

from ._file_lock import file_lock
from .artifact_repository import ArtifactRepository
from .domain import (
    ACTIVE_EXECUTION_STATUSES,
    TERMINAL_EXECUTION_STATUSES,
    EvidenceRef,
    ExecutionMode,
    ExecutionRecord,
    ExecutionState,
    ExecutionStatus,
    RunStatusSummary,
)
from .fs import FileSystem, PathArg
from .fs_local import LocalFileSystem
from .index_store import JsonIndexStore
from .provenance import (
    AgentRef,
    EntityRef,
    ProvenanceRelation,
    ProvenanceStore,
    create_event,
)
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
        provenance: ProvenanceStore | None = None,
        index: JsonIndexStore | None = None,
        artifacts: ArtifactRepository | None = None,
    ) -> None:
        self.workspace_root = str(workspace_root)
        self.run_dir = str(run_dir)
        self.run_id = run_id
        self.project_id = project_id
        self.fs = fs or LocalFileSystem()
        self.provenance = provenance or ProvenanceStore(self.workspace_root, fs=self.fs)
        self.index = index or JsonIndexStore(self.workspace_root, fs=self.fs)
        self.artifacts = artifacts or ArtifactRepository(
            self.workspace_root,
            fs=self.fs,
            provenance=self.provenance,
            index=self.index,
        )

    @property
    def executions_dir(self) -> str:
        return self.fs.join(self.run_dir, "executions")

    def execution_dir(self, execution_id: str) -> str:
        return self.fs.join(self.executions_dir, execution_id)

    def state_path(self, execution_id: str) -> str:
        return self.fs.join(self.execution_dir(execution_id), "execution.json")

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
    ) -> ExecutionState:
        """Allocate a new attempt after validating retry/resume semantics."""
        self.fs.mkdir(self.executions_dir, parents=True, exist_ok=True)
        lock_path = Path(self.executions_dir) / ".create.lock"
        with file_lock(lock_path):
            prior = self.list()
            predecessor = self._validate_creation(
                mode,
                prior,
                based_on_execution_id=based_on_execution_id,
                checkpoint_artifact_id=checkpoint_artifact_id,
            )
            now = datetime.now(UTC)
            state = ExecutionState(
                id=execution_id or generate_uuid7(),
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
            event = create_event(
                "ExecutionCreated",
                subject=EntityRef(id=state.id, type="execution"),
                agent=created_by,
                relations=self._relations(state),
                attributes={"record": state.model_dump(mode="json")},
                occurred_at=now,
            )
            self.provenance.append(event)
            self.index.index_event(event)
            return state

    def get(self, execution_id: str) -> ExecutionState:
        path = self.state_path(execution_id)
        if not self.fs.exists(path):
            raise KeyError(f"Execution {execution_id!r} not found under Run {self.run_id!r}")
        state = ExecutionState.model_validate(read_versioned_json(path, fs=self.fs))
        if state.run_id != self.run_id:
            raise ValueError(f"Execution {execution_id!r} belongs to another Run")
        return state

    def list(self) -> builtins.list[ExecutionState]:
        if not self.fs.exists(self.executions_dir):
            return []
        states: list[ExecutionState] = []
        for path in sorted(self.fs.glob(self.executions_dir, "*/execution.json")):
            states.append(ExecutionState.model_validate(read_versioned_json(path, fs=self.fs)))
        return sorted(states, key=lambda item: (item.created_at, item.id))

    def summary(self) -> RunStatusSummary:
        return RunStatusSummary.from_executions(self.list())

    def record(self, execution_id: str) -> ExecutionRecord | None:
        """Return the immutable sealed record without mutating operational state."""
        state = self.get(execution_id)
        if state.sealed_event_id is None:
            return None
        for event in reversed(self.provenance.events_for(execution_id)):
            if event.event_type != "ExecutionSealed" or event.subject.id != execution_id:
                continue
            raw = event.attributes.get("record")
            if not isinstance(raw, dict):
                raise RuntimeError(f"sealed Execution {execution_id!r} has no canonical record")
            return ExecutionRecord.model_validate(raw)
        # The index is disposable, but rebuilding it is a useful corruption
        # diagnostic when the operational view claims a seal event is missing.
        self.index.rebuild(self.provenance)
        raw = self.index.get_entity("execution", execution_id)
        if raw is None:
            raise RuntimeError(f"sealed Execution {execution_id!r} has no canonical record")
        return ExecutionRecord.model_validate(raw)

    def start(self, execution_id: str) -> ExecutionState:
        current = self.get(execution_id)
        started = self.transition(
            execution_id,
            ExecutionStatus.RUNNING,
            started_at=current.started_at or datetime.now(UTC),
        )
        event = create_event(
            "ExecutionStarted",
            subject=EntityRef(id=started.id, type="execution"),
            agent=started.created_by,
            relations=self._relations(started),
            attributes={"record": started.model_dump(mode="json")},
            occurred_at=started.started_at,
        )
        self.provenance.append(event)
        self.index.index_event(event)
        return started

    def transition(
        self,
        execution_id: str,
        status: ExecutionStatus,
        **updates: object,
    ) -> ExecutionState:
        path = self.state_path(execution_id)
        with file_lock(Path(path + ".lock")):
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

    def add_observed_inputs(self, execution_id: str, entity_ids: tuple[str, ...]) -> ExecutionState:
        path = self.state_path(execution_id)
        with file_lock(Path(path + ".lock")):
            current = self.get(execution_id)
            if current.sealed_event_id is not None:
                raise ValueError(f"Execution {execution_id!r} is sealed")
            merged = tuple(dict.fromkeys((*current.observed_input_ids, *entity_ids)))
            state = current.model_copy(update={"observed_input_ids": merged})
            self._write_state(state)
            return state

    def update_operational(self, execution_id: str, **updates: object) -> ExecutionState:
        """Update unsealed operational fields without creating provenance truth."""
        path = self.state_path(execution_id)
        with file_lock(Path(path + ".lock")):
            current = self.get(execution_id)
            if current.sealed_event_id is not None:
                raise ValueError(f"Execution {execution_id!r} is sealed")
            forbidden = {"id", "run_id", "project_id", "mode", "created_at", "created_by"}
            overlap = forbidden.intersection(updates)
            if overlap:
                raise ValueError(f"cannot update Execution identity fields: {sorted(overlap)}")
            state = current.model_copy(update=updates)
            self._write_state(state)
            return state

    def seal(
        self,
        execution_id: str,
        status: ExecutionStatus,
        *,
        error: dict[str, JSONValue] | None = None,
        declaration_diff: dict[str, JSONValue] | None = None,
    ) -> ExecutionRecord:
        """Commit an immutable terminal fact, then materialize sealed state."""
        with file_lock(Path(self.state_path(execution_id) + ".seal.lock")):
            return self._seal_locked(
                execution_id,
                status,
                error=error,
                declaration_diff=declaration_diff,
            )

    def _seal_locked(
        self,
        execution_id: str,
        status: ExecutionStatus,
        *,
        error: dict[str, JSONValue] | None = None,
        declaration_diff: dict[str, JSONValue] | None = None,
    ) -> ExecutionRecord:
        if status not in TERMINAL_EXECUTION_STATUSES:
            raise ValueError(f"cannot seal non-terminal status {status.value!r}")
        current = self.get(execution_id)
        sealed_events = [
            event
            for event in self.provenance.events_for(execution_id)
            if event.event_type == "ExecutionSealed" and event.subject.id == execution_id
        ]
        if sealed_events:
            sealed_event = sealed_events[-1]
            raw = sealed_event.attributes.get("record")
            if not isinstance(raw, dict):
                raise RuntimeError(f"sealed Execution {execution_id!r} has no canonical record")
            record = ExecutionRecord.model_validate(raw)
            if current.sealed_event_id is None:
                self._write_state(
                    current.model_copy(
                        update={
                            "status": record.status,
                            "finished_at": record.finished_at,
                            "artifact_ids": record.artifact_ids,
                            "error": record.error,
                            "sealed_event_id": sealed_event.event_id,
                        }
                    )
                )
            return record
        if current.sealed_event_id is not None:
            raw = self.index.get_entity("execution", execution_id)
            if raw is None:
                self.index.rebuild(self.provenance)
                raw = self.index.get_entity("execution", execution_id)
            if raw is None:
                raise RuntimeError(f"sealed Execution {execution_id!r} has no canonical record")
            return ExecutionRecord.model_validate(raw)
        if current.status is ExecutionStatus.QUEUED and status in {
            ExecutionStatus.FAILED,
            ExecutionStatus.CANCELLED,
            ExecutionStatus.INTERRUPTED,
        }:
            finalizing = current
        elif current.status is ExecutionStatus.RUNNING:
            finalizing = self.transition(execution_id, ExecutionStatus.FINALIZING)
        elif current.status is ExecutionStatus.FINALIZING:
            finalizing = current
        else:
            raise ValueError(f"cannot seal Execution in status {current.status.value!r}")

        finished_at = datetime.now(UTC)
        artifacts = self.artifacts.list_for_execution(execution_id)
        evidence = tuple(self._collect_evidence(execution_id))
        record = ExecutionRecord(
            id=finalizing.id,
            run_id=finalizing.run_id,
            project_id=finalizing.project_id,
            mode=finalizing.mode,
            status=status,
            created_at=finalizing.created_at,
            started_at=finalizing.started_at or finalizing.created_at,
            finished_at=finished_at,
            created_by=finalizing.created_by,
            based_on_execution_id=finalizing.based_on_execution_id,
            checkpoint_artifact_id=finalizing.checkpoint_artifact_id,
            executor=finalizing.executor,
            environment=finalizing.environment,
            observed_input_ids=finalizing.observed_input_ids,
            artifact_ids=tuple(artifact.id for artifact in artifacts),
            evidence=evidence,
            declaration_diff=declaration_diff or {},
            error=error,
        )
        event = create_event(
            "ExecutionSealed",
            subject=EntityRef(id=record.id, type="execution"),
            agent=record.created_by,
            relations=self._relations(finalizing),
            attributes={"record": record.model_dump(mode="json")},
            occurred_at=finished_at,
        )
        # The event is the commit point. The operational file is only a view.
        self.provenance.append(event)
        self.index.index_event(event)
        sealed = finalizing.model_copy(
            update={
                "status": status,
                "finished_at": finished_at,
                "artifact_ids": record.artifact_ids,
                "error": error,
                "sealed_event_id": event.event_id,
            }
        )
        self._write_state(sealed)
        return record

    def _validate_creation(
        self,
        mode: ExecutionMode,
        prior: builtins.list[ExecutionState],
        *,
        based_on_execution_id: str | None,
        checkpoint_artifact_id: str | None,
    ) -> ExecutionState | None:
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
            checkpoint = self.artifacts.get(checkpoint_artifact_id)
            if checkpoint.execution_id != predecessor.id:
                raise ValueError("resume checkpoint must come from the predecessor Execution")
        elif checkpoint_artifact_id is not None:
            raise ValueError("checkpoint_artifact_id is only valid for resume")
        if mode is ExecutionMode.REPRODUCE and predecessor.status is not ExecutionStatus.SUCCEEDED:
            raise ValueError("reproduce requires a succeeded predecessor")
        return predecessor

    def _relations(self, state: ExecutionState) -> tuple[ProvenanceRelation, ...]:
        relations: list[ProvenanceRelation] = [
            ProvenanceRelation(
                predicate="realizationOf",
                object=EntityRef(id=state.run_id, type="run"),
            )
        ]
        if state.based_on_execution_id:
            relations.append(
                ProvenanceRelation(
                    predicate="wasInformedBy",
                    object=EntityRef(id=state.based_on_execution_id, type="execution"),
                    attributes={"mode": state.mode.value},
                )
            )
        if state.checkpoint_artifact_id:
            relations.append(
                ProvenanceRelation(
                    predicate="used",
                    object=EntityRef(id=state.checkpoint_artifact_id, type="artifact"),
                    attributes={"role": "checkpoint"},
                )
            )
        return tuple(relations)

    def _collect_evidence(self, execution_id: str) -> builtins.list[EvidenceRef]:
        execution_dir = self.execution_dir(execution_id)
        evidence_names = {
            "stdout": "stdout.log",
            "stderr": "stderr.log",
            "runtime": "runtime.log",
            "exception": "exception.json",
            "traceback": "traceback.txt",
            "environment": "environment.json",
            "job": "job.json",
            "workflow": "workflow.json",
            "results": "results.json",
        }
        result: list[EvidenceRef] = []
        for kind, rel_path in evidence_names.items():
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

    def _write_state(self, state: ExecutionState) -> None:
        path = self.state_path(state.id)
        self.fs.mkdir(self.fs.dirname(path), parents=True, exist_ok=True)
        write_versioned_json(path, state.model_dump(mode="json"), fs=self.fs)


__all__ = ["ExecutionRepository"]
