# Workflow Runtime

Execution lives on `WorkflowRuntime`, not on the compiled artifact. You instantiate the runtime (it is cheap and stateless apart from an optional cache) and hand it a `CompiledWorkflow`:

```python
from molab.workflow import Workflow, WorkflowRuntime

wf = Workflow(name="demo")


@wf.task
async def compute(scale: float = 1.0) -> float:
    return 42.0 * scale


compiled = wf.compile()

runtime = WorkflowRuntime()
result = await runtime.execute(compiled)  # block until done
handle = await runtime.start(compiled)  # background handle
result = await handle.wait()
```

The compiled artifact carries a frozen, molab-owned `ExecutionPlan` that a structural engine executes with values-on-edges semantics (task inputs are delivered from upstream outputs; `End` is molab's own sentinel in `molab.workflow.types`) — but most user code should treat that as an implementation detail rather than as a direct API surface.

## What the Runtime Actually Does

When execution begins, the runtime builds the initial workflow state (optionally seeded with already-known task outputs), injects root-task inputs, and drives the lowered graph to completion. Tasks whose dependencies are all satisfied run concurrently. That is why most workflow parallelism in Molab is implicit: you declare the dependency structure, and the runtime extracts the available concurrency from that structure.

If a `RunContext` is attached (`execute(..., run_context=ctx)`), the runtime binds the run's profile config into every task **by name**, binds the run's sweep parameters into root tasks **by name** (with a content-addressed `workdir` exposed as `ctx.workdir`), persists per-node outputs under the run's execution directory, and back-propagates task failures so the run's final status is correct.

The runtime also relies on the compiled workflow identity rather than on ad hoc process state. `workflow_hash` is derived deterministically from the workflow name and task topology, which is what makes it useful for correlating equivalent graphs across executions and machines.

## Where Persistent State Lives

Workflow execution state — the `workflow.json` snapshot under `<run_dir>/executions/<exec_id>/` — is written through workspace's public `atomic_write_json` helper, not raw filesystem calls. The atomicity guarantee is workspace's, not a runtime-layer reinvention. This is the runtime side of the *workflow → workspace* dependency direction documented in CLAUDE.md. Resume is caller-driven: every node records its inputs and output by ref into the run's content-addressed `values/` store, and the caller (e.g. `molab run --resume`, or `--rerun --task NAME` for one node) builds the seeds with `read_attempt_seeds` and passes them as `execute(..., attempt_seeds=...)`. See [Workflow persistence](workflow-persistence.md#node-records).

## Caching

Cache persistence is pluggable. `Caching` orchestrates the cache policy (key derivation, format version, LRU eviction); the storage primitive is a `CacheStore` implementation supplied at construction time:

- `FileCacheStore(`.molab/runs/<run-id>/cache/`)` — the default when you pass a `run_context`; the runtime builds this automatically. Task-result cache lives **under the run**, not at the workspace root.
- `an explicit FileCacheStore` — an explicit workspace-wide cache folder. Execution does not auto-create it.
- `FileCacheStore(path)` — any other directory. Useful when the caller has no run (e.g. ad-hoc scripts; the FastAPI server's process-local cache).

There is no user-home cache. `WorkflowRuntime.execute` / `start` no longer take `run_dir=`. `load_workflow_from_entrypoint` lives in `molab.workflow` only.

## Blocking Execution and Background Execution

`runtime.execute(...)` is the block-and-return path. It runs the workflow to completion and returns a `WorkflowResult`. `runtime.start(...)` launches the same execution as a background asyncio task and returns a `WorkflowExecution` handle, which can later be awaited (`await handle.wait()`) or cancelled (`await handle.cancel()`). The two entry points differ in control style, not in workflow semantics.

## Attaching Persistent State

There are two practical execution modes. The first is pure in-memory execution with no workspace attached. The second is execution under an opened `RunContext`:

```python
import molab as me

await runtime.execute(compiled)
await runtime.execute(compiled, config={"scale": 2.0})

ws = me.Workspace("./lab", name="lab")
exp = ws.add_project("demo").add_experiment("baseline").define(compiled, params={"scale": [2.0]})
run = exp.list_runs()[0]

with run.start() as ctx:  # run.start(profile_config=cfg) to attach a resolved profile
    await runtime.execute(compiled, run_context=ctx)
```

When a live `RunContext` is passed, its profile config supplies the values bound to tasks by name (the `config=` kwarg is ignored in its favor), and the run's lifecycle — status transitions, execution records, error capture — is managed by the `with run.start()` block. For the common "build a fresh run and execute on it" shape, `runtime.run_on(compiled, experiment, params=...)` does both steps in one call.

## Task Executors: Threads, Processes or Inline

How a task body runs is a choice, made per workflow, per task or per run — the run wins, then the task, then the workflow:

```python
wf = Workflow(name="charges", executor="process")  # workflow default


@wf.task(executor="inline")  # this task only
def load(path: str) -> Frame: ...
```

```bash
molab run flow.py --executor process --max-workers 8   # this run, every task
```

The same choice is `execute_run(wf, run, executor="process", max_workers=8)`, `WorkflowRuntime().execute(..., executor=...)`, and `"taskExecutor"` / `"maxWorkers"` on `POST …/executions`. A run's choice is recorded on its Execution (`executor.task_executor`, `executor.task_max_workers`), and each journal record says how and where its body ran (`executor`, `worker_pid`).

| executor | how a body runs | use it for |
|---|---|---|
| `thread` (default) | sync bodies in worker threads (`max_workers` caps a dedicated pool) | I/O, subprocesses, libraries that release the GIL |
| `process` | each body in a worker process — a fresh interpreter (spawn semantics) | CPU-bound Python holding the GIL, native libraries that are not thread-safe, isolation |
| `inline` | on the engine's own thread, one at a time | debugging, thread-bound objects (e.g. a pyo3 `unsendable` value) |

Under `process`, a worker imports the module that defines the workflow and finds the task by name — no closure is pickled. Define the workflow at module level (`wf = Workflow(...)`) or bind it with a locator; a task defined inside a function cannot run in a worker and is refused with a message saying so. A `molab run` script is imported under a private name, so its `if __name__ == "__main__":` block does not run in a worker, but its top level does: keep heavy side effects under the guard. Inputs and outputs cross the boundary in the value store's encoding (JSON, else pickle): an upstream output goes to the worker as its `values/` ref, and the parent stores the bytes the worker encoded without pickling the value again. Inside the worker, `ctx.workdir`, `ctx.metrics`, `ctx.register_artifact` and `from molab import print` behave as in-process: prints land in the attempt's `stdout.log` / `stderr.log`, metrics in its metrics log (tagged with the task), artifacts are recorded by the parent. The node cache, node records, resume and `--rerun --task` behave the same under every executor.

A body's exception fails its task with the exception's own type and message (the worker's traceback is chained to it); a worker that dies (segfault, `SIGKILL`) fails its task with `WorkerCrashedError` naming the signal; cancelling the run kills its running workers. The `process` executor needs a POSIX system.

## Cancellation and Failure

When execution runs through the background handle returned by `runtime.start(...)`, cancellation flows through that handle. A failed task does not raise out of `execute(...)`: the result comes back with `status="failed"`, completed outputs preserved (for `seed_outputs=` resume), and the failure recorded on the run when a `run_context` is attached. Programming errors in the workflow definition itself (cycles, unknown routes, …) do raise, as `WorkflowError` subclasses. Cancellation and failure are not special side channels; they are part of the same run history model as successful completion.

## The Useful Boundary

The most useful way to think about the runtime is that it is responsible for turning a compiled workflow definition into one concrete execution, possibly under a persistent run record. It is not where you should model research structure, scheduler policy, or asset scoping. Those remain separate concerns, which is why the runtime can stay small even as the rest of the system grows around it.

## Runnable Example

`examples/workflow/workflow_runtime.py` shows both entry points — `runtime.execute()` blocking to completion and `runtime.start()` returning a `WorkflowExecution` handle.
