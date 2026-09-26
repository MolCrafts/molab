"""``molab execute`` — the molq worker entry (``cli/workspace/run.py`` ``execute``).

The worker is what a scheduler job runs: it opens the run from its directory,
rebuilds the workflow from the experiment's ``workflow_entrypoint`` and
executes it against a pre-created Execution record. Invoked in-process through
typer's ``CliRunner``; the binding registry holds nothing for the experiment,
so recovery takes the same path a fresh worker process takes.

(Not named ``test_run.py``: neither this directory nor
``tests/test_server/test_routes/`` has an ``__init__.py``, and two
``test_run.py`` basenames collide in pytest's rootdir-relative import.)
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

import molab.cli
from molab.workspace import AgentRef, Workspace
from molab.workspace.domain import ExecutionMode
from molab.workspace.execution_repository import ExecutionRepository
from molab.workspace.project import Project
from molab.workspace.run import Run
from tests.support.journal import poison_node_output

_HEALING_MODULE = """\
from pathlib import Path

from molab.workflow import Workflow, WorkflowCompiler

FLAG = Path({flag!r})
RESULT = Path({result!r})

wf = Workflow(name="healing")


@wf.task
def stage_a(seed: int) -> int:
    return seed + 1


@wf.task(depends_on=["stage_a"])
def stage_b(stage_a: int) -> int:
    if not FLAG.exists():
        raise RuntimeError("not healed yet")
    RESULT.write_text(str(stage_a * 100))
    return stage_a * 100


workflow = WorkflowCompiler().compile(wf)
"""


def _healing_run(tmp_path: Path) -> tuple[Workspace, Project, Run]:
    """A ``{"seed": 1}`` run whose experiment points at ``healing_wf.py:workflow``."""
    wf_file = tmp_path / "healing_wf.py"
    wf_file.write_text(
        _HEALING_MODULE.format(
            flag=str(tmp_path / "healed"),
            result=str(tmp_path / "result.txt"),
        ),
        encoding="utf-8",
    )
    ws = Workspace(root=tmp_path / "ws", name="worker-lab")
    project = ws.add_project("p")
    exp = project.add_experiment("e")
    # Hand-written binding (arch-own-04 replaces this with Experiment.bind_workflow).
    exp.metadata = exp.metadata.model_copy(update={"workflow_entrypoint": f"{wf_file}:workflow"})
    exp.save()
    run = exp.add_run(params={"seed": 1})
    run.materialize()
    return ws, project, run


def _repository(ws: Workspace, project: Project, run: Run) -> ExecutionRepository:
    return ExecutionRepository(ws.root, run.run_dir, run_id=run.id, project_id=project.id, fs=ws.fs)


def _worker(run: Run, execution_id: str) -> int:
    result = CliRunner().invoke(
        molab.cli.app, ["execute", str(run.run_dir), "--execution-id", execution_id]
    )
    return result.exit_code


_TEST_AGENT = AgentRef(id="test", type="person", name="test")


class TestExecute:
    def test_queued_execution_runs_to_success(self, tmp_path: Path) -> None:
        ws, project, run = _healing_run(tmp_path)
        (tmp_path / "healed").write_text("ok")
        queued = _repository(ws, project, run).create(
            mode=ExecutionMode.INITIAL, created_by=_TEST_AGENT
        )
        assert queued.id == "e01"
        assert [e.status.value for e in run.executions] == ["queued"]

        exit_code = _worker(run, "e01")

        assert exit_code == 0
        assert [e.status.value for e in run.executions] == ["succeeded"]
        assert len(run.executions) == 1
        assert (tmp_path / "result.txt").read_text() == "200"

    @pytest.mark.xfail(
        strict=True,
        raises=(ValueError, AssertionError),
        reason="arch-own-03: molab execute on a RESUME record — no checkpoint needed "
        "and the worker seeds from based_on e01, writing result 4100",
    )
    def test_resume_record_seeds_from_based_on(self, tmp_path: Path) -> None:
        ws, project, run = _healing_run(tmp_path)
        repository = _repository(ws, project, run)
        repository.create(mode=ExecutionMode.INITIAL, created_by=_TEST_AGENT)
        assert _worker(run, "e01") == 1
        assert [e.status.value for e in run.executions] == ["failed"]
        # e01 recorded stage_a == 2; the sentinel 41 reaches stage_b only as a
        # seed taken from e01's journal (a recompute yields 2 -> "200").
        poison_node_output(run.run_dir, "e01", "stage_a", 41)
        (tmp_path / "healed").write_text("ok")
        resume = repository.create(
            mode=ExecutionMode.RESUME,
            based_on_execution_id="e01",
            created_by=_TEST_AGENT,
        )
        assert resume.id == "e02"

        exit_code = _worker(run, "e02")

        assert exit_code == 0
        assert [e.status.value for e in run.executions] == ["failed", "succeeded"]
        assert (tmp_path / "result.txt").read_text() == "4100"
