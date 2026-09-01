"""``Plan.open`` / ``Plan.save`` — bind a plan Run and land workflow IR."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from molexp.harness import Plan
from molexp.harness.store.file_artifact_store import FileArtifactStore
from molexp.harness.store.paths import harness_artifact_root
from molexp.workspace import Workspace

_SOURCE = """
from molexp.workflow import TaskContext, Workflow, WorkflowCompiler


def build_workflow() -> Workflow:
    wf = Workflow(name="demo")

    @wf.task
    async def alpha(ctx: TaskContext) -> dict:
        return {"x": 1}

    @wf.task(depends_on=["alpha"])
    async def beta(ctx: TaskContext) -> dict:
        x = ctx.inputs["x"]
        return {"y": x + 1}

    return wf
"""

_PKG_INIT = """
from molexp.workflow import Workflow, WorkflowCompiler
from workflow.gamma import gamma
from workflow.delta import delta


def build_workflow() -> Workflow:
    wf = Workflow(name="pkg-demo")
    wf.task(gamma)
    wf.task(depends_on=["gamma"])(delta)
    return wf
"""

_GAMMA = """
from molexp.workflow import TaskContext


async def gamma(ctx: TaskContext, sigma: float = 1.0) -> dict:
    return {"x": sigma}
"""

_DELTA = """
from molexp.workflow import TaskContext


async def delta(ctx: TaskContext) -> dict:
    x = ctx.inputs["x"]
    return {"y": x + 1}
"""


@pytest.fixture()
def workspace(tmp_path: Path) -> Workspace:
    ws = Workspace(tmp_path / "lab", name="lab")
    ws.materialize()
    return ws


def _put_workflow_source(run, payload: dict) -> None:
    FileArtifactStore(root=harness_artifact_root(run.run_dir)).put_json(
        "workflow_source",
        payload,
        created_by="test",
        parent_ids=[],
    )


class TestPlanOpen:
    def test_same_draft_reuses_the_same_run(self, workspace: Workspace) -> None:
        exp = workspace.add_project("p").add_experiment("e")
        first = Plan.open(exp, "Simulate NEMD")
        second = Plan.open(exp, "Simulate NEMD")
        assert first.bound_run.id == second.bound_run.id
        assert first.bound_run.run_dir == second.bound_run.run_dir

    def test_supersedes_mints_a_different_run(self, workspace: Workspace) -> None:
        exp = workspace.add_project("p").add_experiment("e")
        first = Plan.open(exp, "Simulate NEMD")
        second = Plan.open(exp, "Simulate NEMD", supersedes=first.bound_run.id)
        assert first.bound_run.id != second.bound_run.id


class TestPlanSave:
    def test_stamps_plan_run_id_and_survives_reload(self, workspace: Workspace) -> None:
        experiment = workspace.add_project("p").add_experiment("e")
        plan = Plan.open(experiment, "d")
        _put_workflow_source(
            plan.bound_run,
            {"source": _SOURCE, "module_name": "generated_workflow", "bound_workflow_id": "bw"},
        )

        assert plan.save() is True
        assert experiment.metadata.plan_run_id == plan.bound_run.id
        reloaded = Workspace(workspace.resolve()).get_project("p").get_experiment("e")
        assert reloaded.metadata.plan_run_id == plan.bound_run.id

    def test_save_returns_false_when_no_workflow_source(self, workspace: Workspace) -> None:
        experiment = workspace.add_project("p").add_experiment("e")
        plan = Plan.open(experiment, "d")
        assert plan.save() is False
        assert experiment.metadata.plan_run_id is None

    def test_attaches_per_task_source_without_bleed(self, workspace: Workspace) -> None:
        experiment = workspace.add_project("p").add_experiment("e")
        plan = Plan.open(experiment, "d")
        _put_workflow_source(
            plan.bound_run,
            {"source": _SOURCE, "module_name": "generated_workflow", "bound_workflow_id": "bw"},
        )
        assert plan.save() is True
        ir = json.loads(experiment.metadata.workflow_source or "")
        by_id = {tc["task_id"]: tc for tc in ir["task_configs"]}
        assert set(by_id) == {"alpha", "beta"}
        assert by_id["alpha"]["source"].startswith("@wf.task")
        assert "async def alpha" in by_id["alpha"]["source"]
        assert '@wf.task(depends_on=["alpha"])' in by_id["beta"]["source"]
        assert 'ctx.inputs["x"]' in by_id["beta"]["source"]
        assert "async def beta" not in by_id["alpha"]["source"]

    def test_returns_false_on_non_compiling_source(self, workspace: Workspace) -> None:
        experiment = workspace.add_project("p").add_experiment("e")
        plan = Plan.open(experiment, "d")
        _put_workflow_source(
            plan.bound_run,
            {
                "source": "def build_workflow(:\n    pass",
                "module_name": "generated_workflow",
                "bound_workflow_id": "bw",
            },
        )
        assert plan.save() is False

    def test_compiles_multi_file_package_via_subprocess_and_annotates(
        self, workspace: Workspace
    ) -> None:
        experiment = workspace.add_project("p").add_experiment("e")
        plan = Plan.open(experiment, "d")
        _put_workflow_source(
            plan.bound_run,
            {
                "source": _PKG_INIT,
                "module_name": "workflow",
                "bound_workflow_id": "bw-pkg",
                "symbols": ["WorkflowCompiler", "TaskContext"],
                "files": [
                    {"path": "workflow/__init__.py", "source": _PKG_INIT},
                    {"path": "workflow/gamma.py", "source": _GAMMA},
                    {"path": "workflow/delta.py", "source": _DELTA},
                ],
            },
        )
        assert plan.save() is True
        ir = json.loads(experiment.metadata.workflow_source or "")
        by_id = {tc["task_id"]: tc for tc in ir["task_configs"]}
        assert set(by_id) == {"gamma", "delta"}
        assert "async def gamma" in by_id["gamma"]["source"]
        assert 'ctx.inputs["x"]' in by_id["delta"]["source"]
        assert {f["name"] for f in ir["input_schema"]} == {"sigma"}

    def test_returns_false_on_broken_package(self, workspace: Workspace) -> None:
        experiment = workspace.add_project("p").add_experiment("e")
        plan = Plan.open(experiment, "d")
        broken_src = "import missing_sibling_mod\n\ndef build_workflow():\n    return None\n"
        _put_workflow_source(
            plan.bound_run,
            {
                "source": broken_src,
                "module_name": "workflow",
                "bound_workflow_id": "bw-broken",
                "symbols": [],
                "files": [{"path": "workflow/__init__.py", "source": broken_src}],
            },
        )
        assert plan.save() is False
