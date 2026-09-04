# Artifacts, Assets, and Data Imports

In v2 every persistent byproduct of an experiment falls into one of two surfaces:

- **Artifacts** — outputs a running task explicitly emits via `ctx.emit_artifact(...)` (and `ctx.checkpoint(...)`). They are snapshotted into the execution directory, content-addressed, and recorded in a provenance index.
- **DataAssets** — inputs imported from outside the workspace via `{scope}.data_assets.import_asset(...)`.

Artifacts are queried through an `ArtifactRepository`; DataAssets through a scope's `data_assets` view or the manifest scanner. This guide explains both, how they are scoped, and how the two query paths differ.

## Emitted artifacts

A task (or the driver-side `RunContext`) emits an artifact with `ctx.emit_artifact(data, *, name=...)`:

```python
import molexp as me

ws = me.Workspace("./lab", name="lab")
run = ws.add_project("demo").add_experiment("baseline").add_run({"lr": 1e-3})

with run.start() as ctx:
    ctx.set_active_task("train")
    artifact = ctx.emit_artifact({"loss": 0.1}, name="metrics.json")
    # artifact.run_id == run.id
    # artifact.metadata["task_id"] == "train"
    log = ctx.log("runtime")
    log.append("epoch 1")
    ckpt = ctx.checkpoint("epoch-1", data={"step": 1})
```

`emit_artifact` accepts a `pathlib.Path` to an existing file (it must live inside the execution's `work/` directory), or an in-memory `dict` / `list` / `str` / `bytes` payload — in that case it writes the payload into `work/<name>` first. Every emit returns an `Artifact` carrying its `id`, `run_id`, `execution_id`, `name`, `semantic_type`, and a content digest. `set_active_task(task_id)` stamps the active task id into `artifact.metadata["task_id"]`.

`ctx.log(name)` is execution evidence, not an artifact — the only valid names are `"runtime"`, `"stdout"`, and `"stderr"`. `ctx.checkpoint(...)` writes a checkpoint payload and emits it as an artifact with `semantic_type="checkpoint"`.

## Querying artifacts

Emitted artifacts are queried through an `ArtifactRepository`, which reads the content-addressed provenance index the execution wrote to:

```python
from molexp.workspace.artifact_repository import ArtifactRepository

repo = ArtifactRepository(ws.root)
run_artifacts = repo.list_for_execution(run.executions[-1].id)
same_artifact = repo.get(run_artifacts[0].id)
```

## Importing and querying DataAssets

Data that originates outside the workspace enters through a scope's `data_assets` library:

```python
from pathlib import Path

Path("ligands.csv").write_text("smiles\nCCO\n")

dataset = ws.data_assets.import_asset("lig-library", "ligands.csv")
project_dataset = ws.project("demo").data_assets.import_asset("lig-subset", "ligands.csv")
```

The import stores the payload under `<scope>/assets/<asset_id>/payload/` and registers a `DataAsset` that remembers the action used (`copy` / `move` / `symlink` / `hardlink`) and the source path. Look up imported data by name (`ws.data_assets.get("lig-library")`) or scan the workspace with the module-level manifest scanner:

```python
from molexp.workspace.assets import scan

everything = scan.scan_assets(ws.root)
```

## Concurrency and atomicity

Every write is atomic (temp file + `os.rename`), so a crash never leaves a half-written record. Concurrent emits inside one run all land in the provenance index — nothing is lost and nothing is half-written.

## Runnable Example

`examples/workspace/assets.py` imports a data asset, emits artifact/log/checkpoint records from a tracked run, and then scans the workspace manifests.
