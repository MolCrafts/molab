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

import pytest

from tests.support.boundary_scan import layout_literal_offenders

WORKFLOW_ROOT = Path(__file__).resolve().parents[2] / "src" / "molab" / "workflow"

FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "molab.plugins",
    "molab.server",
    "molab.cli",
    "molab.services",
    "molab.sweep",
    "molab.entry",
)

#: Workspace modules workflow must not import. Later guards append to this tuple.
FORBIDDEN_WORKSPACE_MODULES = ("molab.workspace.naming",)

_LAYOUT_EXACT = frozenset({"executions", "workflow.json"})
_LAYOUT_ALLOWED = frozenset({("molab.workflow._engine.persistence", "JOURNAL_NAME")})


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
                module = node.module or ""
                qualified = [module] if module else []
                qualified.extend(
                    f"{module}.{alias.name}" if module else alias.name for alias in node.names
                )
                for name in qualified:
                    if name == prefix or name.startswith(prefix + "."):
                        hits.append((py, node.lineno, name))
                        break
    return hits


def _format(hits: list[tuple[Path, int, str]]) -> list[str]:
    return [
        f"{path.relative_to(WORKFLOW_ROOT)}:{lineno}: {module}" for path, lineno, module in hits
    ]


def _workflow_module_name(path: Path) -> str:
    parts = list(path.relative_to(WORKFLOW_ROOT).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(["molab", "workflow", *parts])


def test_workflow_imports_no_workspace_naming() -> None:
    offenders: dict[str, list[str]] = {}
    for prefix in FORBIDDEN_WORKSPACE_MODULES:
        hits = _imports_of(prefix, WORKFLOW_ROOT)
        if hits:
            offenders[prefix] = _format(hits)
    assert not offenders, (
        "molab.workflow must not import molab.workspace.naming; "
        "the workspace hands it directories.\n"
        "Offenders:\n  "
        + "\n  ".join(f"[{prefix}] {hit}" for prefix, lines in offenders.items() for hit in lines)
    )


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
    ``execution_dir`` / ``predecessor`` and an attempt record from
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


#: Planted sources and the hard-coded offender lists the layout detector must return.
_PLANTED_LAYOUT_SOURCES: list[tuple[str, str, list[tuple[int, str]]]] = [
    ('Path(d) / "executions" / eid\n', "molab.workflow.x", [(1, "executions")]),
    (
        'f"{d}/executions/{eid}/traceback.txt"\n',
        "molab.workflow.x",
        [(1, "executions")],
    ),
    ('x = "executions"\n', "molab.workflow.x", [(1, "executions")]),
    ('"""see executions/e01"""\n', "molab.workflow.x", []),
    ('JOURNAL_NAME = "workflow.json"\n', "molab.workflow._engine.persistence", []),
    ('JOURNAL_NAME = "workflow.json"\n', "molab.workflow.x", [(1, "workflow.json")]),
    ('"coalesced workflow.json flush failed for "\n', "molab.workflow.x", []),
]


class TestWorkflowComposesNoExecutionsPath:
    """Workflow never composes ``executions/`` or ``workflow.json`` itself.

    The journal file name lives only in ``JOURNAL_NAME`` inside
    ``_engine/persistence.py``. Docstrings are prose and are not offenders.
    """

    def test_no_executions_literal(self) -> None:
        files = _iter_workflow_py_files()
        assert len(files) > 20
        persistence = WORKFLOW_ROOT / "_engine" / "persistence.py"
        tree = ast.parse(persistence.read_text(encoding="utf-8"))
        assert any(
            isinstance(stmt, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "JOURNAL_NAME"
                for target in stmt.targets
            )
            for stmt in tree.body
        )
        offenders = [
            f"{path.relative_to(WORKFLOW_ROOT)}:{lineno}: {name}"
            for path in files
            for lineno, name in layout_literal_offenders(
                path.read_text(encoding="utf-8"),
                _workflow_module_name(path),
                exact=_LAYOUT_EXACT,
                allowed=_LAYOUT_ALLOWED,
            )
        ]
        assert not offenders, "workflow composes an execution path:\n  " + "\n  ".join(offenders)

    @pytest.mark.parametrize(
        ("source", "module_name", "expected"),
        _PLANTED_LAYOUT_SOURCES,
        ids=[
            "path-join",
            "fstring",
            "bare-assignment",
            "module-docstring",
            "journal-name-allowed",
            "journal-name-other-module",
            "prose",
        ],
    )
    def test_planted_source(
        self,
        source: str,
        module_name: str,
        expected: list[tuple[int, str]],
    ) -> None:
        assert (
            layout_literal_offenders(
                source,
                module_name,
                exact=_LAYOUT_EXACT,
                allowed=_LAYOUT_ALLOWED,
            )
            == expected
        )

    def test_imports_of_counts_naming_import_forms(self, tmp_path: Path) -> None:
        (tmp_path / "direct.py").write_text(
            "from molab.workspace.naming import workspace_root\n",
            encoding="utf-8",
        )
        (tmp_path / "alias.py").write_text(
            "from molab.workspace import naming\n",
            encoding="utf-8",
        )
        hits = _imports_of("molab.workspace.naming", tmp_path)
        per_file: dict[str, int] = {}
        for path, _lineno, _module in hits:
            per_file[path.name] = per_file.get(path.name, 0) + 1
        assert per_file == {"alias.py": 1, "direct.py": 1}
