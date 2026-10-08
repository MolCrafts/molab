"""Layer firewall for ``molab.knowledge``.

``molab.knowledge`` is a peer of ``molab.workspace`` and depends on it (the
write verbs take a workspace host), but that dependency must be **lazy**:
``molab/__init__.py`` eagerly loads ``molab.workspace``, so a module-level
back-import would make ``import molab.knowledge`` a cycle. The rule this scan
enforces is therefore scope-aware:

- ``molab.workspace`` (and its submodules) may be imported **inside a function
  body** or inside an ``if TYPE_CHECKING:`` block (a block that never executes —
  it exists so the migrated ``host: Folder`` / ``run: Run`` annotations stay
  type-checkable). A module-level runtime import — the module top level, a class
  body, or a module-level ``if`` / ``try`` whose test is not ``TYPE_CHECKING`` —
  is red.
- ``molab.workflow`` / ``molab.server`` / ``molab.cli`` /
  ``molab.services`` / ``molab.plugins`` / ``molab.sweep`` stay **absolutely**
  banned at any depth.

This is an **AST static scan** of the package source — not a runtime
``sys.modules`` probe. A runtime probe is unsatisfiable: importing any
``molab.X`` submodule first runs the eager ``molab/__init__.py``, which loads
workspace. Mirrors ``tests/test_workspace/test_import_guard.py``.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE_ROOT = REPO_ROOT / "src" / "molab" / "knowledge"

#: Banned at any depth, module scope or function body alike.
ABSOLUTE_BANS: tuple[str, ...] = (
    "molab.workflow",
    "molab.server",
    "molab.cli",
    "molab.services",
    "molab.plugins",
    "molab.sweep",
)

#: Allowed only inside a function body or an ``if TYPE_CHECKING:`` block.
WORKSPACE_PREFIX = "molab.workspace"


def _is_type_checking_test(test: ast.expr) -> bool:
    """Whether *test* is the ``TYPE_CHECKING`` flag (bare or ``typing.``-qualified)."""
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    return isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"


def _legal_ranges(tree: ast.Module) -> list[tuple[int, int]]:
    """Line ranges an import may sit in: function bodies and TYPE_CHECKING blocks."""
    ranges: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        callable_body = isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda)
        type_only = isinstance(node, ast.If) and _is_type_checking_test(node.test)
        if callable_body or type_only:
            ranges.append((node.lineno, node.end_lineno or node.lineno))
    return ranges


def _imports(tree: ast.Module) -> list[tuple[int, str]]:
    """Every ``(lineno, module)`` imported by *tree* (import + from-import)."""
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [(node.lineno, alias.name) for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append((node.lineno, node.module))
    return found


def _workspace_offenders(source: str) -> list[tuple[int, str]]:
    """``molab.workspace`` imports on a module-level runtime path."""
    tree = ast.parse(source)
    legal = _legal_ranges(tree)
    return [
        (lineno, module)
        for lineno, module in _imports(tree)
        if module.startswith(WORKSPACE_PREFIX)
        and not any(start <= lineno <= end for start, end in legal)
    ]


def _absolute_offenders(source: str) -> list[tuple[int, str]]:
    """Imports of a layer :mod:`molab.knowledge` may never touch, at any depth."""
    return [
        (lineno, module)
        for lineno, module in _imports(ast.parse(source))
        if module.startswith(ABSOLUTE_BANS)
    ]


def _package_sources() -> list[Path]:
    return [py for py in sorted(KNOWLEDGE_ROOT.rglob("*.py")) if "__pycache__" not in py.parts]


def test_knowledge_source_has_no_module_level_workspace_import() -> None:
    hits: list[tuple[str, int, str]] = []
    for py in _package_sources():
        for lineno, module in _workspace_offenders(py.read_text(encoding="utf-8")):
            hits.append((py.name, lineno, module))
    assert hits == [], f"module-level molab.workspace imports in molab.knowledge: {hits}"


def test_knowledge_source_imports_no_absolutely_banned_layer() -> None:
    hits: list[tuple[str, int, str]] = []
    for py in _package_sources():
        for lineno, module in _absolute_offenders(py.read_text(encoding="utf-8")):
            hits.append((py.name, lineno, module))
    assert hits == [], f"forbidden imports in molab.knowledge: {hits}"


_MODULE_LEVEL_IMPORT = "from molab.workspace.base import atomic_write_json"
_IN_FUNCTION = f"def f():\n    {_MODULE_LEVEL_IMPORT}\n"
_IN_TYPE_CHECKING = (
    f"from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    {_MODULE_LEVEL_IMPORT}\n"
)
_IN_PLAIN_IF = f"if True:\n    {_MODULE_LEVEL_IMPORT}\n"


def test_a_module_level_workspace_import_is_caught() -> None:
    # Negative control: the scanner must catch a module-level runtime import.
    assert _workspace_offenders(_MODULE_LEVEL_IMPORT) == [(1, "molab.workspace.base")]


def test_a_function_body_workspace_import_is_accepted() -> None:
    assert _workspace_offenders(_IN_FUNCTION) == []


def test_a_type_checking_block_workspace_import_is_accepted() -> None:
    assert _workspace_offenders(_IN_TYPE_CHECKING) == []


def test_a_plain_module_level_if_is_still_caught() -> None:
    # Only a TYPE_CHECKING test opens the exemption -- a runtime `if` does not.
    assert _workspace_offenders(_IN_PLAIN_IF) == [(2, "molab.workspace.base")]


def test_a_class_body_workspace_import_is_still_caught() -> None:
    assert _workspace_offenders(f"class C:\n    {_MODULE_LEVEL_IMPORT}\n") == [
        (2, "molab.workspace.base")
    ]


def test_the_absolute_ban_is_caught_at_any_depth() -> None:
    assert _absolute_offenders("import molab.workflow.compiler") == [(1, "molab.workflow.compiler")]
    assert _absolute_offenders("def f():\n    import molab.server.app\n") == [
        (2, "molab.server.app")
    ]


def _run_python(code: str) -> subprocess.CompletedProcess[str]:
    """Run *code* in a fresh interpreter (its own module graph)."""
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )


def test_a_fresh_interpreter_imports_molab_knowledge() -> None:
    result = _run_python("import molab.knowledge")

    assert result.returncode == 0, result.stderr


def test_a_fresh_interpreter_imports_each_new_submodule() -> None:
    result = _run_python(
        "import molab.knowledge.write, molab.knowledge.harvest, "
        "molab.knowledge.embed, molab.knowledge.search"
    )

    assert result.returncode == 0, result.stderr
