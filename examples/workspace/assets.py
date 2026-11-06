"""Register a file, then open it as the next run's input.

Walks through:

1. ``import_asset`` — copies outside bytes in as an Asset.
2. ``ctx.register`` — copies a task result in as an Asset of the experiment.
3. ``ctx.checkpoint`` — writes a path under ``checkpoints/``. It is not an Asset.
4. ``assets_produced_by`` — the assets one attempt registered.
5. ``Finding.harvest`` — the document cites ``molab:asset/<id>`` and the
   point the conclusion uses (``/loss``).
6. ``finding.inputs`` — the next run's inputs are those asset ids. The root
   task receives them as paths. The workflow does not import knowledge.

Run directly::

    python examples/workspace/assets.py
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import molab as me
from molab.workflow import TaskContext, Workflow, WorkflowRuntime

wf = Workflow(name="train")


@wf.task
def train(ctx: TaskContext) -> str:
    path = ctx.workdir / "metrics.json"
    path.write_text('{"loss": 0.08}\n', encoding="utf-8")
    return ctx.register(path, title="metrics")


compiled = wf.compile()

follow = Workflow(name="read")


@follow.task
def read(inputs: tuple[Path, ...], metrics: Path) -> str:
    opened = inputs[0]
    if opened != metrics:
        raise RuntimeError(f"title binding {metrics} is not inputs[0] {opened}")
    return opened.read_text(encoding="utf-8")


follow_compiled = follow.compile()


async def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="molab-assets-"))
    ws = me.Workspace(root, name="assets-demo")

    external = root / "external.csv"
    external.write_text("x,y\n1,2\n3,4\n", encoding="utf-8")
    imported = ws.assets.import_asset("toy-dataset", external)

    exp = ws.add_project("demo").add_experiment("train").define(compiled, params=None)
    run = exp.list_runs()[0]
    with run.start() as ctx:
        result = await WorkflowRuntime().execute(compiled, run_context=ctx)
        log = ctx.log("run")
        log.append("epoch 1 done  loss=0.08")
        ctx.checkpoint("epoch-1", data={"step": 1})

    from molab.workspace.asset_repository import assets_produced_by

    produced = assets_produced_by(ws, run.executions[-1].id)
    metrics_asset = next(asset for asset in produced if asset.title == "metrics")
    print(f"metrics asset: molab:asset/{metrics_asset.id}")

    from molab.knowledge.concepts import Finding

    finding = Finding.harvest(
        run,
        narrative="The training loss reached 0.08.",
        created_by="example",
        name="train-loss",
        results={"loss": 0.08},
    )
    follow_run = exp.add_run(inputs=finding.inputs)
    with follow_run.start() as follow_ctx:
        follow_result = await WorkflowRuntime().execute(follow_compiled, run_context=follow_ctx)

    print(f"workspace root: {root}")
    print(f"imported:       {imported.ref}  origin={imported.origin.kind}")
    print(f"task returned:  {result.outputs['train']}")
    print(f"produced:       {len(produced)}")
    for asset in produced:
        print(f"  {asset.ref}  {asset.title}  origin={asset.origin.kind}")
    print(f"cited point:    /loss = {finding.read_cited('/loss')}")
    print(f"next inputs:    {follow_run.inputs}")
    print(f"next run read:  {follow_result.outputs['read'].rstrip()}")


if __name__ == "__main__":
    asyncio.run(main())
