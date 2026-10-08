"""Unit tests for molab.workflow.loader.load_workflow_from_entrypoint."""

from __future__ import annotations

import importlib.util
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest

from molab.workflow import CompiledWorkflow
from molab.workflow.loader import load_workflow_from_entrypoint


def _timeout[F: Callable[..., object]](fn: F) -> F:
    if importlib.util.find_spec("pytest_timeout") is not None:
        return cast(F, pytest.mark.timeout(5)(fn))
    return fn


def _write(path: Path, source: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source)
    return path


def _task_prelude() -> str:
    return (
        "from molab.workflow import Task, Workflow\n"
        "\n"
        "class Step(Task):\n"
        "    async def execute(self, ctx):\n"
        "        return 1\n"
        "\n"
    )


def _workflow_attribute_source(var: str, name: str) -> str:
    # ``Workflow.add`` strips a trailing ``_task``; ``@wf.task(name=)`` keeps it.
    return (
        "from molab.workflow import Workflow\n"
        "\n"
        f"{var} = Workflow(name={name!r})\n"
        "\n"
        f"@{var}.task(name='only_task')\n"
        "def only_task(ctx):\n"
        "    return 1\n"
    )


def _workflow_callable_source(fn_name: str, name: str) -> str:
    return (
        _task_prelude()
        + f"def {fn_name}():\n"
        + f"    return Workflow(name={name!r}).add(Step(), name='only_task')\n"
    )


def _write_package(root: Path, workflow_name: str, *, sleep_s: float = 0) -> Path:
    package = root / "workflow"
    package.mkdir(parents=True)
    sleep = ""
    if sleep_s:
        sleep = f"import time\ntime.sleep({sleep_s})\n"
    (package / "step.py").write_text(f"{sleep}NAME = {workflow_name!r}\n")
    (package / "__init__.py").write_text(
        "from workflow.step import NAME\n"
        "from molab.workflow import Task, Workflow\n"
        "\n"
        "class Step(Task):\n"
        "    async def execute(self, ctx):\n"
        "        return 1\n"
        "\n"
        "def build_workflow():\n"
        "    return Workflow(name=NAME).add(Step(), name='only_task')\n"
    )
    return package


class TestLoadWorkflowFromEntrypoint:
    def test_compiled_workflow_attribute_is_same_object(self, tmp_path: Path) -> None:
        identity = tmp_path / "identity.txt"
        source = (
            "from molab.workflow import Task, Workflow, WorkflowCompiler\n"
            "\n"
            "class Step(Task):\n"
            "    async def execute(self, ctx):\n"
            "        return 1\n"
            "\n"
            "wf = WorkflowCompiler().compile(\n"
            "    Workflow(name='script-demo').add(Step(), name='only_task')\n"
            ")\n"
            f"open({str(identity)!r}, 'w').write(str(id(wf)))\n"
        )
        path = _write(tmp_path / "script_demo.py", source)
        loaded = load_workflow_from_entrypoint(f"{path}:wf")
        assert isinstance(loaded, CompiledWorkflow)
        assert loaded.name == "script-demo"
        assert str(id(loaded)) == identity.read_text()

    def test_workflow_attribute_is_compiled(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path / "plain.py",
            _workflow_attribute_source("wf", "plain"),
        )
        loaded = load_workflow_from_entrypoint(f"{path}:wf")
        assert isinstance(loaded, CompiledWorkflow)
        assert set(loaded.registration_by_name) == {"only_task"}

    def test_zero_arg_callable_returning_workflow_is_compiled(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path / "builder.py",
            _workflow_callable_source("build_workflow", "from-callable"),
        )
        loaded = load_workflow_from_entrypoint(f"{path}:build_workflow")
        assert isinstance(loaded, CompiledWorkflow)
        assert loaded.name == "from-callable"

    def test_package_loads_keep_their_own_names(self, tmp_path: Path) -> None:
        pkg_a = _write_package(tmp_path / "pkgA", "wf-one")
        pkg_b = _write_package(tmp_path / "pkgB", "wf-two")
        first = load_workflow_from_entrypoint(f"{pkg_a}:build_workflow")
        second = load_workflow_from_entrypoint(f"{pkg_b}:build_workflow")
        assert isinstance(first, CompiledWorkflow)
        assert isinstance(second, CompiledWorkflow)
        assert first.name == "wf-one"
        assert second.name == "wf-two"

    def test_package_load_does_not_claim_workflow_sys_modules(self, tmp_path: Path) -> None:
        pkg = _write_package(tmp_path / "pkgA", "wf-one")
        sentinel = ModuleType("_molab_test_workflow_sentinel")
        previous = sys.modules.get("workflow")
        preexisting = {key for key in sys.modules if key.startswith("workflow.")}
        sys.modules["workflow"] = sentinel
        try:
            loaded = load_workflow_from_entrypoint(f"{pkg}:build_workflow")
            assert loaded.name == "wf-one"
            assert sys.modules["workflow"] is sentinel
            added = {key for key in sys.modules if key.startswith("workflow.")} - preexisting
            assert added == set()
        finally:
            for key in list(sys.modules):
                if key.startswith("workflow.") and key not in preexisting:
                    del sys.modules[key]
            if previous is None:
                sys.modules.pop("workflow", None)
            else:
                sys.modules["workflow"] = previous

    def test_concurrent_package_loads_stay_isolated(self, tmp_path: Path) -> None:
        pkg_a = _write_package(tmp_path / "pkgA", "wf-one", sleep_s=0.2)
        pkg_b = _write_package(tmp_path / "pkgB", "wf-two", sleep_s=0.2)
        results: dict[str, str] = {}
        errors: list[Exception] = []
        gate = threading.Lock()

        def _load(key: str, package: Path) -> None:
            try:
                loaded = load_workflow_from_entrypoint(f"{package}:build_workflow")
            except Exception as exc:
                with gate:
                    errors.append(exc)
                return
            with gate:
                results[key] = loaded.name

        workers = [
            threading.Thread(target=_load, args=("a", pkg_a)),
            threading.Thread(target=_load, args=("b", pkg_b)),
        ]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(10)
        assert all(not worker.is_alive() for worker in workers)
        assert errors == []
        assert results == {"a": "wf-one", "b": "wf-two"}

    def test_load_lock_is_held_inside_build_workflow(self, tmp_path: Path) -> None:
        flag = tmp_path / "locked.txt"
        source = (
            "from molab.workflow.loader import _LOAD_LOCK\n"
            "from molab.workflow import Workflow\n"
            "\n"
            "def build_workflow():\n"
            f"    open({str(flag)!r}, 'w').write("
            "'1' if _LOAD_LOCK.locked() else '0')\n"
            "    wf = Workflow(name='lock-check')\n"
            "\n"
            "    @wf.task(name='only_task')\n"
            "    def only_task(ctx):\n"
            "        return 1\n"
            "\n"
            "    return wf\n"
        )
        path = _write(tmp_path / "lock_check.py", source)
        loaded = load_workflow_from_entrypoint(f"{path}:build_workflow")
        assert isinstance(loaded, CompiledWorkflow)
        assert flag.read_text() == "1"

    @_timeout
    def test_nested_load_on_same_thread_raises(self, tmp_path: Path) -> None:
        inner = _write(tmp_path / "inner.py", _workflow_attribute_source("wf", "inner"))
        entry = f"{inner}:wf"
        source = (
            "from molab.workflow.loader import load_workflow_from_entrypoint\n"
            "from molab.workflow import Workflow\n"
            "\n"
            "def build_workflow():\n"
            f"    load_workflow_from_entrypoint({entry!r})\n"
            "    return Workflow(name='outer')\n"
        )
        outer = _write(tmp_path / "outer.py", source)
        errors: list[Exception] = []

        def _run() -> None:
            try:
                load_workflow_from_entrypoint(f"{outer}:build_workflow")
            except Exception as exc:
                errors.append(exc)

        worker = threading.Thread(target=_run, daemon=True)
        worker.start()
        worker.join(5)
        assert not worker.is_alive(), "nested load hung"
        assert len(errors) == 1
        assert isinstance(errors[0], RuntimeError)
        assert "nested" in str(errors[0])

    def test_dont_write_bytecode_is_restored_and_pycache_skipped(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = tmp_path / "pkgA"
        pkg = _write_package(root, "wf-one")
        monkeypatch.setattr(sys, "dont_write_bytecode", False)
        loaded = load_workflow_from_entrypoint(f"{pkg}:build_workflow")
        assert isinstance(loaded, CompiledWorkflow)
        assert sys.dont_write_bytecode is False
        assert list(root.rglob("__pycache__")) == []
        assert list(root.rglob("*.pyc")) == []

    def test_single_file_load_adds_one_private_module_key(self, tmp_path: Path) -> None:
        path = _write(tmp_path / "solo.py", _workflow_attribute_source("wf", "solo"))
        before = {key for key in sys.modules if key.startswith("_molab_wf_")}
        load_workflow_from_entrypoint(f"{path}:wf")
        added = {key for key in sys.modules if key.startswith("_molab_wf_")} - before
        assert len(added) == 1
        assert next(iter(added)).startswith("_molab_wf_")

    def test_missing_colon_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            load_workflow_from_entrypoint("not-an-entrypoint")

    def test_missing_file_raises_import_error(self, tmp_path: Path) -> None:
        missing = tmp_path / "gone.py"
        with pytest.raises(ImportError, match="Did the source move"):
            load_workflow_from_entrypoint(f"{missing}:wf")

    def test_directory_without_init_raises_import_error(self, tmp_path: Path) -> None:
        bare = tmp_path / "barepkg"
        bare.mkdir()
        with pytest.raises(ImportError):
            load_workflow_from_entrypoint(f"{bare}:build_workflow")

    def test_missing_attribute_raises_attribute_error(self, tmp_path: Path) -> None:
        path = _write(tmp_path / "mod.py", "x = 1\n")
        with pytest.raises(AttributeError):
            load_workflow_from_entrypoint(f"{path}:missing")

    def test_int_attribute_raises_type_error(self, tmp_path: Path) -> None:
        path = _write(tmp_path / "mod.py", "wf = 3\n")
        with pytest.raises(TypeError):
            load_workflow_from_entrypoint(f"{path}:wf")

    def test_callable_returning_dict_raises_type_error(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path / "mod.py",
            "def build_workflow():\n    return {'nope': True}\n",
        )
        with pytest.raises(TypeError):
            load_workflow_from_entrypoint(f"{path}:build_workflow")

    def test_main_block_does_not_run(self, tmp_path: Path) -> None:
        marker = tmp_path / "main_marker.txt"
        source = (
            "from molab.workflow import Workflow\n"
            "\n"
            "if __name__ == '__main__':\n"
            f"    open({str(marker)!r}, 'w').write('ran')\n"
            "wf = Workflow(name='not-main')\n"
            "\n"
            "@wf.task(name='only_task')\n"
            "def only_task(ctx):\n"
            "    return 1\n"
        )
        path = _write(tmp_path / "entry.py", source)
        loaded = load_workflow_from_entrypoint(f"{path}:wf")
        assert isinstance(loaded, CompiledWorkflow)
        assert loaded.name == "not-main"
        assert not marker.exists()
