"""Workspace boundary firewall (rectification spec — Phase 0 / P0-04).

Workspace is the bottom of the dependency DAG. The only ``molab.*``
imports allowed under ``src/molab/workspace/`` are ``molab._typing``,
``molab.profile``, ``molab.path`` (the cross-host POSIX path primitive),
the layer-0 filesystem seam (``molab.fs`` / ``molab.gitignore``, shared with
the layer above it), and the root-level helpers (``mollog``, ``molcfg``).
Every other ``molab.*`` subpackage — ``workflow``, ``agent``, ``plugins``,
``server``, ``cli``, ``sweep``, ``knowledge`` — is forbidden.

``molab.knowledge`` sits **above** workspace and reaches it only through
function-body imports; the reverse arrow does not exist. Workspace must not
name knowledge in any form — no import, no identifier, no knowledge-named
source file (the residue scan that pins that is
``tests/test_workspace/test_no_knowledge_residue.py``).

This is the mechanical enforcer of the rule documented in the
``§ Layer charters → molab.workspace`` section of CLAUDE.md.

History: until 2026-05-09 this guard allowed ``molab.workflow``
imports — that is the leak the rectification spec flushes out. The
expanded forbidden set below makes the leak in
``workspace/experiment.py:25–28`` show up as a RED test, which is the
entry ticket for Phase 1.
"""  # noqa: RUF002

from __future__ import annotations

import ast
from pathlib import Path

import pytest

WORKSPACE_ROOT = Path(__file__).resolve().parents[2] / "src" / "molab" / "workspace"

FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "molab.workflow",
    "molab.plugins",
    "molab.server",
    "molab.cli",
    "molab.services",
    "molab.sweep",
    "molab.knowledge",
)


def _files_importing(prefix: str, root: Path) -> list[tuple[Path, int, str]]:
    """Return ``(path, lineno, module)`` triples for every match.

    Matches both ``import molab.<prefix>`` and ``from molab.<prefix>
    import …`` (and any subpackage). Returns the import line so failure
    messages can quote the offender directly.
    """
    hits: list[tuple[Path, int, str]] = []
    for py in root.rglob("*.py"):
        if "__pycache__" in py.parts:
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == prefix or alias.name.startswith(prefix + "."):
                        hits.append((py, node.lineno, alias.name))
                        break
            elif isinstance(node, ast.ImportFrom):
                module = node.module
                if module and (module == prefix or module.startswith(prefix + ".")):
                    hits.append((py, node.lineno, module))
    return hits


def _format(hits: list[tuple[Path, int, str]]) -> list[str]:
    return [
        f"{path.relative_to(WORKSPACE_ROOT)}:{lineno}: {module}" for path, lineno, module in hits
    ]


def test_workspace_forbids_all_upstream_layers() -> None:
    """No imports of any forbidden upstream prefix anywhere in workspace/."""
    offenders: dict[str, list[str]] = {}
    for prefix in FORBIDDEN_PREFIXES:
        hits = _files_importing(prefix, WORKSPACE_ROOT)
        if hits:
            offenders[prefix] = _format(hits)
    assert not offenders, (
        "molab.workspace must not import any upstream layer. The "
        "dependency DAG flows downward: workspace ← workflow ← agent.\n"
        "Offenders:\n  "
        + "\n  ".join(f"[{prefix}] {hit}" for prefix, lines in offenders.items() for hit in lines)
    )


@pytest.mark.parametrize("prefix", FORBIDDEN_PREFIXES)
def test_guard_detects_violation_when_simulated(prefix: str, tmp_path: Path) -> None:
    """Negative test: the AST scan must catch a planted import of every ban.

    Parametrised over the whole deny-list, so adding a prefix without proving
    the scanner sees it cannot ship an unscanned name.
    """
    fake = tmp_path / "tainted.py"
    fake.write_text(f"from {prefix}.spec import Planted\n")
    hits = _files_importing(prefix, tmp_path)
    assert any(p == fake for p, _, _ in hits), f"guard failed to detect a planted {prefix} import"


def test_workspace_init_does_not_load_workflow_or_agent() -> None:
    """``import molab.workspace`` must not pull workflow/agent/knowledge into sys.modules.

    Equivalent invariant from CLAUDE.md: workspace is the leaf — touching
    it should never cascade an upstream module load.
    """
    import subprocess
    import sys

    code = (
        "import sys\n"
        "import molab.workspace  # noqa: F401\n"
        "assert 'molab.workflow' not in sys.modules, "
        "    'molab.workspace eagerly imported molab.workflow'\n"
        "assert 'molab.knowledge' not in sys.modules, "
        "    'molab.workspace eagerly imported molab.knowledge'\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr or result.stdout


def test_get_result_in_fresh_process_loads_workflow_lazily(tmp_path: Path) -> None:
    """A process that only imported molab reads node outputs via the lazy seam."""
    import subprocess
    import sys

    root = str(tmp_path / "ws")
    writer = (
        "import molab\n"
        "from molab.workflow import Workflow, WorkflowCompiler\n"
        "wf = Workflow(name='single')\n"
        "@wf.task\n"
        "def train() -> dict:\n"
        "    return {'loss': 0.125}\n"
        f"ws = molab.Workspace({root!r}, name='lab')\n"
        "run = ws.add_project('p').add_experiment('e').add_run(params={'x': 1})\n"
        "run.execute(WorkflowCompiler().compile(wf))\n"
    )
    result = subprocess.run([sys.executable, "-c", writer], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr or result.stdout

    reader = (
        "import sys, molab\n"
        f"ws = molab.Workspace.load({root!r})\n"
        "[run] = ws.get_project('p').get_experiment('e').list_runs()\n"
        "assert 'molab.workflow' not in sys.modules\n"
        "value = run.get_result('train', execution_id='e01')\n"
        "assert value == {'loss': 0.125}, value\n"
        "assert 'molab.workflow' in sys.modules\n"
    )
    result = subprocess.run([sys.executable, "-c", reader], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr or result.stdout
