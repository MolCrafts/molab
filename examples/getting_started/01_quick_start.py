"""Quick start — workspace + experiment + tracked run, end to end.

Matches ``docs/en/getting-started/quick-start.md``.

Run directly::

    python examples/getting_started/01_quick_start.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import molab as me
from molab.workflow import Workflow

wf = Workflow(name="train")


@wf.task
def train(lr: float = 1e-3, epochs: int = 3) -> dict:
    """Root task — its inputs arrive bound to named parameters.

    The engine fills ``lr`` from the run's params and ``epochs`` from its
    default when absent.
    """
    final_loss = 1.0 / (epochs * (lr * 1000 + 1))
    return {"lr": lr, "epochs": epochs, "final_loss": final_loss}


def main() -> None:
    workspace_root = Path(tempfile.mkdtemp(prefix="molab-quickstart-"))
    print(f"workspace root: {workspace_root}")

    ws = me.Workspace(workspace_root, name="quickstart")
    run = ws.add_project("demo").add_experiment("train").add_run(params={"lr": 1e-3})
    result = run.execute(wf)

    print(f"status:     {run.executions[-1].status.value}")
    print(f"final_loss: {result.outputs['train']['final_loss']}")
    print(f"run_dir:    {run.run_dir}")


if __name__ == "__main__":
    main()
