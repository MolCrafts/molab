"""Workflow layering invariant guard (rectification spec — Phase 0 / P0-05).

After rectification, ``src/molab/workflow/`` may import from
``molab.workspace.*`` (workspace is the storage primitive workflow
sits on top of) but must NOT import from any other upstream-or-sibling
layer:

- ``molab.plugins`` (optional capabilities)
- ``molab.server``, ``molab.cli``, ``molab.sweep`` (application shell)

Additionally, ``pydantic_graph`` must not be imported anywhere —
molab dropped the dependency; the engine under ``workflow/_engine/``
is molab-owned (see also ``test_engine_boundary.py`` for the
src/-wide scan).

History: until 2026-05-09 this guard *also* forbade
``molab.workspace`` imports. The rectification spec inverts that
direction; workflow now uses workspace for caching + persistence.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

WORKFLOW_ROOT = Path(__file__).resolve().parents[2] / "src" / "molab" / "workflow"

FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "molab.plugins",
    "molab.server",
    "molab.cli",
    "molab.services",
    "molab.sweep",
)


def _iter_workflow_py_files() -> list[Path]:
    return [p for p in WORKFLOW_ROOT.rglob("*.py") if "__pycache__" not in p.parts]


def _imports_of(prefix: str, root: Path) -> list[tuple[Path, int, str]]:
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
        f"{path.relative_to(WORKFLOW_ROOT)}:{lineno}: {module}" for path, lineno, module in hits
    ]


def test_workflow_forbids_upstream_and_application_layers() -> None:
    offenders: dict[str, list[str]] = {}
    for prefix in FORBIDDEN_PREFIXES:
        hits = _imports_of(prefix, WORKFLOW_ROOT)
        if hits:
            offenders[prefix] = _format(hits)
    assert not offenders, (
        "molab.workflow must not import upstream / sibling layers.\n"
        "Allowed downward: molab.workspace.*, molab._typing, molab.profile.\n"
        "Offenders:\n  "
        + "\n  ".join(f"[{prefix}] {hit}" for prefix, lines in offenders.items() for hit in lines)
    )


def test_compiled_graph_is_layer_private() -> None:
    """No layer above ``workflow`` may read ``CompiledWorkflow.graph``.

    ``.graph`` holds a layer-private ``LoweredGraph`` (live task callables);
    only the workflow runtime reads it. Layers above workflow must use the
    public codec / introspection surface, never ``compiled.graph``. This
    guards the architect's N1 note on the build+compile merge (spec
    workflow-refactor-02).
    """
    src_root = Path(__file__).resolve().parents[2] / "src" / "molab"
    upper_layers = ("server", "cli", "agent", "sweep", "plugins")
    offenders: list[str] = []
    for layer in upper_layers:
        layer_root = src_root / layer
        if not layer_root.exists():
            continue
        for py in layer_root.rglob("*.py"):
            if "__pycache__" in py.parts:
                continue
            for lineno, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
                if re.search(r"\.graph\b", line) and not line.lstrip().startswith("#"):
                    offenders.append(f"{py.relative_to(src_root)}:{lineno}: {line.strip()}")
    assert not offenders, (
        "Layers above 'workflow' must not read the layer-private "
        "CompiledWorkflow.graph; use the public codec/introspection surface.\n  "
        + "\n  ".join(offenders)
    )


#: Private members of workspace objects the workflow layer used to probe.
_WORKSPACE_PRIVATE_MEMBERS = frozenset(
    {"_execution_repository", "_get_execution_id", "_execution_id"}
)


def test_workflow_reads_no_workspace_private_members() -> None:
    """``src/molab/workflow`` reaches workspace only through public members.

    The runtime reads the attempt from ``run_context.id`` /
    ``execution_dir`` / ``based_on_execution_id`` and an attempt record from
    ``run.execution(id)``; no attribute access or ``getattr`` string may name
    the workspace's private execution plumbing.
    """
    hits: list[str] = []
    for py in _iter_workflow_py_files():
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            name = None
            if isinstance(node, ast.Attribute):
                name = node.attr
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                name = node.value
            if name in _WORKSPACE_PRIVATE_MEMBERS:
                hits.append(f"{py.relative_to(WORKFLOW_ROOT)}:{node.lineno}: {name}")
    assert not hits, "workflow probes private workspace members:\n  " + "\n  ".join(hits)
