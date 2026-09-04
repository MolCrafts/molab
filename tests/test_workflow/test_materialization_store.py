"""Return values are not auto-published as artifacts.

``persist_result`` / ``FileMaterializationStore`` retired: a task's return
value lives in ``workflow.json``. Files become run products only through
``register_artifact``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from molexp.workflow import Workflow, WorkflowCompiler, WorkflowRuntime
from molexp.workspace import Workspace


@pytest.mark.asyncio
async def test_json_return_is_not_auto_registered_as_artifact(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "lab")
    run = ws.add_project(name="p").add_experiment(name="e").add_run()
    wf = Workflow(name="plain")

    @wf.task
    async def produce() -> dict:
        return {"value": 42}

    with run.start() as ctx:
        out = await WorkflowRuntime().execute(WorkflowCompiler().compile(wf), run_context=ctx)

    assert out.outputs["produce"] == {"value": 42}
    execution_id = run.executions[-1].id
    artifacts = run._execution_repository().artifacts.list_for_execution(execution_id)
    found = [a for a in artifacts if a.metadata.get("task_id") == "produce"]
    assert found == []
