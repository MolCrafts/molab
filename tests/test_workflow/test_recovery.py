"""``molab.workflow.recovery`` — reconstructing a persisted run's workflow.

One shape reaches ``compiled_workflow_for_run``: the **script experiment**
shape — ``ExperimentMetadata.workflow_entrypoint``, written once by the binding
seam in :mod:`molab.entry`. The workflow belongs to the experiment, so a run
reaches it through its parent and never carries a copy. A legacy run-level
``workflow_snapshot`` is not a recovery path.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

import molab.workflow
from molab._typing import JSONValue
from molab.workflow import (
    CompiledWorkflow,
    TaskContext,
    Workflow,
    WorkflowCompiler,
    WorkflowRecoveryError,
    can_recover_workflow,
    compiled_workflow_for_experiment,
    compiled_workflow_for_run,
    default_binding_registry,
    recovery,
)
from molab.workspace import Experiment, Workspace
from molab.workspace.run import Run

_SCRIPT_MODULE = """\
from molab.workflow import TaskContext, Workflow, WorkflowCompiler

wf = Workflow(name="script-demo")


@wf.task
async def only_task(ctx: TaskContext) -> dict:
    return {"ok": True}


workflow = WorkflowCompiler().compile(wf)
"""


def _bare_run(tmp_path: Path, *, entrypoint: str | None = None) -> Run:
    """A run whose experiment is code-bound only when *entrypoint* is given."""
    ws = Workspace(root=tmp_path, name="recover-lab")
    exp = ws.add_project("p").add_experiment("e")
    if entrypoint is not None:
        exp.bind_workflow("code", entrypoint=entrypoint)
    run = exp.add_run(params={"seed": 1})
    run.materialize()
    return run


def _write_legacy_snapshot(run: Run, entrypoint: str) -> Run:
    """Stamp a legacy ``workflow_snapshot`` onto ``run.json`` and reload the run."""
    path = Path(run.run_dir) / "run.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["workflow_snapshot"] = {"entrypoint": entrypoint}
    path.write_text(json.dumps(payload), encoding="utf-8")
    return Run.load(run.run_dir)


def _script_entrypoint(tmp_path: Path) -> str:
    wf_file = tmp_path / "user_workflow.py"
    wf_file.write_text(textwrap.dedent(_SCRIPT_MODULE), encoding="utf-8")
    return f"{wf_file}:workflow"


def _constant_add_document(task_type_c: str = "core.add") -> dict[str, JSONValue]:
    """Wire IR for constant_add. No ``workflow_id`` — the document is not an identity."""
    return {
        "name": "constant_add",
        "task_configs": [
            {
                "task_id": "a",
                "task_type": "core.constant",
                "config": {"value": 2},
                "status": "pending",
            },
            {
                "task_id": "b",
                "task_type": "core.constant",
                "config": {"value": 3},
                "status": "pending",
            },
            {
                "task_id": "c",
                "task_type": task_type_c,
                "config": {},
                "status": "pending",
            },
        ],
        "links": [
            {"source": "a", "target": "c", "mapping": {}, "status": "pending"},
            {"source": "b", "target": "c", "mapping": {}, "status": "pending"},
        ],
        "metadata": {"label": None, "description": None, "tags": [], "custom": {}},
    }


def _seed(tmp_path: Path) -> tuple[Workspace, Experiment, Run]:
    """One unbound experiment and one run. Callers bind the kind they need."""
    ws = Workspace(tmp_path / "ws", name="ws")
    exp = ws.add_project("p").add_experiment("e")
    run = exp.add_run(params={"seed": 1})
    return ws, exp, run


def _compiled_named(name: str) -> CompiledWorkflow:
    """A compiled workflow distinct from the constant_add document."""
    workflow = Workflow(name=name)

    @workflow.task
    async def only_task(ctx: TaskContext) -> dict[str, bool]:
        del ctx
        return {"ok": True}

    return WorkflowCompiler().compile(workflow)


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
        """A run-level ``workflow_snapshot`` is not a recovery path."""
        run = _bare_run(tmp_path / "ws")
        reloaded = _write_legacy_snapshot(run, f"{tmp_path / 'gone.py'}:wf")
        with pytest.raises(WorkflowRecoveryError):
            compiled_workflow_for_run(reloaded)

    def test_the_experiment_wins_over_a_legacy_run_snapshot(self, tmp_path: Path) -> None:
        """One authority: the experiment, even when a stale copy sits on the run."""
        run = _bare_run(tmp_path / "ws", entrypoint=_script_entrypoint(tmp_path))
        reloaded = _write_legacy_snapshot(run, f"{tmp_path / 'gone.py'}:wf")
        assert compiled_workflow_for_run(reloaded).name == "script-demo"


class TestCanRecoverWorkflow:
    """The executability precondition never compiles."""

    def test_true_via_the_entrypoint(self, tmp_path: Path) -> None:
        run = _bare_run(tmp_path / "ws", entrypoint=_script_entrypoint(tmp_path))
        assert can_recover_workflow(run) is True

    def test_false_when_the_run_carries_neither_shape(self, tmp_path: Path) -> None:
        assert can_recover_workflow(_bare_run(tmp_path)) is False

    def test_document_is_recoverable_only_while_the_ir_file_exists(self, tmp_path: Path) -> None:
        default_binding_registry.clear()
        _ws, exp, run = _seed(tmp_path)
        exp.bind_workflow("document", document=_constant_add_document())
        assert can_recover_workflow(run) is True
        Path(exp.experiment_dir).joinpath("workflow.ir.json").unlink()
        assert can_recover_workflow(run) is False

    def test_code_with_a_locator_is_recoverable(self, tmp_path: Path) -> None:
        default_binding_registry.clear()
        _ws, exp, run = _seed(tmp_path)
        exp.bind_workflow("code", entrypoint=_script_entrypoint(tmp_path))
        assert can_recover_workflow(run) is True

    def test_code_without_a_locator_is_not_recoverable(self, tmp_path: Path) -> None:
        default_binding_registry.clear()
        _ws, exp, run = _seed(tmp_path)
        exp.bind_workflow("code")
        assert can_recover_workflow(run) is False

    def test_kind_none_is_not_recoverable_even_with_an_entrypoint(self, tmp_path: Path) -> None:
        default_binding_registry.clear()
        _ws, exp, run = _seed(tmp_path)
        exp.metadata = exp.metadata.model_copy(
            update={"workflow_entrypoint": _script_entrypoint(tmp_path)}
        )
        exp.save()
        assert exp.workflow_kind is None
        assert can_recover_workflow(run) is False

    def test_code_memo_hit_without_a_locator_is_not_recoverable(self, tmp_path: Path) -> None:
        default_binding_registry.clear()
        _ws, exp, run = _seed(tmp_path)
        exp.bind_workflow("code")
        default_binding_registry.bind(exp, _compiled_named("memo-x"))
        assert can_recover_workflow(run) is False

    def test_code_locator_is_not_imported(self, tmp_path: Path) -> None:
        default_binding_registry.clear()
        _ws, exp, run = _seed(tmp_path)
        body = tmp_path / "explode.py"
        body.write_text('raise RuntimeError("imported")\n', encoding="utf-8")
        exp.bind_workflow("code", entrypoint=f"{body}:wf")
        assert can_recover_workflow(run) is True


class TestNeitherShape:
    def test_error_names_the_entrypoint_and_the_run(self, tmp_path: Path) -> None:
        default_binding_registry.clear()
        _ws, _exp, run = _seed(tmp_path)
        with pytest.raises(WorkflowRecoveryError) as excinfo:
            compiled_workflow_for_run(run)
        message = str(excinfo.value)
        assert "molab migrate workflow-kind" in message
        assert run.id in message
        assert "molab plan" not in message


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
            "compiled_workflow_for_experiment",
            "compiled_workflow_for_run",
        }


class TestKindDispatch:
    """``workflow_kind`` selects memo, locator, or the document. The snapshot does not."""

    def test_code_without_locator_returns_the_memo(self, tmp_path: Path) -> None:
        default_binding_registry.clear()
        _ws, exp, run = _seed(tmp_path)
        exp.bind_workflow("code")
        compiled = _compiled_named("memo-x")
        default_binding_registry.bind(exp, compiled)
        assert compiled_workflow_for_run(run) is compiled

    def test_unbound_experiment_returns_the_memo(self, tmp_path: Path) -> None:
        default_binding_registry.clear()
        _ws, exp, run = _seed(tmp_path)
        assert exp.workflow_kind is None
        compiled = _compiled_named("memo-x")
        default_binding_registry.bind(exp, compiled)
        assert compiled_workflow_for_run(run) is compiled

    def test_document_ignores_a_different_memo(self, tmp_path: Path) -> None:
        default_binding_registry.clear()
        _ws, exp, run = _seed(tmp_path)
        exp.bind_workflow("document", document=_constant_add_document())
        memo = _compiled_named("memo-x")
        default_binding_registry.bind(exp, memo)
        resolved = compiled_workflow_for_run(run)
        assert resolved is not memo
        assert set(resolved.registration_by_name) == {"a", "b", "c"}

    def test_code_file_locator_resolves_a_workflow_object(self, tmp_path: Path) -> None:
        default_binding_registry.clear()
        script = tmp_path / "script_demo.py"
        script.write_text(
            'from molab.workflow import Workflow\n\nwf = Workflow(name="script-demo")\n',
            encoding="utf-8",
        )
        _ws, exp, run = _seed(tmp_path)
        exp.bind_workflow("code", entrypoint=f"{script}:wf")
        assert compiled_workflow_for_run(run).name == "script-demo"

    def test_code_package_locator_resolves_build_workflow(self, tmp_path: Path) -> None:
        default_binding_registry.clear()
        package = tmp_path / "pkgA" / "workflow"
        package.mkdir(parents=True)
        (package / "step.py").write_text('NAME = "wf-one"\n', encoding="utf-8")
        (package / "__init__.py").write_text(
            "from workflow.step import NAME\n"
            "\n"
            "from molab.workflow import Workflow\n"
            "\n"
            "def build_workflow():\n"
            "    return Workflow(name=NAME)\n",
            encoding="utf-8",
        )
        _ws, exp, run = _seed(tmp_path)
        exp.bind_workflow("code", entrypoint=f"{tmp_path}/pkgA/workflow:build_workflow")
        assert compiled_workflow_for_run(run).name == "wf-one"

    def test_code_without_locator_or_memo_asks_to_re_run(self, tmp_path: Path) -> None:
        default_binding_registry.clear()
        _ws, exp, run = _seed(tmp_path)
        exp.bind_workflow("code")
        with pytest.raises(WorkflowRecoveryError, match="re-run"):
            compiled_workflow_for_run(run)

    def test_document_registers_constant_add_tasks(self, tmp_path: Path) -> None:
        default_binding_registry.clear()
        _ws, exp, run = _seed(tmp_path)
        exp.bind_workflow("document", document=_constant_add_document())
        resolved = compiled_workflow_for_run(run)
        assert set(resolved.registration_by_name) == {"a", "b", "c"}

    def test_document_unknown_task_type_raises(self, tmp_path: Path) -> None:
        default_binding_registry.clear()
        _ws, exp, run = _seed(tmp_path)
        exp.bind_workflow("document", document=_constant_add_document(task_type_c="nope.missing"))
        with pytest.raises(WorkflowRecoveryError):
            compiled_workflow_for_run(run)

    def test_unbound_run_ignores_a_legacy_workflow_snapshot(self, tmp_path: Path) -> None:
        default_binding_registry.clear()
        _ws, _exp, run = _seed(tmp_path)
        path = Path(run.run_dir) / "run.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["workflow_snapshot"] = {"entrypoint": f"{tmp_path / 'gone.py'}:wf"}
        path.write_text(json.dumps(payload), encoding="utf-8")
        reloaded = Run.load(run.run_dir)
        default_binding_registry.clear()
        with pytest.raises(WorkflowRecoveryError):
            compiled_workflow_for_run(reloaded)

    def test_resolving_a_document_does_not_touch_the_experiment(self, tmp_path: Path) -> None:
        default_binding_registry.clear()
        _ws, exp, run = _seed(tmp_path)
        exp.bind_workflow("document", document=_constant_add_document())
        experiment_json = Path(exp.experiment_dir) / "experiment.json"
        before = experiment_json.read_bytes()
        revision_id = exp.metadata.revision_id
        revision = exp.metadata.revision
        compiled_workflow_for_run(run)
        assert experiment_json.read_bytes() == before
        assert exp.metadata.revision_id == revision_id
        assert exp.metadata.revision == revision


class TestUnmigratedExperiment:
    """Kind stays ``None`` even when a legacy entrypoint is sitting on the metadata."""

    def test_error_names_migrate_workflow_kind(self, tmp_path: Path) -> None:
        default_binding_registry.clear()
        ws, exp, run = _seed(tmp_path)
        assert exp.workflow_kind is None
        exp.metadata = exp.metadata.model_copy(
            update={"workflow_entrypoint": _script_entrypoint(tmp_path)}
        )
        exp.save()
        assert exp.workflow_kind is None
        default_binding_registry.clear()
        with pytest.raises(WorkflowRecoveryError) as excinfo:
            compiled_workflow_for_run(run)
        message = str(excinfo.value)
        assert "molab migrate workflow-kind" in message
        assert "workflow_kind" in message
        assert run.id in message
        assert str(ws.root) in message
        assert "molab plan" not in message

    def test_can_recover_workflow_is_false(self, tmp_path: Path) -> None:
        default_binding_registry.clear()
        _ws, exp, run = _seed(tmp_path)
        exp.metadata = exp.metadata.model_copy(
            update={"workflow_entrypoint": _script_entrypoint(tmp_path)}
        )
        exp.save()
        assert exp.workflow_kind is None
        default_binding_registry.clear()
        assert can_recover_workflow(run) is False


class TestCompiledWorkflowForExperiment:
    def test_document_experiment_returns_constant_add(self, tmp_path: Path) -> None:
        default_binding_registry.clear()
        _ws, exp, _run = _seed(tmp_path)
        exp.bind_workflow("document", document=_constant_add_document())
        resolved = compiled_workflow_for_experiment(exp)
        assert set(resolved.registration_by_name) == {"a", "b", "c"}

    def test_unbound_memo_cleared_says_no_workflow_bound(self, tmp_path: Path) -> None:
        default_binding_registry.clear()
        _ws, exp, _run = _seed(tmp_path)
        assert exp.workflow_kind is None
        with pytest.raises(WorkflowRecoveryError) as excinfo:
            compiled_workflow_for_experiment(exp)
        assert str(excinfo.value).startswith("no workflow bound")
