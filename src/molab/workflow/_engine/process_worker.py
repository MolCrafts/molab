"""The ``process`` executor's worker: one fresh interpreter running task bodies.

Started by :mod:`.process_pool` as ``python -m molab.workflow._engine.process_worker
<fd>`` — a fresh interpreter (the ``spawn`` start method's semantics) that
does *not* re-import the parent's ``__main__``. It talks to the parent over
the socket *fd* with length-prefixed pickles
(:class:`multiprocessing.connection.Connection`): a hello carrying the parent's
``sys.path``, then one job per task, answered by one result.

A job names the task's body by **locator**, never by pickling it
(:func:`.process_pool.locate_task`): the module that defines the workflow is
imported under the parent's module name (a ``molab run`` script — the
parent's ``__main__`` — is executed under a private name, so its
``if __name__ == "__main__"`` block does not run, and then registered as this
process's ``__main__``), so classes defined there pickle by the same reference
on both sides. The resolved body's ``TaskSnapshot`` key must equal the
parent's, or the job fails (the code changed under the run).

Inside the job the body runs on this process's main thread (the ``inline``
runner) under an :class:`~molab.workspace.tracking.AttachedTracker` for the
parent's execution, so ``from molab import print`` reaches the attempt's
``stdout.log`` / ``stderr.log``, ``ctx.metrics`` writes the attempt's metrics
WAL (tagged with the task), and the records are returned for the node cache.
The output is encoded once, here, in the value store's encoding
(:func:`.values.encode`); the parent stores those bytes as they are.
"""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import inspect
import os
import pickle
import sys
import traceback
from functools import reduce
from multiprocessing.connection import Connection
from pathlib import Path
from types import ModuleType
from typing import Any

#: The private module name a parent ``__main__`` script is executed under.
_MAIN_KEY = "_molab_process_main"

_modules: dict[tuple[str, str | None], ModuleType] = {}
_bodies: dict[tuple, Any] = {}


def _import_as(name: str, file: str | None) -> ModuleType:
    """The parent's module *name* (defined in *file*), imported here under that name."""
    cached = _modules.get((name, file))
    if cached is not None:
        return cached
    if name != "__main__":
        module = sys.modules.get(name)
        if module is None:
            try:
                module = importlib.import_module(name)
            except ImportError:
                if file is None:
                    raise
                module = _exec_file(name, file)
    else:
        if file is None:
            raise ImportError("the parent's __main__ has no file to import")
        module = _exec_file(_MAIN_KEY, file)
        # Now the guard has not run, take the parent's name: classes and
        # functions defined there pickle as ``__main__.X`` on both sides.
        module.__name__ = "__main__"
        for value in vars(module).values():
            if getattr(value, "__module__", None) == _MAIN_KEY and (
                inspect.isclass(value) or inspect.isfunction(value)
            ):
                value.__module__ = "__main__"
        sys.modules["__main__"] = module
    _modules[(name, file)] = module
    return module


def _exec_file(name: str, file: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, file)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import {file}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    parent = str(Path(file).parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)
    spec.loader.exec_module(module)
    return module


def _resolve_body(locator: tuple, task: str, workspace_root: str | None = None) -> Any:  # noqa: ANN401
    """The task body *locator* names (see :func:`.process_pool.locate_task`).

    While the defining module is imported, a rootless ``Workspace(name=...)``
    at its top level resolves to the run's workspace (*workspace_root*), as
    under ``molab run`` (a weak override: an explicit root wins).
    """
    key = (locator, task)
    if key in _bodies:
        return _bodies[key]
    from molab.workspace.workspace import set_cli_root_override

    if workspace_root is not None:
        set_cli_root_override(workspace_root, explicit=False)
    try:
        body = _locate(locator, task)
    finally:
        if workspace_root is not None:
            set_cli_root_override(None)
    _bodies[key] = body
    return body


def _locate(locator: tuple, task: str) -> Any:  # noqa: ANN401
    kind = locator[0]
    if kind == "module":
        _, module_name, file, attr = locator
        target = reduce(getattr, attr.split("."), _import_as(module_name, file))
        body = _body_from(target, task) if _is_workflow(target) else target
    elif kind == "entrypoint":
        from ..loader import load_workflow_from_entrypoint

        body = _body_from(load_workflow_from_entrypoint(locator[1]), task)
    elif kind == "registry":
        from ..registry import default_registry

        _, slug, config = locator
        body = default_registry.get(slug)(config)
    else:
        raise ValueError(f"unknown task locator {locator!r}")
    return body


def _is_workflow(value: object) -> bool:
    from ..compiled import CompiledWorkflow
    from ..compiler import Workflow

    return isinstance(value, (Workflow, CompiledWorkflow))


def _body_from(workflow: object, task: str) -> Any:  # noqa: ANN401
    from ..compiled import CompiledWorkflow
    from ..compiler import Workflow

    tasks = workflow._tasks if isinstance(workflow, (Workflow, CompiledWorkflow)) else None
    if tasks is None:
        raise TypeError(f"{type(workflow).__name__} is not a workflow")
    for registration in tasks:
        if registration.name == task:
            return registration.fn_or_class
    raise LookupError(f"the workflow has no task {task!r}")


def _inputs(spec: tuple) -> Any:  # noqa: ANN401
    from .values import ValueStore, decode

    if spec[0] == "inline":
        return decode(spec[1], spec[2])
    _, root, names, refs = spec
    store = ValueStore(root)
    values = {name: store.get(refs[name]) for name in names}
    return values[names[0]] if len(names) == 1 else values


def _split(raw: Any) -> tuple[str, Any, Any]:  # noqa: ANN401
    """``(shape, value, sentinel)``: the part of *raw* the journal records."""
    from ..outputs import RegisterAsset, RegisterMetric
    from ..types import End, Next

    markers = (RegisterAsset, RegisterMetric)
    if isinstance(raw, (Next, End, *markers)):
        return "raw", None, None
    value, shape, sentinel = raw, "plain", None
    if isinstance(raw, tuple) and len(raw) == 2 and isinstance(raw[1], (Next, End)):
        value, shape, sentinel = raw[0], "pair", raw[1]
    if isinstance(value, markers) or (
        isinstance(value, dict) and any(isinstance(v, markers) for v in value.values())
    ):
        return "raw", None, None
    return shape, value, sentinel


def run_job(job: dict) -> dict:
    """Run one task body and describe the outcome (never raises)."""
    from molab.workspace import tracking

    from .._graph_decl import TaskRegistration
    from ..context import TaskContext
    from ..snapshot import TaskSnapshot
    from .executors import SyncCaller
    from .node import _invoke_body_with_ctx
    from .values import decode, encode

    name = job["task"]
    tracker = None
    token = None
    try:
        body = _resolve_body(job["locator"], name, job.get("workspace_root"))
        expected = job.get("snapshot_key")
        if expected is not None and TaskSnapshot.from_task_body(name, body).key != expected:
            raise RuntimeError(
                f"task {name!r} resolves to different code in the worker than in the "
                "parent (snapshot key mismatch); did its source change during the run?"
            )
        registration = TaskRegistration(
            name=name,
            fn_or_class=body,
            depends_on=list(job["depends_on"]),
            is_actor=job["is_actor"],
        )
        inputs = _inputs(job["inputs"])
        config = decode(*job["config"])
        workdir = Path(job["workdir"]) if job.get("workdir") else None
        task_ctx: TaskContext[Any, Any] = TaskContext(inputs=inputs, config=config, workdir=workdir)
        if job.get("execution_dir"):
            tracker = tracking.AttachedTracker(job["execution_dir"], task=name)
            token = tracking.bind(tracker)
        with tracking.task_scope(name):
            raw = asyncio.run(
                _invoke_body_with_ctx(
                    registration, task_ctx, inputs, config or {}, runner=SyncCaller("inline")
                )
            )
        records = (
            tracker.metrics.take_task_records(name)
            if tracker is not None and tracker._metrics is not None
            else []
        )
        shape, value, sentinel = _split(raw)
        pending = list(task_ctx._pending)
        if shape == "raw":
            rest = pickle.dumps(("raw", raw, pending))
            return {"ok": True, "value": None, "rest": rest, "metrics": records}
        data, encoding = encode(value)
        return {
            "ok": True,
            "value": (data, encoding),
            "rest": pickle.dumps((shape, sentinel, pending)),
            "metrics": records,
        }
    except BaseException as exc:  # every failure goes back to the parent
        return _failure(exc)
    finally:
        if token is not None:
            tracking.unbind(token)
        if tracker is not None:
            tracker.close()


def _failure(exc: BaseException) -> dict:
    text = "".join(traceback.format_exception(exc))
    try:
        payload = pickle.dumps(exc)
        pickle.loads(payload)
    except Exception:
        payload = None
    return {
        "ok": False,
        "error": payload,
        "type": type(exc).__name__,
        "message": str(exc),
        "traceback": text,
    }


def main(argv: list[str]) -> int:
    """Serve jobs on the socket fd ``argv[1]`` until the parent closes it."""
    conn = Connection(int(argv[1]))
    hello = pickle.loads(conn.recv_bytes())
    sys.path[:] = list(hello["sys_path"])
    while True:
        try:
            data = conn.recv_bytes()
        except (EOFError, OSError):
            return 0
        job = pickle.loads(data)
        if job is None:
            return 0
        conn.send_bytes(pickle.dumps(run_job(job)))


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    sys.exit(main(sys.argv))
