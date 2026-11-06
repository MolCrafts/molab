# Assets

An Asset is one registered file: one id, one content, one ref `molab:asset/<id>`. Each asset owns one slot: its title for an import, its run and title for an attempt's product. The same bytes registered again return the existing ref. New bytes in an occupied slot replace the old ones and keep the id, so `molab:asset/<id>` always names the run's current product; git keeps the old record. Logs are refused: they are evidence, not products.

The record and the payload live together under the workspace, a project, or an experiment: `assets/<slot>/asset.json` plus the payload file beside it. An import's slot is its title (`assets/brief/`); an attempt's product is slotted by run (`assets/model-pbix-br--network-data/`). A slot never grows a `-2` suffix. Sealing an attempt commits its run's slots, so the tree is clean afterwards. A run does not store a second product record. "What did this attempt register?" is `assets_produced_by`, a query by producer execution id.

Files a task writes under `out/<task>/` or `work/` are not assets until something registers them. Logs, `traceback.txt`, `alive`, and `metrics.mlp.jsonl` are evidence of the attempt. `ctx.checkpoint` writes a file under `checkpoints/` and returns a path.

## Register

A task registers a file it wants the next run to be able to open:

```python
@wf.task
def simulate(ctx):
    path = ctx.workdir / "final.xyz"
    path.write_text("...")
    return ctx.register(path, title="structure")
```

Inside a task, `ctx.register` returns a marker. The engine copies the bytes next to the asset record and records `molab:asset/<id>` as the output. The working file stays where the task wrote it, so `out/` and `work/` can be pruned later. The task opens paths; it does not look up the library. A driver that already holds `run.start()` calls the same name and gets the `Asset` back directly.

Import bytes that did not come from a run with `{scope}.import_asset` (or `{scope}.assets.import_asset`). Import is an origin, not a second type.

## The next run

Name the ids on the run. At execute time they bind into the root task the way parameters do: `inputs` is `tuple[Path, ...]` in `run.inputs` order, and a title that is a unique Python identifier also binds as a parameter of that name. A title that matches a parameter, including a parameter named `inputs`, is an error.

```python
from molab.workspace.asset_repository import assets_produced_by

produced = assets_produced_by(ws, run.executions[-1].id)
structure = next(asset for asset in produced if asset.title == "structure")
nxt = exp.add_run(params={"temp": 300}, inputs=(structure.id,))


@wf.task
def analyze(ctx, inputs: tuple[Path, ...], structure: Path):
    text = structure.read_text()
```

Inside one graph, a downstream task receives the path resolved from the ref. The journal stores the ref string. Without an execution, the string is left as it is.

## Query

```python
from molab.workspace.asset_repository import assets_produced_by, scan_asset_repositories

produced = assets_produced_by(ws, run.executions[-1].id)
payload = produced[0].content  # digest and size; the file is asset.file
```

`{scope}.assets` is that scope's repository. A record that still has `versions/`, or an `asset.json` with no `origin`, raises `UnmigratedAssetError`. Readers do not rewrite it. `molab init` may mint a new id for bytes that should be kept.

## Knowledge

Harvest cites `molab:asset/<id>` for each asset the latest attempt registered, together with the run and the experiment. Workflow does not import knowledge. The ref is the link.
