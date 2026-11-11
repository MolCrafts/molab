"""Molab v2 scientific, execution, and data domain records."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator, model_validator

from molab._typing import JSONValue

from .history import AgentRef
from .timestamps import as_utc as _as_utc


class ContentRef(BaseModel):
    """Location-independent identity and shape of stored bytes."""

    model_config = ConfigDict(frozen=True)

    digest: str
    size: int
    kind: Literal["file", "directory"] = "file"


class ExecutionMode(StrEnum):
    """How an attempt relates to the attempts of its run before it."""

    INITIAL = "initial"
    RERUN = "rerun"
    RESUME = "resume"
    REPRODUCE = "reproduce"


class ExecutionStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    FINALIZING = "finalizing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


ACTIVE_EXECUTION_STATUSES = frozenset(
    {ExecutionStatus.QUEUED, ExecutionStatus.RUNNING, ExecutionStatus.FINALIZING}
)
TERMINAL_EXECUTION_STATUSES = frozenset(set(ExecutionStatus) - ACTIVE_EXECUTION_STATUSES)
#: Terminal outcomes that count as a failed attempt (anything but success).
FAILED_EXECUTION_STATUSES = frozenset(
    {ExecutionStatus.FAILED, ExecutionStatus.CANCELLED, ExecutionStatus.INTERRUPTED}
)


class RunStatusSummary(BaseModel):
    """Derived aggregate over all Executions realizing a Run."""

    model_config = ConfigDict(frozen=True)

    total: int
    active: int
    not_started: bool
    by_status: dict[str, int] = Field(default_factory=dict)

    @classmethod
    def from_executions(cls, executions: Sequence[Execution]) -> RunStatusSummary:
        counts: dict[str, int] = {}
        for execution in executions:
            key = execution.status.value
            counts[key] = counts.get(key, 0) + 1
        active = sum(counts.get(status.value, 0) for status in ACTIVE_EXECUTION_STATUSES)
        return cls(
            total=len(executions),
            active=active,
            not_started=not executions,
            by_status=counts,
        )


class EvidenceRef(BaseModel):
    """Integrity descriptor for execution evidence that is not an Artifact."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str
    rel_path: str
    digest: str
    size: int


class SourceFile(BaseModel):
    """One source file captured for an Execution, identified by its digest.

    A *digest* is a short fixed-length fingerprint computed from a file's
    bytes (here with the SHA-256 hash function): any change to the bytes
    changes it, so it identifies the content independently of where the file
    lives.

    Attributes:
        name: The file's name inside the captured source set (``wf.py``).
        sha256: The content digest of the file's bytes, prefixed with the
            algorithm name (``sha256:<hex>``).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    sha256: str


class SourceManifest(BaseModel):
    """The workflow source an Execution was created from.

    This is the value type of :attr:`Execution.source`, not a provenance
    sub-object: it records which files were captured and where they came from.
    It carries no directory key, because the directory the files are copied to
    is derived from the declared execution directories, not stored (the
    ``source/`` directory, declared by arch-own-02b, which also adds the
    capture that fills this manifest).

    Attributes:
        entrypoint: Basename of the entry script (``wf.py``).
        locator: Absolute path of the entry script at capture time. It records
            where the source came from and is never used as identity.
        files: The captured files with their digests.
        vcs_commit: The commit of the version-control system (VCS, e.g. git)
            the source was checked out at, if known.
        vcs_dirty: Whether the working tree had uncommitted changes, if known.
        captured_at: When the source was captured; a naive value (one with no
            time zone) is read as UTC.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    entrypoint: str
    locator: str
    files: tuple[SourceFile, ...] = ()
    vcs_commit: str | None = None
    vcs_dirty: bool | None = None
    captured_at: datetime

    @field_validator("captured_at", mode="after")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        return _as_utc(value)


class Execution(BaseModel):
    """One physical attempt at a Run — the whole of it, in one file.

    There is no second "sealed record" living somewhere else: sealing sets
    :attr:`sealed_at` (and the history commit that recorded it) and freezes
    the terminal fields in place. ``executions/e01/execution.json`` is the
    complete, authoritative account of attempt 1.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    seq: int
    run_id: str
    project_id: str
    mode: ExecutionMode
    status: ExecutionStatus = ExecutionStatus.QUEUED
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_by: AgentRef
    based_on_execution_id: str | None = None
    executor: dict[str, JSONValue] = Field(default_factory=dict)
    environment: dict[str, JSONValue] = Field(default_factory=dict)
    bypass_cache: bool = False
    """Whether this attempt was created to ignore the workflow node cache.

    The workflow node cache stores each task's output under a key built from
    the task's code and inputs, so an unchanged task can reuse its earlier
    output instead of running again. ``True`` means this attempt recomputes
    every task. A creation-time fact: it is written when the record is
    created and never changed afterwards.
    """
    selected_tasks: tuple[str, ...] = ()
    """The tasks a partial ``rerun`` attempt re-executes; empty means every task.

    A creation-time fact (``molab run --rerun --task NAME``). A non-empty
    selection runs exactly these tasks with the inputs their predecessor
    recorded: every other completed task is seeded from that record and every
    task downstream of a selected one is skipped. Only valid with ``rerun``.
    """
    source: SourceManifest | None = None
    """The workflow source this attempt was created from, if it was captured.

    A creation-time fact. ``None`` on records that captured no source; no
    production creator captures one until arch-own-02b.
    """
    workflow_hash: str | None = None
    """Content hash of the compiled workflow this attempt ran, recorded at start.

    ``sha256:...`` over the task code and the edges. It changes when that
    graph changes. A start-time fact written by ``ExecutionRepository.start``;
    always ``None`` on a QUEUED record. Records written before this field
    was named ``workflow_hash`` stored the same value as ``workflow_digest``.
    """

    @model_validator(mode="before")
    @classmethod
    def _accept_legacy_workflow_hash(cls, data: object) -> object:
        """Read ``workflow_digest`` from an older ``execution.json``.

        Product lists, checkpoint ids, and observed-input ids from the
        removed artifact record are dropped. They are not assets, and their
        ids are not reused. ``molab init`` mints a new asset id per file
        when the bytes should be kept.
        """
        if not isinstance(data, dict):
            return data
        migrated = dict(data)
        if "workflow_digest" in migrated:
            migrated.setdefault("workflow_hash", migrated.pop("workflow_digest"))
        migrated.pop("workflow_digest", None)
        for key in ("artifacts", "checkpoint_artifact_id", "observed_input_ids"):
            migrated.pop(key, None)
        return migrated

    evidence: tuple[EvidenceRef, ...] = ()
    declaration_diff: dict[str, JSONValue] = Field(default_factory=dict)
    error: dict[str, JSONValue] | None = None
    sealed_at: datetime | None = None
    pruned_at: datetime | None = None
    """When bulk directories were last pruned from this sealed attempt (UTC).

    A *prune* deletes an attempt's reproducible bulk directories to free disk
    space and keeps this record. ``pruned_at`` is half of the post-seal prune
    stamp, the one field set written after ``sealed_at``. Only
    ``ExecutionRepository.mark_pruned`` writes it. ``None`` means the attempt
    was never pruned.
    """
    pruned_dirs: tuple[str, ...] = ()
    """Sorted names of the execution directories pruned so far (``("out", "work")``).

    The other half of the post-seal prune stamp. Every name is a directory
    declared prunable (``molab.workspace.execution_dirs.prunable_dirs``), so
    ``execution.json``, ``workflow.json`` and ``run.log`` are never among them.
    """

    @property
    def sealed(self) -> bool:
        return self.sealed_at is not None

    # Set by Run when it hands the record out. Absent on a bare load from disk.
    # Not part of the record: two attempts compare equal with or without it.
    _run: object | None = PrivateAttr(default=None)

    def __eq__(self, other: object) -> bool:
        if type(other) is not Execution:
            return NotImplemented
        return self.model_dump() == other.model_dump()

    def __hash__(self) -> int:
        return hash(self.model_dump_json())

    def execute(self, workflow: object, /) -> object:
        """Run *workflow* as this queued attempt.

        Starts the record and returns the workflow result. ``run.execute``
        allocates an attempt and then runs it the same way; a scheduler that
        already queued one calls this on ``run.execution(execution_id)``.

        Args:
            workflow: A compiled workflow, or one to compile.

        Returns:
            The workflow result. ``.outputs`` maps task name to output.

        Raises:
            RuntimeError: This record was not read from its Run, or the call
                is inside a running event loop (await :meth:`aexecute`).
        """
        run = self._run
        if run is None:
            raise RuntimeError(
                "execution.execute() needs the Run this attempt belongs to; "
                "read it with run.execution(id)"
            )
        from molab.workspace.run import require_run_executor

        return require_run_executor().execute(run, workflow, execution_id=self.id)  # ty: ignore[invalid-argument-type]

    async def aexecute(self, workflow: object, /) -> object:
        """Async variant of :meth:`execute` — same attempt, awaitable.

        Args:
            workflow: A compiled workflow, or one to compile.

        Returns:
            The workflow result. ``.outputs`` maps task name to output.

        Raises:
            RuntimeError: This record was not read from its Run.
        """
        run = self._run
        if run is None:
            raise RuntimeError(
                "execution.aexecute() needs the Run this attempt belongs to; "
                "read it with run.execution(id)"
            )
        from molab.workspace.run import require_run_executor

        return await require_run_executor().aexecute(run, workflow, execution_id=self.id)  # ty: ignore[invalid-argument-type]

    @field_validator(
        "created_at", "started_at", "finished_at", "sealed_at", "pruned_at", mode="after"
    )
    @classmethod
    def _utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value)


class AssetScope(BaseModel):
    """Identifies which scope (workspace/project/experiment/run) owns an asset.

    ``ids`` is the chain of parent IDs ending with the leaf scope's own id.
    Empty for workspace scope.

    Examples::

        AssetScope(kind="workspace", ids=())
        AssetScope(kind="project", ids=("qm9",))
        AssetScope(kind="experiment", ids=("qm9", "baseline"))
    """

    model_config = ConfigDict(frozen=True)

    kind: Literal["workspace", "project", "experiment"]
    ids: tuple[str, ...] = ()

    @property
    def urn(self) -> str:
        """URN fragment: ``workspace`` or ``run/proj/exp/run-id``."""
        if not self.ids:
            return self.kind
        return f"{self.kind}/{'/'.join(self.ids)}"

    @property
    def scope_id(self) -> str:
        """Flat identifier used as catalog key.

        For workspace: the constant ``workspace``.  Otherwise the last
        segment of ``ids`` (the leaf scope's own id).
        """
        return self.ids[-1] if self.ids else "workspace"

    @property
    def project_id(self) -> str | None:
        """Owning project id, or ``None`` when ``kind`` is ``workspace``.

        Every other kind stores the project as the first id in the chain.
        """
        if self.kind == "workspace":
            return None
        return self.ids[0]


class ExecutionOrigin(BaseModel):
    """Bytes produced by one task of one attempt.

    Attributes:
        kind: Discriminator, always ``execution``.
        project_id: Project that owns the attempt.
        experiment_id: Experiment that owns the attempt.
        run_id: Run the attempt belongs to.
        execution_id: Attempt that produced the file.
        task: Task name, when the file was registered from a task.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["execution"] = "execution"
    project_id: str
    experiment_id: str
    run_id: str
    execution_id: str
    task: str | None = None


class ImportOrigin(BaseModel):
    """Bytes brought in from outside a run.

    Attributes:
        kind: Discriminator, always ``import``.
        uri: Where the bytes were copied from. Provenance only.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["import"] = "import"
    uri: str


AssetOrigin = Annotated[ExecutionOrigin | ImportOrigin, Field(discriminator="kind")]
"""Where an :class:`Asset`'s bytes came from."""


class Asset(BaseModel):
    """One registered file: one id, one content, one ``molab:asset/<id>`` ref.

    The record and the bytes live together under the owning scope's
    ``assets/`` directory. ``scope`` is not persisted. The directory is the
    owner, and the repository injects it on read. The same bytes registered
    again return this id. One asset per slot (its title, plus its run for an
    attempt's product): new bytes in the slot replace the old and keep the id.

    Attributes:
        id: Stable identity.
        scope: Owning scope. Excluded from serialization.
        title: Display label.
        content: Digest and size of the bytes.
        media_type: Optional media type.
        origin: The attempt that produced the file, or the import.
        file: Payload file name inside the asset directory.
        created_at: When the asset was registered. A naive value is read as UTC.
        created_by: Who registered it.
        tags: Free-form string tags.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    scope: AssetScope = Field(exclude=True)
    title: str
    content: ContentRef
    media_type: str | None = None
    origin: AssetOrigin
    file: str
    created_at: datetime
    created_by: AgentRef
    tags: dict[str, str] = Field(default_factory=dict)

    @property
    def project_id(self) -> str | None:
        """Project id derived from :attr:`scope`, or ``None`` at workspace scope."""
        return self.scope.project_id

    @property
    def ref(self) -> str:
        """``molab:asset/<id>``."""
        return f"molab:asset/{self.id}"

    @field_validator("created_at", mode="after")
    @classmethod
    def _utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value)


__all__ = [
    "ACTIVE_EXECUTION_STATUSES",
    "FAILED_EXECUTION_STATUSES",
    "TERMINAL_EXECUTION_STATUSES",
    "Asset",
    "AssetOrigin",
    "AssetScope",
    "ContentRef",
    "EvidenceRef",
    "Execution",
    "ExecutionMode",
    "ExecutionOrigin",
    "ExecutionStatus",
    "ImportOrigin",
    "RunStatusSummary",
    "SourceFile",
    "SourceManifest",
]
