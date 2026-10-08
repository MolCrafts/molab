# Compiler Internals

This page is for contributors who need to understand — or modify — how a `WorkflowCompiler` produces a `CompiledWorkflow` and how that artifact becomes an executable graph. End-users should read the [Quick Start](../getting-started/quick-start.md) first.

There is **no intermediate JSON representation on the execution path**. Compilation happens in memory, in one pass, when `WorkflowCompiler().compile(wf)` is called. The lowering lives in `molab.workflow._engine.*`, which is private to the workflow package. The plan and engine are molab-owned plain Python — the former `pydantic_graph` dependency is gone entirely (no import anywhere in the repo; the `End` sentinel is molab's own, in `molab.workflow.types`).

## Compilation Flow

```
@wf.task / wf.actor / Workflow.add(...)           →  TaskRegistration[]
wf.control / wf.branch / wf.loop / wf.parallel    →  control-flow declarations
                              │
                              ▼   WorkflowCompiler().compile(wf)
                  compile_registrations(...)
                  (validation + snapshotting + structural lowering)
                              │
                              ▼
        CompiledWorkflow (frozen: name, workflow_digest, version,
                          tasks, snapshots, .graph)
                              │
                              ▼
        WorkflowRuntime().execute(compiled, ...)   →  WorkflowResult
```

One compilation boundary: `WorkflowCompiler().compile(wf)` validates the declarations, computes the `workflow_digest`, snapshots every task, and lowers the whole thing to a frozen, molab-owned `ExecutionPlan` stored on the artifact as `.graph`. The runtime never recompiles — it builds fresh per-execution state/deps and drives the prebuilt plan through the structural engine (`engine.run_plan`).

## Source Layout

```
src/molab/workflow/
├── compiler.py            # Workflow (decorator + OOP registration) + WorkflowCompiler.compile + compile_registrations
├── compiled.py            # CompiledWorkflow — frozen artifact (graph + snapshots + IR exports)
├── binding.py             # WorkflowBindingRegistry / default_binding_registry
├── task.py                # Task / Actor convenience base classes
├── context.py             # TaskContext (single context for batch + streaming)
├── protocols.py           # Runnable / Streamable
├── promote.py             # promote_callable — fn(inputs, config) → single-task CompiledWorkflow
├── subworkflow.py         # SubWorkflow composition node
├── cache.py               # Caching (LRU by snapshot + input hash)
├── cache_store.py         # CacheStore / FileCacheStore storage primitives
├── snapshot.py            # TaskSnapshot (AST-normalized code hash + config hash)
├── ir.py                  # WorkflowGraphIR (to_graph_ir export for UI / server)
└── _engine/               # PRIVATE — molab-owned lowering + engine (zero pydantic_graph)
    ├── compiler.py        # WorkflowGraphCompiler — stages 1–5: validation + structural lowering
    ├── plan.py            # ExecutionPlan — frozen lowering artifact (plain data, no pg import)
    ├── engine.py          # run_plan — values-on-edges structural engine
    ├── _graph_analysis.py # back-edge / in-source / recurrent-set derivation
    ├── node.py            # run_task_body dispatcher + return-value classifier
    ├── node_cache.py      # run_task_body_cached — per-task content-addressed cache hook
    ├── node_params.py     # dependent_params resolution
    ├── runtime.py         # WorkflowRuntime (execute / start / run_on)
    ├── state.py           # WorkflowState, WorkflowDeps
    └── persistence.py     # coalescing workflow.json writer + read_journal (resume seed source)
```

The outer API (`molab.workflow.__init__`) is the public boundary. Anything under `_engine/` is an implementation detail and can break between releases.

## Deterministic Workflow ID

`workflow_digest` is a 16-hex-character `sha256` over the workflow `name` plus, for each task, `name + type(fn_or_class).__qualname__ + sorted(depends_on)` (see `_helpers.compute_workflow_digest`):

```python
from molab.workflow import Workflow, WorkflowCompiler

wf = Workflow(name="demo")


@wf.task
async def fetch() -> int:
    return 42


compiled = WorkflowCompiler().compile(wf)
print(compiled.workflow_digest)   # e.g. "c3f9e2b8a7d4e1f0"
```

Properties:

- **Deterministic** — the same task topology on two machines produces the same ID.
- **Topology-scoped** — changing only the *implementation* of a task keeps the ID stable; changing edges or class identity changes it.
- **Cheap** — no source hashing happens at this level; that's `TaskSnapshot`'s job.

Pair `workflow_digest` with `config_hash` on `RunMetadata` and the experiment's persisted graph IR when you need to group runs that share a topology + source version.

## Validation and Lowering

`compile_registrations` hands the declaration set to `WorkflowGraphCompiler` (`_engine/compiler.py`), which runs five stages — all synchronous from `WorkflowCompiler().compile(wf)`, before any user task code runs:

1. **Data-DAG validation** — the `depends_on` graph must be acyclic (`CycleError`) and reference only registered tasks (`UnknownTaskError`).
2. **Edge-set construction** — explicit `wf.control` / `wf.branch` declarations bucket into per-source `UnconditionalEdges` / `BranchEdges`; `wf.parallel` expands into `map_over → body → join` control edges; `wf.loop` expands into a `{"continue", "exit"}` branch on its `until` task; tasks with no explicit edges get a fan-out synthesised from their reverse data edges. Mixing branch + unconditional edges on one source raises `EdgeShapeError`.
3. **Entry resolution** — explicit `wf.entry(...)` wins; workflows with explicit control edges but no entry raise `EntryAmbiguousError`; pure-data DAGs use the data-zero tasks as the entry frontier.
4. **Reachability** — every registered task must be reachable from the entry frontier through control + reverse-data edges (`UnreachableTaskError`).
5. **Lowering** — `_build_plan` emits a frozen `ExecutionPlan` (`plan.py`): out-edges, entry frontier, back-edges (cycle re-entry), per-task forward trigger sources, the recurrent set (tasks on a control cycle), and the `wf.parallel` maps. The plan is plain data — no `pydantic_graph` import, no per-task node classes, no scheduling state.

The structural engine (`engine.py` `run_plan`) executes the plan with **values-on-edges** semantics: each completed task's recorded output rides its trigger edges to its targets, and a task launches exactly when every live forward in-edge has fired *and* every declared `depends_on` value is present. Declared `depends_on` always wins as the input interface; a dep-less task receives the value carried by its activating trigger — that is the channel by which loop-back and branch-routed values reach the task body, which the engine binds to the body's named parameters (`_bind_call_args` in `node.py`). Control flow is engine-owned:

- `wf.branch` / `wf.loop` exits → `BranchEdges` routed by the task's `Next(label)` return value; a non-recurrent branch permanently kills its non-chosen routes, propagating structural death to skipped legs;
- loop back-edges re-launch their target directly, bypassing forward in-edge coalescing; `max_iters` forces `Next("exit")` with a `LoopMaxItersExceeded` warning at the cap;
- `wf.parallel` → an engine-owned `asyncio.gather` over the `map_over` elements under a per-body capacity limiter; per-element failures are captured without cancelling siblings and aggregate into `ParallelExecutionError`; the index-ordered list is published before the join triggers.

Deadlock detection is structural and deterministic — zero timing constants. A control-ready task blocked on a structurally dead dependency raises `WorkflowDeadlockError` immediately; if the engine quiesces with triggered-but-blocked tasks remaining, the same error names the unsatisfiable dependencies. Tasks whose dependencies are satisfied run concurrently — parallelism is a consequence of the graph shape, not of worker configuration.

## State and Deps Injection

Per execution, `WorkflowRuntime` builds one `WorkflowState` (results, completed set, seeded set, root inputs) and one `WorkflowDeps` (the run context, effective config, topology maps, per-`parallel` capacity limiters, the resolved cache, the per-task snapshots, and the materialization store that derives content-addressed `ctx.workdir` paths). The engine routes every node through `run_task_body` in `node.py`, which resolves the node's inputs (fan-out element → root inputs → declared `depends_on` outputs → trigger-carried value), constructs the frozen `TaskContext`, and dispatches to the user body. The resolved values are bound to the body's named parameters (`_bind_call_args`), not read off the context; the `TaskContext` itself exposes only `ctx.workdir`, and `ctx.state` is deprecated (a read-only snapshot that emits a `DeprecationWarning` on access).

For a workspace run, the runtime pre-sets every root task's inputs to `{"params": <run params>, "workdir": <content-addressed Path>}` — capabilities are delivered *as inputs*; a task cannot reach the `RunContext`.

## Runtime Entry

`WorkflowRuntime` (in `_engine/runtime.py`, re-exported publicly) owns execution:

```python
# docs: skip — signature overview (``...`` placeholders, not runnable values)
runtime = WorkflowRuntime()
result = await runtime.execute(compiled, run_context=ctx, seed_outputs=..., cache=...)
handle = await runtime.start(compiled)            # background, returns WorkflowExecution
result = await runtime.run_on(compiled, experiment, parameters=...)  # fresh Run + execute
```

`seed_outputs` pre-populates already-known task outputs (the caller-driven resume path — seeded nodes skip their body but still route); unknown seed names fail fast. Resume seeds come from `read_journal(run_dir, execution_id)`, the persisted node-level state of a prior execution.

Per-node status persistence is observability state, not engine coordination: during a live execution the runtime opens an in-memory execution document (`persistence.open_execution_document`), per-task transitions mutate it and flush within a bounded-staleness window (`WORKFLOW_JSON_MAX_STALENESS_S`), while task failures, terminal states, and the runtime's `finally`-path `close_execution_document` flush synchronously. Nothing in scheduling ever waits on that timer.

## TaskSnapshot — Code + Config Identity

For caching and snapshotting, each task carries a `TaskSnapshot`:

```python
class TaskSnapshot:
    task_id: str
    task_type: str        # module.qualname
    code_hash: str        # sha256 of AST-normalized execute() source
    config_hash: str      # sha256 of the task's serialized config
    code_source: str
    created_at: datetime
    config_data: dict
```

The **code hash** uses AST normalization — comments, whitespace, and decorators are stripped before dumping the AST. Two tasks that differ only in formatting share a hash; a real semantic change produces a new one. Code hashes fall back to bytecode hashing if the source isn't available. A task's config is its `__init__` arguments, captured automatically at construction time.

The combined identity key is `f"{code_hash}:{config_hash}"`; the full cache key adds the input hash. `Caching` (`cache.py`) is orthogonal to the lowering — the engine's per-task cache hook (`node_cache.run_task_body_cached`, batch `Task` bodies only, never `Actor`s) consults it when a cache is supplied:

```python
import molab as me
from molab.workflow import Caching, FileCacheStore, WorkflowRuntime

ws = me.Workspace("./lab", name="lab")

# Run-local cache is built automatically from ``run_context`` at
# ``<run_dir>/cache``. Pass an explicit store only to override:
cache = Caching(store=FileCacheStore("./cache"), max_entries=1000)

result = await WorkflowRuntime().execute(compiled, cache=cache)
```

For callers with no run, use `FileCacheStore(path)` or a plain `store_dir=...` argument. Execute writes `.molab/runs/<run-id>/cache/`, never a workspace-root cache and never a user-home cache. The authoring `remote=` kwarg is removed; remote execution goes through the target and the scheduler.

## What the Compiler Does Not Do

- **It does not serialize executable workflows.** There is no `CompiledWorkflow.load(...)` path; workflows are authored in Python and re-imported on each execution. `to_graph_ir()` / `to_ir()` are one-way exports for the UI, server, and provenance — use them plus `workflow_digest` and the experiment's source snapshot for traceability.
- **It does not allocate workers or pick execution backends.** The authoring `remote=` kwarg is removed; the scheduler path owns remote execution.
- **It does not infer data contracts.** `depends_on` declares both ordering and the data interface — the declared upstreams' outputs are bound to the body's named parameters (keyed by upstream task name) — but the *types* flowing through are your responsibility (use generics on `Task` / `TaskContext` if you want static checking). Optional declared contracts live in `contract.py` (`validate_workflow_contract`).

## Extension Points

Keep the boundaries:

- **New authoring surface** → add to `compiler.py`; make sure `compute_workflow_digest` still produces a stable hash.
- **Different runtime** → a swap-in runtime must consume a `CompiledWorkflow` and honor the `execute` / `start` signatures; `WorkflowRuntime` is the only one we ship.
- **New cache strategy** → implement a `CacheStore`, or compose `Caching` with a different storage backend; don't teach the lowering about caching directly.
- **New snapshot semantics** → change `TaskSnapshot`; bump `CACHE_FORMAT_VERSION` in `cache.py` so stale cache entries are invalidated.

All other public behaviour should route through `molab.workflow`'s re-exports.

## Pointer to the Implementation

- `molab.workflow._helpers.compute_workflow_digest` — workflow ID hash
- `molab.workflow.compiler.compile_registrations` — validation + snapshotting + lowering entry
- `molab.workflow._engine.compiler.WorkflowGraphCompiler` — topology → `ExecutionPlan`
- `molab.workflow._engine.plan.ExecutionPlan` — the frozen lowering artifact
- `molab.workflow._engine.engine.run_plan` — the values-on-edges structural engine
- `molab.workflow.snapshot.TaskSnapshot` — code/config identity
- `molab.workflow.cache.Caching` — LRU cache keyed by snapshot + inputs
