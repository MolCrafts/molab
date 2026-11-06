"""Task executors: how a task body runs — ``thread``, ``process`` or ``inline``.

* ``thread`` (the default) — a sync body runs in a worker thread
  (``asyncio.to_thread``, or a dedicated pool of ``max_workers`` threads), so
  blocking bodies overlap; async bodies are awaited on the engine loop. Cheap,
  but a body holding the GIL gains nothing, and a value bound to the thread
  that made it (a pyo3 ``unsendable`` object) is later touched from another.
* ``process`` — each body runs in a worker process (:mod:`.process_pool`), a
  fresh interpreter (spawn semantics) that imports the workflow's module by
  path and finds the task by name. Truly parallel and isolated; inputs and
  outputs cross the boundary in the value store's encoding.
* ``inline`` — the body runs on the engine's own thread, one at a time. For
  debugging and for thread-bound libraries.

The executor is chosen per run > per task > per workflow > :data:`DEFAULT_EXECUTOR`
(:func:`resolve_executors`); the one exception is an engine capability task
(``SubWorkflow``), which never leaves the parent process.
"""

from __future__ import annotations

import asyncio
import contextvars
import os
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from .._graph_decl import TaskRegistration

#: The executor names, in documentation order.
EXECUTORS: tuple[str, ...] = ("thread", "process", "inline")

#: The executor a task runs under when nothing chooses one.
DEFAULT_EXECUTOR = "thread"

Executor = Literal["thread", "process", "inline"]


def check_executor(value: str | None, *, where: str = "executor") -> str | None:
    """Return *value* when it names an executor (``None`` passes through).

    Raises:
        ValueError: *value* is not one of :data:`EXECUTORS`.
    """
    if value is None or value in EXECUTORS:
        return value
    raise ValueError(f"{where} must be one of {list(EXECUTORS)}, got {value!r}")


def check_max_workers(value: int | None) -> int | None:
    """Return *value* when it is ``None`` or a positive int.

    Raises:
        ValueError: *value* is not a positive integer.
    """
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"max_workers must be a positive integer, got {value!r}")
    return value


def default_max_workers(executor: str) -> int:
    """The worker count when none is given: the CPU count for ``process``."""
    if executor == "process":
        return os.cpu_count() or 1
    return min(32, (os.cpu_count() or 1) + 4)


def resolve_executors(
    registrations: Mapping[str, TaskRegistration],
    *,
    workflow_default: str | None,
    run_override: str | None,
) -> dict[str, str]:
    """``{task: executor}`` by precedence run > task > workflow > default.

    An engine capability task (``__wf_capability__``, e.g. ``SubWorkflow``)
    drives the engine itself and never leaves the parent: under ``process``
    it runs as ``thread``.
    """
    resolved: dict[str, str] = {}
    for name, registration in registrations.items():
        chosen = (
            run_override
            or getattr(registration, "executor", None)
            or workflow_default
            or DEFAULT_EXECUTOR
        )
        if chosen == "process" and getattr(registration.fn_or_class, "__wf_capability__", None):
            chosen = "thread"
        resolved[name] = chosen
    return resolved


class SyncCaller:
    """Runs a sync task body for the ``thread`` or ``inline`` executor.

    ``thread`` without *max_workers* uses ``asyncio.to_thread``; with it, a
    dedicated pool. Either way the caller's context variables (the current
    execution and task) travel with the call. ``inline`` calls the body on
    the engine thread under a lock, so inline bodies run one at a time.
    """

    def __init__(self, executor: str, *, max_workers: int | None = None) -> None:
        self.executor = executor
        self._pool = (
            ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="molab-task")
            if executor == "thread" and max_workers is not None
            else None
        )
        self._lock: asyncio.Lock | None = None

    async def call(
        self,
        func: Callable[..., Any],
        args: list,
        kwargs: dict,
        on_start: Callable[[], None] | None = None,
        on_end: Callable[[], None] | None = None,
    ) -> Any:  # noqa: ANN401
        """Call ``func(*args, **kwargs)`` under this executor.

        *on_start* runs the moment the body itself begins — after any wait for
        the inline lock or a pool worker — and *on_end* the moment it returns
        or raises, so the caller can stamp the span the body really ran.
        """

        def body() -> Any:  # noqa: ANN401
            if on_start is not None:
                on_start()
            try:
                return func(*args, **kwargs)
            finally:
                if on_end is not None:
                    on_end()

        if self.executor == "inline":
            if self._lock is None:
                self._lock = asyncio.Lock()
            async with self._lock:
                return body()
        if self._pool is None:
            return await asyncio.to_thread(body)
        context = contextvars.copy_context()
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._pool, lambda: context.run(body))

    def close(self) -> None:
        """Release the dedicated thread pool, if any."""
        if self._pool is not None:
            self._pool.shutdown(wait=False, cancel_futures=True)


__all__ = [
    "DEFAULT_EXECUTOR",
    "EXECUTORS",
    "Executor",
    "SyncCaller",
    "check_executor",
    "check_max_workers",
    "default_max_workers",
    "resolve_executors",
]
