"""What actually appears on disk when a ``Run`` is tracked.

Matches ``docs/en/getting-started/tracked-runs.md``.

Run directly::

    python examples/getting_started/03_tracked_run.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import molab as me
from molab.workflow import Workflow

wf = Workflow(name="baseline")


@wf.task
def experiment_body(seed: int = 0) -> dict:
    """Root task — the run's param ``seed`` binds to this named parameter."""
    return {"score": 0.87, "seed": seed}


def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="molab-tracked-"))
    print(f"workspace root: {root}\n")

    ws = me.Workspace(root, name="tracked-demo")
    run = ws.add_project("demo").add_experiment("baseline").add_run(params={"seed": 42})
    result = run.execute(wf)

    for path in sorted(root.rglob("*")):
        if path.is_file():
            print(path.relative_to(root))

    print("\nselected run fields (public API)")
    print(f"  id:              {run.id}")
    print(f"  status:          {run.executions[-1].status.value}")
    print(f"  parameters:      {run.parameters}")
    print(f"  definition_hash: {run.metadata.definition_hash}")
    print(f"  execution count: {len(run.executions)}")
    print(f"  score:           {result.outputs['experiment_body']['score']}")


if __name__ == "__main__":
    main()
