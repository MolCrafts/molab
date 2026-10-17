"""arch-own-04e: workflow_digest is the only workflow identity left in source."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import molab.workflow as workflow

_ROOT = Path(__file__).resolve().parents[2]
_SRC = _ROOT / "src" / "molab"
_BANNED_IDS = frozenset(
    {
        "workflow_id",
        "workflow_version",
        "workflow_snapshot",
        "WorkflowVersion",
        "TaskTopologyEntry",
        "WorkflowVersionConflictError",
        "_stable_workflow_id",
    }
)
_WORD = re.compile(r"\bworkflow_id\b|\bworkflow_version\b")


def _docstrings(tree: ast.AST) -> set[ast.AST]:
    found: set[ast.AST] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                found.add(body[0].value)
    return found


class _Scan(ast.NodeVisitor):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.stack: list[str] = []
        self.hits: list[str] = []
        self.snapshot_keys: list[str] = []
        self.docs: set[ast.AST] = set()

    def _flag(self, lineno: int, kind: str, name: str | None) -> None:
        if name in _BANNED_IDS:
            self.hits.append(f"{self.path}:{lineno}:{kind} {name}")

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._flag(node.lineno, "def", node.name)
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._flag(node.lineno, "class", node.name)
        self.generic_visit(node)

    def visit_arg(self, node: ast.arg) -> None:
        self._flag(node.lineno, "arg", node.arg)
        self.generic_visit(node)

    def visit_keyword(self, node: ast.keyword) -> None:
        self._flag(node.lineno, "keyword", node.arg)
        self.generic_visit(node)

    def visit_alias(self, node: ast.alias) -> None:
        for name in (node.name, node.asname):
            leaf = name.rsplit(".", 1)[-1] if name else None
            self._flag(node.lineno, "import", leaf)
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        self._flag(node.lineno, "name", node.id)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        self._flag(node.lineno, "attr", node.attr)
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if not isinstance(node.value, str) or node in self.docs:
            return
        if _WORD.search(node.value) and node.value != "workflow_snapshot":
            self.hits.append(f"{self.path}:{node.lineno}:literal {node.value}")
        if node.value == "workflow_snapshot":
            self.snapshot_keys.append(f"{self.path}:{node.lineno}:{'.'.join(self.stack)}")


class TestIdentityResidue:
    def test_no_retired_identity_in_src_or_examples(self) -> None:
        hits: list[str] = []
        snapshots: list[str] = []
        files = sorted(_SRC.rglob("*.py")) + sorted((_ROOT / "examples").rglob("*.py"))
        for path in files:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            scan = _Scan(path)
            scan.docs = _docstrings(tree)
            scan.visit(tree)
            hits.extend(scan.hits)
            snapshots.extend(scan.snapshot_keys)
        assert snapshots == [f"{_SRC / 'workspace' / 'run.py'}:247:compute_run_definition_hash"]
        assert hits == []

    def test_schema_lives_only_in_the_test_fixture(self) -> None:
        assert not (_SRC / "workflow" / "schema").exists()
        assert not (_SRC / "workflow" / "version.py").exists()
        fixture = Path(__file__).resolve().parent / "fixtures" / "schema"
        assert sorted(p.name for p in fixture.iterdir()) == [
            "README.md",
            "link.json",
            "task_config.json",
            "task_io.json",
            "workflow.json",
            "workflow_contract.json",
        ]
        for path in fixture.iterdir():
            assert _WORD.search(path.read_text(encoding="utf-8")) is None
        import json

        required = json.loads((fixture / "workflow_contract.json").read_text())["required"]
        assert "workflow_digest" in required

    def test_src_does_not_cite_the_moved_schema(self) -> None:
        for path in _SRC.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            assert "schema/workflow.json" not in text
            assert "workflow/schema" not in text

    def test_version_types_are_not_exported(self) -> None:
        for name in ("WorkflowVersion", "TaskTopologyEntry", "WorkflowVersionConflictError"):
            assert not hasattr(workflow, name)
            assert name not in workflow.__all__
