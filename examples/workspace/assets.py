"""Named assets, emitted artifacts, and workspace-wide asset queries.

Walks through:

1. ``ctx.emit_artifact`` — writes a file and records an ``Artifact``.
2. ``ctx.log("run").append`` — appends to the execution evidence log.
3. ``ctx.checkpoint`` — writes a checkpoint ``Artifact``.
4. ``ws.data_assets.import_asset`` — pulls external data in as an ``Asset``.
5. ``ws.assets.versions`` — read that import's origin.
6. ``scan_asset_repositories`` — every named asset in the workspace.

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

    external = root / "external.csv"
    external.write_text("x,y\n1,2\n3,4\n")
    imported = ws.data_assets.import_asset("toy-dataset", external)

    exp = ws.add_project("demo").add_experiment("train").define(compiled, params=None)
    run = exp.list_runs()[0]
    with run.start() as ctx:
        result = await WorkflowRuntime().execute(compiled, run_context=ctx)
        ctx.emit_artifact(result.outputs["train"], name="metrics.json")

        log = ctx.log("run")
        log.append("epoch 1 start")
        log.append("epoch 1 done  loss=0.10")
        log.append("epoch 2 done  loss=0.08")

        ctx.checkpoint("epoch-1", data={"step": 1})
        ctx.checkpoint("epoch-2", data={"step": 2})

        version = ws.assets.versions(imported.id)[-1]
        source = version.origin.uri if version.origin.kind == "import" else ""
        ctx.emit_artifact(
            {"dataset": imported.title, "source": source},
            name="dataset-path.json",
        )

    from molab.workspace.artifact_repository import scan_asset_repositories

    all_assets = [asset for repo in scan_asset_repositories(ws) for asset in repo.list()]
    print(f"workspace root: {root}")
    print(f"total assets:   {len(all_assets)}")
    for asset in all_assets:
        print(f"  [{asset.kind:<11}] {asset.title:<20} scope={asset.scope.kind}")


if __name__ == "__main__":
    asyncio.run(main())
