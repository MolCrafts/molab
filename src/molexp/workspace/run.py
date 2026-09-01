"""Run entity and RunContext execution lifecycle.

A **Run** represents a single execution instance within an experiment.
**RunContext** is the context manager that handles lifecycle, artifacts,
checkpoints, and asset access during execution.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path  # local-FS path for RunContext (LLM/worker-local I/O)
from typing import TYPE_CHECKING, Protocol, cast

from mollog import get_logger

from molexp._typing import (
    JSONValue,
    TaskOutput,
)
from molexp.knowledge.types import concept_type
from molexp.path import Path as MolexpPath
from molexp.profile import ProfileConfig

from .assets import AssetScope
from .base import (
    _load_metadata,
    _reconstruct,
)
from .errors import RunExistsError, RunNotFoundError
from .folder import WORKSPACE_RUN_KIND, Folder
from .fs import PathArg
from .models import (
    ExecutionRecord,
    FolderMetadata,
    RunMetadata,
    RunStatus,
)
from .run_heartbeat import unlink_alive
from .utils import generate_id

if TYPE_CHECKING:
    from .experiment import Experiment
    from .knowledge import Knowledge

# Re-exported for backward compatibility — the canonical definition now
# lives in ``.models`` so the run-lifecycle collaborators can import it
# without a circular ``run.py`` dependency.
from .runcontext import RunContext

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
# Protocol below and registers itself at ``import molexp.workflow`` time
# (see ``molexp.workflow.execute``), so by the time a caller holds a workflow
# object to pass in, the seam is wired.


class RunWorkflowExecutor(Protocol):
    """One-step tracked execution of a workflow against a :class:`Run`.

    Implemented by ``molexp.workflow.execute`` and registered via
    :func:`set_run_executor`. ``workflow`` is opaque to workspace (a
    ``CompiledWorkflow`` / ``Workflow``, or ``None`` to resolve the
    experiment's bound workflow); the return value is an opaque
    ``molexp.workflow.WorkflowResult``.
    """

    def execute(
        self,
        run: Run,
        workflow: object | None,
        *,
        resume: bool = False,
        rerun: bool = False,
        fresh: bool = False,
    ) -> object: ...

    async def aexecute(
        self,
        run: Run,
        workflow: object | None,
        *,
        resume: bool = False,
        rerun: bool = False,
        fresh: bool = False,
    ) -> object: ...


_run_executor: RunWorkflowExecutor | None = None


def set_run_executor(executor: RunWorkflowExecutor) -> None:
    """Register the workflow-layer implementation backing :meth:`Run.execute`.

    Called once at ``import molexp.workflow`` time. Until then,
    :meth:`Run.execute` (and ``RunSet.execute``) fail fast — never a silent
    fallback.
    """
    global _run_executor
    _run_executor = executor


def require_run_executor() -> RunWorkflowExecutor:
    """Return the registered executor, or fail fast with guidance."""
    if _run_executor is None:
        raise RuntimeError(
            "Run.execute needs the workflow layer; `import molexp.workflow` "
            "(e.g. `from molexp.workflow import Workflow`) registers "
            "the executor."
        )
    return _run_executor


# ── Run ─────────────────────────────────────────────────────────────────────


@concept_type(WORKSPACE_RUN_KIND)
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
        _entity_metadata: RunMetadata | None = None,
    ) -> None:
        resolved_parent = parent if parent is not None else experiment
        if resolved_parent is None:
            raise ValueError("Run: parent (or experiment) is required")
        # ``name`` (Folder convention) is the Run's id — Run has no
        # human-readable name distinct from its slug.
        meta = (
            _entity_metadata
            if _entity_metadata is not None
            else RunMetadata(
                id=id or name or generate_id(),
                parameters=parameters or {},
                workflow_snapshot=workflow_snapshot,
                target=target,
            )
        )

        self._parent = resolved_parent
        self._name = meta.id
        self._kind = kind
        self._root_path = None
        # Disk is resolved via the parent chain (:meth:`Folder._disk`).
        self._metadata = FolderMetadata(
            id=meta.id,
            name=meta.id,  # Run has no separate display name
            kind=kind,
            created_at=meta.created_at,
            updated_at=meta.created_at,
        )
        self._children_cache = {}

        # Entity-specific state
        self._entity_metadata: RunMetadata = meta

    # ── Folder hooks ─────────────────────────────────────────────────────

    def resolve(self) -> MolexpPath:
        return MolexpPath(
            self._disk().join(self.experiment.experiment_dir, "runs", f"run-{self.id}")
        )

    @classmethod
    def child_dir(cls, parent: Folder, derived_id: str) -> MolexpPath:
        """Folder hook — runs live under ``runs/run-<id>/``."""
        # resolve() not path() — pure layout math must not mkdir on remote.
        return MolexpPath(parent._disk().join(parent.resolve(), "runs", f"run-{derived_id}"))

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
        attrs = cls.base_from_disk_attrs(parent, folder_meta) | {
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
        """Current run status, sourced from ``run.json`` (:class:`RunMetadata`)."""
        return self.metadata.status.value

    @property
    def is_retryable(self) -> bool:
        """Whether ``resume`` / ``rerun`` apply (status in :data:`RETRYABLE_STATUSES`)."""
        return self.status in RETRYABLE_STATUSES

    @property
    def execution_history(self) -> list[ExecutionRecord]:
        """Run-level execution history, read from ``run.json``."""
        return list(self.metadata.execution_history)

    @property
    def finished_at(self) -> datetime | None:
        """Terminal timestamp, read from ``run.json``."""
        return self.metadata.finished_at

    @property
    def current_execution_id(self) -> str | None:
        """Active/last execution id, read from ``run.json``."""
        return self.metadata.current_execution_id

    @property
    def run_dir(self) -> Path:
        """Alias of :attr:`Folder.path` — the run directory as ``pathlib.Path``."""
        return self.path

    @property
    def scope(self):  # noqa: ANN201

        return AssetScope(
            kind="run",
            ids=(self.experiment.project.id, self.experiment.id, self.id),
        )

    @property
    def assets(self):  # noqa: ANN201
        """Scope-filtered asset view (read-only queries) for this run."""
        from .assets import AssetsView

        return AssetsView(self.experiment.project.workspace.root, self.scope)

    def get_result(self, key: str) -> TaskOutput:
        """Read a result value for *key*.

        Resolution order:

        1. Driver-side results persisted by ``RunContext.set_result`` into
           ``run.json`` (``context.results``) — always win when the key is
           present, even with a ``None`` value.
        2. Fallback: the completed workflow node named *key* in the run's
           most recent execution's persisted node outputs
           (``executions/<exec_id>/workflow.json``). This keeps results of
           CLI-executed runs (``molexp run``), which never call
           ``set_result``, readable through the same accessor.

        Returns ``None`` when neither source has the key, when the run has
        not been executed yet, or when ``run.json`` does not exist on disk.
        A node output flagged ``outputs_lossy`` (the original value was not
        JSON-serializable, so only a truncated observability rendering was
        persisted) is never returned as a real result — a warning explains
        why and ``None`` is returned.
        """
        from .schema_version import read_versioned_json

        run_json = Path(self.run_dir / "run.json")
        if not run_json.exists() or run_json.stat().st_size == 0:
            return None
        try:
            data = read_versioned_json(run_json)
        except (OSError, ValueError):
            return None
        results = data.get("context", {}).get("results", {})
        if isinstance(results, dict) and key in results:
            return results[key]
        return self._latest_execution_node_output(key)

    def _latest_execution_node_output(self, key: str) -> TaskOutput:
        """Fallback for :meth:`get_result` — read *key* from the latest execution.

        The execution history (newest last) is sourced from ``run.json``;
        its last entry names the most recent attempt. Read-only: nothing
        is written back to disk.
        """
        history = self.metadata.execution_history
        if not history:
            return None
        execution_id = history[-1].execution_id
        if not execution_id:
            return None
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

    def write_meta(self) -> str:
        """Stamp concept ``type`` on ``run.json``."""
        self.save()
        return self._disk().join(self.run_dir, "run.json")

    def _sync_entity_identity(self) -> None:
        """Mirror the folder identity into ``run.json`` (``move_to`` hook)."""
        self._entity_metadata = self._entity_metadata.model_copy(update={"id": self._name})
        self.save()

    def save(self) -> None:
        with self._metadata_lock():
            self._write_run_json()

    def persist_driver_context(self, context: dict[str, object]) -> None:
        """Write the driver ``context`` blob under the same lock as identity.

        ``run.json`` is one file: ``RunMetadata`` fields plus an optional
        ``context`` section (results / workflow snapshot used by
        :class:`~molexp.workspace.run_context.ContextStore`). Identity
        writes preserve an existing ``context``; this method is the only
        updater of that section.
        """
        with self._metadata_lock():
            self._reload_metadata_from_disk()
            self._write_run_json(context=context)

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
    ) -> RunContext:
        """Return a context manager for executing this run.

        *profile_config* selects the active molcfg profile; when omitted
        the run executes with an empty (defaults-only) :class:`ProfileConfig`.

        *execution_id* pre-allocates the execution slot — used by external
        submitters (e.g. molq) that need to know the per-attempt directory
        ahead of worker startup.

        The returned :class:`RunContext` supports both ``with`` and
        ``async with`` — choose whichever matches the caller's body.
        For the no-arg case, ``Run`` itself is also a context manager
        (sugar that calls ``self.start()`` internally); see
        :meth:`__enter__` / :meth:`__aenter__`.
        """
        return RunContext(self, profile_config=profile_config, execution_id=execution_id)

    def execute(
        self,
        workflow: object,
        /,
        *,
        resume: bool = False,
        rerun: bool = False,
        fresh: bool = False,
    ) -> object:
        """Execute *workflow* against this run in one step and return the result.

        Folds the driver dance — ``run.start()`` context, workflow-runtime
        dispatch, asyncio plumbing — into a single synchronous call on the
        same execution path ``molexp run`` uses (RunContext lifecycle: status
        machine, ``alive`` heartbeat). *workflow* is a
        ``CompiledWorkflow`` or an uncompiled ``Workflow``
        (auto-compiled). Returns a ``molexp.workflow.WorkflowResult`` whose
        ``.outputs`` maps task name → output.

        Verbs mirror the CLI: a ``pending`` run executes (first attempt); a
        ``failed`` / ``cancelled`` run *resumes* its last execution, or opens
        a fresh attempt with ``rerun=True`` (``--rerun``); ``fresh=True``
        additionally bypasses the cache read and requires ``rerun=True``
        (``--rerun --fresh``); a ``succeeded`` run and a live ``running`` run
        always refuse (done is done; cancel first). A task failure raises
        ``molexp.workflow.RunFailedError`` (the failed state is persisted;
        never silent).

        Must be called from sync code; inside a running event loop use
        :meth:`aexecute`. Delegates through the :func:`set_run_executor`
        seam so workspace never imports the workflow layer.
        """
        return require_run_executor().execute(
            self, workflow, resume=resume, rerun=rerun, fresh=fresh
        )

    async def aexecute(
        self,
        workflow: object,
        /,
        *,
        resume: bool = False,
        rerun: bool = False,
        fresh: bool = False,
    ) -> object:
        """Async variant of :meth:`execute` — same semantics, awaitable."""
        return await require_run_executor().aexecute(
            self, workflow, resume=resume, rerun=rerun, fresh=fresh
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

    def cancel(self) -> None:
        """Mark the run as cancelled and persist the terminal state.

        Sets ``status=cancelled`` + ``finished_at``, clears the ownership
        stamp, and unlinks the ``alive`` heartbeat file. All JSON writes
        go through ``run.json``.
        """
        now = datetime.now()
        unlink_alive(self)
        self._update_metadata(
            status=RunStatus.CANCELLED,
            finished_at=now,
            owner_pid=None,
            owner_host=None,
        )

    def harvest(
        self,
        *,
        cls: type,
        narrative: str,
        created_by: str,
        results: dict[str, JSONValue] | None = None,
        name: str | None = None,
    ) -> Knowledge:
        """Harvest this terminal run into sourced Knowledge under its experiment."""
        from .harvest import harvest_run

        return harvest_run(
            self,
            cls=cls,
            narrative=narrative,
            created_by=created_by,
            results=results,
            name=name,
        )

    def delete_execution(self, execution_id: str) -> None:
        """Delete a single execution attempt from this run.

        Removes ``executions/<execution_id>/`` on disk and pops the matching
        entry from ``execution_history``.  The run itself is left intact.

        Raises:
            KeyError: If the execution id is not present under this run.
        """
        import shutil

        exec_dir = Path(self.run_dir / "executions" / execution_id)
        history = list(self.metadata.execution_history)
        matched_idx = next(
            (i for i, rec in enumerate(history) if rec.execution_id == execution_id),
            None,
        )
        if matched_idx is None and not exec_dir.exists():
            raise KeyError(f"Execution '{execution_id}' not found under run '{self.id}'")
        if exec_dir.exists():
            shutil.rmtree(exec_dir)
        if matched_idx is not None:
            history.pop(matched_idx)
            self._update_metadata(execution_history=tuple(history))

    # ── Internal (frozen-metadata mutation helpers) ──────────────────────

    def _set_status(self, status: RunStatus) -> None:
        self._update_metadata(status=status)

    @contextlib.contextmanager
    def _metadata_lock(self) -> Iterator[None]:
        """Advisory inter-process lock guarding ``run.json`` read-modify-write.

        Uses a ``run.json.lock`` sidecar next to ``run.json``. Degrades to
        a no-op when the run directory is not a lockable local path (remote
        filesystems, non-POSIX platforms) — see
        :func:`molexp.workspace._file_lock.file_lock`.
        """
        from ._file_lock import file_lock

        with file_lock(Path(str(self.run_dir)) / "run.json.lock"):
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
        """Atomically write ``run.json``. Caller holds :meth:`_metadata_lock`.

        When *context* is omitted, any existing ``context`` section on disk is
        preserved so status/ownership updates cannot drop driver results.
        """
        from .file_store import FileStore
        from .schema_version import read_versioned_json, versioned_payload

        fs = self._disk()
        path = fs.join(self.run_dir, "run.json")
        payload: dict[str, object] = dict(self.metadata.model_dump(mode="json"))
        existing_context: object = None
        try:
            if fs.exists(path):
                existing_context = read_versioned_json(path, fs=fs).get("context")
        except Exception:
            existing_context = None
        if context is not None:
            payload["context"] = context
        elif isinstance(existing_context, dict):
            payload["context"] = existing_context
        FileStore(self.run_dir, fs=fs).put("run.json", versioned_payload(payload))

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

        Public spelling used by ``molexp run``, the molq submit plugin, and
        the server start route. Same contract as :meth:`_update_metadata`.
        """
        self._update_metadata(**updates)
