"""What actually appears on disk when a ``Run`` is tracked.

Matches ``docs/en/getting-started/tracked-runs.md``.

Run directly::

    python examples/getting_started/03_tracked_run.py
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import molab as me
from molab.workflow import Workflow, WorkflowCompiler, WorkflowRuntime

wf = Workflow(name="baseline")


@wf.task
async def experiment_body(seed: int = 0) -> dict:
    """Root task — the run's sweep param ``seed`` binds to this named parameter."""
    return {"score": 0.87, "seed": seed}


compiled = WorkflowCompiler().compile(wf)


async def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="molab-tracked-"))
    print(f"workspace root: {root}\n")

    ws = me.Workspace(root, name="tracked-demo")
    exp = ws.add_project("demo").add_experiment("baseline").define(compiled, params={"seed": [42]})

    run = exp.list_runs()[0]
    with run.start() as ctx:
        execution_id = ctx.id
        result = await WorkflowRuntime().execute(compiled, run_context=ctx)
        # Driver-side workspace helpers — results, artifacts, logs.
        ctx.set_result("score", result.outputs["experiment_body"]["score"])
        ctx.emit_artifact("summary goes here", name="report.txt")
        ctx.log("runtime").append("epoch 1 complete")

    for path in sorted(root.rglob("*")):
        if path.is_file():
            print(path.relative_to(root))

    print("\nselected run fields (public API)")
    print(f"  id:              {run.id}")
    print(f"  status:          {run.executions[-1].status.value}")
    print(f"  parameters:      {run.parameters}")
    print(f"  definition_hash: {run.metadata.definition_hash}")
    print(f"  execution count: {len(run.executions)}")
    print(f"  score:           {run.get_result('score', execution_id=execution_id)}")


if __name__ == "__main__":
    asyncio.run(main())
