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
blocks a writer of the record. ``merge_remote`` (folding a worker's record from
another filesystem into the local one) follows the same seal -> state order.

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

Creation-time vs start-time facts. ``create`` writes a QUEUED record with the
facts known when the attempt is allocated (mode, predecessor, checkpoint,
``bypass_cache``, ``source``, and the creator's ``environment`` / ``executor``).
``start`` runs once, from QUEUED only, and adds the facts known when the
attempt begins (host, python, platform, pid, ``workflow_digest``). It merges
by adding missing keys and never overwrites a key the creator wrote.

Immutable fields. ``_IMMUTABLE_FIELDS`` is the union of three named sets:
``_IDENTITY_FIELDS`` (what the attempt is), ``_POST_SEAL_FIELDS`` (the prune
stamp, written only by ``mark_pruned``) and ``_PROVENANCE_FIELDS`` (the
creation-time and start-time facts). The union is composed, not copied, so a
field added to any one set is refused automatically. ``transition`` refuses
all of them, and is never the way into RUNNING: ``start`` is, and it is the
only caller that hands start-time provenance to the transition kernel.
``update_operational`` writes ``executor`` and nothing else, add-only and
never a start-time key: a cluster scheduler's job id only exists once the job
has been submitted, which is normally after creation and before start.
Lifecycle fields (status, seal,
evidence, artifacts) change only through their own verbs.

Legacy attempts. ``fold_legacy_attempt`` builds a current-schema record from
an old layout's scattered *sidecars* (small JSON files an older layout kept
beside ``execution.json``: ``environment.json``, ``exception.json``,
``job.json``) for ``molab migrate layout``. It writes through the same
``_write_execution`` as the repository, so this module is the only writer of
``execution.json``.
"""

from __future__ import annotations

import builtins
import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

from molab._typing import JSONValue

from ._file_lock import file_lock
from .artifact_repository import ArtifactRepository
from .domain import (
    ACTIVE_EXECUTION_STATUSES,
    FAILED_EXECUTION_STATUSES,
    TERMINAL_EXECUTION_STATUSES,
    Artifact,
    EvidenceRef,
    Execution,
    ExecutionMode,
    ExecutionStatus,
    RunStatusSummary,
    SourceManifest,
)
from .execution_dirs import OUT, prunable_dirs
from .fs import FileSystem, PathArg
from .fs_local import LocalFileSystem
from .history import SYSTEM_AGENT, AgentRef, EntityRef, GitHistory, Relation
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

_IDENTITY_FIELDS: frozenset[str] = frozenset(
    {"id", "seq", "run_id", "project_id", "mode", "created_at", "created_by"}
)
"""Fields that say which attempt a record is; fixed by ``create``."""

_CREATION_PROVENANCE_FIELDS: frozenset[str] = frozenset(
    {"based_on_execution_id", "checkpoint_artifact_id", "bypass_cache", "source"}
)
"""Creation-time facts other than identity; written once, by ``create``."""

_START_PROVENANCE_FIELDS: frozenset[str] = frozenset(
    {"environment", "workflow_digest", "started_at"}
)
"""Start-time facts; ``start`` writes them (``environment`` merged, add-only).

``environment`` is here, not in ``_CREATION_PROVENANCE_FIELDS``, because it
grows at start: the creator's keys are compared key by key (a later record may
add keys, never change or drop one), not as a whole value.
"""

_PROVENANCE_FIELDS: frozenset[str] = _CREATION_PROVENANCE_FIELDS | _START_PROVENANCE_FIELDS
"""Creation-time and start-time facts; never written by an update verb.

``create`` writes the creation-time ones and ``start`` the start-time ones
(``started_at``, the merged ``environment``, ``workflow_digest``). ``seal``
also writes one: an attempt sealed straight from QUEUED never started, so
``seal`` fills ``started_at`` with ``created_at``. (``fold_legacy_attempt``
builds a whole record from scratch and is not an update.)
"""

_IMMUTABLE_FIELDS: frozenset[str] = _IDENTITY_FIELDS | _POST_SEAL_FIELDS | _PROVENANCE_FIELDS
"""Every field ``transition`` and ``update_operational`` refuse.

Composed from the three named sets rather than listing their members, so a
field added to any of them (for example a new post-seal field) is refused here
too. ``executor`` is not in it. When molq (the plugin that submits an
attempt to a cluster's batch-queue scheduler) hands the job over, the
scheduler's job id appears only after submission and normally before start,
so it is recorded afterwards with ``update_operational``.
"""

_OPERATIONAL_FIELDS: frozenset[str] = frozenset({"executor"})
"""The only fields ``update_operational`` writes."""

_START_TIME_KEYS: frozenset[str] = frozenset({"host", "pid", "python", "platform"})
"""Keys known only when an attempt starts; a creator must never write them.

``ExecutionRepository.start`` never overwrites a key already on the record, and
``run_reaper`` reads ``executor.host`` before ``environment.host``. A creator
that wrote ``host`` would pin the reaper to a machine the attempt never ran on,
so ``update_operational`` refuses an ``executor`` update carrying any of them.
The one definition; ``execution_context`` imports it from here.
"""

_CREATION_FIELDS: frozenset[str] = _IDENTITY_FIELDS | _CREATION_PROVENANCE_FIELDS
"""Fields a remote record must share with the local one to be the same attempt.

Composed from the named sets, so a field added to either is compared too.
"""

_LIFECYCLE_RANK: dict[ExecutionStatus, int] = {
    ExecutionStatus.QUEUED: 0,
    ExecutionStatus.RUNNING: 1,
    ExecutionStatus.FINALIZING: 1,
    **dict.fromkeys(TERMINAL_EXECUTION_STATUSES, 2),
}
"""How far along its lifecycle a status is; a merge may never move a record back."""

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
        based_on_execution_id: str | None = None,
        checkpoint_artifact_id: str | None = None,
        executor: dict[str, JSONValue] | None = None,
        environment: dict[str, JSONValue] | None = None,
        bypass_cache: bool = False,
        source: SourceManifest | None = None,
    ) -> Execution:
        """Allocate the next attempt after validating retry/resume semantics.

        This is the one place a run's ``eNN`` ids are allocated: the id is
        always the next sequence slug and is never reused. The only caller in
        ``src`` is ``Run.create_execution``. The record is written QUEUED with
        its creation-time facts only.

        Args:
            mode: How this attempt relates to earlier ones.
            created_by: The agent creating the attempt.
            based_on_execution_id: The predecessor attempt, when ``mode`` needs one.
            checkpoint_artifact_id: The checkpoint to resume from (``resume`` only).
            executor: Creation-time executor facts (backend, target).
            environment: Creation-time environment facts (profile, script).
            bypass_cache: Whether the attempt ignores the workflow node cache.
            source: The captured workflow source, if any.

        Returns:
            The QUEUED record as written.

        Raises:
            ValueError: ``mode`` and the predecessor / checkpoint disagree.
            KeyError: The named predecessor does not exist.
            FileExistsError: A record with the next id already exists (for
                example a legacy directory of that name).
        """
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
                id=execution_slug(seq),
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
                bypass_cache=bypass_cache,
                source=source,
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

    def start(
        self,
        execution_id: str,
        *,
        environment: dict[str, JSONValue] | None = None,
        executor: dict[str, JSONValue] | None = None,
        workflow_digest: str | None = None,
    ) -> Execution:
        """Start a QUEUED attempt exactly once, adding its start-time facts.

        The read, the QUEUED check, the merge and the write all happen under
        the attempt's state lock, so two processes starting the same attempt
        (a scheduler requeue, a duplicate dispatch) cannot both succeed: the
        second sees RUNNING and is refused. The history commit is recorded
        after the lock is released.

        Merge rule: ``environment`` and ``executor`` only add keys the record
        does not already have. A key written at creation keeps its value, so a
        starter cannot overwrite a creation-time fact. ``started_at`` is set to
        the current UTC time and ``workflow_digest`` is written as given; both
        are always unset on a QUEUED record, so nothing is overwritten.

        Args:
            execution_id: The attempt to start (``e01``).
            environment: Start-time environment facts (host, python, platform, pid).
            executor: Start-time executor facts (kind, host, pid).
            workflow_digest: Digest of the compiled workflow this attempt runs
                (``sha256:...``). No production caller passes it yet; its
                writers land in arch-own-03a / arch-own-03g.

        Returns:
            The RUNNING record as written.

        Raises:
            ValueError: The attempt is not QUEUED (already started, or sealed).
            KeyError: No attempt ``execution_id`` exists under this Run.
        """
        with file_lock(self._state_lock(execution_id)):
            current = self.get(execution_id)
            if current.status is not ExecutionStatus.QUEUED:
                raise ValueError(
                    f"Execution {execution_id!r} is {current.status.value}, not queued; "
                    "an Execution is started exactly once"
                )
            started = self._transition_locked(
                execution_id,
                ExecutionStatus.RUNNING,
                updates={"executor": {**(executor or {}), **current.executor}},
                provenance={
                    "started_at": datetime.now(UTC),
                    "environment": {**(environment or {}), **current.environment},
                    "workflow_digest": workflow_digest,
                },
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

        Never the way into RUNNING: ``start`` is, because it checks QUEUED
        under the lock and merges the start-time facts without overwriting.

        Args:
            execution_id: The attempt to move (``e01``).
            status: The target status; must be allowed from the current one,
                and must not be RUNNING.
            **updates: Extra fields written in the same record update; none
                may be an identity, provenance or post-seal field.

        Returns:
            The record as written (unchanged when already in ``status``).

        Raises:
            ValueError: The transition is not allowed, ``status`` is RUNNING,
                or ``updates`` names an immutable field (``_IMMUTABLE_FIELDS``).
            KeyError: No attempt ``execution_id`` exists under this Run.
        """
        _refuse_immutable_updates(updates)
        if status is ExecutionStatus.RUNNING:
            raise ValueError(
                f"cannot transition Execution {execution_id!r} to running; "
                "use start(): an Execution is started exactly once"
            )
        with file_lock(self._state_lock(execution_id)):
            return self._transition_locked(execution_id, status, updates=updates)

    def _transition_locked(
        self,
        execution_id: str,
        status: ExecutionStatus,
        *,
        updates: Mapping[str, object] | None = None,
        provenance: Mapping[str, object] | None = None,
    ) -> Execution:
        """Lock-free transition kernel; the caller must hold the state lock.

        Both field sets are explicit mappings, never ``**kwargs``, so a key in
        ``updates`` can never bind to ``provenance``.

        Args:
            execution_id: The attempt to move (``e01``).
            status: The target status; must be allowed from the current one.
            updates: Extra fields written in the same record update; none may
                be an identity, provenance or post-seal field.
            provenance: Start-time provenance, merged in after the check on
                ``updates``. Only ``start`` passes it.

        Returns:
            The record as written (unchanged when already in ``status``).

        Raises:
            ValueError: The transition is not allowed, or ``updates`` names an
                immutable field (only ``start`` writes provenance and only
                ``mark_pruned`` writes the prune stamp).
        """
        updates = updates or {}
        _refuse_immutable_updates(updates)
        current = self.get(execution_id)
        if status == current.status:
            return current
        if status not in _ALLOWED_TRANSITIONS[current.status]:
            raise ValueError(
                f"invalid Execution transition: {current.status.value} -> {status.value}"
            )
        state = current.model_copy(update={**updates, **(provenance or {}), "status": status})
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
        """Update the operational field of an unsealed attempt: ``executor``.

        ``executor`` stays writable because a cluster scheduler's job id is
        known only after the job is submitted, which is normally after
        creation and before start. Every other field is refused:
        ``_IMMUTABLE_FIELDS`` (identity, provenance, prune stamp) first, then
        the lifecycle fields, which change only through ``start`` /
        ``transition`` / ``seal``.

        The ``executor`` merge is add-only: the written value is
        ``{**updates["executor"], **current.executor}``, so a key already on
        the record (the creator's ``backend`` / ``target``, a fast worker's
        ``kind`` / ``host`` / ``pid``) keeps its value and only missing keys
        are added. The read, the merge and the write all happen under the
        attempt's state lock, the same lock ``start`` takes, so a worker
        starting the attempt concurrently cannot lose its keys.

        An ``executor`` update carrying a start-time key (``host`` / ``pid``
        / ``python`` / ``platform``, ``_START_TIME_KEYS``) is refused: only
        ``start`` writes those, and the reaper reads ``executor.host`` first.

        Args:
            execution_id: The attempt to update (``e01``).
            **updates: The operational fields to write (``executor`` only).

        Returns:
            The record as written.

        Raises:
            ValueError: The attempt is sealed, ``updates`` names a field other
                than ``executor``, or the ``executor`` update carries a
                start-time key.
            TypeError: The ``executor`` update is not a mapping.
            KeyError: No attempt ``execution_id`` exists under this Run.
        """
        with file_lock(self._state_lock(execution_id)):
            current = self.get(execution_id)
            if current.sealed:
                raise ValueError(f"Execution {execution_id!r} is sealed")
            overlap = _IMMUTABLE_FIELDS.intersection(updates)
            if overlap:
                raise ValueError(
                    f"cannot update Execution identity or provenance fields: {sorted(overlap)}"
                )
            lifecycle = sorted(set(updates) - _OPERATIONAL_FIELDS)
            if lifecycle:
                raise ValueError(
                    "update_operational only updates executor; lifecycle fields change "
                    f"through start/transition/seal: {lifecycle}"
                )
            merged: dict[str, object] = {}
            if "executor" in updates:
                executor = updates["executor"]
                if not isinstance(executor, Mapping):
                    raise TypeError(
                        f"executor update must be a mapping, got {type(executor).__name__}"
                    )
                start_keys = sorted(_START_TIME_KEYS.intersection(executor))
                if start_keys:
                    raise ValueError(
                        f"cannot write start-time executor keys {start_keys} through "
                        "update_operational; only start() writes them"
                    )
                merged["executor"] = {**executor, **current.executor}
            state = current.model_copy(update=merged)
            self._write_state(state)
            return state

    def merge_remote(self, execution_id: str, document: Mapping[str, object]) -> Execution:
        """Fold the record a worker wrote on another filesystem into this one.

        ``document`` is the remote ``execution.json`` of the same attempt. Its
        ``schema_version`` key is dropped (the ``read_versioned_json`` rule, no
        version gate) and the rest validated as an ``Execution``.

        Merge rule: the remote record wins for status, ``started_at`` /
        ``finished_at``, ``environment``, artifacts, evidence, error and
        ``sealed_at``. ``executor`` is merged with the local keys winning (the
        scheduler job ids); keys only the worker knows (``kind`` / ``host`` /
        ``pid``) are kept. The remote ``sealed_commit`` is always dropped: it
        names a commit in the remote tree's history. The status only moves
        forward, and the prune stamp is never taken from the remote record
        (``mark_pruned`` is its one writer).

        Creation-time environment rule: every key of the local
        ``environment`` must be present in the remote one with an equal value.
        The remote record may only add keys (the worker's start-time facts);
        it can never replace ``config_hash`` / ``script`` / ``submit_cwd``.

        Locks follow ``seal``: the seal lock for the whole call, the state
        lock around the read-check-write, history outside the state lock, and
        the ``sealed_commit`` stamp under a re-taken state lock on a fresh
        read of the record.

        Args:
            execution_id: The local attempt the remote record describes (``e01``).
            document: The remote ``execution.json`` contents.

        Returns:
            The record as written; the unchanged local record when it was
            already sealed (a sealed attempt is immutable, so a replayed merge
            is a no-op).

        Raises:
            KeyError: No attempt ``execution_id`` exists locally; nothing is
                created.
            ValueError: The remote record is another attempt (a
                ``_CREATION_FIELDS`` value differs); its status is behind the
                local one (QUEUED < RUNNING / FINALIZING < terminal); it has
                ``sealed_at`` with a non-terminal status; it carries a prune
                stamp (``pruned_at`` / ``pruned_dirs``, written only by
                ``mark_pruned``); or it rewrites or drops a creation-time
                ``environment`` key. Nothing is written.
            pydantic.ValidationError: ``document`` is not a valid ``Execution``.
        """
        remote = Execution.model_validate(
            {key: value for key, value in document.items() if key != "schema_version"}
        )
        with file_lock(self._seal_lock(execution_id)):
            with file_lock(self._state_lock(execution_id)):
                current = self.get(execution_id)
                if current.sealed:
                    return current
                mismatched = sorted(
                    name
                    for name in _CREATION_FIELDS
                    if getattr(remote, name) != getattr(current, name)
                )
                if mismatched:
                    raise ValueError(f"remote execution.json is not this attempt: {mismatched}")
                if _LIFECYCLE_RANK[remote.status] < _LIFECYCLE_RANK[current.status]:
                    raise ValueError(
                        f"remote execution.json status {remote.status.value!r} is behind "
                        f"local {current.status.value!r}"
                    )
                if remote.sealed_at is not None and (
                    remote.status not in TERMINAL_EXECUTION_STATUSES
                ):
                    raise ValueError(
                        "remote execution.json is sealed with non-terminal status "
                        f"{remote.status.value!r}"
                    )
                if remote.pruned_at is not None or remote.pruned_dirs:
                    raise ValueError(
                        "remote execution.json carries a prune stamp; only mark_pruned "
                        "writes pruned_at / pruned_dirs"
                    )
                rewritten = [
                    key
                    for key, value in current.environment.items()
                    if key not in remote.environment or remote.environment[key] != value
                ]
                if rewritten:
                    raise ValueError(
                        "remote execution.json rewrites creation-time environment: "
                        f"{sorted(rewritten)}"
                    )
                merged = remote.model_copy(
                    update={
                        "executor": {**remote.executor, **current.executor},
                        "sealed_commit": None,
                        "pruned_at": current.pruned_at,
                        "pruned_dirs": current.pruned_dirs,
                    }
                )
                self._write_state(merged)
            if not merged.sealed:
                return merged
            commit = self._record("ExecutionSealed", merged, when=merged.sealed_at)
            if commit is None:
                return merged
            with file_lock(self._state_lock(execution_id)):
                latest = self.get(execution_id)
                stamped = latest.model_copy(update={"sealed_commit": commit})
                self._write_state(stamped)
            return stamped

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
        if mode is ExecutionMode.RETRY and predecessor.status not in FAILED_EXECUTION_STATUSES:
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
        _write_execution(self.fs, self.state_path(state.id), state)


def _refuse_immutable_updates(updates: Mapping[str, object]) -> None:
    """Refuse a transition update that names an immutable field.

    Raises:
        ValueError: ``updates`` names a post-seal field, or an identity or
            provenance field.
    """
    post_seal = sorted(_POST_SEAL_FIELDS.intersection(updates))
    if post_seal:
        raise ValueError(f"cannot write post-seal fields in a transition: {post_seal}")
    protected = sorted(_IMMUTABLE_FIELDS.intersection(updates))
    if protected:
        raise ValueError(
            f"cannot write identity or provenance fields in a transition: {protected}; "
            "only create() and start() write them"
        )


def _write_execution(fs: FileSystem, path: str | Path, state: Execution) -> None:
    """Write one ``execution.json``, the only way that file is ever written.

    Args:
        fs: The filesystem the record lives on.
        path: The record's path (``.../executions/e01/execution.json``).
        state: The validated record; stamped with ``MOLAB_SCHEMA_VERSION``.
    """
    fs.mkdir(fs.dirname(path), parents=True, exist_ok=True)
    write_versioned_json(path, state.model_dump(mode="json"), fs=fs)


# ── legacy attempts (``molab migrate layout``) ──────────────────────────────


def _read_legacy(path: Path, fs: FileSystem | None = None) -> dict[str, object]:
    """Read a legacy sidecar without its ``schema_version``.

    Missing, unreadable, or not a JSON object reads as ``{}``.
    """
    disk = fs or LocalFileSystem()
    if not disk.is_file(path):
        return {}
    try:
        with disk.open(str(path)) as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    data.pop("schema_version", None)
    return data


def legacy_attempt_created_at(attempt_dir: Path) -> str:
    """Return a legacy attempt's ``created_at`` string, for ordering attempts.

    ``molab migrate layout`` sorts a run's legacy attempts by this value
    before numbering them. Unlike ``fold_legacy_attempt`` it takes no ``fs``
    and always reads the local disk.

    Args:
        attempt_dir: The legacy attempt directory holding ``execution.json``.

    Returns:
        The ``created_at`` value as written, or ``""`` when the file is
        missing or the value is not a string.
    """
    value = _read_legacy(attempt_dir / "execution.json").get("created_at")
    return value if isinstance(value, str) else ""


def fold_legacy_attempt(
    src: Path,
    dst: Path,
    *,
    workspace_root: Path,
    seq: int,
    run_id: str,
    project_id: str,
    artifacts: Sequence[tuple[Mapping[str, object], str]] = (),
    fs: FileSystem | None = None,
) -> Execution:
    """Fold an old layout's attempt sidecars into one current-schema record.

    A *sidecar* is one of the small JSON files an older layout kept beside
    an attempt's legacy state file (``execution.json``). Reads that state
    file plus ``environment.json``, ``exception.json`` and ``job.json`` under
    ``src`` (a missing or unreadable one reads as empty), builds the record
    through ``Execution.model_validate`` and writes ``dst/execution.json``
    through ``_write_execution``. The rules are the ones
    ``molab migrate layout`` always applied:

    - The id is ``execution_slug(seq)``. ``mode`` defaults to ``initial`` for
      seq 1 and ``rerun`` otherwise. ``based_on_execution_id`` is the previous
      slug only when seq > 1 and the source named a predecessor.
    - ``created_at`` defaults to now; ``started_at`` defaults to ``created_at``.
    - ``error`` is the state's error, else the ``exception.json`` payload.
    - ``executor`` is the state's executor, else ``{"job": <job.json>}``.
    - ``environment`` is the state's, else ``environment.json`` with its
      ``{"environment": ...}`` wrapper removed.
    - An attempt with no recorded status is ``interrupted``, never
      ``succeeded``: the migration does not invent a result the source tree
      does not claim. ``sealed_at`` is ``finished_at`` only when the attempt
      was sealed or is terminal, so a terminal attempt with no
      ``finished_at`` (including the defaulted ``interrupted`` one) folds to
      an unsealed record.
    - Each artifact is rebound to this attempt (``execution_id`` / ``run_id``
      / ``project_id``), its ``path`` becomes workspace-relative, and a
      missing ``source_path`` defaults to ``out/<name>``.
    - ``bypass_cache``, ``source`` and ``workflow_digest`` are left at their
      defaults; an old layout recorded none of them.

    No history is recorded here; ``molab migrate layout`` commits once at the
    end. The caller has already hard-linked the bytes into ``dst``.

    Args:
        src: The legacy attempt directory.
        dst: The target attempt directory (``.../executions/e01``).
        workspace_root: The target workspace root; artifact paths are relative to it.
        seq: The attempt's 1-based sequence number within its Run.
        run_id: The id of the Run the attempt belongs to.
        project_id: The id of the Project the Run belongs to.
        artifacts: Pairs of (legacy ``artifact.json`` record, path of its bytes
            relative to ``dst``, e.g. ``"artifacts/metrics.jsonl"``).
        fs: The filesystem both trees live on; defaults to the local disk.

    Returns:
        The record as written.

    Raises:
        pydantic.ValidationError: The folded record is not a valid
            ``Execution``; nothing is written.
    """
    disk = fs or LocalFileSystem()
    state = _read_legacy(src / "execution.json", disk)
    environment = _read_legacy(src / "environment.json", disk)
    exception = _read_legacy(src / "exception.json", disk)
    job = _read_legacy(src / "job.json", disk)
    slug = execution_slug(seq)

    folded_artifacts: list[dict[str, object]] = []
    for legacy, out_rel in artifacts:
        record = {key: value for key, value in legacy.items() if key != "schema_version"}
        name = str(record.get("name") or Path(out_rel).name)
        record["name"] = name
        record["path"] = (dst / out_rel).relative_to(workspace_root).as_posix()
        record.setdefault("source_path", f"{OUT.name}/{Path(name).name}")
        record["execution_id"] = slug
        record["run_id"] = run_id
        record["project_id"] = project_id
        folded_artifacts.append(record)

    created_value = state.get("created_at")
    created = created_value if isinstance(created_value, str) else datetime.now(UTC).isoformat()
    error = state.get("error") or (exception or None)
    executor = state.get("executor") or ({"job": job} if job else {})
    wrapped = environment.get("environment")
    if isinstance(wrapped, dict):
        environment = wrapped
    if environment and not state.get("environment"):
        state["environment"] = environment
    # An attempt with no state file never recorded how it ended. That is
    # "interrupted", never "succeeded".
    status = str(state.get("status") or "interrupted")
    sealed = state.get("sealed_event_id") is not None or status in TERMINAL_EXECUTION_STATUSES
    record = {
        "id": slug,
        "seq": seq,
        "run_id": run_id,
        "project_id": project_id,
        "mode": state.get("mode") or ("initial" if seq == 1 else "rerun"),
        "status": status,
        "created_at": created,
        "started_at": state.get("started_at") or created,
        "finished_at": state.get("finished_at"),
        "created_by": state.get("created_by") or SYSTEM_AGENT.model_dump(mode="json"),
        "based_on_execution_id": execution_slug(seq - 1)
        if seq > 1 and state.get("based_on_execution_id")
        else None,
        "checkpoint_artifact_id": state.get("checkpoint_artifact_id"),
        "executor": executor,
        "environment": state.get("environment") or {},
        "observed_input_ids": state.get("observed_input_ids") or [],
        "artifacts": folded_artifacts,
        "evidence": [],
        "declaration_diff": {},
        "error": error,
        "sealed_at": state.get("finished_at") if sealed else None,
        "sealed_commit": None,
    }
    execution = Execution.model_validate(record)
    _write_execution(disk, dst / "execution.json", execution)
    return execution


__all__ = ["ExecutionRepository", "fold_legacy_attempt", "legacy_attempt_created_at"]
