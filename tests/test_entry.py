"""Tests for entry point registry."""

from pathlib import Path

import pytest

from molab.entry import _registry, clear_registry, entry, load_workspaces
from molab.workspace import Workspace
from molab.workspace.workspace import set_cli_root_override


@pytest.fixture(autouse=True)
def clean_registry():
    clear_registry()
    yield
    clear_registry()


class TestEntry:
    def test_entry_populates_registry(self, tmp_path):
        ws = Workspace(tmp_path / "ws", name="ws")
        entry(ws)
        assert len(_registry) == 1
        assert _registry[0] is ws

    def test_two_workspace_objects_on_one_root_register_once(self, tmp_path):
        first = Workspace(tmp_path / "ws", name="ws")
        second = Workspace(tmp_path / "ws", name="ws")

        entry(first)
        entry(second)

        assert len(_registry) == 1
        assert _registry[0] is first


class TestLoadWorkspaces:
    def test_load_from_script(self, tmp_path):
        ws_path = tmp_path / "ws"
        script = tmp_path / "test_script.py"
        script.write_text(
            "from molab.workspace import Workspace\n"
            "from molab.entry import entry\n"
            f"ws = Workspace({str(ws_path)!r}, name='from-script')\n"
            "entry(ws)\n"
        )
        workspaces = load_workspaces(script)
        assert len(workspaces) == 1
        assert workspaces[0].name == "from-script"


@pytest.fixture
def restore_cli_root_override():
    """Guarantee the module-global override is cleared after the test.

    The override is process-global state in ``molab.workspace.workspace``;
    leaking a non-``None`` value would silently rewrite the root of every
    ``Workspace(...)`` constructed in later tests.
    """
    set_cli_root_override(None)
    try:
        yield
    finally:
        set_cli_root_override(None)


class TestInferWorkspaceRoot:
    """ac-001 / ac-002 — the pure path helper."""

    def test_empty_path_raises_value_error(self):
        # ac-002: fail fast on a falsy / unresolvable path, no silent default.
        from molab.entry import infer_workspace_root

        with pytest.raises(ValueError):
            infer_workspace_root(Path())


class TestWorkspaceRootInference:
    """ac-003 / ac-004 / ac-005 — the constructor boundary."""

    def test_rootless_workspace_uses_cli_override(self, tmp_path, restore_cli_root_override):
        # ac-003: Workspace(name=...) with no root resolves to the override.
        override_dir = tmp_path / "override"
        override_dir.mkdir()
        set_cli_root_override(override_dir)

        ws = Workspace(name="x")

        assert ws.root == override_dir.resolve()

    def test_rootless_workspace_without_override_raises(self, restore_cli_root_override):
        # ac-004: no root and no active override -> clear ValueError.
        with pytest.raises(ValueError):
            Workspace(name="x")

    def test_explicit_root_unaffected_by_inference(self, tmp_path, restore_cli_root_override):
        # ac-005: explicit root resolves to that path when no override is set.
        explicit = tmp_path / "explicit"

        ws = Workspace(explicit, name="x")

        assert ws.root == explicit.resolve()


class TestFluentExperimentChain:
    """``add_project → add_experiment → define(workflow, params=...)``.

    Importing :mod:`molab.entry` registers the cross-layer ``WorkflowExecutor``
    seam, so ``Experiment.define`` works without workspace importing workflow.
    """

    @staticmethod
    def _workflow() -> object:
        from molab.workflow import Task, TaskContext, Workflow, WorkflowCompiler

        class Step(Task):
            async def execute(self, ctx: TaskContext) -> int:
                return 1

        return WorkflowCompiler().compile(Workflow(name="wf").add(Step(), name="step"))

    def test_execute_binds_workflow_and_registers_entry(self, tmp_path):
        from molab.workflow import default_binding_registry

        exp = (
            Workspace(tmp_path / "ws", name="ws")
            .add_project("p")
            .add_experiment("e")
            .define(self._workflow())
        )
        # Workflow bound (the CLI resolves it via the registry)…
        assert default_binding_registry.for_experiment(exp) is not None
        # …and the workspace registered for CLI discovery.
        assert any(w is exp.project.workspace for w in _registry)

    def test_define_then_entry_registers_the_workspace_once(self, tmp_path):
        # ``define`` already registers the workspace; a following
        # ``me.entry(ws)`` must not list it a second time (``molab run`` would
        # dispatch every run twice).
        ws = Workspace(tmp_path / "ws", name="ws")
        ws.add_project("p").add_experiment("e").define(self._workflow())

        entry(ws)

        assert [w for w in _registry if w is ws] == [ws]
        assert len(_registry) == 1

    def test_execute_without_registered_executor_fails_fast(self, tmp_path, monkeypatch):
        # The seam is required; without it execute() must not silently no-op.
        import molab.workspace.experiment as exp_mod

        monkeypatch.setattr(exp_mod, "_workflow_executor", None)
        exp = Workspace(tmp_path / "ws", name="ws").add_project("p").add_experiment("e")
        with pytest.raises(RuntimeError, match="workflow layer"):
            exp.define(self._workflow())
