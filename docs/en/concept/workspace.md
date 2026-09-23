# Workspace Model

The workspace layer is the persistent record on disk. It answers *what survives after execution*.

## The four-level hierarchy

```
Workspace          ← root directory (e.g. ./lab)
└── Project        ← groups related work (e.g. qm9)
    └── Experiment ← repeatable definition (workflow + params)
        └── Run    ← one concrete execution attempt
```

| Level | What it is | On disk |
|---|---|---|
| **Workspace** | Root of a body of work | `workspace.json` |
| **Project** | Groups related experiments | `projects/<slug>/project.json` |
| **Experiment** | One workflow + parameter space | `projects/<slug>/experiments/<slug>/experiment.json` |
| **Run** | One execution with status and outputs | `projects/<slug>/experiments/<slug>/runs/<params>/run.json` |

## Definition vs. outcome

The critical distinction is between **experiment** (what you intend to repeat) and **run** (what actually happened). An experiment carries the workflow reference, parameter space, and provenance. A run is immutable intent (`run.json`). Each attempt is an Execution under `executions/eNN/` (`execution.json` holds status, results, errors).

Without that split, retries and comparisons become ambiguous.

## Profiles and metadata

Profiles (`molcfg.yaml`) live at the boundary between workflow execution and workspace persistence. Tasks read profile fields as named parameters. The resolved profile — name, merged config, `config_hash` — is stored on the run record. You can look at `run.json` later and recover the exact configuration a run used.

## What's on disk

```
workspace_root/
├── workspace.json                ← entity metadata (UUIDv7 `id`)
├── index.md                      ← workspace narrative; markdown links are the graph
├── knowledges/<slug>/            ← optional workspace-level notes / literature
│   ├── note.json                 ← class-named head (no meta.json, no type/kind)
│   └── index.md
└── projects/<project-slug>/
    ├── project.json
    ├── knowledges/<slug>/        ← Finding / Plan / Note / …
    └── experiments/<experiment-slug>/
        ├── experiment.json
        ├── knowledges/<slug>/
        └── runs/<key=value_…>/   ← directory name is the parameters
            ├── run.json          ← logical definition only
            └── executions/e01/   ← one attempt; `e01` is its id
                ├── execution.json
                ├── alive         ← owner heartbeat is mtime
                ├── workflow.json
                ├── artifacts/
                ├── out/<task>/
                └── jobs/
```

There is no children-index file. `ls` is the index. Knowledge is class-named json + `index.md`.

## Next

- For the concrete Python API, see [Workspace API](../guide/workspace-api.md).
- For reusable data and provenance, see [Assets and Reproducibility](assets-and-reproducibility.md).
- For the CLI that discovers this hierarchy, see [CLI and Profiles](../getting-started/cli-and-profiles.md).
