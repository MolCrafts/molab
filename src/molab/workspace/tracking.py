"""The current execution of this process, and ``molab.print`` (D92).

Each execution manages its own stdio. While an
:class:`~molab.workspace.execution_context.ExecutionContext` is entered it is
the *current* execution: a :class:`~contextvars.ContextVar` holds it, so a
workflow task body — an asyncio task or an ``asyncio.to_thread`` call, each
with its own copy of the context — sees the execution that started it, and
two executions in one process (``RunSet.execute``, two threads) never see
each other.

:func:`print` has the builtin's signature and behaviour. It always writes to
the original target first, then copies the same text into the current
execution's ``stdout.log`` / ``stderr.log``. Outside an execution it is the
builtin. Opt in per module with ``from molab import print``; nothing is
captured at the file-descriptor level and ``sys.stdout`` is never replaced.
A ``from molab import *`` also shadows the builtin in that module, which is
the same function outside an execution.

The engine layers the running task's name on top with :func:`task_scope`, so
:func:`current_task` answers "which task is this" under parallelism.

Metrics (D93): the current execution's ``metrics`` is a :class:`TrackedMetrics`
over its one WAL writer. It tags a record written inside a task with
``tags.task`` and keeps the task's records in memory so the node cache can
replay them on a hit. Off-workspace, a task gets a :class:`BufferedMetrics`
with the same methods, which only keeps the records in memory.

Code that is not a molab task (D94): :func:`track` returns the current
execution, or an :class:`AttachedTracker` in a child process molab started
(``MOLAB_EXECUTION_DIR``), or a live execution of a run it opens, or an
:class:`OfflineTracker` that writes the same layout into a plain directory.
A child and an offline script never write ``execution.json``: their stdio
and metrics land at their final paths, and a file worth registering is only
*staged* (``work/_molab/staged/`` plus one line in ``work/_molab/staged.jsonl``).
The owner folds the manifest at seal; ``molab runs adopt --from`` folds an
offline directory.

Stdlib only at import (plus ``mollog``, ``molab.atomicio`` and the
stdlib-only ``metrics_seam`` / ``execution_dirs``), so ``import molab``
stays light.
"""

from __future__ import annotations

import atexit
import builtins
import json
import mimetypes
import os
import platform
import shutil
import sys
import threading
import time
import warnings
from collections.abc import Callable, Generator, Iterable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import IO, TYPE_CHECKING, Literal, Protocol, Self, runtime_checkable

from mollog import get_logger

from molab._typing import JSONValue
from molab.atomicio import atomic_write_json

from .execution_dirs import WORK
from .metrics_seam import MetricRecord, MetricsSink, create_metrics_writer

if TYPE_CHECKING:
    from _typeshed import SupportsWrite

    from .execution_context import ExecutionContext
    from .fs import PathArg

_logger = get_logger(__name__)

#: A stdio stream of one execution.
Stream = Literal["stdout", "stderr"]


@runtime_checkable
class Tracker(Protocol):
    """What the current execution offers to code running inside it.

    :class:`~molab.workspace.execution_context.ExecutionContext` satisfies it.
    """

    @property
    def execution_dir(self) -> Path:
        """The attempt's directory, ``executions/eNN``."""
        ...

    @property
    def metrics(self) -> TrackedMetrics:
        """The attempt's one metrics writer (D93)."""
        ...

    def write_stdio(self, stream: Stream, text: str, *, flush: bool = False) -> None:
        """Append *text* verbatim to the attempt's *stream* file."""
        ...

    def register(
        self,
        data: object,
        *,
        title: str,
        media_type: str | None = None,
        tags: dict[str, str] | None = None,
    ) -> object:
        """Register *data* as an asset of the attempt.

        The owning process mints the asset at once. A child or an offline
        script stages the bytes for the owner (:class:`StagedFile`).
        """
        ...

    def child_env(self) -> dict[str, str]:
        """The environment a subprocess needs to attach to this attempt (D94).

        ``MOLAB_EXECUTION_DIR`` (absolute) and ``MOLAB_TASK`` (the current
        task, or empty). Merge it over ``os.environ`` for the child.
        """
        ...


_CURRENT: ContextVar[Tracker | None] = ContextVar("molab_current_execution", default=None)
"""The execution this context runs inside, or ``None``."""

_TASK: ContextVar[str | None] = ContextVar("molab_current_task", default=None)
"""The workflow task this context runs inside, or ``None``."""

_PROCESS: Tracker | None = None
"""The tracker :func:`track` bound for the whole process (cases 2 and 4), or ``None``.

Consulted only when no execution is current in the context, so a
``run.start()`` inside a tracked script is still current for its body.
"""

_process_lock = threading.Lock()


def current() -> Tracker | None:
    """The current execution, or ``None`` outside one.

    The execution entered in this context wins; otherwise the tracker
    :func:`track` bound for this process (an attached child, an offline
    script).
    """
    tracker = _CURRENT.get()
    return tracker if tracker is not None else _PROCESS


def current_task() -> str | None:
    """The name of the workflow task running in this context, or ``None``."""
    return _TASK.get()


def bind(tracker: Tracker) -> Token[Tracker | None]:
    """Make *tracker* the current execution of this context.

    Returns:
        The token :func:`unbind` takes to restore the previous one, so a
        context entered inside another restores the outer one on exit.
    """
    return _CURRENT.set(tracker)


def unbind(token: Token[Tracker | None]) -> None:
    """Restore the execution that was current before the matching :func:`bind`."""
    _CURRENT.reset(token)


def enter_task(name: str | None) -> Token[str | None]:
    """Make *name* the current task of this context (``None``: no task).

    An execution enters ``None`` when it becomes current, so a run started
    inside another execution's task does not inherit that task's name.

    Returns:
        The token :func:`exit_task` takes to restore the previous task.
    """
    return _TASK.set(name)


def exit_task(token: Token[str | None]) -> None:
    """Restore the task that was current before the matching :func:`enter_task`."""
    _TASK.reset(token)


@contextmanager
def task_scope(name: str) -> Generator[None]:
    """Mark the code inside as the body of workflow task *name*."""
    token = enter_task(name)
    try:
        yield
    finally:
        exit_task(token)


class StdioFiles:
    """The two append handles of one execution's stdio.

    Each handle opens on its first write (text mode, utf-8,
    ``errors="replace"``, ``newline=""`` so bytes are written as given) and
    has its own lock, so one write — one whole ``print`` call — never
    interleaves with another on the same stream. Writes are buffered;
    ``flush=True``, :meth:`flush` and :meth:`close` push them to disk.

    After :meth:`close` a write still lands, through a one-shot append, so a
    late ``ctx.log("stdout").append`` keeps working and leaks no handle.
    Local filesystem only, like every in-process execution.

    Args:
        execution_dir: The attempt's directory.
        names: File name per stream (``execution_repository.STDIO_FILES``).
    """

    def __init__(self, execution_dir: Path, names: Mapping[str, str]) -> None:
        self._paths: dict[str, Path] = {
            stream: execution_dir / name for stream, name in names.items()
        }
        self._locks: dict[str, threading.Lock] = {stream: threading.Lock() for stream in names}
        self._handles: dict[str, IO[str]] = {}
        self._closed: set[str] = set()

    def path(self, stream: Stream) -> Path:
        """The file *stream* is appended to."""
        return self._paths[stream]

    def write(self, stream: Stream, text: str, *, flush: bool = False) -> None:
        """Append *text* to *stream* as one locked write."""
        path = self._paths[stream]
        with self._locks[stream]:
            if stream in self._closed:
                with path.open("a", encoding="utf-8", errors="replace", newline="") as handle:
                    handle.write(text)
                return
            handle = self._handles.get(stream)
            if handle is None:
                path.parent.mkdir(parents=True, exist_ok=True)
                # Line-buffered, so a live ``/logs/{stream}`` poll sees each line as it is printed.
                handle = path.open("a", encoding="utf-8", errors="replace", newline="", buffering=1)
                self._handles[stream] = handle
            handle.write(text)
            if flush:
                handle.flush()

    def flush(self, stream: Stream | None = None) -> None:
        """Push buffered writes of *stream* (or of both) to disk."""
        for name in (stream,) if stream is not None else tuple(self._locks):
            with self._locks[name]:
                handle = self._handles.get(name)
                if handle is not None:
                    handle.flush()

    def close(self) -> None:
        """Flush and close both handles. Idempotent."""
        for name, lock in self._locks.items():
            with lock:
                handle = self._handles.pop(name, None)
                self._closed.add(name)
                if handle is not None:
                    handle.close()


#: The most records :class:`TrackedMetrics` keeps for one task. Past it the
#: task's list is dropped and the task is not replayed from the node cache.
TASK_RECORD_CAP = 50_000

#: The ``semantic_type`` of an image archived by ``metrics.image``.
IMAGE_SEMANTIC_TYPE = "molplot.image"


def _wall_time(wall_time: str | datetime | None) -> str:
    """A record's ``w``: the given time, or now in UTC."""
    if isinstance(wall_time, datetime):
        return wall_time.isoformat()
    if isinstance(wall_time, str):
        return wall_time
    return datetime.now(UTC).isoformat()


def _with_task(
    tags: dict[str, JSONValue] | None, default: str | None = None
) -> dict[str, JSONValue] | None:
    """*tags* plus ``task`` when a task scope is active; an explicit ``task`` wins.

    *default* names the task outside a task scope: an attached child's
    ``MOLAB_TASK``.
    """
    task = _TASK.get() or default
    if task is None:
        return tags
    merged: dict[str, JSONValue] = {"task": task}
    if tags:
        merged.update(tags)
    return merged


class _MetricsFront:
    """The five record types over one :class:`MetricsSink`, tagged with the task."""

    def __init__(self, sink: MetricsSink, *, task: str | None = None) -> None:
        self._sink = sink
        self._task = task

    def _tags(self, tags: dict[str, JSONValue] | None) -> dict[str, JSONValue] | None:
        return _with_task(tags, self._task)

    def _wrote(self, record: MetricRecord) -> MetricRecord:
        """Called with every record this front appended; returns it."""
        return record

    def scalar(
        self,
        key: str,
        value: int | float,
        step: int | float | None = None,
        *,
        wall_time: str | datetime | None = None,
        tags: dict[str, JSONValue] | None = None,
    ) -> MetricRecord:
        """Append one number, ``t="scalar"``."""
        return self._wrote(
            self._sink.scalar(key, value, step, wall_time=wall_time, tags=self._tags(tags))
        )

    def histogram(
        self,
        key: str,
        bins: list[int | float],
        counts: list[int | float],
        step: int | float | None = None,
        *,
        wall_time: str | datetime | None = None,
        tags: dict[str, JSONValue] | None = None,
    ) -> MetricRecord:
        """Append one distribution, ``t="histogram"`` with ``v={bins, counts}``."""
        return self._wrote(
            self._sink.histogram(
                key, bins, counts, step, wall_time=wall_time, tags=self._tags(tags)
            )
        )

    def text(
        self,
        key: str,
        text: str,
        step: int | float | None = None,
        *,
        wall_time: str | datetime | None = None,
        tags: dict[str, JSONValue] | None = None,
    ) -> MetricRecord:
        """Append one string, ``t="text"``."""
        return self._wrote(
            self._sink.text(key, text, step, wall_time=wall_time, tags=self._tags(tags))
        )

    def image_ref(
        self,
        key: str,
        path: str | Path,
        step: int | float | None = None,
        *,
        caption: str | None = None,
        wall_time: str | datetime | None = None,
        tags: dict[str, JSONValue] | None = None,
    ) -> MetricRecord:
        """Append a reference to an image file, ``t="image_ref"`` with ``v={path, caption}``."""
        return self._wrote(
            self._sink.image_ref(
                key, path, step, caption=caption, wall_time=wall_time, tags=self._tags(tags)
            )
        )

    def json(
        self,
        key: str,
        value: JSONValue,
        step: int | float | None = None,
        *,
        wall_time: str | datetime | None = None,
        tags: dict[str, JSONValue] | None = None,
    ) -> MetricRecord:
        """Append any JSON value, ``t="json"``."""
        return self._wrote(
            self._sink.json(key, value, step, wall_time=wall_time, tags=self._tags(tags))
        )

    def flush(self) -> None:
        """Push buffered records to their destination."""
        self._sink.flush()


class TrackedMetrics(_MetricsFront):
    """One execution's metrics: its WAL writer, tagged and captured per task (D93).

    ``ExecutionContext.metrics`` returns it, and so does ``TaskContext.metrics``
    under an execution, so a driver script and a workflow task write the same
    ``metrics.mlp.jsonl`` at the attempt root, live.

    - A record written while a task scope is active gets ``tags.task`` (an
      explicit ``tags["task"]`` wins) and is also kept in memory under the
      task's name, at most :data:`TASK_RECORD_CAP` per task. The node cache
      takes them with :meth:`take_task_records` to replay on a hit.
    - :meth:`image` registers the image as an asset, then appends an
      ``image_ref`` to that asset's ref. A child cannot mint the id, so it
      records the staged path until the owner registers the file.

    Args:
        sink: The execution's WAL writer (``metrics_seam.create_metrics_writer``).
        register: The execution's ``register``, which :meth:`image` calls.
            ``None``: :meth:`image` raises.
        execution_dir: The attempt's directory. An image file outside it is
            registered from a copy of its bytes.
        task: The task a record is tagged with outside a task scope (an
            attached child's ``MOLAB_TASK``, D94). Such records are not kept
            for the node cache: only the owner's task scope captures.
    """

    def __init__(
        self,
        sink: MetricsSink,
        *,
        register: Callable[..., object] | None = None,
        execution_dir: Path | None = None,
        task: str | None = None,
    ) -> None:
        super().__init__(sink, task=task)
        self._register = register
        self._execution_dir = execution_dir
        self._lock = threading.Lock()
        self._captured: dict[str, list[MetricRecord]] = {}
        self._incomplete: set[str] = set()
        self._touched = False

    @property
    def sink(self) -> MetricsSink:
        """The WAL writer underneath."""
        return self._sink

    @property
    def touched(self) -> bool:
        """True once any record of any type was appended through this object."""
        return self._touched

    def _wrote(self, record: MetricRecord) -> MetricRecord:
        self._touched = True
        task = _TASK.get()
        if task is not None:
            self._capture(task, record)
        return record

    def _capture(self, task: str, record: MetricRecord) -> None:
        with self._lock:
            if task in self._incomplete:
                return
            kept = self._captured.setdefault(task, [])
            if len(kept) >= TASK_RECORD_CAP:
                del self._captured[task]
                self._incomplete.add(task)
                _logger.info(
                    f"task {task!r} wrote more than {TASK_RECORD_CAP} metric records; "
                    "a node-cache hit will not replay them"
                )
                return
            kept.append(record)

    def take_task_records(self, name: str) -> list[MetricRecord] | None:
        """Pop the records task *name* wrote.

        Returns:
            The records in write order (empty when it wrote none), or ``None``
            when the task went past :data:`TASK_RECORD_CAP`.
        """
        with self._lock:
            records = self._captured.pop(name, [])
            if name in self._incomplete:
                self._incomplete.discard(name)
                return None
            return records

    def keep_task_records(self, name: str, records: Iterable[MetricRecord]) -> None:
        """Keep records task *name* wrote elsewhere (a worker process) for the node cache.

        They are already in the WAL — the worker appended them — so nothing
        is written; they are only kept, as if written here in the task's
        scope (the :data:`TASK_RECORD_CAP` applies).
        """
        for record in records:
            self._capture(name, record)

    def replay(self, records: Iterable[MetricRecord], *, replayed_from: str) -> int:
        """Append recorded events again, each tagged ``replayed_from``.

        Each record keeps its ``w``, ``s`` and other tags. Replayed records
        are not captured for the task again.

        Returns:
            How many records were appended.
        """
        tagged: list[MetricRecord] = []
        for record in records:
            if not isinstance(record, dict):
                continue
            copy = dict(record)
            old = copy.get("tags")
            tags: dict[str, JSONValue] = dict(old) if isinstance(old, dict) else {}
            tags["replayed_from"] = replayed_from
            copy["tags"] = tags
            tagged.append(copy)
        if not tagged:
            return 0
        self._touched = True
        return self._sink.log_many(tagged)

    def _inside_execution(self, path: Path) -> bool:
        if self._execution_dir is None:
            return True
        return path.resolve().is_relative_to(self._execution_dir.resolve())

    def image(
        self,
        key: str,
        data: Path | str | bytes,
        step: int | float | None = None,
        *,
        caption: str | None = None,
        name: str | None = None,
        tags: dict[str, JSONValue] | None = None,
    ) -> MetricRecord:
        """Register an image as an asset, then reference it with ``image_ref``.

        Args:
            key: The metric key.
            data: A path to an existing image file (one outside the attempt
                is registered from a copy of its bytes), or the image's bytes.
            step: The step this image belongs to.
            caption: A caption for the viewer.
            name: Title of the asset; required for bytes, the file's name by
                default. Each image is its own asset, so two images need
                two titles.
            tags: Record tags.

        Returns:
            The ``image_ref`` record. ``v.path`` is ``molab:asset/<id>`` when
            the owner registered it, or the staged path when a child wrote it.

        Raises:
            ValueError: *data* is bytes without *name*, or a string that is not
                an existing path.
            RuntimeError: No ``register`` was given.
        """
        if self._register is None:
            raise RuntimeError("metrics.image needs an execution to register the image")
        source: object
        if isinstance(data, (bytes, bytearray)):
            if not name:
                raise ValueError("metrics.image: name is required when data is bytes")
            source = bytes(data)
            label = name
        else:
            path = Path(data)
            if not path.is_file():
                raise ValueError(f"metrics.image: {str(data)!r} is not an existing file")
            label = name or path.name
            source = path if self._inside_execution(path) else path.read_bytes()
        media_type, _ = mimetypes.guess_type(label)
        registered = self._register(source, title=label, media_type=media_type)
        pointer = getattr(registered, "ref", None)
        if not isinstance(pointer, str):
            pointer = getattr(registered, "path", label)
        return self.image_ref(key, pointer, step, caption=caption, tags=tags)


class _MemorySink:
    """A :class:`MetricsSink` that keeps records in a list, unvalidated."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.records: list[MetricRecord] = []

    def _add(
        self,
        kind: str,
        key: str,
        value: JSONValue,
        step: int | float | None,
        wall_time: str | datetime | None,
        tags: dict[str, JSONValue] | None,
    ) -> MetricRecord:
        record: MetricRecord = {"t": kind, "k": key}
        if step is not None:
            record["s"] = step
        record["w"] = _wall_time(wall_time)
        record["v"] = value
        if tags is not None:
            record["tags"] = dict(tags)
        with self._lock:
            self.records.append(record)
        return record

    def scalar(
        self,
        key: str,
        value: int | float,
        step: int | float | None = None,
        *,
        wall_time: str | datetime | None = None,
        tags: dict[str, JSONValue] | None = None,
    ) -> MetricRecord:
        return self._add("scalar", key, value, step, wall_time, tags)

    def histogram(
        self,
        key: str,
        bins: list[int | float],
        counts: list[int | float],
        step: int | float | None = None,
        *,
        wall_time: str | datetime | None = None,
        tags: dict[str, JSONValue] | None = None,
    ) -> MetricRecord:
        value: JSONValue = {"bins": list(bins), "counts": list(counts)}
        return self._add("histogram", key, value, step, wall_time, tags)

    def text(
        self,
        key: str,
        text: str,
        step: int | float | None = None,
        *,
        wall_time: str | datetime | None = None,
        tags: dict[str, JSONValue] | None = None,
    ) -> MetricRecord:
        return self._add("text", key, text, step, wall_time, tags)

    def image_ref(
        self,
        key: str,
        path: str | Path,
        step: int | float | None = None,
        *,
        caption: str | None = None,
        wall_time: str | datetime | None = None,
        tags: dict[str, JSONValue] | None = None,
    ) -> MetricRecord:
        value: JSONValue = {"path": str(path), "caption": caption}
        return self._add("image_ref", key, value, step, wall_time, tags)

    def json(
        self,
        key: str,
        value: JSONValue,
        step: int | float | None = None,
        *,
        wall_time: str | datetime | None = None,
        tags: dict[str, JSONValue] | None = None,
    ) -> MetricRecord:
        return self._add("json", key, value, step, wall_time, tags)

    def log_many(
        self, records: Iterable[MetricRecord], *, tags: dict[str, JSONValue] | None = None
    ) -> int:
        count = 0
        for record in records:
            copy = dict(record)
            if tags is not None:
                copy["tags"] = dict(tags)
            with self._lock:
                self.records.append(copy)
            count += 1
        return count

    def flush(self) -> None:
        """Nothing to push; the records are already in the list."""


class BufferedMetrics(_MetricsFront):
    """In-memory metrics for a task that runs without molab (D93).

    The same methods as :class:`TrackedMetrics`, so one task body runs with
    and without an execution. Records (tagged with the task, as under an
    execution) collect in :attr:`records`; nothing is written to disk, and
    :meth:`image` keeps only the reference.
    """

    def __init__(self) -> None:
        self._memory = _MemorySink()
        super().__init__(self._memory)

    @property
    def records(self) -> list[MetricRecord]:
        """Every record written so far, in write order."""
        return self._memory.records

    def image(
        self,
        key: str,
        data: Path | str | bytes,
        step: int | float | None = None,
        *,
        caption: str | None = None,
        name: str | None = None,
        tags: dict[str, JSONValue] | None = None,
    ) -> MetricRecord:
        """Append an ``image_ref`` to *data*'s path (or *name* for bytes); archive nothing."""
        if isinstance(data, (bytes, bytearray)):
            if not name:
                raise ValueError("metrics.image: name is required when data is bytes")
            path: str | Path = name
        else:
            path = data
        return self.image_ref(key, path, step, caption=caption, tags=tags)


# ── molab.track(): plain scripts and child processes (D94) ────────────────

#: The environment variable naming the attempt a child attaches to (absolute).
EXECUTION_DIR_ENV = "MOLAB_EXECUTION_DIR"

#: The environment variable naming the task that started a child.
TASK_ENV = "MOLAB_TASK"

#: Set (non-empty) by ``CommandTask``, which captures the child's stdout and
#: stderr and archives them itself; an attached child then copies no print,
#: so no line lands twice.
STDIO_CAPTURED_ENV = "MOLAB_STDIO_CAPTURED"

#: Where :func:`track` writes when nothing else applies.
DEFAULT_TRACK_DIR = "molab-track"

#: How often, at most, an attached child re-reads the seal before a write.
SEAL_CHECK_SECONDS = 5.0

#: The ``semantic_type`` of a metrics WAL. The file is evidence, not an asset.
METRICS_SEMANTIC_TYPE = "molplot.metrics"

#: ``work/_molab/``: what a child or an offline script leaves for the owner.
TRACK_DIR = PurePosixPath(WORK.name, "_molab")

#: Staged file bytes, ``work/_molab/staged/<n>-<basename>``.
STAGED_DIR = TRACK_DIR / "staged"

#: The staging manifest: one JSON line per staged file.
MANIFEST = TRACK_DIR / "staged.jsonl"

#: An offline directory's own record: start / finish times and the process.
TRACK_RECORD = TRACK_DIR / "track.json"


@dataclass(frozen=True)
class StagedFile:
    """A file a child or an offline script staged for the owner to register.

    Attributes:
        name: Title the owner registers the asset under.
        path: Where the bytes wait, relative to the tracked directory. A
            child's ``image_ref`` points here until the owner registers it.
        staged: Same relative path as :attr:`path`.
        media_type: The media type to record.
        semantic_type: Kept so an older manifest line still parses. Unused.
        tags: Tags recorded on the asset.
        task: The task that staged it (``MOLAB_TASK``), if any.
        created_at: When it was staged (ISO, UTC).
    """

    name: str
    path: str
    staged: str
    media_type: str | None = None
    semantic_type: str | None = None
    tags: dict[str, str] = field(default_factory=dict)
    task: str | None = None
    created_at: str = ""

    def to_line(self) -> str:
        """The manifest line, ending in a newline."""
        record = {
            "staged": self.staged,
            "name": self.name,
            "media_type": self.media_type,
            "semantic_type": self.semantic_type,
            "tags": self.tags,
            "task": self.task,
            "created_at": self.created_at,
        }
        return json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"

    @classmethod
    def from_line(cls, line: str) -> StagedFile:
        """Parse one manifest line.

        Raises:
            ValueError: The line is not a manifest entry, or its ``staged``
                path is not under ``work/_molab/staged/``.
        """
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"not JSON: {exc}") from None
        if not isinstance(raw, dict):
            raise ValueError("not a JSON object")
        staged, name = raw.get("staged"), raw.get("name")
        if not isinstance(staged, str) or not isinstance(name, str):
            raise ValueError("an entry needs string 'staged' and 'name'")
        rel = PurePosixPath(staged)
        if rel.is_absolute() or ".." in rel.parts or rel.parent != STAGED_DIR:
            raise ValueError(f"staged path {staged!r} is not under {STAGED_DIR}/")
        _check_register_name(name)
        tags = raw.get("tags")

        def _text(key: str) -> str | None:
            value = raw.get(key)
            return value if isinstance(value, str) and value else None

        return cls(
            name=name,
            path=staged,
            staged=staged,
            media_type=_text("media_type"),
            semantic_type=_text("semantic_type"),
            tags={str(k): str(v) for k, v in tags.items()} if isinstance(tags, dict) else {},
            task=_text("task"),
            created_at=_text("created_at") or "",
        )

    @property
    def created_time(self) -> datetime | None:
        """:attr:`created_at` as a datetime, or ``None`` when missing or not ISO."""
        return _parse_time(self.created_at)

    def metadata(self, staged_by: str) -> dict[str, JSONValue]:
        """Tags the owner records: ``staged_by``, the task, and the entry's tags."""
        meta: dict[str, JSONValue] = {"staged_by": staged_by}
        if self.task:
            # ``task_id`` is the producer key the server and the cache read.
            meta["task"] = self.task
            meta["task_id"] = self.task
        if self.tags:
            meta["tags"] = dict(self.tags)
        return meta


def _check_register_name(name: str) -> None:
    """Refuse a title that cannot be a staged file name.

    Raises:
        ValueError: *name* is empty, absolute, or has ``..``.
    """
    rel = PurePosixPath(name)
    if not name or rel.is_absolute() or ".." in rel.parts or rel.as_posix() != name:
        raise ValueError(f"asset title must be a plain relative name: {name!r}")
    if rel.parts[0] == "_molab":
        raise ValueError("_molab is reserved")


def manifest_entries(directory: Path) -> Iterator[tuple[int, StagedFile | ValueError]]:
    """Each line of *directory*'s staging manifest, parsed or with why it is not.

    Yields ``(line number, entry or error)``; blank lines are skipped. Nothing
    when there is no manifest.
    """
    path = directory / MANIFEST
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8", errors="replace")
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            yield number, StagedFile.from_line(line)
        except ValueError as exc:
            yield number, exc


@dataclass(frozen=True)
class TrackedDirectory:
    """What an offline :func:`track` directory holds, for ``runs adopt --from``.

    Attributes:
        root: The directory.
        stdio: Stream -> its existing log file (``stdout.log`` / ``stderr.log``).
        metrics: The ``*.mlp.jsonl`` WALs at the directory root.
        staged: The staged files, in manifest order.
        started_at: ``track.json``'s start, if recorded.
        finished_at: ``track.json``'s finish, if recorded.
    """

    root: Path
    stdio: dict[str, Path]
    metrics: tuple[Path, ...]
    staged: tuple[StagedFile, ...]
    started_at: datetime | None = None
    finished_at: datetime | None = None

    def files(self) -> list[Path]:
        """Every file an adoption moves."""
        return [
            *self.stdio.values(),
            *self.metrics,
            *(self.root / entry.staged for entry in self.staged),
        ]


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.astimezone()


def read_tracked(directory: PathArg) -> TrackedDirectory:
    """Read an offline :func:`track` directory without changing it.

    Raises:
        FileNotFoundError: *directory* is not a directory.
        ValueError: A manifest line is malformed.
    """
    from .execution_repository import STDIO_FILES

    root = Path(str(directory))
    if not root.is_dir():
        raise FileNotFoundError(f"{root} is not a directory")
    stdio = {stream: root / name for stream, name in STDIO_FILES.items() if (root / name).is_file()}
    metrics = tuple(sorted(p for p in root.glob("*.mlp.jsonl") if p.is_file()))
    entries: list[StagedFile] = []
    for number, entry in manifest_entries(root):
        if isinstance(entry, ValueError):
            raise ValueError(f"{root / MANIFEST}:{number}: {entry}")
        entries.append(entry)
    started = finished = None
    record = root / TRACK_RECORD
    if record.is_file():
        try:
            raw = json.loads(record.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{record}: not JSON: {exc}") from None
        if isinstance(raw, dict):
            started = _parse_time(raw.get("started_at"))
            finished = _parse_time(raw.get("finished_at"))
    return TrackedDirectory(
        root=root,
        stdio=stdio,
        metrics=metrics,
        staged=tuple(entries),
        started_at=started,
        finished_at=finished,
    )


class _AppendFiles:
    """Unbuffered ``O_APPEND`` writers: one descriptor and one lock per file.

    Each write is one ``os.write`` of the whole text, so lines from the owner
    and from other children appending to the same file never interleave
    within a write on a local filesystem.
    """

    _FLAGS = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_BINARY", 0)

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._files: dict[Path, tuple[int, threading.Lock]] = {}

    def write(self, path: Path, text: str) -> None:
        data = text.encode("utf-8", errors="replace")
        with self._lock:
            entry = self._files.get(path)
            if entry is None:
                path.parent.mkdir(parents=True, exist_ok=True)
                entry = (os.open(path, self._FLAGS, 0o644), threading.Lock())
                self._files[path] = entry
        fd, lock = entry
        with lock:
            view = memoryview(data)
            while view:
                view = view[os.write(fd, view) :]

    def close(self) -> None:
        with self._lock:
            files, self._files = self._files, {}
        for fd, _lock in files.values():
            os.close(fd)


class _StagingTracker:
    """The tracking surface of a process that does not own the attempt (D94).

    stdio goes to ``<dir>/stdout.log`` / ``stderr.log`` and metrics to
    ``<dir>/<stem>.mlp.jsonl`` (through the seam), both appended
    with ``O_APPEND``. A file worth registering is copied into
    ``<dir>/work/_molab/staged/<n>-<basename>`` and announced by one line in
    ``<dir>/work/_molab/staged.jsonl``. Nothing here writes
    ``execution.json``.
    """

    #: ``metadata.staged_by`` of what this tracker stages.
    staged_by = "child"

    def __init__(self, directory: Path, *, task: str | None) -> None:
        from .execution_repository import STDIO_FILES

        self._dir = directory
        self._task = task
        self._stdio_paths: dict[str, Path] = {
            stream: directory / name for stream, name in STDIO_FILES.items()
        }
        self._files = _AppendFiles()
        self._stage_lock = threading.Lock()
        self._metrics: TrackedMetrics | None = None
        self._copy_stdio = not os.environ.get(STDIO_CAPTURED_ENV)
        self._claim_with = False
        self._withs: list[bool] = []

    @property
    def execution_dir(self) -> Path:
        """The directory this tracker writes into."""
        return self._dir

    @property
    def task(self) -> str | None:
        """The task this process runs for (``MOLAB_TASK``), if any."""
        return self._task

    def _writable(self) -> bool:
        """Whether a write may land now."""
        return True

    def write_stdio(self, stream: Stream, text: str, *, flush: bool = False) -> None:  # noqa: ARG002 — unbuffered
        """Append *text* to ``stdout.log`` / ``stderr.log`` in one write.

        Nothing is copied when the parent captures this process's streams
        (``MOLAB_STDIO_CAPTURED``) or once the attempt is sealed.
        """
        if not self._copy_stdio or not self._writable():
            return
        self._files.write(self._stdio_paths[stream], text)

    def _append_wal(self, name: str | Path, line: str) -> None:
        if not self._writable():
            return
        self._files.write(self._dir / name, line if line.endswith("\n") else line + "\n")

    @property
    def metrics(self) -> TrackedMetrics:
        """Metrics appended live to ``<dir>/metrics.mlp.jsonl``."""
        if self._metrics is None:
            sink = create_metrics_writer(self._dir, self._append_wal)
            self._metrics = TrackedMetrics(
                sink, register=self.register, execution_dir=self._dir, task=self._task
            )
        return self._metrics

    def register(
        self,
        data: object,
        *,
        title: str,
        media_type: str | None = None,
        tags: dict[str, str] | None = None,
    ) -> StagedFile:
        """Stage *data* for the owner to register as an asset titled *title*.

        The same forms as ``ExecutionContext.register``: a path to a file or
        directory (copied, so later changes to it are not recorded), or bytes
        / a dict or list (as JSON) / anything else (as text).

        Raises:
            ValueError: *title* is empty or already staged here.
            FileNotFoundError: A path that does not exist.
            RuntimeError: The attempt is sealed.
        """
        if not self._writable():
            raise RuntimeError(f"cannot stage a file: the attempt at {self._dir} is sealed")
        source: Path | None = None
        if isinstance(data, Path):
            source = data
            if not source.exists():
                raise FileNotFoundError(source)
        elif isinstance(data, str) and Path(data).exists():
            source = Path(data)
        if not title or not title.strip():
            raise ValueError("register requires a title")
        label = title.strip()
        _check_register_name(label)
        task = current_task() or self._task
        with self._stage_lock:
            if any(
                isinstance(entry, StagedFile) and entry.name == label
                for _, entry in manifest_entries(self._dir)
            ):
                raise ValueError(f"{label!r} is already staged; stage it under another title")
            is_dir = source is not None and source.is_dir()
            target = self._reserve(PurePosixPath(label).name, is_dir=is_dir)
            try:
                if source is None:
                    _write_data(target, data)
                elif is_dir:
                    shutil.copytree(source, target, dirs_exist_ok=True)
                else:
                    shutil.copyfile(source, target)
            except BaseException:
                if target.is_dir():
                    shutil.rmtree(target, ignore_errors=True)
                else:
                    target.unlink(missing_ok=True)
                raise
            relative = target.relative_to(self._dir).as_posix()
            staged = StagedFile(
                name=label,
                path=relative,
                staged=relative,
                media_type=media_type,
                tags=dict(tags or {}),
                task=task,
                created_at=datetime.now(UTC).isoformat(),
            )
            self._files.write(self._dir / MANIFEST, staged.to_line())
        return staged

    def _reserve(self, basename: str, *, is_dir: bool) -> Path:
        """Claim ``staged/<n>-<basename>`` exclusively, even against other processes."""
        staged_dir = self._dir / STAGED_DIR
        staged_dir.mkdir(parents=True, exist_ok=True)
        n = sum(1 for _ in staged_dir.iterdir()) + 1
        while True:
            candidate = staged_dir / f"{n}-{basename}"
            try:
                if is_dir:
                    candidate.mkdir()
                else:
                    os.close(os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644))
            except FileExistsError:
                n += 1
                continue
            return candidate

    def child_env(self) -> dict[str, str]:
        """``MOLAB_EXECUTION_DIR`` and ``MOLAB_TASK`` for a subprocess of this one."""
        return {EXECUTION_DIR_ENV: str(self._dir), TASK_ENV: current_task() or self._task or ""}

    def close(self) -> None:
        """Close the open files and stop being this process's tracker. Idempotent."""
        _unbind_process(self)
        self._files.close()

    def __enter__(self) -> Self:
        self._withs.append(self._claim_with)
        self._claim_with = False
        return self

    def __exit__(self, *exc_info: object) -> bool:
        if self._withs and self._withs.pop():
            self.close()
        return False


def _write_data(target: Path, data: object) -> None:
    """Write in-memory *data* the way ``ExecutionContext.register`` does."""
    if isinstance(data, (bytes, bytearray)):
        target.write_bytes(bytes(data))
    elif isinstance(data, (dict, list)):
        target.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    else:
        target.write_text(str(data), encoding="utf-8")


def _read_sealed(record: Path) -> str | None:
    """The seal of an attempt record (``sealed_at``), or ``None`` when open or unreadable."""
    try:
        raw = json.loads(record.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    sealed = raw.get("sealed_at") if isinstance(raw, dict) else None
    return sealed if isinstance(sealed, str) and sealed else None


class AttachedTracker(_StagingTracker):
    """A child process writing into its parent's attempt (D94).

    :func:`track` returns one when ``MOLAB_EXECUTION_DIR`` is set. stdio and
    metrics land at their final paths; files are staged, and the owner
    registers them when it seals. A metric record carries ``tags.task`` from
    ``MOLAB_TASK``. ``with`` is a no-op.

    The seal is re-read at most every :data:`SEAL_CHECK_SECONDS` before a
    write. After it, a print or a metric is dropped (one ``RuntimeWarning``,
    never an exception), and ``register`` raises.

    Under an offline directory (``work/_molab/track.json``, no
    ``execution.json``) there is no seal to check.

    Args:
        execution_dir: The attempt (or offline) directory.
        task: The task that started this process.

    Raises:
        RuntimeError: The directory has no ``execution.json`` (and is not an
            offline directory), or the attempt is already sealed.
    """

    def __init__(self, execution_dir: PathArg, *, task: str | None = None) -> None:
        from .execution_repository import EXECUTION_RECORD_FILENAME

        directory = Path(str(execution_dir)).absolute()
        record = directory / EXECUTION_RECORD_FILENAME
        self._record_path: Path | None = None
        if record.is_file():
            sealed = _read_sealed(record)
            if sealed is not None:
                raise RuntimeError(
                    f"cannot attach to {directory}: the attempt was sealed at {sealed}"
                )
            self._record_path = record
        elif not (directory / TRACK_RECORD).is_file():
            raise RuntimeError(
                f"cannot attach to {directory}: it has no {EXECUTION_RECORD_FILENAME}"
            )
        super().__init__(directory, task=task or None)
        self._checked_at = time.monotonic()
        self._sealed = False

    def _writable(self) -> bool:
        if self._record_path is None:
            return True
        if self._sealed:
            return False
        now = time.monotonic()
        if now - self._checked_at < SEAL_CHECK_SECONDS:
            return True
        self._checked_at = now
        if _read_sealed(self._record_path) is None:
            return True
        self._sealed = True
        warnings.warn(
            f"the attempt at {self._dir} is sealed; molab drops this process's later "
            "prints and metrics",
            RuntimeWarning,
            stacklevel=2,
        )
        return False


class OfflineTracker(_StagingTracker):
    """A script with no molab around it, writing the attempt layout into a directory (D94).

    ``stdout.log`` / ``stderr.log``, ``metrics.mlp.jsonl``, the staged
    files and their manifest, plus ``work/_molab/track.json``
    (``started_at``, host, pid, argv, python, cwd), whose ``finished_at`` is
    written by :meth:`close`, at interpreter exit, or when the first ``with``
    around it exits. ``molab runs adopt P E RUN --from DIR`` folds the
    directory into a sealed attempt.

    A directory written before keeps its first ``started_at``: it is one
    attempt, adopted once.

    Args:
        directory: Where to write; created when missing.
    """

    staged_by = "offline"

    def __init__(self, directory: PathArg = DEFAULT_TRACK_DIR) -> None:
        root = Path(str(directory)).absolute()
        root.mkdir(parents=True, exist_ok=True)
        super().__init__(root, task=None)
        self._closed = False
        self._claim_with = True
        started = datetime.now(UTC).isoformat()
        previous = _read_track_record(root / TRACK_RECORD)
        if previous is not None and isinstance(previous.get("started_at"), str):
            started = str(previous["started_at"])
        self._track: dict[str, JSONValue] = {
            "started_at": started,
            "finished_at": None,
            "host": platform.node(),
            "pid": os.getpid(),
            "argv": list(sys.argv),
            "python": sys.version,
            "cwd": str(Path.cwd()),
        }
        self._write_record()
        atexit.register(self.close)

    def _write_record(self) -> None:
        path = self._dir / TRACK_RECORD
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(path, self._track)

    def close(self) -> None:
        """Write ``finished_at`` and close the files. Idempotent."""
        if self._closed:
            return
        self._closed = True
        atexit.unregister(self.close)
        try:
            self._track["finished_at"] = datetime.now(UTC).isoformat()
            self._write_record()
        finally:
            super().close()


def _read_track_record(path: Path) -> dict[str, JSONValue] | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return raw if isinstance(raw, dict) else None


def _bind_process(tracker: Tracker) -> None:
    global _PROCESS
    with _process_lock:
        _PROCESS = tracker


def _unbind_process(tracker: Tracker) -> None:
    global _PROCESS
    with _process_lock:
        if _PROCESS is tracker:
            _PROCESS = None


def _void_claim(tracker: Tracker) -> None:
    """A tracker handed out again by :func:`track` is borrowed: its ``with`` ends nothing."""
    if isinstance(tracker, _StagingTracker):
        tracker._claim_with = False
        return
    from .execution_context import ExecutionContext

    if isinstance(tracker, ExecutionContext):
        tracker._release_track_claim()


def _open_run(
    root: Path, project: str, experiment: str, params: dict[str, JSONValue] | None
) -> ExecutionContext:
    from .workspace import Workspace

    workspace = Workspace(root)
    run = workspace.add_project(project).add_experiment(experiment).add_run(params=params)
    return run.start()._enter_for_track()


def track(
    dir: PathArg | None = None,
    *,
    project: str | None = None,
    experiment: str | None = None,
    params: dict[str, JSONValue] | None = None,
) -> Tracker:
    """The tracking surface for code that is not a molab task (D94).

    Decided in this order:

    1. An execution is current (``run.start()``, a workflow task, an earlier
       ``track()``): that one, unchanged.
    2. ``MOLAB_EXECUTION_DIR`` is set (a child of a molab execution): an
       :class:`AttachedTracker` on it, current for this process.
    3. *project* and *experiment* are given and the working directory is
       inside a workspace: the experiment is opened (idempotent on its name),
       a run is added with *params*, and its ``run.start()`` is entered and
       returned — a live attempt, sealed when the first ``with`` around it
       exits (or at interpreter exit, failed when an uncaught exception ended
       the script).
    4. Otherwise: an :class:`OfflineTracker` writing into *dir*
       (``./molab-track`` by default), current for this process. Adopt it
       later with ``molab runs adopt P E RUN --from DIR``.

    Every result works as a context manager; for cases 1 and 2 ``with`` is a
    no-op.

    Args:
        dir: The offline directory (case 4 only).
        project: The project of a new run (case 3).
        experiment: The experiment of a new run (case 3).
        params: The new run's parameters (case 3).

    Raises:
        ValueError: Only one of *project* / *experiment* is given.
        RuntimeError: ``MOLAB_EXECUTION_DIR`` names a sealed or missing attempt.
    """
    tracker = current()
    if tracker is not None:
        _void_claim(tracker)
        return tracker
    if (project is None) != (experiment is None):
        raise ValueError("molab.track: pass both project and experiment, or neither")
    attached_dir = os.environ.get(EXECUTION_DIR_ENV)
    if attached_dir:
        attached = AttachedTracker(attached_dir, task=os.environ.get(TASK_ENV) or None)
        _bind_process(attached)
        return attached
    if project is not None and experiment is not None:
        from .workspace import Workspace

        root = Workspace.enclosing_root(Path.cwd())
        if root is not None:
            return _open_run(Path(root), project, experiment, params)
        _logger.info(
            f"molab.track: {Path.cwd()} is not inside a workspace; tracking offline "
            f"into {dir if dir is not None else DEFAULT_TRACK_DIR}"
        )
    offline = OfflineTracker(dir if dir is not None else DEFAULT_TRACK_DIR)
    _bind_process(offline)
    return offline


_warn_lock = threading.Lock()
_warned = False


def _warn_copy_failed() -> None:
    """Log the first failure to copy a print into the execution; then stay quiet."""
    global _warned
    with _warn_lock:
        if _warned:
            return
        _warned = True
    _logger.warning(
        "molab.print could not copy output into the current execution's stdio log; "
        "the original output is unaffected (logged once per process)",
        exc_info=True,
    )


def _stream_of(file: object) -> Stream | None:
    """Which execution stream a ``print(file=…)`` target is, if any."""
    if file is None or file is sys.stdout or file is sys.__stdout__:
        return "stdout"
    if file is sys.stderr or file is sys.__stderr__:
        return "stderr"
    return None


# Shadows the builtin on purpose: user code opts in with ``from molab import print``.
def print(
    *values: object,
    sep: str | None = " ",
    end: str | None = "\n",
    file: SupportsWrite[str] | None = None,
    flush: bool = False,
) -> None:
    """The builtin ``print``, also recorded in the current execution's stdio.

    Writes to the original target exactly as the builtin does. Then, inside
    an execution, appends the same text to ``stdout.log`` (``file`` is
    ``None`` or the standard output) or ``stderr.log`` (the standard error).
    Any other ``file`` is not copied. A failure to copy never reaches the
    caller; it is logged once.
    """
    # typeshed overloads ``print`` on ``flush`` (a flushable file when it is
    # true); the arguments are forwarded unchanged, so the call is the user's.
    builtins.print(*values, sep=sep, end=end, file=file, flush=flush)  # ty: ignore[no-matching-overload]
    tracker = current()
    if tracker is None:
        return
    stream = _stream_of(file)
    if stream is None:
        return
    try:
        text = (sep if sep is not None else " ").join(map(str, values)) + (
            end if end is not None else "\n"
        )
        tracker.write_stdio(stream, text, flush=flush)
    except Exception:
        _warn_copy_failed()


__all__ = [
    "DEFAULT_TRACK_DIR",
    "EXECUTION_DIR_ENV",
    "IMAGE_SEMANTIC_TYPE",
    "MANIFEST",
    "METRICS_SEMANTIC_TYPE",
    "SEAL_CHECK_SECONDS",
    "STAGED_DIR",
    "STDIO_CAPTURED_ENV",
    "TASK_ENV",
    "TASK_RECORD_CAP",
    "TRACK_DIR",
    "TRACK_RECORD",
    "AttachedTracker",
    "BufferedMetrics",
    "OfflineTracker",
    "StagedFile",
    "StdioFiles",
    "Stream",
    "TrackedDirectory",
    "TrackedMetrics",
    "Tracker",
    "bind",
    "current",
    "current_task",
    "enter_task",
    "exit_task",
    "manifest_entries",
    "print",
    "read_tracked",
    "task_scope",
    "track",
    "unbind",
]
