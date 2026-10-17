"""molab stands alone: it boots, serves and runs science with no plugin at all.

The Python harness was deleted by D86. molab keeps the three plugin entry-point
groups (``molab.cli_plugins`` / ``molab.server_plugins`` / ``molab.ui_plugins``)
as public extension points but registers nothing in any of them itself, so the
default boot path is the zero-plugin one (D-1).

* ``TestImportMolabStaysLight`` — ``import molab`` loads no LLM SDK. It is the
  one SDK lightness guard in the repo: every ``import molab.<layer>`` runs
  ``molab/__init__`` first, so it covers the per-layer probes.
* ``TestTheHarnessIsGone`` — the package is not importable and no plugin entry
  point resolves into ``molab``.
* ``TestMolabBootsWithoutPlugins`` — with every ``molab.*`` entry-point group
  emptied, the CLI, the server and a script run still work.

Each probe runs in a fresh subprocess, so no ``sys.modules`` or discovery
cache left by another test can make it pass for the wrong reason.
"""

from __future__ import annotations

import importlib.metadata
import importlib.util
import subprocess
import sys
from pathlib import Path

#: Subprocess preamble: every ``molab.*`` entry-point group discovers nothing;
#: every other group (e.g. ``molcrafts.metric_readers``) passes through.
_EMPTY_MOLAB_GROUPS = """\
import importlib.metadata as _md

_real_entry_points = _md.entry_points


def _is_molab(group):
    return str(group or "").startswith("molab.")


class _Filtered:
    def __init__(self, inner):
        self._inner = inner

    def select(self, **params):
        if _is_molab(params.get("group")):
            return _md.EntryPoints(())
        return self._inner.select(**params)

    def __iter__(self):
        return iter(self._inner)

    def __getattr__(self, name):
        return getattr(self._inner, name)


def _entry_points(**params):
    if params:
        if _is_molab(params.get("group")):
            return _md.EntryPoints(())
        return _real_entry_points(**params)
    return _Filtered(_real_entry_points())


_md.entry_points = _entry_points
"""


def _run(probe: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=False
    )


class TestImportMolabStaysLight:
    def test_import_molab_loads_no_llm_sdk(self) -> None:
        probe = (
            "import sys, molab\n"
            "leaked = [m for m in ('pydantic_ai', 'pydantic_graph') if m in sys.modules]\n"
            "assert not leaked, f'import molab pulled {leaked}'\n"
        )
        result = _run(probe)
        assert result.returncode == 0, result.stderr


class TestTheHarnessIsGone:
    """D86: the Python harness is deleted, not merely undiscovered."""

    def test_the_package_is_not_importable(self) -> None:
        # A directory holding only ``__pycache__/`` would still import as a
        # namespace package, so this also catches an incomplete ``rm -rf``.
        assert importlib.util.find_spec("molab.harness") is None

    def test_no_plugin_entry_point_resolves_into_molab(self) -> None:
        for group in ("molab.cli_plugins", "molab.server_plugins"):
            ours = [
                ep.value
                for ep in importlib.metadata.entry_points(group=group)
                if ep.value.startswith("molab.")
            ]
            assert ours == [], f"molab still registers {group}: {ours}"


class TestMolabBootsWithoutPlugins:
    """Every ``molab.*`` entry-point group is empty; molab keeps its capability."""

    @staticmethod
    def _run_without_plugins(body: str) -> subprocess.CompletedProcess[str]:
        return _run(_EMPTY_MOLAB_GROUPS + body)

    def test_the_metrics_writer_is_wired(self) -> None:
        """The mlp WAL factory is registered by ``import molab`` itself."""
        result = self._run_without_plugins(
            "import molab\n"
            "from molab.workspace.metrics_seam import get_metrics_writer_factory\n"
            "assert get_metrics_writer_factory() is not None, 'metrics seam unwired'\n"
        )
        assert result.returncode == 0, result.stderr

    def test_the_cli_carries_molabs_own_verbs(self) -> None:
        result = self._run_without_plugins(
            "from typer.main import get_command\n"
            "from molab.cli import app\n"
            "names = set(get_command(app).commands)\n"
            "missing = {'run', 'serve', 'init', 'runs', 'project', 'experiment'} - names\n"
            "assert not missing, f'molab lost its own verbs: {missing}'\n"
            "leaked = {'plan', 'agent', 'curate', 'harness', 'mcp'} & names\n"
            "assert not leaked, f'deleted verbs still present: {leaked}'\n"
        )
        assert result.returncode == 0, result.stderr

    def test_the_server_serves_molabs_own_routes(self) -> None:
        result = self._run_without_plugins(
            "from molab.server.app import create_app\n"
            # FastAPI 0.141+ keeps included routers as ``_IncludedRouter``
            # (no ``.path``); OpenAPI paths are the stable surface to assert.
            "paths = set(create_app(serve_static=False).openapi()['paths'])\n"
            "missing = {'/api/workspace/info', '/api/projects'} - paths\n"
            "assert not missing, f'molab lost its own routes: {missing}'\n"
            "leaked = {\n"
            "    p for p in paths\n"
            "    if p.startswith(('/api/agent', '/api/approvals', '/api/plans'))\n"
            "    or '/plan-tasks' in p or 'curate' in p\n"
            "}\n"
            "assert not leaked, f'deleted routes still served: {sorted(leaked)}'\n"
        )
        assert result.returncode == 0, result.stderr

    def test_a_script_run_executes(self, tmp_path: Path) -> None:
        """The whole point: science runs with no plugin in the process."""
        script = tmp_path / "wf.py"
        script.write_text(
            "import molab as me\n"
            "from molab.workflow import Workflow, WorkflowCompiler\n"
            "wf = Workflow(name='no-plugins')\n"
            "@wf.task\n"
            "async def step() -> dict:\n"
            "    return {'ok': True}\n"
            "compiled = WorkflowCompiler().compile(wf)\n"
            f"me.Workspace(r'{tmp_path / 'ws'}', name='lab').add_project('p')"
            ".add_experiment('e').define(compiled, params={'seed': [0]})\n",
            encoding="utf-8",
        )
        result = self._run_without_plugins(
            # ``Run.execute`` is the workspace one-step API; it reaches the
            # engine through the ``set_run_executor`` inversion seam, so this
            # covers the seam as well as the engine.
            "from pathlib import Path\n"
            "from molab.entry import load_workspaces\n"
            "from molab.workflow.binding import default_binding_registry\n"
            f"ws = load_workspaces(Path(r'{script}'))[0]\n"
            "exp = ws.list_folders()[0].list_folders()[0]\n"
            "run = exp.list_runs()[0]\n"
            "run.execute(default_binding_registry.for_experiment(exp))\n"
            "summary = run.status_summary\n"
            "assert summary.by_status.get('succeeded'), summary\n"
            "print('ok', summary)\n"
        )
        assert result.returncode == 0, result.stderr
