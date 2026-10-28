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

Stdlib only (plus ``mollog`` and the stdlib-only ``metrics_seam``), so
``import molab`` stays light.
"""

from __future__ import annotations

import builtins
import mimetypes
import sys
import threading
from collections.abc import Callable, Generator, Iterable, Mapping
from contextlib import contextmanager
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, TYPE_CHECKING, Literal, Protocol, runtime_checkable

from mollog import get_logger

from molab._typing import JSONValue

from .metrics_seam import MetricRecord, MetricsSink

if TYPE_CHECKING:
    from _typeshed import SupportsWrite

    from .domain import Artifact

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

    def emit_artifact(
        self,
        data: object,
        *,
        name: str | None = None,
        media_type: str | None = None,
        semantic_type: str | None = None,
    ) -> Artifact:
        """Archive *data* as an Artifact of the attempt."""
        ...


_CURRENT: ContextVar[Tracker | None] = ContextVar("molab_current_execution", default=None)
"""The execution this context runs inside, or ``None``."""

_TASK: ContextVar[str | None] = ContextVar("molab_current_task", default=None)
"""The workflow task this context runs inside, or ``None``."""


def current() -> Tracker | None:
    """The current execution, or ``None`` outside one."""
    return _CURRENT.get()


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


def _with_task(tags: dict[str, JSONValue] | None) -> dict[str, JSONValue] | None:
    """*tags* plus ``task`` when a task scope is active; an explicit ``task`` wins."""
    task = _TASK.get()
    if task is None:
        return tags
    merged: dict[str, JSONValue] = {"task": task}
    if tags:
        merged.update(tags)
    return merged


class _MetricsFront:
    """The five record types over one :class:`MetricsSink`, tagged with the task."""

    def __init__(self, sink: MetricsSink) -> None:
        self._sink = sink

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
            self._sink.scalar(key, value, step, wall_time=wall_time, tags=_with_task(tags))
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
                key, bins, counts, step, wall_time=wall_time, tags=_with_task(tags)
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
            self._sink.text(key, text, step, wall_time=wall_time, tags=_with_task(tags))
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
                key, path, step, caption=caption, wall_time=wall_time, tags=_with_task(tags)
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
            self._sink.json(key, value, step, wall_time=wall_time, tags=_with_task(tags))
        )

    def flush(self) -> None:
        """Push buffered records to their destination."""
        self._sink.flush()


class TrackedMetrics(_MetricsFront):
    """One execution's metrics: its WAL writer, tagged and captured per task (D93).

    ``ExecutionContext.metrics`` returns it, and so does ``TaskContext.metrics``
    under an execution, so a driver script and a workflow task write the same
    ``artifacts/metrics.mlp.jsonl``, live.

    - A record written while a task scope is active gets ``tags.task`` (an
      explicit ``tags["task"]`` wins) and is also kept in memory under the
      task's name, at most :data:`TASK_RECORD_CAP` per task. The node cache
      takes them with :meth:`take_task_records` to replay on a hit.
    - :meth:`image` archives the image as an Artifact first, then appends an
      ``image_ref`` to that Artifact's path.

    Args:
        sink: The execution's WAL writer (``metrics_seam.create_metrics_writer``).
        emit_artifact: The execution's ``emit_artifact``, which :meth:`image`
            archives through. ``None``: :meth:`image` raises.
        execution_dir: The attempt's directory. An image file outside it is
            archived from a copy of its bytes, since an Artifact is a product
            of the attempt.
    """

    def __init__(
        self,
        sink: MetricsSink,
        *,
        emit_artifact: Callable[..., Artifact] | None = None,
        execution_dir: Path | None = None,
    ) -> None:
        super().__init__(sink)
        self._emit_artifact = emit_artifact
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
        """Archive an image as an Artifact, then reference it with ``image_ref``.

        Args:
            key: The metric key.
            data: A path to an existing image file (one outside the attempt
                is archived from a copy of its bytes), or the image's bytes.
            step: The step this image belongs to.
            caption: A caption for the viewer.
            name: The Artifact's name; required for bytes, the file's name by
                default. Each image is its own Artifact, so two images need
                two names.
            tags: Record tags.

        Returns:
            The ``image_ref`` record; its ``v.path`` is the Artifact's path
            (``artifacts/<name>``, relative to the execution directory).

        Raises:
            ValueError: *data* is bytes without *name*, or a string that is not
                an existing path.
            RuntimeError: No ``emit_artifact`` was given.
        """
        if self._emit_artifact is None:
            raise RuntimeError("metrics.image needs an execution to archive the image")
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
        artifact = self._emit_artifact(
            source,
            name=label,
            media_type=media_type,
            semantic_type=IMAGE_SEMANTIC_TYPE,
        )
        return self.image_ref(key, artifact.path, step, caption=caption, tags=tags)


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
    tracker = _CURRENT.get()
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
    "IMAGE_SEMANTIC_TYPE",
    "TASK_RECORD_CAP",
    "BufferedMetrics",
    "StdioFiles",
    "Stream",
    "TrackedMetrics",
    "Tracker",
    "bind",
    "current",
    "current_task",
    "enter_task",
    "exit_task",
    "print",
    "task_scope",
    "unbind",
]
