"""``molab.fs`` is a layer-0 primitive: stdlib only, never molq-bound.

The filesystem seam moved to the package root so that **two** bottom layers can
share it — ``molab.workspace`` and ``molab.knowledge``. A knowledge Bundle
opened over a plain directory (a group wiki, no workspace anywhere) must not
drag an SSH transport into the process to read a ``meta.yaml``.

That is why only the Protocol (``base.py``) and the stdlib implementation
(``local.py``) live here: ``fs_remote`` / ``fs_cached`` stay in
``molab.workspace``, and ``fs_remote`` is the **sole** importer of ``molq`` in
the filesystem family.

This is an **AST source scan**, not a runtime ``sys.modules`` probe, for the
same reason ``tests/test_knowledge/test_import_guard.py`` is: importing any
``molab.X`` submodule first runs the eager ``molab/__init__.py``, which loads
workspace (and therefore molq). A runtime probe is unsatisfiable until that
eager init is made lazy — an independent change. The source law is checkable
today, and it is the law that actually matters.
"""

from __future__ import annotations

import ast
from pathlib import Path

FS_ROOT = Path(__file__).resolve().parents[2] / "src" / "molab" / "fs"

#: Nothing heavier than the stdlib may be imported by the filesystem seam.
#: ``molq`` is the transport; the business layers are all upstream of layer 0.
FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "molq",
    "molab.workspace",
    "molab.knowledge",
    "molab.workflow",
    "molab.agent",
    "molab.services",
    "molab.server",
    "molab.cli",
    "molab.plugins",
    "pydantic_graph",
)


def _imported_modules(source: str) -> list[str]:
    """Every module name imported by *source* (import + from-import)."""
    names: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def _offenders(source: str) -> list[str]:
    return [m for m in _imported_modules(source) if m.startswith(FORBIDDEN_PREFIXES)]


def test_fs_source_imports_nothing_heavier_than_stdlib() -> None:
    hits: list[tuple[str, str]] = []
    for py in sorted(FS_ROOT.rglob("*.py")):
        if "__pycache__" in py.parts:
            continue
        hits += [(py.name, mod) for mod in _offenders(py.read_text(encoding="utf-8"))]
    assert hits == [], f"forbidden imports in molab.fs: {hits}"


def test_scanner_detects_a_planted_violation() -> None:
    # Negative control: the scanner must catch the exact import it exists to ban.
    assert _offenders("from molq.transport import Transport") == ["molq.transport"]
    assert _offenders("import molab.workspace.run") == ["molab.workspace.run"]


def test_remote_filesystems_stay_out_of_layer_zero() -> None:
    # The split is what keeps molq out: if fs_remote ever moves here, the
    # scan above would start failing — this states the intent directly.
    assert not (FS_ROOT / "remote.py").exists()
    assert not (FS_ROOT / "cached.py").exists()
