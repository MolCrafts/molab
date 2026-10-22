"""What survives re-opening a run: ``run.json`` + ``execution_history``.

Matches ``docs/en/guide/workflow-persistence.md``.

Executes the same run twice (first failing, then succeeding) and prints
the public run fields that let you trace the attempt history, profile
metadata, and deterministic config hash.

Run directly::

    python examples/workspace/workflow_persistence.py
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import molab as me
from molab.profile import ProfileConfig
from molab.workflow import Workflow, WorkflowCompiler, WorkflowRuntime
from molab.workspace.domain import ExecutionMode

# Module-level marker so the first attempt fails and the second succeeds.
_FAIL_ONCE_MARKER: Path | None = None

wf = Workflow(name="flaky")


@wf.task
async def flaky_train(epochs: int = 3) -> dict:
    # Config values bind to task parameters by name (``epochs`` from the profile).
    assert _FAIL_ONCE_MARKER is not None
    if not _FAIL_ONCE_MARKER.exists():
        _FAIL_ONCE_MARKER.touch()
        raise RuntimeError("first attempt boom")
    return {"epochs": epochs}


compiled = WorkflowCompiler().compile(wf)


async def main() -> None:
    global _FAIL_ONCE_MARKER

    root = Path(tempfile.mkdtemp(prefix="molab-persist-"))
    _FAIL_ONCE_MARKER = root / "fail-once"

    ws = me.Workspace(root, name="persist-demo")
    exp = ws.add_project("demo").add_experiment("train").define(compiled, params={"seed": [0]})

    cfg = ProfileConfig({"epochs": 5}, name="smoke")
    run = exp.list_runs()[0]

    # ``execute()`` captures task failures and records them on the run
    # without re-raising — inspect ``result.status`` instead.
    with run.start(profile_config=cfg) as ctx:
        first_execution_id = ctx.id
        result = await WorkflowRuntime().execute(compiled, run_context=ctx)
    print(f"attempt 1: status={result.status}")

    with run.start(
        mode=ExecutionMode.RETRY,
        predecessor=first_execution_id,
        profile_config=cfg,
    ) as ctx:
        result = await WorkflowRuntime().execute(compiled, run_context=ctx)
    print(f"attempt 2: status={result.status}")

    print("\nrun fields (public API)")
    print(f"  id:               {run.id}")
    print(f"  status:           {run.executions[-1].status.value}")
    print(f"  definition_hash:  {run.metadata.definition_hash}")
    print(f"  parameters:       {run.parameters}")
    print(f"  attempts:         {len(run.executions)}")
    for i, entry in enumerate(run.executions):
        print(
            f"    #{i + 1}: status={entry.status.value}, "
            f"started={entry.started_at}, finished={entry.finished_at}"
        )


if __name__ == "__main__":
    asyncio.run(main())
