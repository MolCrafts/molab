# Workspace Architecture

Molab organizes experiments in a four-tier hierarchy:

```
Workspace
└── Project
    └── Experiment      (parameter-space container + replica config)
        └── Run          (one execution attempt; re-runs append ExecutionRecords)
```

Every persistent byproduct — imported data, task artifacts, logs, checkpoints, error traces, workflow execution state — is a typed `Asset` subclass recorded in a per-scope `asset.json` manifest. Those manifests are authoritative and are what asset queries scan directly — there is no derived asset index beside them. Every metadata write is atomic (temp-file + `os.rename`), so a crash never leaves a half-written JSON file.

Workspace is the bottom of the molab dependency DAG. It owns filesystem layout, atomic JSON, content-addressed assets, and generic per-kind subsystem storage — and **does not know about workflows or knowledge**. Upstream layers (workflow, knowledge, services, cli, server) reach *down* into workspace's public surface; the inverse is forbidden by the import-guard test.

## Hierarchy Levels

| Level | Directory | Metadata file | Purpose |
|-------|-----------|---------------|---------|
| `Workspace` | `<root>/` | `workspace.json` | Top-level container. Materialized explicitly or when the first child is created. |
| `Project` | `<root>/projects/<project_id>/` | `project.json` | Research-area container (MD, ML training, data pipeline, …). |
| `Experiment` | `<project>/experiments/<exp_id>/` | `experiment.json` | Concrete parameter set + replica count. Workspace stores the parameter binding; pairing the experiment with a workflow is the *caller's* concern. |
| `Run` | `<exp>/runs/<params>/` | `run.json` | Single execution instance; re-runs append `ExecutionRecord` entries. |

Children are **not** stored as lists in the parent metadata — parents discover children by scanning the filesystem. This keeps writes local and avoids lock contention.

## Why This Design

Scientific workflows tend to run the same pipeline many times with different parameters, then compare outcomes. The `Experiment → Run` split reflects that:

- **Experiment** is the *definition* — parameters, replica count, seeds, optional advisory `workflow_kind` / `workflow_kind` strings used by the UI for grouping.
- **Run** is a *realization* — one execution, one set of concrete parameter values, one outcome.

Each `Run` captures reproducibility metadata: an opaque `workflow_digest` payload (the canonical typed shape lives in `molab.workflow.workflow_digest`; workspace stores it as a JSON `dict`), the resolved molcfg profile, a `config_hash`, execution history, error info, and produced artifacts.

## Creating a Hierarchy

The hierarchy is created from the top down, but not every step has identical identity rules. `ws.add_project(...)` and `project.add_experiment(...)` are create-or-get operations keyed by slug or explicit id, so repeated calls can load existing objects from disk (the bare-noun spellings `ws.project(...)` / `project.experiment(...)` are strict getters that raise when the node is absent). `exp.add_run(...)` is different: it creates a fresh run unless you provide an explicit `id`, in which case it becomes a get-or-load operation for that concrete run directory. Runs seeded by `exp.define(workflow, params=...)` derive their ids from their parameters, so the sweep declaration is idempotent.

```python
import molab as me

ws = me.Workspace("./lab", name="lab")                    # lightweight object; no files yet
project = ws.add_project("MD Simulations")                # materializes workspace.json and project.json
exp = project.add_experiment(
    "temperature-300K",
    params={"T": 300, "pressure": 1.0},
    n_replicas=3,
    seeds=[42, 43, 44],
)
run = exp.add_run(
    {"T": 300, "pressure": 1.0, "seed": 42},
    id="temperature-300K-seed-42",
)                                                         # materializes run.json
```

Re-calling `add_project` / `add_experiment` with the same name or id returns the same in-memory object within the current process and loads from disk when needed. Runs only behave that way when the run id is stable.

## Pairing an Experiment with a Workflow

Workspace itself stores no workflow-shaped types. The association is declared through `Experiment.define(workflow, params=...)`, which records the workflow's graph IR on the experiment and binds the live `CompiledWorkflow` in the workflow layer's `default_binding_registry`:

```python
from molab.workflow import Task, TaskContext, Workflow, WorkflowCompiler, WorkflowRuntime


class TrainTask(Task):
    async def execute(self, ctx: TaskContext, lr: float = 1e-3) -> dict:
        return {"loss": lr * 10}


compiled = WorkflowCompiler().compile(Workflow(name="train").add(TrainTask()))   # task auto-named "train"
exp = project.add_experiment("baseline").define(compiled, params={"lr": [1e-3]})

# Workspace just provides the Run the workflow executes within.
run = exp.list_runs()[0]
with run.start() as ctx:
    result = await WorkflowRuntime().execute(compiled, run_context=ctx)
```

This decoupling came out of the 2026-05-09 rectification: workspace stays a storage primitive, workflow stays a graph engine, and the cross-layer seam (`molab.entry`) wires `Experiment.define` to the binding registry without workspace ever importing the workflow layer.

## Parameter Combinations

`GridSpace` and `UniformSpace` generate parameter combinations. `Experiment.define(workflow, params=...)` accepts a space (or a plain `{axis: [values]}` grid mapping) directly and materializes one content-addressed `Run` per cell:

```python
from molab import GridSpace

grid = GridSpace({"T": [300, 310, 320], "force_field": ["amber", "charmm"]})

sweep = project.add_experiment("md-sweep").define(compiled, params=grid)
print(len(sweep.list_runs()))  # 6 — one per grid cell
```

`UniformSpace(param_values, n_samples, seed=None)` samples `n_samples` combinations uniformly at random — handy for broader search spaces.

## Executing a Run

```python
from molab.workspace.domain import ExecutionMode

with run.start(mode=ExecutionMode.RERUN) as ctx:
    result = await WorkflowRuntime().execute(compiled, run_context=ctx)
```

Entering `run.start()` opens a `RunContext` which:

1. Ensures the run directory exists (subdirectories like `work/` are created lazily by the accessors that write into them).
2. Records temporary ownership metadata for the active execution.
3. Appends a new `ExecutionState` to `run.executions`.
4. Runs the workflow; the heartbeat `alive` file is touched every 30 s.
5. On success, seals the execution as `succeeded` with the final timestamp.
6. On failure, seals it as `failed` and writes `executions/<exec_id>/traceback.txt`.

Every attempt appears in `run.executions`, newest last. An execution is opened with `ExecutionMode.INITIAL` the first time. A later attempt needs an explicit mode: `RERUN` after any terminal attempt, `RESUME` when the predecessor failed, was cancelled, or was interrupted, and `REPRODUCE` after a success. `ExecutionMode.RETRY` is stored as `RERUN`.

## Assets

Emitted artifacts are recorded by the execution (`ctx.emit_artifact` / `ctx.checkpoint`) and queried through the `ArtifactRepository`; imported data lives in a scope's `data_assets` library. See [Artifacts, Assets, and Data Imports](assets.md).

```python
from pathlib import Path

Path("qm9.csv").write_text("mol,energy\nH2O,-76.4\n")
ws.data_assets.import_asset("bert-model", "qm9.csv")
project.data_assets.import_asset("dataset", "qm9.csv")

# Driver-side, around the workflow execution
with run.start(mode=ExecutionMode.RERUN) as ctx:
    dataset = project.data_assets.get("dataset")
    result = await WorkflowRuntime().execute(compiled, run_context=ctx)
    ctx.emit_artifact(result.outputs["train"], name="metrics.json")
    ctx.log("runtime").append("epoch 1")
```

`import_asset(name, src, action="copy", meta=None)` supports `"copy"`, `"move"`, `"symlink"`, and `"hardlink"` for ingestion.

## CLI Surface

The same hierarchy is exposed through the CLI:

```bash
molab project   create|list|info
molab experiment create|list
molab runs      create|list|info|cancel|prune
molab asset     list
molab info      # show workspace summary
```

`molab runs prune` interactively walks the project → experiment → run → execution tree and lets you delete per-execution records (removes `executions/<exec_id>/` and rewrites `run.execution_history`).

## Directory Layout

```
./lab/
├── workspace.json
├── asset.json                     # workspace-scoped asset manifest (authoritative)
├── data_assets/<asset_id>/payload/ # imported DataAssets
└── projects/
    └── qm9/
        ├── project.json
        ├── asset.json             # project-scoped asset manifest
        ├── data_assets/            # project-scoped DataAssets
        └── experiments/
            └── baseline/
                ├── experiment.json
                ├── asset.json     # experiment-scoped asset manifest
                ├── data_assets/    # experiment-scoped DataAssets
                └── runs/
                    └── <key=value_…>/
                        ├── run.json        # logical definition only
                        └── executions/e01/ # one attempt
                            ├── execution.json
                            ├── alive       # owner heartbeat is mtime
                            ├── workflow.json
                            ├── artifacts/
                            └── out/<task>/
```

## Upgrading an existing workspace

Run these once on a tree that predates the current layout:

- `molab migrate assets` — until this has run, any leftover legacy asset record makes asset reads answer 409 `MIGRATION_REQUIRED`.
- `molab migrate workflow-kind` — records whether each experiment runs code or a graph document.
- `molab migrate knowledge` — moves old documents into `<host>/knowledges/<slug>.md`.

A registered wiki whose documents sit under `<wiki>/knowledges/` must re-register that directory as its source root: `molab knowledge sources remove <name>`, then `molab knowledge sources add <name> <wiki>/knowledges`.

A new workspace's `workspace.json` id is a UUIDv7, written create-if-absent the first time it is materialized and never rewritten. An existing slug id is kept.

### Removed API

- `WorkflowRuntime.execute` / `start` no longer take `run_dir=`. The cache and the journal live at `.molab/runs/<run-id>/cache/` and `executions/eNN/workflow.json`, taken from the run's identity.
- `ErrorInfo` (removed; read `Execution.error`)
- `molab.entry.load_workflow_from_entrypoint` is gone. Import `molab.workflow.load_workflow_from_entrypoint`. `molab.entry` does not re-export it.
- The authoring `remote=` kwarg is removed. Remote execution goes through the compute target and the scheduler.

## Runnable Example

`examples/workspace/workspace_architecture.py` seeds a tracked run and then prints the full on-disk tree with file sizes so you can see each layer for yourself.
