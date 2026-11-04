# Workflow Persistence

Molab **does not serialize workflow topology** to JSON. Workflows are authored in Python and re-imported on every execution. This page documents what *is* persisted — the reproducibility data needed to recreate a run — and how to use it.

## Persistent Metadata

Three pieces of data, all written atomically (temp file + `os.rename`):

### 1. `Experiment.workflow_kind`

`Experiment.bind_workflow` is the only writer. `code` names an entrypoint; `document` stores the graph. An experiment with no `workflow_kind` is unbound until something calls `bind_workflow`. `workflow_digest` lives on the Execution and in the journal header, not in the document.

```json
{
  "id": "baseline",
  "name": "Baseline",
  "workflow_kind": "code",
  "workflow_entrypoint": "workflow.py:build",
  "git_commit": "abc123",
  "parameter_space": {"lr": 0.001}
}
```

### 2. `RunMetadata.workflow_digest`

An opaque JSON dict captured at run-creation time. The canonical shape is `molab.workflow.snapshot_ref.workflow_digest` — but workspace stores the value as a plain dict to keep the dependency direction one-way (workspace ← workflow). Workflow-layer code dumps the model into JSON before handing it to workspace; workspace just round-trips it:

```json
{
  "workflow_digest": {
    "source": "train.py",
    "git_commit": "abc123",
    "code_hash": null,
    "config_hash": null
  }
}
```

`source` + `git_commit` let you retrieve the exact code that produced the run.

### 3. `RunMetadata.config` / `config_hash`

The fully merged molcfg profile data the run executed against, plus a `sha256` digest for fast querying. Profiles are opaque to molab — it stores them verbatim.

```json
{
  "profile": "smoke",
  "config": {"lr": 0.001, "epochs": 3},
  "config_hash": "f8d9..."
}
```

## Deliberate Omissions

- The workflow topology (DAG shape) — recomputed from `workflow_kind` on replay.
- Task code — implicit in `workflow_kind` + `git_commit`.
- Per-task configuration — implicit in the workflow definition.

This is deliberate: a serialized DAG can drift from the live code base. Re-importing the script guarantees the on-disk `Run` always lines up with the current Python definition. If the definition has changed, the `workflow_digest` (topology hash) or `TaskSnapshot.code_hash` will too.

## Replaying a Run

```bash
# Re-execute from the CLI
molab run train.py --profile smoke

# Or execute a worker from an existing run directory
molab execute path/to/<params>/
```

`molab execute` is the worker entry point used by cluster backends. It reads the run record, re-imports the script, matches the project + experiment, and drives the bound `Workflow` against the existing run directory — opening a new attempt under `executions/eNN`.

## Identity and Correlation

| Field | Where | Meaning |
|-------|-------|---------|
| `Workflow.workflow_digest` | derived | sha256 over `name + task topology`; stable across machines |
| `TaskSnapshot.code_hash` | derived | sha256 over AST-normalized `execute()` source |
| `TaskSnapshot.config_hash` | derived | sha256 over serialized task config |
| `RunMetadata.workflow_digest.source` | `run.json` | path to the defining script |
| `RunMetadata.workflow_digest.git_commit` | `run.json` | commit SHA at experiment-creation time |
| `RunMetadata.config_hash` | `run.json` | sha256 over the merged profile dict |

Use these to group, compare, and replay runs.

## Workspace-Level Files

```
./lab/
├── workspace.json
└── projects/<proj_id>/
    ├── project.json
    └── experiments/<exp_id>/
        ├── experiment.json
        └── runs/<key=value_…>/
            ├── run.json                  ← logical definition only
            │                                (params, definition_hash, revision links)
            ├── values/<sha256>.json|.pkl ← every task input/output, stored once,
            │                                shared by all attempts (a record, in git)
            └── executions/e01/           ← one attempt; `e01` is its id
                ├── execution.json        ← status, ownership, evidence, error, seal
                ├── alive                 ← owner heartbeat is mtime
                ├── workflow.json         ← per-node journal: status + input/output refs
                ├── artifacts/
                ├── out/<task>/
                └── run.log               ← the attempt's one log
```

A run's `run.json` is the logical definition. Status lives on each attempt's `execution.json`; the owner heartbeat is the mtime of that attempt's `alive` file. There is no sidecar of hot state next to `run.json`.

## Node Records

After any attempt, molab knows what every task received and returned. Each task record in `executions/eNN/workflow.json` (journal schema 4) carries:

- `input_refs` — written when the task **starts**, so a failed task keeps it: `{"upstream": {dep: ref}, "root": ref, "delivered": ref, "config": ref}` — each upstream output it consumed, its run parameters (root tasks), a trigger-delivered value, its effective config.
- `output_ref` / `output_encoding` (`json` or `pickle`) / `output_preview` (pickled values) — on completion.
- `queued_at` — when the engine launched the task; `started_at` / `finished_at` — the span the body itself ran, stamped by the executor (a task waiting for the inline lock or a busy pool is queued, not running), so the web app's timeline shows computing time.

A ref is `sha256:<hex>`: the digest of the encoded value in the run's `values/` directory. JSON-safe values are stored as canonical JSON, anything else (a `molpy.Atomistic`, a `Frame`, …) is pickled. Values are deduplicated by content: an upstream's output and the downstream input it feeds are the same file, and two attempts that produce the same value share it. A value that can be neither JSON-encoded nor pickled is recorded as `output_unrecordable` with the reason; that node cannot be resumed or re-run from the record. `values/` is a record tracked in git; it unpickles on read, so load it only from workspaces you trust. Journals from older molab versions (inline `outputs`) are legacy: they are still displayed, but cannot seed a resume or a partial rerun — rerun those runs from the top.

`molab.workflow.read_journal(run, "e01")` presents the journal with each JSON output resolved under `outputs` (pickled ones are flagged `outputs_pickled` beside their `output_preview`); `read_outputs(run, "e01")` returns every recorded output, pickled values included.

All JSON files are written atomically (temp file + `os.rename`); structure is discovered by scanning directories, so you can move, inspect, or archive experiments independently without rewriting parent metadata.

## Rerun, Resume, and the Cache

A run that ended `failed` or `cancelled` can be re-executed on the **same** `run_id` in exactly two ways — there is no "clone into a new run" operation:

- **`--resume`** creates a new Execution. Every completed task is seeded from the output its predecessor recorded (pickled values included), and only unfinished nodes recompute; a failed node re-executes from the very inputs its record shows.
- **`--rerun`** opens a *fresh* attempt (`eNN`): a new `ExecutionRecord`, executed from the top of the graph.
- **`--rerun --task NAME`** (repeatable; `execute_run(wf, run, rerun=True, only=("NAME",))`, or `"tasks": [...]` on `POST …/executions`) re-executes just that task with the inputs the latest attempt recorded. Every other completed task is seeded from its record, and every task downstream of a selected one is journalled `skipped` (`reason: "not selected for this rerun"`) — it is not run. The selection is recorded on the Execution (`selected_tasks`) and in the journal header (`selected_tasks`, plus `seeded_from` naming the predecessor and ref of each seed). When an upstream the task needs has no usable recorded output (it failed, its value is missing, or its code changed since), the rerun is refused with an error naming that upstream; select it too, or rerun the whole workflow. A partial rerun also requires the predecessor's profile.

Resume and partial rerun go through one seeding path (`molab.workflow.read_attempt_seeds`), and the seed gate applies to both: a task whose code, config or `dependent_params` changed — or whose upstream did — is not seeded.

`--rerun` interacts with the content-addressed cache. A full rerun does not seed anything, but every task whose cache identity (code + config + upstream outputs + sweep params) is unchanged **may hit the cache** — a deterministic task that already succeeded can be served its previous output instead of recomputing. That is usually what you want; when it is not (say the task reads mutable external state the cache key cannot see), pass `--rerun --fresh` to bypass cache *reads* for that execution, forcing every node to genuinely re-execute while still writing fresh cache entries.

Neither verb touches `pending` or `succeeded` runs, and a live `running` run must be cancelled first — retrying is always an explicit verb, never implicit.

## Runnable Example

`examples/workspace/workflow_persistence.py` runs a deliberately flaky task twice and prints each attempt from `run.executions`, plus the run's definition hash and parameters.
