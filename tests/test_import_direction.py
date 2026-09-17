"""Direction guard: molab never imports the harness.

The harness is a *consumer* of molab, not a layer inside it. It happens to
ship in the same wheel today, but the dependency arrow points one way:

    harness ──> molab (workspace / workflow / knowledge / services / server / cli)

so molab core must contain **no** import of ``molab.harness`` — not at
module level, not in a function body, not under ``TYPE_CHECKING``. The harness
reattaches through public entry-point seams instead
(:mod:`molab.plugins.cli` / :mod:`molab.plugins.server` /
:mod:`molab.plugins.ui`), which is why extracting it later is a file move
rather than an architecture change.

This is an **AST source scan**, not a ``sys.modules`` probe: importing
``molab.cli`` legitimately loads the harness *through the entry point*, so a
runtime probe cannot tell a seam from a violation. The import statements can.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "molab"
HARNESS = SRC / "harness"

#: Everything the harness owns. molab core may not name any of it.
FORBIDDEN_PREFIXES: tuple[str, ...] = ("molab.harness",)


def _core_sources() -> list[Path]:
    """Every molab source file that is NOT part of the harness subtree."""
    return [p for p in sorted(SRC.rglob("*.py")) if HARNESS not in p.parents and p != HARNESS]


def _imports_with_prefix(prefix: str, root: Path) -> list[tuple[Path, int, str]]:
    """Every ``import``/``from`` statement naming *prefix*, anywhere in *root*."""
    hits: list[tuple[Path, int, str]] = []
    for path in sorted(root.rglob("*.py")):
        if HARNESS in path.parents:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module == prefix or module.startswith(f"{prefix}."):
                    hits.append((path, node.lineno, module))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == prefix or alias.name.startswith(f"{prefix}."):
                        hits.append((path, node.lineno, alias.name))
    return hits


class TestMolabNeverImportsHarness:
    def test_core_sources_exist(self) -> None:
        """Guard the guard: a mistyped root would make every assertion vacuous."""
        assert HARNESS.is_dir(), HARNESS
        assert len(_core_sources()) > 100

    def test_no_core_module_imports_the_harness(self) -> None:
        offenders: list[str] = []
        for prefix in FORBIDDEN_PREFIXES:
            offenders += [
                f"{path.relative_to(SRC)}:{lineno}: {module}"
                for path, lineno, module in _imports_with_prefix(prefix, SRC)
            ]
        assert not offenders, (
            "molab must not import the harness — the harness depends on "
            "molab, never the reverse. Reattach through the entry-point "
            "seams (molab.plugins.cli / .server / .ui) or an inversion seam "
            "such as molab.workflow.set_workflow_recoverer.\nOffenders:\n  "
            + "\n  ".join(offenders)
        )

    def test_the_scan_catches_a_planted_violation(self, tmp_path: Path) -> None:
        """Negative test: an import hidden in a function body must be caught."""
        planted = tmp_path / "molab" / "leak.py"
        planted.parent.mkdir()
        planted.write_text(
            "def f():\n    from molab.harness import Plan\n    return Plan\n",
            encoding="utf-8",
        )
        hits = _imports_with_prefix("molab.harness", tmp_path)
        assert [module for _p, _l, module in hits] == ["molab.harness"]


class TestMolabStaysLightWithoutTheHarness:
    def test_import_molab_loads_neither_the_harness_nor_an_llm_sdk(self) -> None:
        """``import molab`` is the library path — it boots no agent stack.

        Run in a fresh subprocess: another test in this session may already
        have imported the harness, and a stale ``sys.modules`` would make the
        assertion pass for the wrong reason.
        """
        probe = (
            "import sys, molab\n"
            "leaked = [m for m in ('molab.harness', 'pydantic_ai', 'pydantic_graph')\n"
            "          if m in sys.modules]\n"
            "assert not leaked, f'import molab pulled {leaked}'\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", probe], capture_output=True, text=True, check=False
        )
        assert result.returncode == 0, result.stderr


class TestMolabWorksWithoutTheHarness:
    """Removing the harness must not remove molab capability.

    These run in a subprocess with ``molab.harness`` blocked at import, which
    is stricter than merely not discovering its entry points: it catches a
    lazy ``import molab.harness`` hidden in a function body on a molab code
    path.
    """

    @staticmethod
    def _run_with_harness_blocked(body: str) -> subprocess.CompletedProcess[str]:
        # ``find_spec`` — the legacy ``find_module`` hook was removed in 3.12,
        # so a blocker written against it silently blocks nothing and every
        # assertion below passes for the wrong reason.
        probe = (
            "import sys\n"
            "class _Block:\n"
            "    def find_spec(self, name, path=None, target=None):\n"
            "        if name == 'molab.harness' or name.startswith('molab.harness.'):\n"
            "            raise ImportError('harness is not installed')\n"
            "        return None\n"
            "sys.meta_path.insert(0, _Block())\n"
        ) + body
        return subprocess.run(
            [sys.executable, "-c", probe], capture_output=True, text=True, check=False
        )

    def test_the_metrics_writer_is_wired_without_a_plugin_host(self) -> None:
        """``molab run`` produces its mlp WAL with no harness in the process.

        The run path used to build a harness ``Host`` just to mount
        ``MetricsPlugin``; the factory is registered by ``import molab``
        itself, so dropping the host changed nothing. This asserts that.
        """
        result = self._run_with_harness_blocked(
            "import molab\n"
            "from molab.workspace.metrics_seam import get_metrics_writer_factory\n"
            "assert get_metrics_writer_factory() is not None, 'metrics seam unwired'\n"
        )
        assert result.returncode == 0, result.stderr

    def test_the_cli_still_carries_molabs_own_verbs(self) -> None:
        result = self._run_with_harness_blocked(
            "from typer.main import get_command\n"
            "from molab.cli import app\n"
            "names = set(get_command(app).commands)\n"
            "missing = {'run', 'serve', 'init', 'runs', 'project', 'experiment'} - names\n"
            "assert not missing, f'molab lost its own verbs: {missing}'\n"
            "leaked = {'plan', 'agent', 'curate', 'harness'} & names\n"
            "assert not leaked, f'harness verbs present without the harness: {leaked}'\n"
        )
        assert result.returncode == 0, result.stderr

    def test_the_server_still_serves_molabs_own_routes(self) -> None:
        result = self._run_with_harness_blocked(
            "from molab.server.app import create_app\n"
            # FastAPI 0.141+ keeps included routers as ``_IncludedRouter``
            # (no ``.path``); OpenAPI paths are the stable surface to assert.
            "paths = set(create_app(serve_static=False).openapi()['paths'])\n"
            "missing = {'/api/workspace/info', '/api/projects'} - paths\n"
            "assert not missing, f'molab lost its own routes: {missing}'\n"
            "leaked = {p for p in paths if p.startswith(('/api/agent', '/api/approvals'))}\n"
            "assert not leaked, f'harness routes present without the harness: {leaked}'\n"
        )
        assert result.returncode == 0, result.stderr

    def test_a_script_run_executes_without_the_harness(self, tmp_path: Path) -> None:
        """The whole point: science runs when the agent product is absent."""
        script = tmp_path / "wf.py"
        script.write_text(
            "import molab as me\n"
            "from molab.workflow import Workflow, WorkflowCompiler\n"
            "wf = Workflow(name='no-harness')\n"
            "@wf.task\n"
            "async def step() -> dict:\n"
            "    return {'ok': True}\n"
            "compiled = WorkflowCompiler().compile(wf)\n"
            f"me.Workspace(r'{tmp_path / 'ws'}', name='lab').add_project('p')"
            ".add_experiment('e').define(compiled, params={'seed': [0]})\n",
            encoding="utf-8",
        )
        result = self._run_with_harness_blocked(
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


class TestTheHarnessReattachesThroughTheSeams:
    """The harness is discovered, never imported by name."""

    def test_it_registers_as_a_cli_plugin(self) -> None:
        from molab.plugins import discover_cli_plugins

        assert "harness" in {p.id for p in discover_cli_plugins()}

    def test_it_registers_as_a_server_plugin(self) -> None:
        from molab.plugins import discover_server_plugins

        assert "harness" in {p.id for p in discover_server_plugins()}

    def test_the_seams_carry_its_user_facing_surface(self) -> None:
        """A molab with the harness installed serves plan/agent/approvals."""
        from molab.server.app import create_app

        paths = set(create_app(serve_static=False).openapi()["paths"])
        assert "/api/approvals" in paths
        assert "/api/agent-tasks" in paths


class TestThePluginOwnsItsWire:
    """molab's schema package holds no model only the harness uses.

    A plugin that has to add a class to its host's schema module is not
    using a seam. The check is reachability, not naming: a model counts as
    molab's when it appears in the OpenAPI surface molab serves **without**
    any server plugin, or when molab's own Python references it.
    """

    @staticmethod
    def _core_only_openapi_schemas() -> set[str]:
        """The schema names a plugin-less molab puts on the wire."""
        import molab.plugins.server as server_plugins
        from molab.server.app import create_app

        original = server_plugins.discover_server_plugins
        server_plugins.discover_server_plugins = lambda: ()
        try:
            return set(create_app(serve_static=False).openapi()["components"]["schemas"])
        finally:
            server_plugins.discover_server_plugins = original

    def test_no_schema_in_molab_is_only_referenced_by_the_harness(self) -> None:
        import ast
        import re

        schemas = SRC / "server" / "schemas"
        defined: dict[str, str] = {}
        for module in ("responses.py", "requests.py"):
            path = schemas / module
            for node in ast.parse(path.read_text(encoding="utf-8")).body:
                if isinstance(node, ast.ClassDef):
                    defined[node.name] = module

        on_the_wire = self._core_only_openapi_schemas()
        core_text = "\n".join(
            p.read_text(encoding="utf-8")
            for p in SRC.rglob("*.py")
            if HARNESS not in p.parents and schemas not in p.parents
        )

        strays = [
            f"{module}: {name}"
            for name, module in defined.items()
            if name not in on_the_wire and not re.search(rf"\b{re.escape(name)}\b", core_text)
        ]
        assert not strays, (
            "molab/server/schemas/ defines models that plugin-less molab never "
            "serves and never references — they belong to whichever plugin uses "
            "them (see molab/harness/server/schemas.py), or they are dead.\n  "
            + "\n  ".join(sorted(strays))
        )


class TestAPluginNeverEditsItsHost:
    def test_the_harness_cli_attaches_only_to_the_app_it_is_handed(self) -> None:
        """``register(app)`` must not reach into molab's own command tree.

        Grafting a subcommand onto ``molab.cli.config_cmd.config_app`` is how
        ``molab config dump`` used to work; it is host-editing, not a seam.
        """
        import ast

        source = (HARNESS / "cli" / "__init__.py").read_text(encoding="utf-8")
        reached = [
            node.module
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("molab.cli.")
        ]
        assert not reached, (
            "the harness CLI plugin imports molab's own command modules "
            f"({reached}) — attach to the Typer app passed to register() instead"
        )

    def test_register_failures_are_not_silent_in_the_served_surface(self) -> None:
        """``register`` is exception-guarded, so assert the routes really land.

        A plugin whose ``register`` raises is skipped with a warning so one
        broken extension cannot take the API down — which means a regression
        inside it is invisible unless something checks the result.
        """
        from molab.server.app import create_app

        paths = set(create_app(serve_static=False).openapi()["paths"])
        missing = {
            "/api/agent-tasks",
            "/api/agent/provider",
            "/api/approvals",
            "/api/plans",
            "/api/workspace/curate",
        } - paths
        assert not missing, f"harness routes silently absent: {sorted(missing)}"
