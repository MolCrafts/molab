# Assets and Reproducibility

Reproducibility in Molab is not only about rerunning code. It's about recovering the workflow definition, the configuration, the execution record, and the data the workflow depended on. The asset layer gives those resources first-class names and scopes.

## Assets as named resources

An Asset is one registered file: one id, one content, one ref `molab:asset/<id>`. It lives under the workspace, a project, or an experiment (`assets/<slug>/asset.json` plus the payload). A run does not keep a second copy. Logs, checkpoints, and `metrics.mlp.jsonl` are evidence of the attempt. They are not assets.

| Scope | Example |
|---|---|
| Workspace | A dataset imported for every project |
| Project | A force-field file imported once |
| Experiment | A structure a run registered, or a file imported for that experiment |

The next run names those ids in `inputs`. At execute time the root task receives them as paths. See [Assets](../guide/assets.md).

```python
# docs: skip — conceptual illustration; requires a workspace and a finished run
from molab.workspace.asset_repository import assets_produced_by

produced = assets_produced_by(ws, run.executions[-1].id)
nxt = exp.add_run(inputs=(produced[0].id,))
```

## Reproducibility records

Beyond outputs, Molab persists the metadata that makes a run interpretable later:

| Record | Where | What it captures |
|---|---|---|
| Workflow snapshot | `run.json` | The exact graph identity (`workflow_hash`) |
| Config hash | `run.json` | The resolved profile's `config_hash` |
| Execution history | `executions/eNN/execution.json` + `alive` | Status, timestamps, attempt; heartbeat is `alive` mtime |
| Per-task outputs | `executions/<exec_id>/workflow.json` | Each task's return value |

Together, these turn a run directory into a scientific record — not just a pile of output files.

## FAIR boundaries

Molab supports FAIR-oriented practice inside a managed workspace:

- **Findable** — one id, one ref, queried by the attempt that registered it
- **Accessible** — Python API, server, and UI all read the same record
- **Interoperable** — the ref is `molab:asset/<id>`, and a task opens the path it resolves to
- **Reusable** — the next run names the id in `inputs`

What Molab does **not** do automatically: publish external identifiers, enforce a community schema, or turn local records into a repository-grade FAIR archive. It gives you a strong internal record. That is a substantial improvement over ad hoc folders.

## Why this matters

Most workflow systems fail gradually. The script still exists, but nobody remembers which dataset directory was the real one, which profile was used for the paper figure, or whether the checkpoint was generated before or after the last code change. Molab keeps the workflow, the run metadata, and the reusable assets in one persistent structure — so those questions have answers.
