"""``molab.workflow.recovery`` — reconstructing a persisted run's workflow.

Two shapes reach ``compiled_workflow_for_run``:

* the **script experiment** shape — ``ExperimentMetadata.workflow_entrypoint``,
  written once by the binding seam in :mod:`molab.entry`. The workflow belongs
  to the experiment, so a run reaches it through its parent and never carries a
  copy;
* the **generated-source** shape belongs to whichever package wrote it and
  arrives through the ``set_workflow_recoverer`` inversion seam.

molab therefore never parses a generated format here, and these tests use a
stub recoverer rather than any particular producer of one.
"""

from __future__ import annotations

import textwrap
from collections.abc import Iterator
from pathlib import Path

import pytest

from molab.workflow import (
    CompiledWorkflow,
    Workflow,
    WorkflowCompiler,
    WorkflowRecoveryError,
    can_recover_workflow,
    compiled_workflow_for_run,
    get_workflow_recoverer,
    set_workflow_recoverer,
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


@pytest.fixture(autouse=True)
def _unwired_seam() -> Iterator[None]:
    """Start every test from an unwired seam; restore the process state after.

    The seam is process-global and any face that imports a generated-source
    producer wires it, so a test must never inherit whatever ran before it.
    """
    previous = get_workflow_recoverer()
    set_workflow_recoverer(None)
    try:
        yield
    finally:
        set_workflow_recoverer(previous)


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


def _stub_compiled(name: str) -> CompiledWorkflow:
    wf = Workflow(name=name)

    @wf.task
    async def generated(ctx: object) -> dict:
        return {}

    return WorkflowCompiler().compile(wf)


class _StubRecoverer:
    """A generated-source producer that answers for every run it is given."""

    def __init__(self, compiled: CompiledWorkflow | None) -> None:
        self._compiled = compiled
        self.recover_calls = 0

    def can_recover(self, run: Run) -> bool:
        return self._compiled is not None

    def recover(self, run: Run) -> CompiledWorkflow | None:
        self.recover_calls += 1
        return self._compiled


class TestScriptExperimentShape:
    """The built-in shape: the experiment's ``workflow_entrypoint``."""

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


class TestSeamDispatch:
    """A registered recoverer supplies the generated-source shape."""

    def test_registered_recoverer_supplies_the_workflow(self, tmp_path: Path) -> None:
        set_workflow_recoverer(_StubRecoverer(_stub_compiled("generated-demo")))
        run = _bare_run(tmp_path)
        assert compiled_workflow_for_run(run).name == "generated-demo"

    def test_generated_shape_wins_over_the_entrypoint(self, tmp_path: Path) -> None:
        """Dispatch order is fixed, so a run carrying both is not ambiguous."""
        set_workflow_recoverer(_StubRecoverer(_stub_compiled("generated-demo")))
        run = _bare_run(tmp_path / "ws", entrypoint=_script_entrypoint(tmp_path))
        assert compiled_workflow_for_run(run).name == "generated-demo"

    def test_recoverer_declining_falls_through_to_the_entrypoint(self, tmp_path: Path) -> None:
        set_workflow_recoverer(_StubRecoverer(None))
        run = _bare_run(tmp_path / "ws", entrypoint=_script_entrypoint(tmp_path))
        assert compiled_workflow_for_run(run).name == "script-demo"


class TestCanRecoverWorkflow:
    """The executability precondition never compiles."""

    def test_true_via_the_recoverer_without_compiling(self, tmp_path: Path) -> None:
        recoverer = _StubRecoverer(_stub_compiled("generated-demo"))
        set_workflow_recoverer(recoverer)
        assert can_recover_workflow(_bare_run(tmp_path)) is True
        assert recoverer.recover_calls == 0

    def test_true_via_the_entrypoint(self, tmp_path: Path) -> None:
        run = _bare_run(tmp_path / "ws", entrypoint=_script_entrypoint(tmp_path))
        assert can_recover_workflow(run) is True

    def test_false_when_the_run_carries_neither_shape(self, tmp_path: Path) -> None:
        assert can_recover_workflow(_bare_run(tmp_path)) is False


class TestNeitherShape:
    def test_error_names_both_shapes_and_the_run(self, tmp_path: Path) -> None:
        run = _bare_run(tmp_path)
        with pytest.raises(WorkflowRecoveryError) as excinfo:
            compiled_workflow_for_run(run)
        message = str(excinfo.value)
        assert "workflow_entrypoint" in message
        assert "generated workflow source" in message
        assert run.id in message
