"""Residue scan: the workspace source carries no knowledge name (knowledge-crossref-10).

The workspace's read paths no longer know knowledge — the assembler projects no
``knowledge`` rows, the layout validator owns no knowledge head-file set, and the
cache prefetch helper is named for the ``meta.json`` Concept mounts it actually
serves. This pins the terminal state by **identifier and import only** (D12): a
docstring or comment may still say "knowledge" (review-only, never a criterion),
but no symbol or import under ``src/molab/workspace/`` may carry the name beyond
the survivors the workspace legitimately owns:

* ``knowledges`` / ``knowledges.json`` — disk names the workspace owns.
* ``KnowledgeRef`` / the ``knowledge`` field / ``relevant_knowledge`` — the
  retained read-model shape (its one producer is ``molab.services``).
* the four ``from molab.knowledge.types import concept_type`` registrations in
  ``workspace.py`` / ``project.py`` / ``experiment.py`` / ``run.py`` — owned by
  knowledge-crossref-11-guards (D13), deliberately exempt here.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import molab

WORKSPACE = Path(molab.__file__).resolve().parent / "workspace"

#: The names the workspace keeps: disk names it owns + the retained read-model.
ALLOWED_NAMES = frozenset(
    {"knowledges", "knowledges.json", "KnowledgeRef", "knowledge", "relevant_knowledge"}
)

#: The four registrations 11-guards removes (D13) — exempt by file + module + symbol.
CONCEPT_TYPE_FILES = frozenset({"workspace.py", "project.py", "experiment.py", "run.py"})
CONCEPT_TYPE_MODULE = "molab.knowledge.types"
CONCEPT_TYPE_SYMBOL = "concept_type"


def _sources() -> list[Path]:
    return [p for p in sorted(WORKSPACE.rglob("*.py")) if "__pycache__" not in p.parts]


def _is_exempt_concept_type(py: Path, node: ast.ImportFrom) -> bool:
    return (
        py.name in CONCEPT_TYPE_FILES
        and node.module == CONCEPT_TYPE_MODULE
        and [alias.name for alias in node.names] == [CONCEPT_TYPE_SYMBOL]
    )


def _knowledge_imports(source: str, py: Path) -> list[tuple[int, str]]:
    """``(lineno, module)`` for every ``molab.knowledge`` import."""
    out: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            is_knowledge = module == "molab.knowledge" or module.startswith("molab.knowledge.")
            if is_knowledge and not _is_exempt_concept_type(py, node):
                out.append((node.lineno, module))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "molab.knowledge" or alias.name.startswith("molab.knowledge."):
                    out.append((node.lineno, alias.name))
    return out


def _identifier(alias: ast.alias) -> str:
    """The name an alias introduces — its ``as`` name, or the last dotted part."""
    return alias.asname or alias.name.rsplit(".", 1)[-1]


def _names_for(node: ast.AST) -> list[str]:
    """The identifiers a node introduces or names, if any."""
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.Attribute):
        return [node.attr]
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        return [node.name]
    if isinstance(node, ast.arg):
        return [node.arg]
    if isinstance(node, ast.keyword):
        return [node.arg] if node.arg is not None else []
    if isinstance(node, ast.alias):
        return [_identifier(node)]
    return []


def _knowledge_identifiers(source: str) -> list[tuple[int, str]]:
    """``(lineno, name)`` for every identifier carrying ``knowledge``."""
    out: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(source)):
        for name in _names_for(node):
            if "knowledge" in name.lower() and name not in ALLOWED_NAMES:
                out.append((node.lineno, name))
    return out


class TestNoKnowledgeResidue:
    @pytest.mark.unit
    def test_no_knowledge_import_under_workspace(self) -> None:
        offenders = [
            f"{py.relative_to(WORKSPACE)}:{lineno}: {module}"
            for py in _sources()
            for lineno, module in _knowledge_imports(py.read_text(encoding="utf-8"), py)
        ]
        assert not offenders, "still importing molab.knowledge:\n  " + "\n  ".join(offenders)

    @pytest.mark.unit
    def test_workspace_source_has_no_knowledge_token(self) -> None:
        offenders = [
            f"{py.relative_to(WORKSPACE)}:{lineno}: {name}"
            for py in _sources()
            for lineno, name in _knowledge_identifiers(py.read_text(encoding="utf-8"))
        ]
        assert not offenders, "knowledge-named identifier remains:\n  " + "\n  ".join(offenders)

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "symbol",
        ["_prefetch_knowledge_children", "_KNOWLEDGE_SKIP_DEFAULT", "_check_knowledge_container"],
    )
    def test_deleted_symbol_leaves_no_identifier(self, symbol: str) -> None:
        offenders = [
            str(py.relative_to(WORKSPACE))
            for py in _sources()
            if symbol in py.read_text(encoding="utf-8")
        ]
        assert not offenders, f"{symbol!r} still present in: {offenders}"
