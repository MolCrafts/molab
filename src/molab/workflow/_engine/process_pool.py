"""The ``process`` executor's parent side: a pool of worker interpreters.

Each worker is ``python -m molab.workflow._engine.process_worker`` — a fresh
interpreter, which is what the ``spawn`` start method gives (safe on macOS
and next to threaded native libraries), started with :mod:`subprocess`
rather than :mod:`multiprocessing` so the parent's ``__main__`` (a
``molab run`` script, whose top level wires up workspaces) is not
re-imported in every worker. Parent and worker talk over a socket pair with
:class:`multiprocessing.connection.Connection` framing. POSIX only.

A worker serves one task at a time and is reused for the next; at most
``max_workers`` run at once. A task the run cancels kills its worker (and
reaps it); a worker that dies (segfault, ``SIGKILL``, ``os._exit``) fails its
task with :class:`WorkerCrashedError` naming the signal or exit code — the
run never hangs on it. :meth:`ProcessPool.close` stops every worker.

:func:`locate_task` is how a worker finds a task without pickling its body.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import os
import pickle
import signal
import socket
import subprocess
import sys
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from multiprocessing.connection import Connection
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .._graph_decl import TaskRegistration

#: The worker module ``python -m`` runs.
WORKER_MODULE = "molab.workflow._engine.process_worker"


class ProcessExecutorError(RuntimeError):
    """A task cannot run under the ``process`` executor."""


class WorkerCrashedError(RuntimeError):
    """The worker process running a task died before answering."""


class RemoteTaskError(RuntimeError):
    """A task body failed in a worker with an exception that could not be pickled back."""


class _RemoteTraceback(Exception):
    """The worker-side traceback, chained as the ``__cause__`` of a re-raised error."""

    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.text = text

    def __str__(self) -> str:
        return f"\n\nworker traceback:\n{self.text}"


def locate_task(
    name: str,
    registration: TaskRegistration,
    *,
    entrypoint: str | None = None,
) -> tuple:
    """How a worker finds task *name*'s body without pickling it.

    In order: the module-level ``Workflow`` / ``CompiledWorkflow`` (in the
    module that defines the body) holding this very registration; the
    experiment's code locator *entrypoint*; the body itself when it is a
    module-level function; a registered task type (``task_type`` slug) with
    its ``__init__`` config.

    Raises:
        ProcessExecutorError: None applies (e.g. a task defined inside a
            function, in a workflow no module or locator names).
    """
    from ..compiled import CompiledWorkflow
    from ..compiler import Workflow
    from ..registry import default_registry
    from ..snapshot import task_config_of

    body = registration.fn_or_class
    modules = [getattr(body, "__module__", None), type(body).__module__]
    for module_name in dict.fromkeys(m for m in modules if m):
        module = sys.modules.get(module_name)
        file = getattr(module, "__file__", None)
        if module is None or file is None:
            continue
        for attr, value in list(vars(module).items()):
            if isinstance(value, (Workflow, CompiledWorkflow)) and any(
                task.name == name and task.fn_or_class is body for task in value._tasks
            ):
                return ("module", module_name, file, attr)
    if entrypoint:
        return ("entrypoint", entrypoint)
    qualname = getattr(body, "__qualname__", "")
    module_name = getattr(body, "__module__", None)
    module = sys.modules.get(module_name) if module_name else None
    file = getattr(module, "__file__", None)
    if inspect.isfunction(body) and "<locals>" not in qualname and file is not None:
        return ("module", module_name, file, qualname)
    slug = registration.task_type
    if slug is not None and default_registry.has(slug):
        return ("registry", slug, task_config_of(body))
    raise ProcessExecutorError(
        f"task {name!r} cannot run under the process executor: a worker process "
        "finds a task by importing the module that defines its workflow, and "
        f"{qualname or type(body).__qualname__!r} is not reachable that way. Define "
        "the workflow at module level (wf = Workflow(...)), bind it with a locator, "
        "or choose executor='thread' / 'inline' for this task."
    )


def describe_exit(code: int | None) -> str:
    """``died with SIGKILL`` / ``exited with code 3`` for a worker return code."""
    if code is None:
        return "stopped answering"
    if code < 0:
        try:
            return f"died with {signal.Signals(-code).name}"
        except ValueError:
            return f"died with signal {-code}"
    return f"exited with code {code}"


class _Worker:
    """One worker interpreter and its connection."""

    def __init__(self) -> None:
        if os.name != "posix":
            raise ProcessExecutorError("the process executor needs a POSIX system")
        parent_sock, child_sock = socket.socketpair()
        try:
            self.proc = subprocess.Popen(
                [sys.executable, "-m", WORKER_MODULE, str(child_sock.fileno())],
                pass_fds=(child_sock.fileno(),),
                stdin=subprocess.DEVNULL,
                cwd=Path.cwd(),
            )
        finally:
            child_sock.close()
        self.conn = Connection(parent_sock.detach())
        self.conn.send_bytes(pickle.dumps({"sys_path": list(sys.path)}))

    @property
    def pid(self) -> int:
        return self.proc.pid

    def call(self, payload: bytes) -> bytes:
        """Send one job and wait for its answer (blocking; run off the loop)."""
        self.conn.send_bytes(payload)
        return self.conn.recv_bytes()

    def kill(self) -> None:
        """Kill and reap the worker; idempotent."""
        if self.proc.poll() is None:
            self.proc.kill()
        with contextlib.suppress(subprocess.TimeoutExpired):
            self.proc.wait(timeout=10)
        self.conn.close()

    def stop(self) -> None:
        """Ask the worker to exit, then make sure it did."""
        try:
            self.conn.send_bytes(pickle.dumps(None))
            self.proc.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired, ValueError):
            pass
        self.kill()


class ProcessPool:
    """At most *max_workers* worker processes, reused across tasks of one execution."""

    def __init__(self, max_workers: int) -> None:
        self.max_workers = max_workers
        self._idle: list[_Worker] = []
        self._busy: set[_Worker] = set()
        self._slots: asyncio.Semaphore | None = None
        # One blocking send/receive per running worker, off the event loop.
        self._io = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="molab-proc")
        self._closed = False

    async def run(self, job: dict, *, on_start: Callable[[int], None] | None = None) -> dict:
        """Run *job* in a worker and return its result document.

        Raises:
            WorkerCrashedError: The worker died before answering.
            asyncio.CancelledError: The task was cancelled; its worker is killed.
        """
        if self._slots is None:
            self._slots = asyncio.Semaphore(self.max_workers)
        async with self._slots:
            if self._closed:
                raise ProcessExecutorError("the process pool is closed")
            worker = self._idle.pop() if self._idle else _Worker()
            self._busy.add(worker)
            if on_start is not None:
                on_start(worker.pid)
            payload = pickle.dumps(job)
            loop = asyncio.get_running_loop()
            try:
                answer = await loop.run_in_executor(self._io, worker.call, payload)
            except asyncio.CancelledError:
                self._busy.discard(worker)
                worker.kill()
                raise
            except (EOFError, OSError) as exc:
                self._busy.discard(worker)
                code = worker.proc.wait()
                worker.kill()
                raise WorkerCrashedError(
                    f"worker process {worker.pid} running task {job.get('task')!r} "
                    f"{describe_exit(code)} before returning a result"
                ) from exc
            self._busy.discard(worker)
            if self._closed:
                worker.stop()
            else:
                self._idle.append(worker)
            return pickle.loads(answer)

    def close(self) -> None:
        """Stop idle workers and kill busy ones. Idempotent."""
        self._closed = True
        for worker in self._idle:
            worker.stop()
        self._idle.clear()
        for worker in list(self._busy):
            worker.kill()
        self._busy.clear()
        self._io.shutdown(wait=False, cancel_futures=True)


def raise_remote_failure(result: dict) -> None:
    """Re-raise a worker's failure: its own exception when it pickled, chained to its traceback."""
    remote = _RemoteTraceback(str(result.get("traceback", "")))
    payload = result.get("error")
    if payload is not None:
        try:
            exc: Any = pickle.loads(payload)
        except Exception:
            exc = None
        if isinstance(exc, BaseException):
            raise exc from remote
    raise RemoteTaskError(f"{result.get('type')}: {result.get('message')}") from remote


__all__ = [
    "ProcessExecutorError",
    "ProcessPool",
    "RemoteTaskError",
    "WorkerCrashedError",
    "describe_exit",
    "locate_task",
    "raise_remote_failure",
]
