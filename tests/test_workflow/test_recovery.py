"""``molab.workflow.recovery`` — reconstructing a persisted run's workflow.

One shape reaches ``compiled_workflow_for_run``: the **script experiment**
shape — ``ExperimentMetadata.workflow_entrypoint``, written once by the binding
seam in :mod:`molab.entry`. The workflow belongs to the experiment, so a run
reaches it through its parent and never carries a copy. A legacy run-level
``workflow_snapshot`` entrypoint is still read as a fallback.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

import molab.workflow
from molab.workflow import (
    CompiledWorkflow,
    WorkflowRecoveryError,
    can_recover_workflow,
    compiled_workflow_for_run,
    recovery,
)
from molab.workspace import Workspace
from molab.workspace.run import Run

_SCRIPT_MODULE = """\
from molab.workflow import TaskContext, Workflow, WorkflowCompiler

wf = Workflow(name="script-demo")


@wf.task
async def only_task(ctx: TaskContext) -> dict:
    return {"ok": True}


workflow = WorkflowCompiler().compile(wf)
"""


def _bare_run(tmp_path: Path, *, entrypoint: str | None = None, **run_kwargs: object) -> Run:
    """A run whose experiment optionally records a workflow entrypoint."""
    ws = Workspace(root=tmp_path, name="recover-lab")
    exp = ws.add_project("p").add_experiment("e", workflow_source="s.py", params={})
    if entrypoint is not None:
        exp.metadata = exp.metadata.model_copy(update={"workflow_entrypoint": entrypoint})
        exp.save()
    run = exp.add_run(params={"seed": 1}, **run_kwargs)  # type: ignore[arg-type]
    run.materialize()
    return run


def _script_entrypoint(tmp_path: Path) -> str:
    wf_file = tmp_path / "user_workflow.py"
    wf_file.write_text(textwrap.dedent(_SCRIPT_MODULE), encoding="utf-8")
    return f"{wf_file}:workflow"


class TestScriptExperimentShape:
    """The only shape: the experiment's ``workflow_entrypoint``."""

    def test_entrypoint_loads_and_compiles(self, tmp_path: Path) -> None:
        run = _bare_run(tmp_path / "ws", entrypoint=_script_entrypoint(tmp_path))
        compiled = compiled_workflow_for_run(run)
        assert isinstance(compiled, CompiledWorkflow)
        assert compiled.name == "script-demo"
        assert set(compiled.registration_by_name) == {"only_task"}

    def test_dead_entrypoint_raises_recovery_error(self, tmp_path: Path) -> None:
        run = _bare_run(tmp_path / "ws", entrypoint=f"{tmp_path / 'gone.py'}:wf")
        with pytest.raises(WorkflowRecoveryError):
            compiled_workflow_for_run(run)

    def test_a_legacy_run_level_snapshot_is_still_readable(self, tmp_path: Path) -> None:
        """Runs written before the locator moved to the experiment still resume.

        Read-only compatibility: nothing writes ``workflow_snapshot`` any more.
        """
        run = _bare_run(tmp_path / "ws", entrypoint=_script_entrypoint(tmp_path))
        assert compiled_workflow_for_run(run).name == "script-demo"

    def test_the_experiment_wins_over_a_legacy_run_snapshot(self, tmp_path: Path) -> None:
        """One authority: the experiment, even when a stale copy sits on the run."""
        run = _bare_run(
            tmp_path / "ws",
            entrypoint=_script_entrypoint(tmp_path),
            workflow_snapshot={"entrypoint": f"{tmp_path / 'gone.py'}:wf"},
        )
        assert compiled_workflow_for_run(run).name == "script-demo"


class TestCanRecoverWorkflow:
    """The executability precondition never compiles."""

    def test_true_via_the_entrypoint(self, tmp_path: Path) -> None:
        run = _bare_run(tmp_path / "ws", entrypoint=_script_entrypoint(tmp_path))
        assert can_recover_workflow(run) is True

    def test_false_when_the_run_carries_neither_shape(self, tmp_path: Path) -> None:
        assert can_recover_workflow(_bare_run(tmp_path)) is False


class TestNeitherShape:
    def test_error_names_the_entrypoint_and_the_run(self, tmp_path: Path) -> None:
        run = _bare_run(tmp_path)
        with pytest.raises(WorkflowRecoveryError) as excinfo:
            compiled_workflow_for_run(run)
        message = str(excinfo.value)
        assert "workflow_entrypoint" in message
        assert run.id in message
        assert "molab plan" not in message
        assert "generated" not in message


class TestRecoverySurface:
    """The generated-source recoverer seam is gone (D86)."""

    @pytest.mark.parametrize(
        "name", ["set_workflow_recoverer", "get_workflow_recoverer", "WorkflowRecoverer"]
    )
    def test_the_recoverer_seam_is_not_exported(self, name: str) -> None:
        assert not hasattr(molab.workflow, name)
        assert not hasattr(recovery, name)

    def test_the_public_surface_is_entrypoint_recovery_only(self) -> None:
        assert set(recovery.__all__) == {
            "WorkflowRecoveryError",
            "can_recover_workflow",
            "compiled_workflow_for_run",
        }
