"""The ``Workspace → Project → Experiment → Run`` walk, end to end.

Matches ``docs/en/guide/workspace-api.md``.

Shows the idempotent create-or-get calls (``ws.add_project``,
``project.add_experiment``), the strict bare-noun getters (``ws.project``,
``project.experiment``), the ``exp.define(workflow, params=...)`` sweep
declaration, and how re-opening a workspace returns the same logical entities
instead of creating duplicates.

Run directly::

    python examples/workspace/workspace_api.py
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import molab as me
from molab.workflow import Workflow, WorkflowCompiler, WorkflowRuntime

wf = Workflow(name="step")


@wf.task
async def step(seed: int | None = None) -> dict:
    # A run's sweep params bind to task parameters by name (``seed`` here).
    return {"noted": True, "seed": seed}


compiled = WorkflowCompiler().compile(wf)


async def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="molab-ws-api-"))
    print(f"workspace root: {root}\n")

    ws = me.Workspace(root, name="ws-api-demo")
    project = ws.add_project("demo")  # create-or-get
    exp = project.add_experiment("baseline")  # create-or-get

    # Declare the sweep: one content-addressed Run per parameter cell.
    exp.define(compiled, params={"seed": [0, 1]})
    runs = exp.list_runs()

    for run in runs:
        with run.start() as ctx:
            await WorkflowRuntime().execute(compiled, run_context=ctx)

    # add_* is idempotent; the bare-noun spelling is the strict getter
    # (it raises *NotFoundError when the node does not exist yet).
    same_project = ws.add_project("demo")
    same_exp = same_project.add_experiment("baseline")
    print("ws.add_project('demo') is idempotent:         ", same_project is project)
    print("add_experiment('baseline') is idempotent:     ", same_exp is exp)
    print("strict getter sees the same project:          ", ws.project("demo") is project)

    # Re-declaring the same sweep adds no duplicate runs.
    exp.define(compiled, params={"seed": [0, 1]})
    print("re-declaring the sweep adds no runs:      ", len(exp.list_runs()) == len(runs))

    # Reload the workspace from disk — same logical state.
    reopened = me.Workspace.load(root)
    print("\nafter Workspace.load(root):")
    print(f"  projects:    {[p.name for p in reopened.list_projects()]}")
    reopened_proj = reopened.get_project("demo")
    reopened_exp = reopened_proj.get_experiment(exp.id)
    print(f"  experiments: {[e.name for e in reopened_proj.list_experiments()]}")
    print(f"  runs:        {[r.id for r in reopened_exp.list_runs()]}")
    print(f"  run status:  {[r.executions[-1].status.value for r in reopened_exp.list_runs()]}")


if __name__ == "__main__":
    asyncio.run(main())
