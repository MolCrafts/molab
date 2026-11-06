"""Public context for one physical Execution of a logical Run."""

from __future__ import annotations

import atexit
import contextlib
import json
import os
import platform
import sys
import threading
import traceback
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, cast

from mollog import get_logger

from molab._typing import JSONValue, TaskOutput
from molab.profile import ProfileConfig

from .domain import (
    Asset,
    Execution,
    ExecutionMode,
    ExecutionOrigin,
    ExecutionStatus,
)
from .execution_dirs import (
    CHECKPOINTS,
    OUT,
    WORK,
    ExecutionDir,
    list_execution_dirs,
    resolve_execution_dir,
)
from .execution_repository import _START_TIME_KEYS, STDIO_FILES, ExecutionRepository
from .file_store import FileStore
from .history import AgentRef
from .metrics_seam import MetricRecord, create_metrics_writer
from .run_heartbeat import HEARTBEAT_INTERVAL_SECONDS, touch_alive, unlink_alive
from .tracking import (
    EXECUTION_DIR_ENV,
    MANIFEST,
    STAGED_DIR,
    TASK_ENV,
    StagedFile,
    StdioFiles,
    Stream,
    TrackedMetrics,
    Tracker,
    bind,
    current,
    current_task,
    enter_task,
    exit_task,
    manifest_entries,
    unbind,
)

if TYPE_CHECKING:
    from contextvars import Token
    from types import TracebackType

    from .run import Run

_logger = get_logger(__name__)


def _register_filename(title: str, data: object) -> str:
    """A filename for in-memory bytes registered under *title*."""
    from .naming import entity_slug

    slug = entity_slug(title, fallback="asset")
    if isinstance(data, (bytes, bytearray)):
        return slug
    if isinstance(data, (dict, list)):
        return f"{slug}.json"
    return f"{slug}.txt"


def _system_agent() -> AgentRef:
    host = platform.node() or "local"
    return AgentRef(
        id=f"process:{host}:{os.getpid()}",
        type="system",
        name=f"Python {platform.python_version()} on {host}",
    )


def profile_config_hash(profile_config: ProfileConfig | None) -> str | None:
    """Hash the effective configuration of a profile, or ``None`` when there is none.

    The one ``config_hash`` rule: an Execution record's
    ``environment.config_hash`` and the ``config_hash`` folded into a run's
    ``definition_hash`` both come from here, so the two always agree for the
    same profile.

    The hash is content-only. It is ``ProfileConfig.content_hash()``, which
    covers the configuration data and not the profile name: the name is a
    label, recorded per attempt as ``environment.profile``, and is not part of
    identity. Two profiles with the same content but different names therefore
    hash the same. A name still marks the profile as present, so a named empty
    profile hashes to the empty content's hash rather than ``None``.

    Args:
        profile_config: The active profile; ``None`` is treated as an empty,
            unnamed one.

    Returns:
        ``profile_config.content_hash()`` when the profile has content or a
        name, otherwise ``None``.
    """
    cfg = profile_config if profile_config is not None else ProfileConfig({}, name=None)
    return cfg.content_hash() if len(cfg) > 0 or cfg.name else None


_PROFILE_FACTS: dict[str, Callable[[ProfileConfig], JSONValue]] = {
    "profile": lambda cfg: cfg.name,
    "config": lambda cfg: cfg.to_dict(),
    "config_hash": profile_config_hash,
}
"""How each profile-derived environment key is computed at creation."""

_PROFILE_KEYS: frozenset[str] = frozenset(_PROFILE_FACTS)
"""Environment keys that only ``profile_config`` may supply at creation."""

_START_FACTS: dict[str, Callable[[], JSONValue]] = {
    "python": lambda: sys.version,
    "platform": platform.platform,
    "host": platform.node,
    "pid": os.getpid,
}
"""How each start-time key (``_START_TIME_KEYS``) is read from this process."""

_EXECUTOR_START_KEYS: frozenset[str] = frozenset({"host", "pid"})
"""The start-time keys a local starter also writes into ``executor``."""


def _creation_environment(
    profile_config: ProfileConfig | None,
    *,
    inherit_from: Execution | None = None,
) -> dict[str, JSONValue]:
    """Build the creation-time environment from the active profile.

    The one home of the profile rule shared by every creator: every key in
    ``_PROFILE_KEYS`` is always written, and ``config_hash`` is set only when
    the profile has content or a name.

    Inheritance (arch-own-03a, D57): with *profile_config* ``None`` and an
    *inherit_from* predecessor, the three keys are copied verbatim from the
    predecessor's recorded environment; a key it lacks is written as
    ``None``. An explicit *profile_config* (even an empty one) always wins.

    Args:
        profile_config: The active profile; ``None`` means an empty, unnamed
            one, or the predecessor's when *inherit_from* is given.
        inherit_from: The predecessor whose recorded config a non-initial
            attempt inherits when no profile is passed.

    Returns:
        A dict whose keys are exactly ``_PROFILE_KEYS``.
    """
    if profile_config is None and inherit_from is not None:
        recorded = inherit_from.environment
        return {key: recorded.get(key) for key in _PROFILE_FACTS}
    cfg = profile_config if profile_config is not None else ProfileConfig({}, name=None)
    return {key: fact(cfg) for key, fact in _PROFILE_FACTS.items()}


def _recorded_config(environment: dict[str, JSONValue]) -> ProfileConfig:
    """The profile an attempt runs with, projected from its recorded environment.

    Args:
        environment: The record's ``environment``.

    Returns:
        A :class:`ProfileConfig` built from the recorded ``config`` and
        ``profile`` (empty and unnamed where they are missing).
    """
    recorded_config = environment.get("config")
    recorded_profile = environment.get("profile")
    return ProfileConfig(
        dict(recorded_config) if isinstance(recorded_config, dict) else {},
        name=recorded_profile if isinstance(recorded_profile, str) else None,
    )


def _start_environment() -> dict[str, JSONValue]:
    """The start-time environment facts of the current process.

    Returns:
        A dict whose keys are exactly ``_START_TIME_KEYS``.
    """
    return {key: _START_FACTS[key]() for key in _START_TIME_KEYS}


def _start_executor(environment: dict[str, JSONValue]) -> dict[str, JSONValue]:
    """The start-time executor facts, taken from the start-time environment.

    Args:
        environment: The result of ``_start_environment``.

    Returns:
        ``kind`` (always ``"local"``) plus ``_EXECUTOR_START_KEYS`` from
        *environment*.
    """
    return {"kind": "local", **{key: environment[key] for key in _EXECUTOR_START_KEYS}}


class _BoundEvidenceLog:
    """One evidence log of an attempt: ``run.log``, ``stdout.log`` or ``stderr.log``.

    ``stdout`` / ``stderr`` append through the attempt's :class:`StdioFiles`,
    the same handles and locks ``molab.print`` uses, so a line appended here
    never splits a printed line (D92). ``run`` keeps its own file.
    """

    def __init__(
        self,
        path: Path,
        *,
        stdio: StdioFiles | None = None,
        stream: Stream | None = None,
    ) -> None:
        self.path = path
        self._stdio = stdio
        self._stream = stream

    def append(self, line: str) -> None:
        payload = line if line.endswith("\n") else line + "\n"
        if self._stdio is not None and self._stream is not None:
            self._stdio.write(self._stream, payload, flush=True)
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(payload)

    def tail(self, n: int = 100) -> list[str]:
        if self._stdio is not None and self._stream is not None:
            self._stdio.flush(self._stream)
        if not self.path.exists():
            return []
        return self.path.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]


class _ExecutionLogs:
    """Execution evidence streams; these are deliberately not Artifacts."""

    def __init__(self, execution_dir: Path, stdio: StdioFiles | None = None) -> None:
        self._execution_dir = execution_dir
        self._stdio = stdio

    def __call__(self, name: str = "run") -> _BoundEvidenceLog:
        if name not in {"run", "stdout", "stderr"}:
            raise ValueError("Execution log name must be run, stdout, or stderr")
        if name == "run" or self._stdio is None:
            return _BoundEvidenceLog(self._execution_dir / f"{name}.log")
        stream: Stream = "stdout" if name == "stdout" else "stderr"
        return _BoundEvidenceLog(self._stdio.path(stream), stdio=self._stdio, stream=stream)


class _CheckpointWriter:
    """Write a resumable payload under ``checkpoints/``. It is not an asset."""

    def __init__(self, context: ExecutionContext) -> None:
        self._context = context

    def __call__(
        self,
        name: str | None = None,
        *,
        data: dict[str, JSONValue] | None = None,
        tags: dict[str, str] | None = None,
    ) -> Path:
        del tags
        label = name or f"checkpoint-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%f')}"
        path = self._context.get_dir(CHECKPOINTS.name) / f"{label}.json"
        if path.exists():
            raise ValueError(f"checkpoint label {label!r} already exists")
        path.write_text(
            json.dumps(
                {
                    "name": label,
                    "created_at": datetime.now(UTC).isoformat(),
                    "data": data or {},
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return path


class ExecutionContext:
    """Context manager for exactly one new or preallocated Execution.

    Run is immutable scientific intent. Operational state, evidence, results,
    heartbeat, workflow state, and emitted outputs all live below this
    Execution's physical directory.

    Constructing the context writes nothing. Entering it creates the QUEUED
    record through ``Run._create_execution`` (or, with *execution_id*, looks
    up the one already created) and then starts it; leaving it seals the
    attempt.

    While entered it is the *current* execution of its context
    (:func:`molab.workspace.tracking.current`), so ``molab.print`` copies into
    its ``stdout.log`` / ``stderr.log``. A context entered inside another is
    current until it exits, and then the outer one is again (D92).

    A ``with`` on the context while it is entered and current (``molab.track()``
    hands it out again) borrows it: entering and leaving does nothing. A child
    process attaches through :meth:`child_env`; what it staged under
    ``work/_molab/`` is recorded when this context exits, before the seal (D94).

    Args:
        run: The Run this attempt realizes.
        profile_config: The active profile; ``None`` means empty and unnamed
            for an ``initial`` attempt, and the predecessor's recorded config
            for any other mode. With *execution_id* it may be omitted (the recorded config runs)
            or equal the recorded one; a different ``profile`` or
            ``config_hash`` raises ``ValueError`` on entry.
        execution_id: A *preallocated* attempt, i.e. one already created by
            ``run._create_execution(...)`` (for example by a scheduler
            submitter) and still QUEUED. Its creation facts are fixed, so
            passing *mode*, *predecessor*, or *bypass_cache* alongside it
            raises ``ValueError``.
        mode: How a newly created attempt relates to earlier ones.
        predecessor: The predecessor of a newly created attempt.
        checkpoint: The checkpoint a newly created ``resume``
            attempt starts from.
        created_by: Who creates the attempt; defaults to this process.
        bypass_cache: Whether a newly created attempt ignores the workflow
            node cache (the per-task result store that lets an unchanged task
            reuse its earlier output). Read back through :attr:`bypass_cache`.
        workflow_hash: An opaque digest of the workflow this attempt runs,
            recorded by the start transition before any task runs. A
            start-time fact, so it may be passed with *execution_id*.
    """

    def __init__(
        self,
        run: Run,
        *,
        profile_config: ProfileConfig | None = None,
        execution_id: str | None = None,
        mode: ExecutionMode = ExecutionMode.INITIAL,
        predecessor: str | None = None,
        created_by: AgentRef | None = None,
        bypass_cache: bool = False,
        workflow_hash: str | None = None,
    ) -> None:
        if execution_id is not None:
            conflicts = [
                name
                for name, given in (
                    ("mode", mode is not ExecutionMode.INITIAL),
                    ("predecessor", predecessor is not None),
                    ("bypass_cache", bypass_cache),
                )
                if given
            ]
            if conflicts:
                raise ValueError(
                    f"Execution {execution_id!r} is preallocated; {', '.join(conflicts)} "
                    "cannot be passed with an explicit execution_id, because "
                    "they were fixed when the queued attempt was created"
                )
        self.run = run
        self.run_dir = Path(run.run_dir)
        self._requested_profile_config = profile_config
        self._profile_config = (
            profile_config if profile_config is not None else ProfileConfig({}, name=None)
        )
        self._explicit_execution_id = execution_id
        self._execution_id: str | None = None
        self._mode = mode
        self._based_on_execution_id = predecessor
        self._bypass_cache = bypass_cache
        self._workflow_hash = workflow_hash
        self._execution_dir: Path | None = None
        self._created_by = created_by or _system_agent()
        self._state: Execution | None = None
        self._active_task_id: str | None = None
        self._failure: dict[str, JSONValue] | None = None
        self._workflow_succeeded = False
        self._entered = False
        self._results: dict[str, TaskOutput] = {}
        self._register_lock = threading.Lock()
        self._heartbeat_stop: threading.Event | None = None
        self._heartbeat_thread: threading.Thread | None = None
        self._metrics: TrackedMetrics | None = None
        self._stdio: StdioFiles | None = None
        self._tracking_token: Token[Tracker | None] | None = None
        self._task_token: Token[str | None] | None = None
        self._track_claim = False
        self._seal_at_exit_registered = False
        self._borrows = 0
        workspace = run.experiment.project.workspace
        self._executions = ExecutionRepository(
            workspace.root,
            run.run_dir,
            run_id=run.id,
            project_id=run.experiment.project.id,
            fs=workspace.fs,
        )

    @property
    def id(self) -> str:
        if self._execution_id is None:
            raise RuntimeError("ExecutionContext has not been entered")
        return self._execution_id

    @property
    def execution_dir(self) -> Path:
        """This attempt's directory, as ``Run.execution_dir`` lays it out.

        Cached on entry, so repeated ``get_dir`` / ``log`` / ``metrics``
        calls do not rebuild the repository.

        Raises:
            RuntimeError: The context has not been entered.
        """
        if self._execution_dir is None:
            raise RuntimeError("ExecutionContext has not been entered")
        return self._execution_dir

    @property
    def values_dir(self) -> Path:
        """The run's recorded-value store, as ``Run.values_dir`` lays it out.

        Where the workflow engine writes the values its node journal cites.
        """
        return self.run.values_dir()

    @property
    def predecessor(self) -> str | None:
        """Selected predecessor for rerun/resume/reproduce provenance."""
        return self._state.based_on_execution_id if self._state is not None else None

    @property
    def bypass_cache(self) -> bool:
        """Whether this attempt ignores the workflow node cache.

        Read from the recorded Execution, not from the constructor argument,
        so a preallocated attempt reports the flag its creator wrote.
        ``False`` before the context is entered.
        """
        return self._state.bypass_cache if self._state is not None else False

    def get_dir(self, name: str, *parts: str) -> Path:
        """One of this attempt's directories, created on demand.

        Peers: ``get_dir("work")`` and ``get_dir("artifacts")`` differ in
        what they promise, never in how you reach them. An undeclared name
        raises rather than creating a directory nothing validates.
        """
        resolve_execution_dir(name)
        path = self.execution_dir.joinpath(name, *parts)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def has_dir(self, name: str) -> bool:
        """True when this attempt has actually created *name* on disk."""
        return (self.execution_dir / name).is_dir()

    def list_dirs(self) -> tuple[ExecutionDir, ...]:
        """Every declared directory and what it promises."""
        return list_execution_dirs()

    @property
    def files(self) -> FileStore:
        return FileStore(self.get_dir(WORK.name), fs=self.run._disk())

    @property
    def params(self) -> dict[str, JSONValue]:
        return self.run.parameters

    @property
    def config(self) -> ProfileConfig:
        """The profile this attempt runs with.

        ``ctx.config`` is always the record's config: once entered, it is
        projected from the ``profile`` / ``config`` keys of the attempt's
        recorded environment, whether the attempt was created here (and
        possibly inherited its predecessor's config) or preallocated.
        """
        return self._profile_config

    @property
    def log(self) -> _ExecutionLogs:
        return _ExecutionLogs(self.execution_dir, self._stdio)

    def write_stdio(self, stream: Stream, text: str, *, flush: bool = False) -> None:
        """Append *text* verbatim to this attempt's ``stdout.log`` / ``stderr.log``.

        The :class:`~molab.workspace.tracking.Tracker` method behind
        ``molab.print``: one call is one locked write, so lines from parallel
        tasks never split. Buffered; ``flush=True`` pushes it to disk, and
        ``__exit__`` closes the files before the seal hashes them.

        Raises:
            RuntimeError: The context has not been entered.
        """
        if self._stdio is None:
            raise RuntimeError("ExecutionContext has not been entered")
        self._stdio.write(stream, text, flush=flush)

    def child_env(self) -> dict[str, str]:
        """The environment a subprocess needs to attach to this attempt (D94).

        ``MOLAB_EXECUTION_DIR`` (absolute) and ``MOLAB_TASK`` (the current
        task, or empty). In the child, ``molab.track()`` then returns an
        attached tracker: its prints and metrics land in this attempt's files,
        and its artifacts are recorded when this context exits::

            subprocess.run(cmd, env={**os.environ, **ctx.child_env()})

        Raises:
            RuntimeError: The context has not been entered.
        """
        return {
            EXECUTION_DIR_ENV: str(self.execution_dir.absolute()),
            TASK_ENV: current_task() or "",
        }

    @property
    def checkpoint(self) -> _CheckpointWriter:
        return _CheckpointWriter(self)

    @property
    def metrics(self) -> TrackedMetrics:
        """This attempt's metrics, written live to ``metrics.mlp.jsonl`` (D93).

        ``scalar`` / ``histogram`` / ``text`` / ``image_ref`` / ``json``, plus
        ``image`` (registered as an asset, then referenced by its ref). A
        record written inside a workflow task carries ``tags.task``. Built
        on first use; the WAL file appears with the first record.
        """
        if self._metrics is None:
            store = FileStore(self.execution_dir, fs=self.run._disk())
            sink = create_metrics_writer(
                self.execution_dir,
                lambda name, line: store.append(Path(name), line),
            )
            self._metrics = TrackedMetrics(
                sink, register=self.register, execution_dir=self.execution_dir
            )
        return self._metrics

    def task_workdir(self, task_name: str) -> Path:
        """Where one workflow task writes: ``out/<task>/``.

        The bulk tier, not scratch. What a task body writes is genuinely
        mixed — the inputs it generated, its intermediates, and the
        trajectory — and those cannot be separated from outside the body.
        They land in the tier that is *kept*; anything worth citing is then
        registered as an asset by ``ctx.register``.

        ``work/`` is left to the framework's own scratch (``ctx.files``),
        which is genuinely disposable.
        """
        return self.get_dir(OUT.name, task_name)

    def set_active_task(self, task_id: str | None) -> None:
        """The producer task stamped on an artifact emitted outside a task scope.

        A private seam: the engine stamps through
        :func:`molab.workspace.tracking.task_scope`, which is per task even
        when same-level tasks run in parallel, and :meth:`_emit` reads that
        first. This slot is the fallback when no task scope is active.
        """
        self._active_task_id = task_id

    def __enter__(self) -> ExecutionContext:
        if self._entered:
            if self._track_claim:
                # The ``with`` around ``molab.track(project=…, experiment=…)``:
                # entered already, and this ``with``'s exit seals it.
                self._track_claim = False
                return self
            if current() is self:
                self._borrows += 1
                return self
            raise RuntimeError("ExecutionContext cannot be entered twice")
        state: Execution
        if self._explicit_execution_id is not None:
            state = self._preallocated(self._explicit_execution_id)
        else:
            state = self._create()
        # The QUEUED check above only gives a friendlier message; the locked
        # ``start`` decides. If another process started the record in between,
        # it raises here: no heartbeat, the context is not entered.
        environment = _start_environment()
        self._state = self._executions.start(
            state.id,
            environment=environment,
            executor=_start_executor(environment),
            workflow_hash=self._workflow_hash,
        )
        self._execution_id = state.id
        self._execution_dir = self.run.execution_dir(state.id)
        self._prepare_execution_files()
        self._stdio = StdioFiles(self.execution_dir, STDIO_FILES)
        self.log("run").append(
            f"{datetime.now(UTC).isoformat()} execution started mode={state.mode.value}"
        )
        self._entered = True
        self._start_heartbeat()
        # Last, so a failure above never leaves a dead context current. No
        # task is current in a fresh execution, even one started in a task.
        self._tracking_token = bind(self)
        self._task_token = enter_task(None)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        if self._borrows:
            self._borrows -= 1
            return False
        if self._seal_at_exit_registered:
            atexit.unregister(self._seal_at_exit)
            self._seal_at_exit_registered = False
        self._track_claim = False
        # Stop touching, but leave the file until seal succeeds. A crash in
        # the work below then still has a heartbeat the reaper can judge.
        self._stop_heartbeat()
        # Before the seal: it hashes stdout.log / stderr.log into the evidence,
        # so the digests must cover the final bytes.
        self._release_stdio()
        if exc_type is not None:
            self._write_exception(exc_type, exc_val, exc_tb)
        status = (
            ExecutionStatus.FAILED
            if exc_type is not None or self._failure is not None
            else ExecutionStatus.SUCCEEDED
        )
        self._fold_staged()
        self._register_metrics()
        self._emit_results()
        self.log("run").append(
            f"{datetime.now(UTC).isoformat()} execution finished status={status.value}"
        )
        self._executions.seal(self.id, status, error=self._failure)
        self._remove_heartbeat()
        self._entered = False
        return False

    async def __aenter__(self) -> ExecutionContext:
        return self.__enter__()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        return self.__exit__(exc_type, exc_val, exc_tb)

    def _enter_for_track(self) -> ExecutionContext:
        """Enter for ``molab.track(project=…, experiment=…)`` (D94).

        The first ``with`` around the returned context adopts this entry and
        seals on exit. Without one, the attempt is sealed at interpreter exit.
        """
        self.__enter__()
        self._track_claim = True
        atexit.register(self._seal_at_exit)
        self._seal_at_exit_registered = True
        return self

    def _release_track_claim(self) -> None:
        """Handed out again by ``molab.track()``: a ``with`` now only borrows."""
        self._track_claim = False

    def _seal_at_exit(self) -> None:
        """Seal an attempt ``molab.track()`` entered and no ``with`` exited.

        An uncaught exception that ended the script (``sys.last_exc``) seals
        it failed; otherwise it succeeded.
        """
        self._seal_at_exit_registered = False
        if not self._entered:
            return
        self._borrows = 0
        error = getattr(sys, "last_exc", None)
        if isinstance(error, BaseException):
            self.__exit__(type(error), error, error.__traceback__)
        else:
            self.__exit__(None, None, None)

    def register(
        self,
        data: object,
        *,
        title: str,
        media_type: str | None = None,
        mime: str | None = None,
        tags: dict[str, str] | None = None,
    ) -> Asset:
        """Register *data* as an asset produced by this attempt.

        The bytes are copied next to the asset record, at this run's
        experiment. The same bytes registered again return the existing
        asset. *title* is a label. The task's working file is left in place.

        Returns:
            The asset. ``asset.ref`` is ``molab:asset/<id>``.

        Raises:
            RuntimeError: Called outside an execution.
            ValueError: In-memory *data* has no *title*.
        """
        if not self._entered:
            raise RuntimeError("register must be called inside an ExecutionContext")
        if not title.strip():
            raise ValueError("register requires a title")
        source: Path
        if isinstance(data, Path):
            source = data
        elif isinstance(data, str) and Path(data).exists():
            source = Path(data)
        else:
            source = self.get_dir(WORK.name) / _register_filename(title, data)
            source.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(data, (bytes, bytearray)):
                source.write_bytes(bytes(data))
            elif isinstance(data, (dict, list)):
                source.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
            else:
                source.write_text(str(data), encoding="utf-8")
        origin = ExecutionOrigin(
            project_id=self.run.experiment.project.id,
            experiment_id=self.run.experiment.id,
            run_id=self.run.id,
            execution_id=self.id,
            task=current_task() or self._active_task_id,
        )
        with self._register_lock:
            return self.run.experiment.assets.register(
                source,
                title=title,
                created_by=self._created_by,
                origin=origin,
                media_type=media_type or mime,
                tags=tags,
            )

    def register_metric(
        self,
        key: str,
        value: float,
        *,
        step: int | None = None,
        tags: dict[str, str] | None = None,
    ) -> MetricRecord:
        return self.metrics.scalar(key, value, step, tags=cast("dict[str, JSONValue] | None", tags))

    def set_result(self, key: str, value: TaskOutput) -> None:
        """Snapshot one result in memory until this context's ``__exit__``.

        Values persist only when the context exits: ``__exit__`` writes them
        to an asset titled ``results``. A driver
        killed before ``__exit__`` loses them. ``ctx.checkpoint`` is the
        durable path for data that must outlive the process.

        Args:
            key: Result name. A later call with the same key overwrites.
            value: A JSON value, snapshotted at the call. ``None`` is a set
                value. A non-JSON value raises ``TypeError`` from
                ``json.dumps``.

        Raises:
            RuntimeError: Called outside an ``ExecutionContext``.
            TypeError: ``value`` is not JSON-serializable.
        """
        if not self._entered:
            raise RuntimeError("set_result must be called inside an ExecutionContext")
        self._results[key] = json.loads(json.dumps(value))

    def get_result(self, key: str) -> TaskOutput:
        return self._results.get(key)

    def mark_failed(self, error: str | None = None, traceback_text: str | None = None) -> None:
        if self._failure is not None:
            return
        self._failure = {
            "type": "WorkflowError",
            "message": error or "workflow failed",
            "timestamp": datetime.now(UTC).isoformat(),
        }
        if traceback_text:
            (self.execution_dir / "traceback.txt").write_text(traceback_text, encoding="utf-8")

    def mark_succeeded(self) -> None:
        if self._failure is None:
            self._workflow_succeeded = True

    def _create(self) -> Execution:
        """Write this attempt's QUEUED record through ``Run._create_execution``.

        Start-time facts (host, python, pid) are added by ``start`` in
        ``__enter__``, so both paths record them at the same moment.

        The *requested* profile is passed through (``None`` stays ``None``),
        so a non-initial attempt without a profile inherits its
        predecessor's config; the context then runs with the config the
        record holds, never a default it did not record.

        Returns:
            The QUEUED record as written.
        """
        state = self.run._create_execution(
            mode=self._mode,
            predecessor=self._based_on_execution_id,
            bypass_cache=self._bypass_cache,
            profile_config=self._requested_profile_config,
            created_by=self._created_by,
        )
        self._profile_config = _recorded_config(state.environment)
        return state

    def _preallocated(self, execution_id: str) -> Execution:
        """Look up a preallocated QUEUED record and adopt its recorded config.

        Every check runs before ``start``, so a failure leaves the record
        QUEUED. The locked ``start`` re-checks the status authoritatively.

        Args:
            execution_id: The attempt queued earlier for this run.

        Returns:
            The QUEUED record.

        Raises:
            ValueError: The record does not exist, is not QUEUED, or was
                created with a different ``profile`` / ``config_hash`` than
                the ``profile_config`` passed here.
        """
        try:
            state = self._executions.get(execution_id)
        except KeyError:
            raise ValueError(
                f"Execution {execution_id!r} does not exist under Run {self.run.id!r}"
            ) from None
        if state.status is not ExecutionStatus.QUEUED:
            raise ValueError(
                f"preallocated Execution {state.id!r} is {state.status.value}, not queued"
            )
        env = state.environment
        recorded = _recorded_config(env)
        requested = self._requested_profile_config
        if requested is not None:
            wanted = _creation_environment(requested)
            if (wanted["profile"], wanted["config_hash"]) != (
                env.get("profile"),
                env.get("config_hash"),
            ):
                raise ValueError(
                    f"profile_config differs from the one Execution {state.id!r} was "
                    f"created with (profile={env.get('profile')!r}, "
                    f"config_hash={env.get('config_hash')!r}); an Execution runs only "
                    "with the config recorded at its creation"
                )
        self._profile_config = recorded
        return state

    def _prepare_execution_files(self) -> None:
        """Make the attempt's two directories. Its state is already one file."""
        self.execution_dir.mkdir(parents=True, exist_ok=True)
        self.get_dir(OUT.name)

    def _write_exception(
        self,
        exc_type: type[BaseException],
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._failure is None:
            self._failure = {
                "type": exc_type.__name__,
                "message": str(exc_val),
                "timestamp": datetime.now(UTC).isoformat(),
            }
        # The failure is carried on the Execution itself (sealed into
        # ``execution.json``); only the traceback text is too big for a field,
        # and it belongs in the attempt's one log.
        self.log("run").append("".join(traceback.format_exception(exc_type, exc_val, exc_tb)))

    def _release_stdio(self) -> None:
        """Stop being the current execution, then flush and close the stdio files.

        Never raises, so ``__exit__`` always reaches the seal. Resetting the
        token restores whichever execution was current before this one.
        """
        task_token, self._task_token = self._task_token, None
        if task_token is not None:
            # As below: exited in another context, the scope dies with it.
            with contextlib.suppress(ValueError):
                exit_task(task_token)
        token, self._tracking_token = self._tracking_token, None
        if token is not None:
            try:
                unbind(token)
            except ValueError:
                # Exited in a different context than it was entered in; the
                # binding dies with that context.
                _logger.warning(
                    f"execution {self.id} exited outside the context it was entered in",
                    exc_info=True,
                )
        if self._stdio is not None:
            try:
                self._stdio.close()
            except Exception:
                _logger.warning(f"could not close stdio of execution {self.id}", exc_info=True)

    def _register_metrics(self) -> None:
        """Flush the metrics WAL. The file is evidence, not an asset."""
        if self._metrics is not None:
            self._metrics.flush()

    def _fold_staged(self) -> None:
        """Register files a child staged under ``work/_molab/`` (D94).

        Each manifest entry is registered as an asset. An entry that cannot
        be registered is logged in ``run.log`` and does not fail the attempt.
        """
        entries = list(manifest_entries(self.execution_dir))
        if not entries:
            return
        if self._executions.get(self.id).sealed:
            self.log("run").append(
                f"staged files not recorded: Execution {self.id} was sealed before exit"
            )
            return
        previous = self._active_task_id
        for number, entry in entries:
            try:
                if isinstance(entry, ValueError):
                    raise entry
                self._fold_one(entry)
            except Exception as exc:
                self.log("run").append(
                    f"staged file {MANIFEST}:{number} not recorded: {type(exc).__name__}: {exc}"
                )
        self._active_task_id = previous

    def _fold_one(self, entry: StagedFile) -> None:
        staged = self.execution_dir / entry.staged
        if staged.parent != self.execution_dir / STAGED_DIR or not staged.exists():
            raise FileNotFoundError(f"{entry.staged} is not a staged file")
        self._active_task_id = entry.task
        tags = dict(entry.tags)
        tags["staged_by"] = "child"
        self.register(staged, title=entry.name, media_type=entry.media_type, tags=tags)

    def _emit_results(self) -> None:
        """Register in-memory results as an asset titled ``results``.

        A sealed attempt is left untouched: one ``run.log`` line records why,
        and this method does not raise, so ``__exit__`` can still finish.
        """
        if not self._results:
            return
        execution = self._executions.get(self.id)
        if execution.sealed:
            self.log("run").append(
                "results not recorded: Execution "
                f"{self.id} was sealed before exit ({execution.status.value})"
            )
            return
        self.set_active_task(None)
        path = self.get_dir(WORK.name) / "results.json"
        path.write_text(json.dumps(self._results, indent=2, sort_keys=True), encoding="utf-8")
        self.register(path, title="results", media_type="application/json")

    def _start_heartbeat(self) -> None:
        touch_alive(self.run, self.id)
        stop = threading.Event()
        thread = threading.Thread(
            target=self._heartbeat_loop,
            args=(stop,),
            name=f"molab-execution-heartbeat-{self.id}",
            daemon=True,
        )
        self._heartbeat_stop = stop
        self._heartbeat_thread = thread
        thread.start()

    def _stop_heartbeat(self) -> None:
        if self._heartbeat_stop is not None:
            self._heartbeat_stop.set()
        if self._heartbeat_thread is not None:
            self._heartbeat_thread.join(timeout=5)
        self._heartbeat_stop = None
        self._heartbeat_thread = None

    def _heartbeat_loop(self, stop: threading.Event) -> None:
        # A remote ``touch`` can fail transiently; one failure must not kill
        # the thread, or the owner looks stale while it is still running.
        while not stop.wait(HEARTBEAT_INTERVAL_SECONDS):
            try:
                touch_alive(self.run, self.id)
            except Exception:
                _logger.warning(
                    f"heartbeat touch failed for execution {self.id}; retrying next interval",
                    exc_info=True,
                )

    def _remove_heartbeat(self) -> None:
        # Best effort: a leftover ``alive`` only ages into staleness, while a
        # raise here would skip ``seal`` and mask the body's own exception.
        try:
            unlink_alive(self.run, self.id)
        except Exception:
            _logger.warning(f"could not remove heartbeat for execution {self.id}", exc_info=True)


RunContext = ExecutionContext

__all__ = ["ExecutionContext", "RunContext", "profile_config_hash"]
