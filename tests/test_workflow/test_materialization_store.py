"""Return values are not auto-published as assets.

A task's return value lives in ``workflow.json``. A file becomes an asset
only through ``ctx.register``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from molab.workflow import Workflow, WorkflowRuntime
from molab.workspace import Workspace


@pytest.mark.asyncio
async def test_json_return_is_not_auto_registered(tmp_path: Path) -> None:
    from molab.workspace.asset_repository import assets_produced_by

    ws = Workspace(tmp_path / "lab")
    run = ws.add_project(name="p").add_experiment(name="e").add_run()
    wf = Workflow(name="plain")

    @wf.task
    async def produce() -> dict:
        return {"value": 42}

    with run.start() as ctx:
        out = await WorkflowRuntime().execute((wf).compile(), run_context=ctx)

    assert out.outputs["produce"] == {"value": 42}
    assert assets_produced_by(ws, run.executions[-1].id) == []
