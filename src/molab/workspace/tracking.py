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

Stdlib only (plus ``mollog``), so ``import molab`` stays light.
"""

from __future__ import annotations

import builtins
import sys
import threading
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar, Token
from pathlib import Path
from typing import IO, TYPE_CHECKING, Literal, Protocol, runtime_checkable

from mollog import get_logger

if TYPE_CHECKING:
    from _typeshed import SupportsWrite

_logger = get_logger(__name__)

#: A stdio stream of one execution.
Stream = Literal["stdout", "stderr"]


@runtime_checkable
class Tracker(Protocol):
    """What the current execution offers to code running inside it.

    :class:`~molab.workspace.execution_context.ExecutionContext` satisfies it.
    Deliberately minimal: later phases add metrics and artifact staging.
    """

    @property
    def execution_dir(self) -> Path:
        """The attempt's directory, ``executions/eNN``."""
        ...

    def write_stdio(self, stream: Stream, text: str, *, flush: bool = False) -> None:
        """Append *text* verbatim to the attempt's *stream* file."""
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


@contextmanager
def task_scope(name: str) -> Generator[None]:
    """Mark the code inside as the body of workflow task *name*."""
    token = _TASK.set(name)
    try:
        yield
    finally:
        _TASK.reset(token)


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
    "StdioFiles",
    "Stream",
    "Tracker",
    "bind",
    "current",
    "current_task",
    "print",
    "task_scope",
    "unbind",
]
