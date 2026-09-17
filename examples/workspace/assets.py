"""Artifacts, logs, checkpoints, data imports, and asset queries.

Matches ``docs/en/guide/assets.md``.

Walks through:

1. ``ctx.emit_artifact`` — writes a file and records an ``Artifact``.
2. ``ctx.log("runtime").append`` — appends to the execution evidence log.
3. ``ctx.checkpoint`` — writes a checkpoint ``Artifact``.
4. ``ws.data_assets.import_asset`` — pulls external data into the workspace.
5. ``ws.data_assets.get`` — look up an imported ``DataAsset`` by name.
6. ``scan.scan_assets`` — workspace-wide asset queries over the authoritative
   on-disk manifests (the manifest scanner that replaced the SQLite catalog).

Task bodies receive their inputs as named parameters (nothing on ``ctx`` but
``ctx.workdir``); the asset helpers live on the ``RunContext`` the driver opened
via ``run.start()``.

Run directly::

    python examples/workspace/assets.py
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import molab as me
from molab.workflow import TaskContext, Workflow, WorkflowCompiler, WorkflowRuntime

wf = Workflow(name="train")


@wf.task
async def train(ctx: TaskContext) -> dict:
    return {"loss": 0.08, "acc": 0.94}


compiled = WorkflowCompiler().compile(wf)


async def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="molab-assets-"))
    ws = me.Workspace(root, name="assets-demo")

    # 4. Import a workspace-scoped dataset from outside.
    external = root / "external.csv"
    external.write_text("x,y\n1,2\n3,4\n")
    ws.data_assets.import_asset("toy-dataset", external)

    exp = ws.add_project("demo").add_experiment("train").define(compiled, params=None)
    run = exp.list_runs()[0]
    with run.start() as ctx:
        result = await WorkflowRuntime().execute(compiled, run_context=ctx)

        # 1. Artifact — arbitrary payload snapshotted into the execution.
        ctx.emit_artifact(result.outputs["train"], name="metrics.json")

        # 2. Log — line-oriented evidence log, scoped to this execution.
        log = ctx.log("runtime")
        log.append("epoch 1 start")
        log.append("epoch 1 done  loss=0.10")
        log.append("epoch 2 done  loss=0.08")

        # 3. Checkpoints.
        ctx.checkpoint("epoch-1", data={"step": 1})
        ctx.checkpoint("epoch-2", data={"step": 2})

        # 5. The imported DataAsset is looked up by name (no scope walk).
        dataset = ws.data_assets.get("toy-dataset")
        if dataset is not None:
            ctx.emit_artifact(
                {"dataset": dataset.name, "source": dataset.source_path}, name="dataset-path.json"
            )

    # 6. Asset queries — flat view over the whole workspace, scanned from the
    #    authoritative on-disk manifests.
    from molab.workspace.assets import scan

    all_assets = scan.scan_assets(ws.root)
    print(f"workspace root: {root}")
    print(f"total assets:   {len(all_assets)}")
    for asset in all_assets:
        kind = type(asset).__name__.removesuffix("Asset").lower()
        print(f"  [{kind:<11}] {asset.name:<20} scope={asset.scope.kind}")


if __name__ == "__main__":
    asyncio.run(main())
