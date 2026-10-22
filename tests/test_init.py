"""``molab/__init__`` — the composition root wires the run-executor seam lazily.

``import molab`` registers ``_LazyRunExecutor`` on the workspace seam without
loading ``molab.workflow``; the first ``execute`` / ``aexecute`` /
``read_outputs`` call imports the workflow layer's public factory
``molab.workflow.execute.workspace_run_executor`` and delegates to it.
"""

from __future__ import annotations

import asyncio
import inspect
import subprocess
import sys
from pathlib import Path

import molab
from molab.workspace.run import RunWorkflowExecutor


def _run_code(code: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)


class _FakeExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    def execute(
        self,
        run,
        workflow,
        *,
        resume=False,
        rerun=False,
        fresh=False,
        checkpoint=None,
        execution_id=None,
    ):
        self.calls.append(
            ("execute", run, workflow, resume, rerun, fresh, checkpoint, execution_id)
        )
        return "sync"

    async def aexecute(
        self,
        run,
        workflow,
        *,
        resume=False,
        rerun=False,
        fresh=False,
        checkpoint=None,
        execution_id=None,
    ):
        self.calls.append(
            ("aexecute", run, workflow, resume, rerun, fresh, checkpoint, execution_id)
        )
        return "async"

    def read_outputs(self, run, execution_id):
        self.calls.append(("read_outputs", run, execution_id))
        return {"train": 1}


class TestLazyRunExecutor:
    def test_import_molab_wires_seam_without_loading_workflow(self) -> None:
        result = _run_code(
            "import sys, molab\n"
            "from molab.workspace.run import require_run_executor\n"
            "assert type(require_run_executor()).__name__ == '_LazyRunExecutor', "
            "type(require_run_executor())\n"
            "assert 'molab.workflow' not in sys.modules\n"
        )
        assert result.returncode == 0, result.stderr or result.stdout

    def test_loads_once_and_delegates_read_outputs(self) -> None:
        fake = _FakeExecutor()
        calls: list[int] = []
        proxy = molab._LazyRunExecutor(load=lambda: calls.append(1) or fake)
        run = object()

        assert proxy.read_outputs(run, "e01") == {"train": 1}  # type: ignore[arg-type]
        assert proxy.read_outputs(run, "e01") == {"train": 1}  # type: ignore[arg-type]

        assert len(calls) == 1
        assert fake.calls == [("read_outputs", run, "e01"), ("read_outputs", run, "e01")]

    def test_delegates_execute_and_aexecute_kwargs(self) -> None:
        fake = _FakeExecutor()
        proxy = molab._LazyRunExecutor(load=lambda: fake)
        run, wf = object(), object()

        assert proxy.execute(run, wf, rerun=True, fresh=True) == "sync"  # type: ignore[arg-type]
        assert asyncio.run(proxy.aexecute(run, None, resume=True)) == "async"  # type: ignore[arg-type]

        assert fake.calls == [
            ("execute", run, wf, False, True, True, None, None),
            ("aexecute", run, None, True, False, False, None, None),
        ]

    def test_default_loader_imports_workflow_on_first_call(self, tmp_path: Path) -> None:
        result = _run_code(
            "import sys, molab\n"
            "from molab.workspace.run import require_run_executor\n"
            f"ws = molab.Workspace({str(tmp_path / 'ws')!r}, name='lab')\n"
            "run = ws.add_project('p').add_experiment('e').add_run(params={'x': 1})\n"
            "assert 'molab.workflow' not in sys.modules\n"
            "assert require_run_executor().read_outputs(run, 'e01') == {}\n"
            "assert 'molab.workflow' in sys.modules\n"
        )
        assert result.returncode == 0, result.stderr or result.stdout

    def test_proxy_mirrors_protocol_signatures(self) -> None:
        members = ("execute", "aexecute", "read_outputs")
        for name in members:
            assert inspect.signature(getattr(molab._LazyRunExecutor, name)) == inspect.signature(
                getattr(RunWorkflowExecutor, name)
            ), name
        protocol_public = {
            name
            for name, value in vars(RunWorkflowExecutor).items()
            if not name.startswith("_") and callable(value)
        }
        assert protocol_public == set(members)
        assert protocol_public <= set(dir(molab._LazyRunExecutor))

    def test_root_does_not_name_private_workflow_class(self) -> None:
        assert "_WorkspaceRunExecutor" not in Path(molab.__file__).read_text(encoding="utf-8")

    def test_proxy_not_exported(self) -> None:
        assert "_LazyRunExecutor" not in molab.__all__
