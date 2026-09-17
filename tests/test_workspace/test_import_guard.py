"""Workspace boundary firewall (rectification spec — Phase 0 / P0-04).

Workspace is the bottom of the dependency DAG. The only ``molab.*``
imports allowed under ``src/molab/workspace/`` are ``molab._typing``,
``molab.profile``, ``molab.path`` (the cross-host POSIX path primitive),
the layer-0 filesystem seam (``molab.fs`` / ``molab.gitignore``, shared with
the ``molab.knowledge`` peer layer), ``molab.knowledge`` itself (the OKF
library workspace reconstructs typed Concepts through), and the root-level
helpers (``mollog``, ``molcfg``).
Every other ``molab.*`` subpackage — ``workflow``, ``agent``,
``plugins``, ``server``, ``cli``, ``sweep`` — is forbidden.

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

WORKSPACE_ROOT = Path(__file__).resolve().parents[2] / "src" / "molab" / "workspace"

FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "molab.workflow",
    "molab.harness",
    "molab.plugins",
    "molab.server",
    "molab.cli",
    "molab.services",
    "molab.sweep",
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


def test_guard_detects_violation_when_simulated(tmp_path: Path) -> None:
    """Negative test: the AST scan must catch a freshly-introduced import."""
    fake = tmp_path / "tainted.py"
    fake.write_text("from molab.workflow.spec import WorkflowSpec\n")
    hits = _files_importing("molab.workflow", tmp_path)
    assert any(p == fake for p, _, _ in hits), (
        "guard failed to detect a planted molab.workflow import"
    )


def test_workspace_init_does_not_load_workflow_or_agent() -> None:
    """``import molab.workspace`` must not pull workflow/agent into sys.modules.

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
        "assert 'molab.harness' not in sys.modules, "
        "    'molab.workspace eagerly imported molab.harness'\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr or result.stdout


# ── Curation subpackage allow-set ────────────────────────────────────────────
#
# ``molab.workspace.curation`` composes existing workspace primitives. As a
# member of the workspace layer it may import the cross-layer identity / path
# / profile primitives and any intra-``molab.workspace`` module — nothing
# else. This guard is RED until the package exists (the dir-existence
# assertion documents that it is not yet implemented), then it pins the
# subpackage's import surface using the same AST walk as the deny-list above.

CURATION_ROOT = WORKSPACE_ROOT / "curation"

CURATION_ALLOWED_MOLAB: frozenset[str] = frozenset(
    {"molab._typing", "molab.profile", "molab.path", "molab.ids"}
)


def _curation_import_allowed(module: str) -> bool:
    """Allow the four cross-layer primitives plus any intra-workspace module."""
    return module in CURATION_ALLOWED_MOLAB or module.startswith("molab.workspace")


def test_curation_subpackage_allowed_imports() -> None:
    """Every ``molab.*`` import under ``workspace/curation/`` is in the allow-set.

    Reuses :func:`_files_importing` with the broad ``"molab"`` prefix to
    enumerate every absolute ``molab.*`` import in the subpackage, then
    rejects any that is neither a sanctioned cross-layer primitive nor an
    intra-``molab.workspace`` import.
    """
    assert CURATION_ROOT.exists(), (
        "molab.workspace.curation is not implemented yet "
        f"(expected package directory at {CURATION_ROOT})"
    )
    offenders = [
        f"{path.relative_to(WORKSPACE_ROOT)}:{lineno}: {module}"
        for path, lineno, module in _files_importing("molab", CURATION_ROOT)
        if not _curation_import_allowed(module)
    ]
    assert not offenders, (
        "molab.workspace.curation may import only the cross-layer primitives "
        f"{sorted(CURATION_ALLOWED_MOLAB)} plus intra-workspace modules.\n"
        "Offenders:\n  " + "\n  ".join(offenders)
    )
