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
| **Workspace** | Root of a body of work | `index.md` |
| **Project** | Groups related experiments | `projects/<slug>/index.md` |
| **Experiment** | One workflow + parameter space | `projects/<slug>/experiments/<slug>/index.md` |
| **Run** | One execution with status and outputs | `projects/<slug>/experiments/<slug>/runs/<params>/index.md` |

Each level keeps exactly one file, its `index.md`. The YAML frontmatter at the top is the level's **record** — the fields molab writes (`type`, `id`, `name`, …, `schema_version`). The markdown after it is the narrative you write. Under the `index:` key of the frontmatter molab also keeps a derived block that points at the next level down (`children` rows with a relative `path`, a run's `executions`, a `parent` link), so a person or an agent can start at the root `index.md` and walk the whole tree without listing directories. molab rewrites that block on every change and never reads it to decide anything; `molab index sync` rebuilds it.

```markdown
---
type: workspace.experiment
id: 01a0f297-…
name: lj-vcom
parameter_space: {…}
schema_version: 6
index:
  parent: ../../index.md
  entrypoint: workflow.py
  scratch: false
  children:
    - name: seed=0_v=ar
      path: runs/seed=0_v=ar/index.md
      id: 01a0…
      params: {seed: 0, v: ar}
---
# lj-vcom
Notes about this experiment.
```

## Definition vs. outcome

The critical distinction is between **experiment** (what you intend to repeat) and **run** (what actually happened). An experiment carries the workflow reference, parameter space, and provenance. A run is immutable intent (the record in its `index.md`). Each attempt is an Execution under `executions/eNN/` (`execution.json` holds status, results, errors).

Without that split, retries and comparisons become ambiguous.

## Profiles and metadata

Profiles (`molcfg.yaml`) live at the boundary between workflow execution and workspace persistence. Tasks read profile fields as named parameters. The resolved profile — name, merged config, `config_hash` — is stored on each attempt's record. You can look at `executions/eNN/execution.json` later and recover the exact configuration that attempt used.

## What's on disk

```
workspace_root/
├── index.md                      ← workspace record (UUIDv7 `id`) + `index:` + narrative
├── knowledges/<name>.md          ← optional workspace-level knowledge (one markdown file)
└── projects/<project-slug>/
    ├── index.md                  ← project record + `index:` + narrative
    ├── knowledges/<name>.md      ← Finding / Plan / Note / …
    └── experiments/<experiment-slug>/
        ├── index.md              ← experiment record + `index:` + narrative
        ├── knowledges/<name>.md
        └── runs/<key=value_…>/   ← directory name is the parameters
            ├── index.md          ← run record: logical definition only
            └── executions/e01/   ← one attempt; `e01` is its id
                ├── execution.json
                ├── alive         ← owner heartbeat is mtime
                ├── workflow.json
                ├── artifacts/
                ├── out/<task>/
                └── jobs/
```

There is no children-index file. `ls` is the index; the `index:` block is a convenience copy that molab keeps in step with it. A workspace written before the `index.md` records (with `workspace.json` / `project.json` / `experiment.json` / `run.json` / `meta.json`) is upgraded in place with `molab migrate index`. Built-in knowledge lands as one markdown file per document — `knowledges/<name>.md`, with the Knowledge class named in the file's `class:` frontmatter. `.md` is the form that is written; `.mdx` is accepted on read only. The format belongs to `molab.knowledge`, which owns every knowledge document; the workspace treats it as a file in its tree and never names knowledge itself.

## Next

- For the concrete Python API, see [Workspace API](../guide/workspace-api.md).
- For reusable data and provenance, see [Assets and Reproducibility](assets-and-reproducibility.md).
- For the CLI that discovers this hierarchy, see [CLI and Profiles](../getting-started/cli-and-profiles.md).
