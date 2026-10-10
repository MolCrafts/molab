"""``WorkflowBindingRegistry`` — the explicit ``{experiment_id → CompiledWorkflow}`` store.

Binding flows through :class:`WorkflowBindingRegistry` (and the process-global
:data:`default_binding_registry`), not the old module-level free functions on the
workflow artifact. Pins the registry's verbs and its one validation boundary.
"""

from __future__ import annotations

import pytest

from molab.workflow import (
    CompiledWorkflow,
    Workflow,
    WorkflowBindingRegistry,
    WorkflowCompiler,
    default_binding_registry,
)
from molab.workflow.binding import WorkflowBinding


class _StubExperiment:
    def __init__(self, exp_id: str) -> None:
        self.id = exp_id


@pytest.fixture(autouse=True)
def _isolate_registry():
    default_binding_registry.clear()
    yield
    default_binding_registry.clear()


def _make_spec(name: str = "wf") -> CompiledWorkflow:
    builder = Workflow(name=name)

    @builder.task
    def noop() -> None:
        return None

    return WorkflowCompiler().compile(builder)


class TestWorkflowBindingRegistry:
    def test_unbind_returns_presence_and_clears_binding(self) -> None:
        reg = WorkflowBindingRegistry()
        spec = _make_spec("a")
        exp = _StubExperiment("e1")
        assert reg.unbind(exp) is False
        reg.bind(exp, spec)
        assert reg.unbind(exp) is True
        assert reg.is_bound(exp, spec) is False

    def test_binding_carries_workflow_digest(self) -> None:
        reg = WorkflowBindingRegistry()
        spec = _make_spec("digest")
        exp = _StubExperiment("e1")
        binding = reg.bind(exp, spec)
        assert binding.workflow_digest == spec.workflow_digest
        assert "workflow_id" not in WorkflowBinding.model_fields

    def test_bind_rejects_target_without_string_id(self) -> None:
        reg = WorkflowBindingRegistry()
        with pytest.raises(ValueError):
            reg.bind(object(), _make_spec("a"))
