"""Script that is meant to be driven by ``molab run`` — not by ``python``.

Matches ``docs/en/getting-started/cli-and-profiles.md``.

The script declares a workspace, an experiment, and the workflow it runs via
the declaration chain ``ws.add_project(...).add_experiment(...).define(wf, params=...)`` —
that declaration is what the CLI discovers. Execute it with::

    molab run examples/getting_started/04_cli_and_profiles/train.py --profile smoke
    molab run examples/getting_started/04_cli_and_profiles/train.py --profile prod
    molab run examples/getting_started/04_cli_and_profiles/train.py \\
        --profile smoke --override lr=5e-4

``molcfg.yaml`` in this directory defines the ``smoke`` and ``prod`` profiles.
"""

from __future__ import annotations

from pathlib import Path

import molab as me
from molab.workflow import Workflow, WorkflowCompiler

# Workspace lives next to this script so repeated ``molab run`` calls reuse it.
WORKSPACE_ROOT = Path(__file__).resolve().parent / "_workspace"

wf = Workflow(name="train")


@wf.task
async def train(lr: float = 1e-3, epochs: int = 10) -> dict:
    """Profile fields bind by name.

    ``--profile`` merges ``molcfg.yaml`` into the run's build-time config, and
    the engine fills ``lr`` / ``epochs`` from it — each falling back to its
    declared default when the selected profile omits it. The chosen profile
    name is recorded on the run record, not read inside the task.
    """
    final_loss = 1.0 / (epochs * (lr * 1000 + 1))
    return {"lr": lr, "epochs": epochs, "final_loss": final_loss}


(
    me.Workspace(WORKSPACE_ROOT, name="cli-demo")
    .add_project("demo")
    .add_experiment("train")
    .define(WorkflowCompiler().compile(wf), params={"seed": [0]})
)
