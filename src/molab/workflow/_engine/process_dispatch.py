"""Run one task body under the ``process`` executor (the parent's half of a job).

Called by :func:`.node.run_task_body` in place of the in-process body call,
after the inputs, effective config and ``workdir`` are resolved the same way
for every executor. It builds the job, hands it to the execution's
:class:`~.process_pool.ProcessPool`, and turns the answer back into what an
in-process body would have produced:

* inputs travel as the upstream outputs' value-store refs when every one has
  one (the worker loads those bytes; nothing is re-encoded), otherwise
  inline in the store's encoding;
* the output comes back encoded by the worker; the parent decodes it for
  ``state.results`` and stashes the bytes in ``state.encoded_outputs`` so
  :func:`.node_record.output_fields` stores them as they are;
* deferred ``register_artifact`` / ``register_metric`` markers come back and
  are promoted by the caller exactly as in-process ones; metric records the
  body wrote (already in the attempt's WAL — the worker writes it) are kept
  for the node cache;
* the journal record gets ``worker_pid`` once a worker takes the job.
"""

from __future__ import annotations

import pickle
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from .node import NO_OUTPUT
from .persistence import mark_task_status
from .process_pool import ProcessExecutorError, locate_task, raise_remote_failure
from .values import UnrecordableValueError, decode, encode

if TYPE_CHECKING:
    from ..context import TaskContext
    from ..protocols import JSONMapping, TaskInput, TaskOutput
    from .state import WorkflowDeps, WorkflowState


def _locator(deps: WorkflowDeps, name: str) -> tuple:
    found = deps.process_locators.get(name)
    if found is None:
        found = locate_task(
            name, deps.registration_by_name[name], entrypoint=deps.process_entrypoint
        )
        deps.process_locators[name] = found
    return found


def _inputs_spec(
    deps: WorkflowDeps,
    state: WorkflowState,
    name: str,
    inputs: TaskInput,
    *,
    element: TaskInput,
) -> tuple:
    """Refs into the value store when the inputs are exactly upstream outputs, else inline."""
    registration = deps.registration_by_name[name]
    store = deps.values
    depends_on = list(registration.depends_on)
    if store is not None and depends_on and element is NO_OUTPUT and name not in state.root_inputs:
        refs = {dep: (state.output_records.get(dep) or {}).get("output_ref") for dep in depends_on}
        if all(isinstance(ref, str) for ref in refs.values()):
            return ("refs", store.root, depends_on, refs)
    try:
        data, encoding = encode(inputs)
    except UnrecordableValueError as exc:
        raise ProcessExecutorError(
            f"the inputs of task {name!r} cannot be sent to a worker process: {exc}"
        ) from exc
    return ("inline", data, encoding)


def _workspace_root(deps: WorkflowDeps) -> str | None:
    """The run's workspace root, for a rootless ``Workspace`` in the defining module."""
    try:
        root = deps.run.experiment.project.workspace.root  # ty: ignore[unresolved-attribute]
    except AttributeError:
        return None
    return str(root) if root is not None else None


def _keep_metrics(deps: WorkflowDeps, name: str, records: object) -> None:
    metrics = getattr(deps.run_context, "metrics", None)
    keep = getattr(metrics, "keep_task_records", None)
    if callable(keep) and isinstance(records, list) and records:
        keep(name, records)


async def run_in_worker(
    name: str,
    deps: WorkflowDeps,
    state: WorkflowState,
    task_ctx: TaskContext[Any, TaskInput],
    inputs: TaskInput,
    config: JSONMapping,
    *,
    element: TaskInput = NO_OUTPUT,
    delivered: TaskInput = NO_OUTPUT,  # noqa: ARG001 - already folded into *inputs*
) -> TaskOutput:
    """Run task *name*'s body in a worker process and return its raw output.

    Raises:
        ProcessExecutorError: The task cannot be located or its inputs sent.
        WorkerCrashedError: The worker died while running it.
        BaseException: The body's own exception, re-raised with the worker's
            traceback as its cause.
    """
    pool = deps.process_pool
    if pool is None:
        raise ProcessExecutorError("no process pool is open for this execution")
    registration = deps.registration_by_name[name]
    snapshot = deps.snapshots.get(name)
    plain_config = dict(config) if isinstance(config, Mapping) else config
    try:
        config_encoded = encode(plain_config)
    except UnrecordableValueError as exc:
        raise ProcessExecutorError(
            f"the config of task {name!r} cannot be sent to a worker process: {exc}"
        ) from exc
    run_context = deps.run_context
    execution_dir = getattr(run_context, "execution_dir", None) if deps.journal_dir else None
    job = {
        "task": name,
        "locator": _locator(deps, name),
        "snapshot_key": snapshot.key if snapshot is not None else None,
        "depends_on": list(registration.depends_on),
        "is_actor": bool(registration.is_actor),
        "inputs": _inputs_spec(deps, state, name, inputs, element=element),
        "config": config_encoded,
        "workdir": str(task_ctx.workdir) if task_ctx.workdir is not None else None,
        "execution_dir": str(execution_dir) if execution_dir is not None else None,
        "workspace_root": _workspace_root(deps),
    }

    def _started(pid: int) -> None:
        mark_task_status(
            deps.journal_dir,
            name,
            "running",
            runner={"executor": "process", "worker_pid": pid},
            started=True,
        )

    result = await pool.run(job, on_start=_started)
    mark_task_status(deps.journal_dir, name, "running", ended=True)
    if not result.get("ok"):
        raise_remote_failure(result)
    _keep_metrics(deps, name, result.get("metrics"))
    kind, extra, pending = pickle.loads(result["rest"])
    task_ctx._pending.extend(pending)
    if kind == "raw":
        return extra
    data, encoding = result["value"]
    value = decode(data, encoding)
    state.encoded_outputs[name] = (value, data, encoding)
    return value if kind == "plain" else (value, extra)


__all__ = ["run_in_worker"]
