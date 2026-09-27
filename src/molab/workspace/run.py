"""Logical Run identity and its physical Execution factory.

A :class:`Run` is immutable scientific intent. :class:`ExecutionContext`
owns one real attempt and all mutable/runtime state beneath it.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator, Mapping
from datetime import datetime
from pathlib import Path  # local-FS path for RunContext (LLM/worker-local I/O)
from typing import TYPE_CHECKING, ClassVar, Protocol, cast

from mollog import get_logger

from molab._typing import (
    JSONValue,
    TaskOutput,
)
from molab.ids import compute_definition_hash, generate_uuid7
from molab.path import Path as MolabPath
from molab.profile import ProfileConfig

from .base import (
    _load_metadata,
    _reconstruct,
)
from .errors import RunExistsError, RunNotFoundError
from .execution_dirs import execution_dir_names
from .folder import WORKSPACE_RUN_KIND, Folder, register_entity_class
from .fs import PathArg
from .models import FolderMetadata, RunMetadata, RunStatus
from .naming import run_slug

if TYPE_CHECKING:
    from .experiment import Experiment

# Re-exported for backward compatibility — the canonical definition now
# lives in ``.models`` so the run-lifecycle collaborators can import it
# without a circular ``run.py`` dependency.
from .domain import (
    ACTIVE_EXECUTION_STATUSES,
    FAILED_EXECUTION_STATUSES,
    Execution,
    ExecutionMode,
    ExecutionStatus,
    RunStatusSummary,
)
from .execution_context import (
    _PROFILE_KEYS,
    RunContext,
    _creation_environment,
    _system_agent,
)
from .execution_repository import _START_TIME_KEYS, ExecutionRepository
from .history import AgentRef
from .source_snapshot import SourceCaptureError, copy_sources, source_manifest

_logger = get_logger(__name__)

__all__ = [
    "RETRYABLE_STATUSES",
    "TERMINAL_STATUSES",
    "Run",
    "RunContext",
    "RunStatus",
    "RunWorkflowExecutor",
    "set_run_executor",
]

#: The run statuses ``resume`` / ``rerun`` apply to — the single source of
#: truth for the retryable domain (consumed by both the CLI and the server
#: routes). The three verbs stay orthogonal: ``pending`` is plain run's job,
#: ``succeeded`` is done, and a live ``running`` run must never get a second
#: concurrent execution.
RETRYABLE_STATUSES: frozenset[str] = frozenset({RunStatus.FAILED.value, RunStatus.CANCELLED.value})

#: Terminal statuses — a finished run carries a ``finished_at``.
TERMINAL_STATUSES: frozenset[str] = frozenset(
    {RunStatus.SUCCEEDED.value, RunStatus.FAILED.value, RunStatus.CANCELLED.value}
)


# ── Cross-layer run-execution seam ──────────────────────────────────────────
#
# Workspace MUST NOT import the workflow layer (hard layer-DAG invariant), yet
# ``run.execute(workflow)`` should read fluently. Same inversion pattern as
# ``experiment.set_workflow_executor``: the workflow layer implements the
# Protocol below and registers itself at ``import molab.workflow`` time
# (see ``molab.workflow.execute``), so by the time a caller holds a workflow
# object to pass in, the seam is wired.


class RunWorkflowExecutor(Protocol):
    """One-step tracked execution of a workflow against a :class:`Run`.

    Implemented by ``molab.workflow.execute`` and registered via
    :func:`set_run_executor`. ``workflow`` is opaque to workspace (a
    ``CompiledWorkflow`` / ``Workflow``, or ``None`` to resolve the
    experiment's bound workflow); the return value is an opaque
    ``molab.workflow.WorkflowResult``.
    """

    def execute(
        self,
        run: Run,
        workflow: object | None,
        *,
        resume: bool = False,
        rerun: bool = False,
        fresh: bool = False,
        checkpoint_artifact_id: str | None = None,
    ) -> object: ...

    async def aexecute(
        self,
        run: Run,
        workflow: object | None,
        *,
        resume: bool = False,
        rerun: bool = False,
        fresh: bool = False,
        checkpoint_artifact_id: str | None = None,
    ) -> object: ...


_run_executor: RunWorkflowExecutor | None = None


def set_run_executor(executor: RunWorkflowExecutor) -> None:
    """Register the workflow-layer implementation backing :meth:`Run.execute`.

    Called once at ``import molab.workflow`` time. Until then,
    :meth:`Run.execute` (and ``RunSet.execute``) fail fast — never a silent
    fallback.
    """
    global _run_executor
    _run_executor = executor


def require_run_executor() -> RunWorkflowExecutor:
    """Return the registered executor, or fail fast with guidance."""
    if _run_executor is None:
        raise RuntimeError(
            "Run.execute needs the workflow layer; `import molab.workflow` "
            "(e.g. `from molab.workflow import Workflow`) registers "
            "the executor."
        )
    return _run_executor


# ── Run ─────────────────────────────────────────────────────────────────────


def compute_run_definition_hash(
    *,
    experiment_revision_id: str | None,
    parameters: Mapping[str, object] | None,
    input_asset_ids: tuple[str, ...] = (),
    config_hash: str | None = None,
) -> str:
    """The ONE definition-hash for a Run — every seeding path calls this.

    A Run's reproducibility identity is *what varies between the runs of one
    experiment*: the experiment revision it belongs to, its parameter cell,
    and its declared inputs. Nothing else.

    ``workflow_snapshot`` is pinned to ``None`` on purpose. A run's workflow
    is its **experiment's** property — reached through
    ``experiment_revision_id`` — and a workflow snapshot carries a *locator*
    (``entrypoint`` / ``source`` are file paths), so folding it in would
    violate "identity is never the path": moving the defining script would
    silently change what a run *is*. The key stays in the digest input so
    hashes computed before this rule remain stable.

    ``parameters`` is typed loosely on purpose: a sweep cell is a
    ``Params`` (``Mapping[str, Any]``) and the JSON-value contract is enforced
    where it belongs — at the ``RunMetadata`` model boundary. Restating it
    here would be a promise nothing checks.

    Before this function existed there were three call sites with two
    different digest shapes (``Run.__init__`` omitted ``input_asset_ids``),
    and the server folded a synthesized snapshot in while ``Experiment.define``
    did not — so the same experiment + params got a different identity
    depending on whether a script or the HTTP API created it.

    ``config_hash`` is the profile configuration's content hash. It folds
    into the digest **only when given**: with ``None`` the ``"config_hash"``
    key is absent from the digest input, so the input is byte-identical to
    the one hashed before the key existed and every existing
    ``definition_hash`` stays stable. Two runs of the same parameters under
    different profiles are therefore two runs.

    Args:
        experiment_revision_id: The owning experiment revision.
        parameters: The run's parameter cell.
        input_asset_ids: Declared input asset ids.
        config_hash: Profile configuration hash, or ``None`` for none.

    Returns:
        The ``"sha256:…"`` definition hash.
    """
    definition: dict[str, object] = {
        "experiment_revision_id": experiment_revision_id,
        "parameters": dict(parameters or {}),
        "workflow_snapshot": None,
        "input_asset_ids": tuple(input_asset_ids),
    }
    if config_hash is not None:
        definition["config_hash"] = config_hash
    return compute_definition_hash(definition)


@register_entity_class
class Run(Folder):
    """Single execution instance within an experiment.

    Inherits :class:`Folder` (sub-spec 02): ``kind`` is
    :data:`WORKSPACE_RUN_KIND`, ``parent`` is the owning
    :class:`Experiment`. The on-disk directory uses the ``run-<id>``
    prefix preserved from the pre-refactor layout — see
    :meth:`child_dir`.

    Example::

        run = experiment.add_run(params={"lr": 0.001})
        with run.start() as ctx:
            result = my_workflow(ctx)
            ctx.set_result("output", result)
    """

    _exists_error_cls = RunExistsError
    _not_found_error_cls = RunNotFoundError

    #: Run-internal subtrees that never hold a Concept: the directories a run
    #: *produces* (per-attempt state, job output, caches, logs), as opposed to
    #: the knowledge mounted beside them. Read by
    #: :func:`molab.knowledge.types.non_concept_subdirs` when a bundle walk is
    #: standing in a run, so pruning is scoped by position, not by bare name —
    #: a Note in a directory called ``logs`` elsewhere stays visible.
    NON_CONCEPT_SUBDIRS: ClassVar[frozenset[str]] = execution_dir_names() | frozenset(
        {"executions", "assets", "cache", "logs", "source", "harness", "alive"}
    )

    def __init__(
        self,
        *,
        parent: Experiment | None = None,
        name: str | None = None,
        kind: str = WORKSPACE_RUN_KIND,
        experiment: Experiment | None = None,
        parameters: dict[str, JSONValue] | None = None,
        id: str | None = None,
        workflow_snapshot: dict[str, JSONValue] | None = None,
        target: str | None = None,
        definition_hash: str | None = None,
        experiment_revision_id: str | None = None,
        input_asset_ids: tuple[str, ...] = (),
        _entity_metadata: RunMetadata | None = None,
    ) -> None:
        resolved_parent = parent if parent is not None else experiment
        if resolved_parent is None:
            raise ValueError("Run: parent (or experiment) is required")
        # ``name`` (Folder convention) is the Run's *directory*: its parameters.
        # Identity is the UUIDv7 in ``id`` and never leaks into the path.
        meta = (
            _entity_metadata
            if _entity_metadata is not None
            else RunMetadata(
                id=id or generate_uuid7(),
                parameters=parameters or {},
                workflow_snapshot=workflow_snapshot,
                target=target,
                definition_hash=definition_hash
                or compute_run_definition_hash(
                    experiment_revision_id=experiment_revision_id,
                    parameters=parameters,
                    input_asset_ids=input_asset_ids,
                ),
                experiment_revision_id=experiment_revision_id
                or resolved_parent.metadata.revision_id,
                input_asset_ids=input_asset_ids,
            )
        )

        self._parent = resolved_parent
        self._name = name or run_slug(meta.parameters, fallback=meta.definition_hash)
        self._kind = kind
        self._root_path = None
        # Disk is resolved via the parent chain (:meth:`Folder._disk`).
        self._metadata = FolderMetadata(
            id=meta.id,
            name=name or run_slug(meta.parameters, fallback=meta.definition_hash),
            kind=kind,
            created_at=meta.created_at,
            updated_at=meta.created_at,
        )
        self._children_cache = {}

        # Entity-specific state
        self._entity_metadata: RunMetadata = meta

    # ── Folder hooks ─────────────────────────────────────────────────────

    def resolve(self) -> MolabPath:
        return MolabPath(self._disk().join(self.experiment.experiment_dir, "runs", self._name))

    @classmethod
    def child_dir(cls, parent: Folder, derived_id: str) -> MolabPath:
        """Folder hook — runs live under ``runs/<params>/``."""
        # resolve() not path() — pure layout math must not mkdir on remote.
        return MolabPath(parent._disk().join(parent.resolve(), "runs", derived_id))

    @classmethod
    def from_disk(cls, child_dir: PathArg, parent: Folder) -> Run:
        """Load ``run.json`` and rebuild entity state. See Folder.from_disk hook docs."""
        meta = _load_metadata(
            RunMetadata, parent._disk().join(child_dir, "run.json"), fs=parent._disk()
        )
        # Runs have no separate human name — ``RunMetadata`` only carries ``id``.
        folder_meta = FolderMetadata(
            id=meta.id,
            name=meta.id,
            kind=WORKSPACE_RUN_KIND,
            created_at=meta.created_at,
            updated_at=meta.created_at,
        )
        attrs = cls.base_from_disk_attrs(
            parent, folder_meta, slug=parent._disk().basename(child_dir)
        ) | {
            "_entity_metadata": meta,
        }
        return _reconstruct(cls, attrs)

    def children(self, kind: str | None = None) -> list[Folder]:  # noqa: ARG002
        """Run has no entity children — executions live under ``executions/``
        but are not Folder-tracked (sub-spec 03 may revisit)."""
        return []

    # ── Properties ──────────────────────────────────────────────────────

    @property
    def experiment(self) -> Experiment:
        """The owning :class:`Experiment` (alias for :attr:`Folder.parent`)."""
        if self._parent is None:  # pragma: no cover — Run always has a parent
            raise RuntimeError("Run has no parent experiment")
        return cast("Experiment", self._parent)

    @property
    def metadata(self) -> RunMetadata:  # type: ignore[override]
        return self._entity_metadata

    @metadata.setter
    def metadata(self, value: RunMetadata) -> None:
        self._entity_metadata = value

    @property
    def id(self) -> str:
        return self._entity_metadata.id

    @property
    def parameters(self) -> dict[str, JSONValue]:
        return self._entity_metadata.parameters

    @property
    def status(self) -> str:
        """Deprecated scalar spelling; use :attr:`status_summary`."""
        raise AttributeError(
            "Run has no scalar status in schema v2; use run.status_summary or "
            "inspect run.executions"
        )

    @property
    def status_summary(self) -> RunStatusSummary:
        """Derived counts across every Execution realizing this Run."""
        return self._execution_repository().summary()

    @property
    def status_label(self) -> str:
        """The latest attempt's status, as the one word a person reads.

        A Run has no scalar status (that is :attr:`status`, which raises on
        purpose). This label is the status of the most recent Execution —
        the state the run is in *now* — derived on every read, never stored.
        ``queued`` and ``finalizing`` are reported as themselves.

        History is not folded in: an earlier failed attempt followed by a
        successful one reads ``succeeded``. Ask :attr:`has_failures` whether
        any attempt ever failed.

        Returns:
            The latest Execution's ``status.value``, or ``"pending"`` when
            the run has no Execution at all.
        """
        executions = self.executions
        if executions:
            return executions[-1].status.value
        return RunStatus.PENDING.value

    @property
    def has_failures(self) -> bool:
        """Whether any attempt of this run ended without succeeding.

        Returns:
            True when at least one Execution is ``failed``, ``cancelled`` or
            ``interrupted``, regardless of what later attempts did.
        """
        return any(item.status in FAILED_EXECUTION_STATUSES for item in self.executions)

    @property
    def is_retryable(self) -> bool:
        """Whether resume/rerun may open a new attempt.

        A live Execution (queued/running/finalizing) must not get a concurrent
        sibling. Otherwise any failed/cancelled/interrupted attempt
        (:attr:`has_failures`) makes the run retryable.
        """
        return self.status_summary.active == 0 and self.has_failures

    @property
    def executions(self) -> list[Execution]:
        """Every physical Execution, ordered by creation time."""
        return self._execution_repository().list()

    @property
    def execution_history(self) -> list[Execution]:
        """Deprecated read alias; history is stored by Execution, not Run."""
        return self.executions

    @property
    def finished_at(self) -> datetime | None:
        """When the latest attempt ended — the timestamp beside :attr:`status_label`.

        Returns:
            The newest Execution's ``finished_at``; ``None`` when there is no
            attempt yet or the newest one is still active.
        """
        executions = self.executions
        if not executions or executions[-1].status in ACTIVE_EXECUTION_STATUSES:
            return None
        return executions[-1].finished_at

    @property
    def current_execution_id(self) -> str | None:
        """Id of the newest still-active attempt, if any."""
        active = [item for item in self.executions if item.status in ACTIVE_EXECUTION_STATUSES]
        return active[-1].id if active else None

    @property
    def run_dir(self) -> Path:
        """Alias of :attr:`Folder.path` — the run directory as ``pathlib.Path``."""
        return self.path

    def get_result(self, key: str, *, execution_id: str) -> TaskOutput:
        """Read a result value for *key*.

        Resolution order:

        1. Driver-side results persisted by ``RunContext.set_result`` into
           ``run.json`` (``context.results``) — always win when the key is
           present, even with a ``None`` value.
        2. Fallback: the completed workflow node named *key* in the run's
           most recent execution's persisted node outputs
           (``executions/<exec_id>/workflow.json``). This keeps results of
           CLI-executed runs (``molab run``), which never call
           ``set_result``, readable through the same accessor.

        Returns ``None`` when neither source has the key, when the run has
        not been executed yet, or when ``run.json`` does not exist on disk.
        A node output flagged ``outputs_lossy`` (the original value was not
        JSON-serializable, so only a truncated observability rendering was
        persisted) is never returned as a real result — a warning explains
        why and ``None`` is returned.
        """
        from .schema_version import read_versioned_json

        results_path = Path(self.run_dir / "executions" / execution_id / "results.json")
        if not results_path.exists() or results_path.stat().st_size == 0:
            return self._execution_node_output(execution_id, key)
        try:
            data = read_versioned_json(results_path)
        except (OSError, ValueError):
            return None
        results = data.get("results", {})
        if isinstance(results, dict) and key in results:
            return results[key]
        return self._execution_node_output(execution_id, key)

    def _execution_node_output(self, execution_id: str, key: str) -> TaskOutput:
        """Read one workflow node result from the selected Execution."""
        from .execution_results import read_completed_node_outputs

        record = read_completed_node_outputs(Path(str(self.run_dir)), execution_id).get(key)
        if record is None:
            return None
        if record.lossy:
            _logger.warning(
                f"run {self.id}: node output {key!r} from execution {execution_id!r} "
                f"is not returned by get_result — the original value was not "
                f"JSON-serializable, so only a lossy (truncated) observability "
                f"rendering was persisted. Make the task return a JSON-safe value, "
                f"or persist it explicitly with ctx.set_result({key!r}, ...) from a "
                f"driver-side run."
            )
            return None
        return record.value

    # ── Persistence ─────────────────────────────────────────────────────

    def materialize(self) -> None:
        d = self.run_dir
        self._disk().mkdir(d, parents=True, exist_ok=True)
        self.save()
        from .scientific_repository import ScientificRepository

        ScientificRepository(self.experiment.project.workspace.root, fs=self._disk()).record_run(
            self._definition_record(),
            experiment_id=self.experiment.id,
            path=self.run_dir,
        )

    def write_meta(self) -> str:
        """Stamp concept ``type`` on ``run.json``."""
        self.save()
        return self._disk().join(self.run_dir, "run.json")

    def _move_target_id(self, new_name: str | None) -> str:
        """A Run keeps its UUID id across a move; it has no human name to change."""
        del new_name
        return self._name

    def _sync_entity_identity(self) -> None:
        # A Run's id is immutable and it has no separate human name, so a move
        # changes nothing about its persisted identity.
        return None

    def save(self) -> None:
        with self._metadata_lock():
            self._write_run_json()

    def persist_driver_context(self, context: dict[str, object]) -> None:
        """Reject the removed Run-level runtime state channel.

        Results and workflow runtime state belong to a selected Execution.
        Keeping this method as a loud tombstone prevents an older caller from
        silently putting mutable history back into ``run.json``.
        """
        del context
        raise RuntimeError(
            "Run-level driver context was removed in schema v2; write through "
            "ExecutionContext.set_result()"
        )

    @classmethod
    def load(cls, run_dir: PathArg) -> Run:
        """Load a :class:`Run` from its on-disk directory.

        Layout contract (single implementation used by train scripts)::

            <workspace>/projects/<project>/experiments/<exp>/runs/run-<id>/

        Args:
            run_dir: Path to the ``run-<id>`` directory (contains ``run.json``).

        Returns:
            Reconstructed :class:`Run` bound to its parent experiment.

        Raises:
            FileNotFoundError: Missing workspace / project / experiment / run.json.
            RunNotFoundError: Parent chain incomplete.
        """
        from .workspace import Workspace

        run_path = Path(str(run_dir)).resolve()
        # <ws>/projects/<proj>/experiments/<exp>/runs/run-<id>
        # parents: [0]=runs, [1]=exp, [2]=experiments, [3]=proj, [4]=projects, [5]=ws
        workspace_root = run_path.parents[5]
        project_id = run_path.parents[3].name
        experiment_id = run_path.parents[1].name
        run_name = run_path.name
        run_id = run_name.removeprefix("run-") if run_name.startswith("run-") else run_name

        workspace = Workspace.load(workspace_root)
        project = workspace.project(project_id)
        experiment = project.experiment(experiment_id)
        # Prefer loading via experiment so cache/indices stay consistent.
        if experiment.has_run(run_id):
            return experiment.get_run(run_id)
        # Fallback: reconstruct from run.json (NFS race / partial index).
        meta = _load_metadata(RunMetadata, run_path / "run.json")
        return _reconstruct(cls, {"experiment": experiment, "metadata": meta})

    # ── Execution ───────────────────────────────────────────────────────

    def start(
        self,
        profile_config: ProfileConfig | None = None,
        *,
        execution_id: str | None = None,
        mode: ExecutionMode = ExecutionMode.INITIAL,
        based_on_execution_id: str | None = None,
        checkpoint_artifact_id: str | None = None,
        bypass_cache: bool = False,
    ) -> RunContext:
        """Return a context manager for executing this run.

        The returned :class:`RunContext` supports both ``with`` and
        ``async with`` — choose whichever matches the caller's body.
        For the no-arg case, ``Run`` itself is also a context manager
        (sugar that calls ``self.start()`` internally); see
        :meth:`__enter__` / :meth:`__aenter__`.

        Args:
            profile_config: The active molcfg profile; when omitted the run
                executes with an empty (defaults-only) :class:`ProfileConfig`.
            execution_id: Start a pre-allocated attempt — used by external
                submitters (e.g. molq, the plugin that hands an attempt to a
                cluster's batch-queue scheduler) that need to know the
                per-attempt directory ahead of worker startup. When the
                record already exists, ``mode``, ``based_on_execution_id``,
                ``checkpoint_artifact_id`` and ``bypass_cache`` are ignored:
                the record was fixed when it was created.
            mode: How a newly created attempt relates to earlier ones.
            based_on_execution_id: The predecessor of a newly created attempt.
            checkpoint_artifact_id: The checkpoint a newly created ``resume``
                attempt starts from.
            bypass_cache: Record that a newly created attempt ignores the
                workflow node cache — the per-task result store that lets an
                unchanged task reuse its earlier output instead of running
                again. Read back as ``ctx.bypass_cache``.

        Returns:
            An un-entered :class:`RunContext`; entering it creates (if needed)
            and starts the attempt.
        """
        return RunContext(
            self,
            profile_config=profile_config,
            execution_id=execution_id,
            mode=mode,
            based_on_execution_id=based_on_execution_id,
            checkpoint_artifact_id=checkpoint_artifact_id,
            bypass_cache=bypass_cache,
        )

    def create_execution(
        self,
        *,
        mode: ExecutionMode = ExecutionMode.INITIAL,
        based_on_execution_id: str | None = None,
        checkpoint_artifact_id: str | None = None,
        bypass_cache: bool = False,
        profile_config: ProfileConfig | None = None,
        environment: dict[str, JSONValue] | None = None,
        executor: dict[str, JSONValue] | None = None,
        created_by: AgentRef | None = None,
        source_entrypoint: PathArg | None = None,
    ) -> Execution:
        """Record a new QUEUED attempt carrying its creation-time facts only.

        The one public way to allocate an attempt (``e01``, ``e02``, …) ahead
        of starting it. A *profile* is the named configuration the run
        executes under (a :class:`ProfileConfig`). The record's
        ``environment`` always holds the three profile keys ``profile`` (its
        name) / ``config`` (its contents) / ``config_hash`` (a digest of it)
        built from *profile_config* (``config_hash`` is ``None`` for an
        empty, unnamed profile); the caller's *environment* (e.g. ``script``,
        ``submit_cwd``) is merged in beside them. Start-time facts (host,
        python, platform, pid) are added later, once, by whoever starts the
        attempt.

        Key rules, checked before anything is written:

        - ``profile`` / ``config`` / ``config_hash`` come only from
          *profile_config*; naming one in *environment* is refused.
        - The start-time keys ``host`` / ``pid`` / ``python`` / ``platform``
          are refused in *environment* **and** *executor*. Starting never
          overwrites an existing key, and the zombie reaper (``run_reaper``,
          which marks a ``running`` attempt failed once its owning process on
          the recorded host is gone) trusts the recorded host, so a
          creator-written host would pin it to a machine the attempt never
          ran on.

        Source capture, when *source_entrypoint* is given, runs in this
        order, after the key rules:

        1. Build the :class:`SourceManifest` (the entrypoint and its
           first-party imports, with digests and VCS state) from the
           originals. A missing entrypoint or an unreadable file raises
           here, before any record exists.
        2. Create the QUEUED record with ``source=`` that manifest.
        3. Copy the files into this attempt's ``executions/eNN/source/`` and
           verify each copy against the manifest. If that fails — or is
           interrupted (``KeyboardInterrupt`` / ``SystemExit``) — the attempt
           is sealed ``failed`` with error type ``SourceCaptureError`` (the
           record keeps the manifest it tried to capture) and the error is
           raised, so no QUEUED record claims source it does not hold. An
           interrupt is re-raised as itself, not wrapped.

        The ``ExecutionCreated`` history commit therefore precedes the
        ``source/`` files; history is a soft dependency, and the later
        Started / Sealed commits carry the files. Nothing is written to a
        run-level ``runs/<slug>/source/``: source belongs to the attempt.

        Args:
            mode: How this attempt relates to earlier ones.
            based_on_execution_id: The predecessor, when *mode* needs one.
            checkpoint_artifact_id: The checkpoint to resume from (``resume`` only).
            bypass_cache: Whether the attempt ignores the workflow node cache;
                recorded once and never changed.
            profile_config: The active profile; ``None`` means empty and unnamed.
            environment: Extra creation-time environment facts.
            executor: Creation-time executor facts (backend, target).
            created_by: Who creates the attempt; defaults to this process.
            source_entrypoint: The workflow script to capture; ``None``
                captures nothing and leaves ``source`` unset.

        Returns:
            The QUEUED record as written.

        Raises:
            ValueError: *environment* names a profile key, *environment* or
                *executor* names a start-time key, or *mode* and the
                predecessor / checkpoint disagree.
            KeyError: The named predecessor does not exist.
            FileNotFoundError: *source_entrypoint* is not a file; no record
                is created.
            SourceCaptureError: A file in the source closure exists but
                cannot be read (raised before any record exists), or the
                source copy failed or did not match the manifest (the attempt
                was sealed ``failed``).
        """
        extra = dict(environment or {})
        profile_conflicts = sorted(_PROFILE_KEYS & extra.keys())
        if profile_conflicts:
            raise ValueError(f"environment keys {profile_conflicts} come only from profile_config")
        start_conflicts = sorted(_START_TIME_KEYS & (extra.keys() | (executor or {}).keys()))
        if start_conflicts:
            raise ValueError(
                f"start-time keys {start_conflicts} cannot be recorded at creation; "
                "they are added when the Execution starts"
            )
        manifest = source_manifest(source_entrypoint) if source_entrypoint is not None else None
        repo = self._execution_repository()
        state = repo.create(
            mode=mode,
            created_by=created_by or _system_agent(),
            based_on_execution_id=based_on_execution_id,
            checkpoint_artifact_id=checkpoint_artifact_id,
            executor=dict(executor or {}),
            environment={**_creation_environment(profile_config), **extra},
            bypass_cache=bypass_cache,
            source=manifest,
        )
        if manifest is None:
            return state
        try:
            copy_sources(manifest, repo.execution_dir(state.id), fs=repo.fs)
        except BaseException as exc:
            # BaseException too: an interrupt between create and copy must not
            # leave a QUEUED record naming source files that are not on disk.
            message = (
                str(exc)
                if isinstance(exc, Exception)
                else f"source capture interrupted by {type(exc).__name__}"
            )
            repo.seal(
                state.id,
                ExecutionStatus.FAILED,
                error={"type": "SourceCaptureError", "message": message},
            )
            if isinstance(exc, SourceCaptureError) or not isinstance(exc, Exception):
                raise
            raise SourceCaptureError(str(exc)) from exc
        return state

    def execution(self, execution_id: str) -> Execution:
        """Read one attempt of this run.

        Args:
            execution_id: The attempt id (``e01``).

        Returns:
            The attempt's current record.

        Raises:
            KeyError: No attempt ``execution_id`` exists under this run.
        """
        return self._execution_repository().get(execution_id)

    def execute(
        self,
        workflow: object,
        /,
        *,
        resume: bool = False,
        rerun: bool = False,
        fresh: bool = False,
        checkpoint_artifact_id: str | None = None,
    ) -> object:
        """Execute *workflow* against this run in one step and return the result.

        Folds the driver dance — ``run.start()`` context, workflow-runtime
        dispatch, asyncio plumbing — into a single synchronous call on the
        same execution path ``molab run`` uses (RunContext lifecycle: status
        machine, ``alive`` heartbeat). *workflow* is a
        ``CompiledWorkflow`` or an uncompiled ``Workflow``
        (auto-compiled). Returns a ``molab.workflow.WorkflowResult`` whose
        ``.outputs`` maps task name → output.

        Verbs mirror the CLI: a ``pending`` run executes (first attempt); a
        ``failed`` / ``cancelled`` run *resumes* its last execution, or opens
        a fresh attempt with ``rerun=True`` (``--rerun``); ``fresh=True``
        additionally bypasses the cache read and requires ``rerun=True``
        (``--rerun --fresh``); a ``succeeded`` run and a live ``running`` run
        always refuse (done is done; cancel first). A task failure raises
        ``molab.workflow.RunFailedError`` (the failed state is persisted;
        never silent).

        Must be called from sync code; inside a running event loop use
        :meth:`aexecute`. Delegates through the :func:`set_run_executor`
        seam so workspace never imports the workflow layer.
        """
        return require_run_executor().execute(
            self,
            workflow,
            resume=resume,
            rerun=rerun,
            fresh=fresh,
            checkpoint_artifact_id=checkpoint_artifact_id,
        )

    async def aexecute(
        self,
        workflow: object,
        /,
        *,
        resume: bool = False,
        rerun: bool = False,
        fresh: bool = False,
        checkpoint_artifact_id: str | None = None,
    ) -> object:
        """Async variant of :meth:`execute` — same semantics, awaitable."""
        return await require_run_executor().aexecute(
            self,
            workflow,
            resume=resume,
            rerun=rerun,
            fresh=fresh,
            checkpoint_artifact_id=checkpoint_artifact_id,
        )

    # ── Sugar: ``with run as ctx:`` / ``async with run as ctx:`` ────────
    #
    # Equivalent to ``with run.start() as ctx:`` / ``async with``. Sugar
    # form does not accept ``profile_config`` / ``execution_id``; for
    # those, call ``run.start(...)`` explicitly. Internally we cache the
    # ``RunContext`` on first ``__enter__`` so ``__exit__`` sees the
    # same instance.

    def __enter__(self) -> RunContext:
        self._sugar_ctx = self.start()
        return self._sugar_ctx.__enter__()

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:  # noqa: ANN001
        ctx = self._sugar_ctx
        del self._sugar_ctx
        return ctx.__exit__(exc_type, exc_val, exc_tb)

    async def __aenter__(self) -> RunContext:
        self._sugar_ctx = self.start()
        return await self._sugar_ctx.__aenter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:  # noqa: ANN001
        ctx = self._sugar_ctx
        del self._sugar_ctx
        return await ctx.__aexit__(exc_type, exc_val, exc_tb)

    def cancel(self, execution_id: str) -> None:
        """Cancel one selected active Execution; a Run itself is not cancellable."""
        self._execution_repository().seal(execution_id, ExecutionStatus.CANCELLED)

    def _execution_repository(self) -> ExecutionRepository:
        workspace = self.experiment.project.workspace
        return ExecutionRepository(
            workspace.root,
            self.run_dir,
            run_id=self.id,
            project_id=self.experiment.project.id,
            fs=workspace.fs,
        )

    # ── Internal (frozen-metadata mutation helpers) ──────────────────────

    def _set_status(self, status: RunStatus) -> None:
        self._update_metadata(status=status)

    @contextlib.contextmanager
    def _metadata_lock(self) -> Iterator[None]:
        """Advisory inter-process lock guarding ``run.json`` read-modify-write.

        The lock file lives under the workspace's ``.molab/locks/`` — machine
        state never sits in a scientific directory. Degrades to a no-op when
        the workspace is not a lockable local path (remote filesystems,
        non-POSIX platforms) — see
        :func:`molab.workspace._file_lock.file_lock`.
        """
        from ._file_lock import file_lock

        locks = Path(str(self.experiment.project.workspace.root)) / ".molab" / "locks"
        locks.mkdir(parents=True, exist_ok=True)
        with file_lock(locks / f"{self.id}.run.lock"):
            yield

    def _reload_metadata_from_disk(self) -> None:
        """Refresh in-memory metadata from ``run.json`` when it exists.

        Called under :meth:`_metadata_lock` before applying a partial
        update, so concurrent writers (server, CLI, detached workers)
        layering updates onto *distinct* fields don't drop each other's
        writes. Missing or unreadable files keep the in-memory copy
        (first write before ``materialize()``, remote filesystems).
        """
        path = self._disk().join(self.run_dir, "run.json")
        try:
            if not self._disk().exists(path):
                return
            self._entity_metadata = _load_metadata(RunMetadata, path, fs=self._disk())
        except Exception:
            _logger.debug(f"run {self.id}: could not reload run.json; keeping in-memory copy")

    def _write_run_json(self, *, context: dict[str, object] | None = None) -> None:
        """Write only logical Run definition fields to ``run.json``.

        ``RunMetadata`` temporarily retains deprecated fields as an in-memory
        compatibility shell for callers being migrated. They are deliberately
        excluded here: operational state and results can only be persisted by
        an Execution.
        """
        from .file_store import FileStore
        from .schema_version import versioned_payload

        fs = self._disk()
        del context
        payload: dict[str, object] = dict(self._definition_record())
        FileStore(self.run_dir, fs=fs).put("run.json", versioned_payload(payload))

    def _definition_record(self) -> dict[str, JSONValue]:
        """Return the portable logical definition shared by view + provenance."""
        return self.metadata.model_dump(
            mode="json",
            include={
                "id",
                "type",
                "parameters",
                "created_at",
                "definition_hash",
                "experiment_revision_id",
                "input_asset_ids",
                "workflow_snapshot",
                "target",
                "workflow_id",
                "workflow_version",
            },
        )

    def _update_metadata(self, **updates: object) -> None:
        """Forward field updates into ``RunMetadata.model_copy`` and persist.

        Values flow through pydantic's per-field validators; the parameter
        type is the true Python top-type ``object`` (not ``Any`` — the
        function does not interact with the values, it only forwards
        them, and pydantic owns the per-field type contract).

        The read-modify-write cycle (reload from disk → apply updates →
        atomic save) runs under :meth:`_metadata_lock` so concurrent
        processes updating different fields cannot drop each other's
        writes (lost-update protection). Status, ownership, and
        execution history are first-class ``RunMetadata`` fields and
        may be written here.
        """
        with self._metadata_lock():
            self._reload_metadata_from_disk()
            self.metadata = self.metadata.model_copy(update=updates)
            self._write_run_json()

    def update_provenance(self, **updates: object) -> None:
        """Patch ``RunMetadata`` fields on ``run.json`` and persist.

        Public spelling used by ``molab run``, the molq submit plugin, and
        the server start route. Same contract as :meth:`_update_metadata`.
        """
        self._update_metadata(**updates)
