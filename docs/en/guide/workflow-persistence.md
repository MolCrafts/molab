# Workflow Persistence

Molab **does not serialize workflow topology** to JSON. Workflows are authored in Python and re-imported on every execution. This page documents what *is* persisted — the reproducibility data needed to recreate a run — and how to use it.

## Persistent Metadata

Three pieces of data, all written atomically (temp file + `os.rename`):

### 1. `Experiment.workflow_kind`

`Experiment.bind_workflow` is the only writer. `code` names an entrypoint; `document` stores the graph. An experiment that has not been migrated answers 409 until `molab migrate workflow-kind` runs. `workflow_digest` lives on the Execution and in the journal header, not in the document.

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

`molab execute` is the worker entry point used by cluster backends. It reads `run.json` for the `script` field, re-imports the script, matches the project + experiment IDs via `find_workflow_for_run(...)`, and drives the bound `Workflow` against the existing run directory — appending a new `ExecutionRecord` to `execution_history`.

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
            └── executions/e01/           ← one attempt; `e01` is its id
                ├── execution.json        ← status, ownership, evidence, error, seal
                ├── alive                 ← owner heartbeat is mtime
                ├── workflow.json         ← per-node status + outputs (resume seed)
                ├── artifacts/
                ├── out/<task>/
                └── run.log               ← the attempt's one log
```

A run's `run.json` is the logical definition. Status lives on each attempt's `execution.json`; the owner heartbeat is the mtime of that attempt's `alive` file. Resume seeds from `executions/eNN/workflow.json`. There is no sidecar of hot state next to `run.json`.

All JSON files are written atomically (temp file + `os.rename`); structure is discovered by scanning directories, so you can move, inspect, or archive experiments independently without rewriting parent metadata.

## Rerun, Resume, and the Cache

A run that ended `failed` or `cancelled` can be re-executed on the **same** `run_id` in exactly two ways — there is no "clone into a new run" operation:

- **`--resume`** creates a new Execution. Completed task outputs are seeded from the predecessor journal, and only unfinished nodes recompute.
- **`--rerun`** opens a *fresh* attempt (`eNN`): a new `ExecutionRecord`, executed from the top of the graph.

`--rerun` interacts with the content-addressed cache. A rerun does not seed anything, but every task whose cache identity (code + config + upstream outputs + sweep params) is unchanged **may hit the cache** — a deterministic task that already succeeded can be served its previous output instead of recomputing. That is usually what you want; when it is not (say the task reads mutable external state the cache key cannot see), pass `--rerun --fresh` to bypass cache *reads* for that execution, forcing every node to genuinely re-execute while still writing fresh cache entries.

Neither verb touches `pending` or `succeeded` runs, and a live `running` run must be cancelled first — retrying is always an explicit verb, never implicit.

## Runnable Example

`examples/workspace/workflow_persistence.py` runs a deliberately flaky task twice and prints the `execution_history`, `profile`, `config`, and `config_hash` fields from `run.json`.
