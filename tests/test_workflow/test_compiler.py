"""Tests for :meth:`molab.workflow.Workflow.compile`.

``compile()`` lowers the registrations exactly once and emits a single frozen
:class:`CompiledWorkflow` carrying the executable graph, per-task snapshots,
and (when an experiment is supplied) an experiment binding. It carries no
workflow version and no ``workflow_id``.
"""

from __future__ import annotations

import inspect

import pytest

from molab.workflow import CompiledWorkflow, Workflow
from molab.workflow._graph_decl import TaskRegistration


class _Exp:
    """Minimal experiment stand-in (duck-typed `.id`)."""

    def __init__(self, exp_id: str) -> None:
        self.id = exp_id


class TestWorkflowCompilerCompile:
    @pytest.mark.unit
    def test_emits_compiled_workflow_with_snapshots_version_and_graph(self):
        wf = Workflow(name="pipeline")

        @wf.task
        async def fetch(ctx):
            return {"a": 1}

        @wf.task(depends_on=["fetch"])
        async def train(ctx):
            return {"b": 2}

        compiled = (wf).compile()
        assert isinstance(compiled, CompiledWorkflow)
        # exactly one TaskSnapshot per registered task
        assert set(compiled.snapshots) == {"fetch", "train"}
        assert all(s.code_hash for s in compiled.snapshots.values())
        assert not hasattr(compiled, "version")
        assert not hasattr(compiled, "workflow_id")
        # a non-None executable graph — the engine's structural ExecutionPlan
        # (one node per task; values-on-edges execution, no pg lowering).
        from molab.workflow._engine.plan import ExecutionPlan

        assert isinstance(compiled.graph, ExecutionPlan)
        assert set(compiled.graph.task_names) == {"fetch", "train"}
        # no binding without an experiment
        assert compiled.binding is None

    @pytest.mark.unit
    def test_binds_to_experiment_when_given(self):
        wf = Workflow(name="b")

        @wf.task
        async def t(ctx):
            return 1

        from molab.workflow import WorkflowBindingRegistry

        reg = WorkflowBindingRegistry()
        exp = _Exp("exp-001")
        compiled = wf.compile(experiment=exp, registry=reg)
        assert reg.for_experiment(exp) is compiled
        assert compiled.binding is not None
        assert compiled.binding.experiment_id == "exp-001"
        from molab.workflow.digest import compute_workflow_hash

        assert compiled.binding.workflow_hash == compiled.workflow_hash
        assert compiled.workflow_hash == compute_workflow_hash(compiled)

    @pytest.mark.unit
    def test_compile_is_a_method_on_the_graph(self):
        wf = Workflow(name="x")

        @wf.task
        def only() -> int:
            return 1

        compiled = wf.compile()
        assert compiled.name == "x"
        assert compiled.workflow_hash.startswith("sha256:")
        import molab
        import molab.workflow as workflow

        assert "WorkflowCompiler" not in molab.__all__
        assert "WorkflowCompiler" not in workflow.__all__

    @pytest.mark.unit
    def test_run_returns_task_outputs(self):
        wf = Workflow(name="x")

        @wf.task
        def only() -> int:
            return 1

        result = wf.run()
        assert result.status == "succeeded"
        assert result.outputs["only"] == 1

    @pytest.mark.asyncio
    async def test_run_refuses_a_running_loop(self):
        wf = Workflow(name="x")

        @wf.task
        def only() -> int:
            return 1

        with pytest.raises(RuntimeError, match=r"await wf\.arun\(\)"):
            wf.run()


class TestRemoteKwargRemoved:
    """Authoring ``remote=`` is gone from ``Workflow.task`` / ``add`` / ``TaskRegistration``."""

    @pytest.mark.unit
    def test_task_and_add_omit_remote_parameter(self) -> None:
        assert "remote" not in inspect.signature(Workflow.task).parameters
        assert "remote" not in inspect.signature(Workflow.add).parameters

    @pytest.mark.unit
    def test_registration_omits_remote_slot(self) -> None:
        assert "remote" not in TaskRegistration.__slots__
        assert "remote" not in inspect.signature(TaskRegistration.__init__).parameters

    @pytest.mark.unit
    def test_task_rejects_remote_kwarg(self) -> None:
        with pytest.raises(TypeError):
            Workflow("w").task(lambda x: x, name="a", remote={"queue": "q"})

    @pytest.mark.unit
    def test_subgraph_registrations_have_no_remote(self) -> None:
        wf = Workflow(name="chain")

        @wf.task
        def a() -> int:
            return 1

        @wf.task(depends_on=["a"])
        def b(a: int) -> int:
            return a + 1

        compiled = (wf).compile()
        sub = compiled.subgraph(["b"])
        assert isinstance(sub, CompiledWorkflow)
        registrations = list(sub.registration_by_name.values())
        assert registrations
        for reg in registrations:
            assert not hasattr(reg, "remote")
