# Molab Examples

Each guide in `docs/guide/` (and each onboarding page in `docs/getting-started/`)
has a runnable example here. Read the guide for prose, run the example to see
the same idea working.

Most examples execute the workflow in-process and write into a temporary
directory under the system temp location (printed at the top of every run).
You can delete these freely; none of them touch `~/` or any system path.

## Getting Started

| Guide | Example | What it shows |
|---|---|---|
| [quick-start](../docs/getting-started/quick-start.md) | `getting_started/01_quick_start.py` | End-to-end: workspace + experiment + run + result |
| [first-workflow](../docs/getting-started/first-workflow.md) | `getting_started/02_first_workflow.py` | A `Workflow` with no workspace attached |
| [tracked-runs](../docs/getting-started/tracked-runs.md) | `getting_started/03_tracked_run.py` | What appears on disk when a run is tracked |
| [cli-and-profiles](../docs/getting-started/cli-and-profiles.md) | `getting_started/04_cli_and_profiles/` | `molab run` + `molcfg.yaml` + `--profile` |

## Workflow Authoring

| Guide | Example | What it shows |
|---|---|---|
| [task-and-actor](../docs/guide/task-and-actor.md) | `workflow/task_and_actor.py` | Decorator, OOP, and Protocol-form tasks, plus a streaming actor |
| [task-context](../docs/guide/task-context.md) | `workflow/task_context.py` | Named-parameter binding (upstream output / run param / build-time config) and `ctx.workdir` — the pure task context |
| [workflow-runtime](../docs/guide/workflow-runtime.md) | `workflow/workflow_runtime.py` | `WorkflowRuntime.execute()` vs `.start()` |
| [control-flow](../docs/guide/control-flow.md) | `workflow/control_flow.py` | Diamond fan-out, conditionals, build-time and `wf.parallel` fan-out |
| [control-flow](../docs/guide/control-flow.md) | `workflow/branch_and_loop.py` | `wf.branch` routing and `wf.loop` repeat-until — `(value, Next(label))` values bind to the target's named parameters |
| [subworkflows](../docs/guide/subworkflows.md) | `workflow/subworkflows.py` | Calling a sub-spec from inside a task |
| [ir-export](../docs/guide/ir-export.md) | `workflow/ir_export.py` | Mermaid diagrams, JSON IR round-trip, full-graph IR for UIs |

## Records and Assets

| Guide | Example | What it shows |
|---|---|---|
| [workspace-api](../docs/guide/workspace-api.md) | `workspace/workspace_api.py` | `Workspace → Project → Experiment → Run` walk |
| [workspace-architecture](../docs/guide/workspace-architecture.md) | `workspace/workspace_architecture.py` | What files actually land on disk |
| [workflow-persistence](../docs/guide/workflow-persistence.md) | `workspace/workflow_persistence.py` | `run.json`, `execution_history`, `config_hash` |
| [assets](../docs/guide/assets.md) | `workspace/assets.py` | Artifact, log, checkpoint, `find_asset` |
| [assets](../docs/guide/assets.md) | `workspace/assets_extended.py` | Error traces, checkpoint chaining, content-hash lookup, import actions |

## Sweeps

| Guide | Example | What it shows |
|---|---|---|
| [sweeps](../docs/guide/sweeps.md) | `sweeps/grid_and_space.py` | GridSpace, UniformSpace, RunSet.execute, to_records, min_by, idempotent re-declaration |

## Knowledge

| Guide | Example | What it shows |
|---|---|---|
| [knowledge](../docs/guide/knowledge.md) | `knowledge/notes_and_references.py` | Bundle, Note, ReferenceConcept, cite, backlinks, search |

## Operations

| Guide | Example | What it shows |
|---|---|---|
| [run-profiles](../docs/guide/run-profiles.md) | `operations/run_profiles/` | `molcfg.yaml`, `--profile`, `--override` |
| [server-lifecycle](../docs/guide/server-lifecycle.md) | `operations/server_lifecycle.py` | Programmatic `ServerManager.start()` / `stop()` |
| [molq](../docs/guide/molq.md) | `operations/scheduler_molq.py` | How `--scheduler slurm` composes a `SubmitHandler` |
| [run-profiles](../docs/guide/run-profiles.md) | `operations/run_profiles_advanced/` | Profile inheritance (`extends`), `--override` dot notation |
| [workspace-architecture](../docs/guide/workspace-architecture.md) | `operations/remote_targets.py` | LocalTarget, RemoteTarget, ComputeTarget resolution |

## A Minimal Script End to End

| Example | What it shows |
|---|---|
| `agent/code_loop_golden_path.py` | A minimal public-API workflow script: create a workspace, add a project and an experiment, sweep a one-task workflow over a parameter grid, read the results back with `to_records()`, and (when `molplot` is installed) save a figure under the workspace. The `agent/` directory name is historical; the script uses only the public molab API. |

## Plugins

| Guide | Example | What it shows |
|---|---|---|
| [plugins](../docs/concept/plugins.md) | `plugins/custom_submit_handler.py` | CliPlugin construction, SubmitHandler Protocol, entry-point registration pattern |

## CLI Commands

| Guide | Example | What it shows |
|---|---|---|
| [workspace-architecture](../docs/guide/workspace-architecture.md) | `cli/commands.sh` | `molab init`, `info`, `project`, `experiment`, `runs`, `asset` — full CLI tour |

## Driving a Run

The sanctioned surface is the fluent chain: declare which workflow an
experiment runs (this seeds one content-addressed `Run` per parameter cell
and binds the compiled workflow), then either let `molab run` drive the
runs or execute one in-process through `WorkflowRuntime`:

```python
from molab.workflow import Workflow, WorkflowCompiler, WorkflowRuntime

compiled = WorkflowCompiler().compile(Workflow(name="train").add(Train()))

exp = ws.project("demo").experiment("train").run(compiled, params={"lr": [1e-3]})

run = exp.list_runs()[0]
with run.start(profile_config=cfg) as ctx:
    result = await WorkflowRuntime().execute(compiled, run_context=ctx)
    ctx.set_result("final_loss", result.outputs["train"])
```

`Experiment.run(workflow, params=...)` binds the compiled workflow to the
experiment in `molab.workflow.default_binding_registry` (an explicit,
injectable `{experiment_id → CompiledWorkflow}` store — the old class-level
`bind_to` registry was replaced) and registers the workspace for CLI
discovery, so a separate `me.entry(ws)` call is no longer needed. The
registry is process-local — cluster workers re-establish it by re-running
the user script on import.

Task bodies declare the runtime values they consume as named parameters: a
root task of a tracked run receives its sweep params by name, an upstream
task's output binds to a parameter named after that task, and build-time
config fields bind by name (each with a declared default). The only data
surface on the `TaskContext` itself is `ctx.workdir`. Workspace helpers
(`set_result` / `artifact` / `log`) live on the driver-side `RunContext`; read
persisted results back with the public `run.get_result(key)` instead of parsing
`run.json` by hand.

## Running an Example

Every `.py` example runs stand-alone:

```bash
python examples/getting_started/01_quick_start.py
```

Examples under a subdirectory (`04_cli_and_profiles/`, `run_profiles/`) ship
a matching `molcfg.yaml` and run through the `molab` CLI:

```bash
molab run examples/getting_started/04_cli_and_profiles/train.py --profile smoke
```
