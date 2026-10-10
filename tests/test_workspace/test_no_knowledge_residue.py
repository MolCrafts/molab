"""Residue scan: workspace source carries no knowledge vocabulary.

Identifiers, literals, docstrings and comments under ``src/molab/workspace/``
are all in scope. The allowlist is empty.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

import molab

WORKSPACE = Path(molab.__file__).resolve().parent / "workspace"

#: Nothing under workspace may carry the word.
ALLOWED_NAMES = frozenset()

#: A run of identifier characters — the unit a name, a literal or a stem is read in.
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*")


def _sources() -> list[Path]:
    return [p for p in sorted(WORKSPACE.rglob("*.py")) if "__pycache__" not in p.parts]


def _carries_knowledge(text: str) -> bool:
    return "knowledge" in text.lower()


def _tokens(text: str) -> list[str]:
    """Every identifier-shaped run in *text* that carries the word ``knowledge``."""
    return [word for word in _WORD.findall(text) if _carries_knowledge(word)]


def _docstring_constants(tree: ast.Module) -> set[int]:
    """The ``id()`` of every docstring constant node — prose, never a criterion."""
    found: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if not node.body:
            continue
        first = node.body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            found.add(id(first.value))
    return found


def _knowledge_imports(source: str) -> list[tuple[int, str]]:
    """``(lineno, module)`` for every ``molab.knowledge`` import."""
    out: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "molab.knowledge" or module.startswith("molab.knowledge."):
                out.append((node.lineno, module))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "molab.knowledge" or alias.name.startswith("molab.knowledge."):
                    out.append((node.lineno, alias.name))
    return out


def _knowledge_tokens(source: str) -> list[tuple[int, str]]:
    """``(lineno, token)`` for every knowledge-bearing name, literal or import.

    Docstrings are skipped — prose is review-only (D12) — while a runtime string
    literal is *not*: a name the code passes around is a name.
    """
    tree = ast.parse(source)
    docstrings = _docstring_constants(tree)
    found: set[tuple[int, str]] = set()

    def add(lineno: int, text: str) -> None:
        found.update((lineno, token) for token in _tokens(text))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                add(node.lineno, alias.name)
                if alias.asname is not None:
                    add(node.lineno, alias.asname)
        elif isinstance(node, ast.ImportFrom):
            add(node.lineno, node.module or "")
            for alias in node.names:
                add(node.lineno, alias.name)
                if alias.asname is not None:
                    add(node.lineno, alias.asname)
        elif isinstance(node, ast.Attribute):
            add(node.lineno, node.attr)
        elif isinstance(node, ast.Name):
            add(node.lineno, node.id)
        elif isinstance(node, ast.arg | ast.keyword):
            add(node.lineno, node.arg or "")
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            add(node.lineno, node.name)
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
        ):
            add(node.lineno, node.value)
    return sorted(found)


def _knowledge_stems() -> list[str]:
    """Source files whose *stem* carries the word — a knowledge-named module."""
    return [str(py.relative_to(WORKSPACE)) for py in _sources() if _carries_knowledge(py.stem)]


class TestNoKnowledgeResidue:
    @pytest.mark.unit
    def test_no_knowledge_import_under_workspace(self) -> None:
        offenders = [
            f"{py.relative_to(WORKSPACE)}:{lineno}: {module}"
            for py in _sources()
            for lineno, module in _knowledge_imports(py.read_text(encoding="utf-8"))
        ]
        assert not offenders, "still importing molab.knowledge:\n  " + "\n  ".join(offenders)

    @pytest.mark.unit
    def test_workspace_source_has_no_knowledge_token(self) -> None:
        scanned = {py: _knowledge_tokens(py.read_text(encoding="utf-8")) for py in _sources()}
        offenders = [
            f"{py.relative_to(WORKSPACE)}:{lineno}: {token}"
            for py, tokens in scanned.items()
            for lineno, token in tokens
            if token not in ALLOWED_NAMES
        ]
        offenders += [f"{stem}: knowledge-named module" for stem in _knowledge_stems()]
        assert not offenders, "knowledge-named name remains:\n  " + "\n  ".join(offenders)

    @pytest.mark.unit
    def test_workspace_prose_names_no_knowledge(self) -> None:
        offenders = [
            str(py.relative_to(WORKSPACE))
            for py in _sources()
            if "knowledge" in py.read_text(encoding="utf-8").lower()
        ]
        assert not offenders, "prose still names knowledge:\n  " + "\n  ".join(offenders)

    @pytest.mark.unit
    def test_detector_sees_a_planted_name(self) -> None:
        found = _knowledge_tokens("KnowledgeRef = 1\nx = 'knowledges'\n")

        assert (1, "KnowledgeRef") in found
        assert (2, "knowledges") in found

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "symbol",
        [
            "_prefetch_knowledge_children",
            "_KNOWLEDGE_SKIP_DEFAULT",
            "_check_knowledge_container",
            "NON_CONCEPT_SUBDIRS",
            "_check_strays",
            "KnowledgeRef",
        ],
    )
    def test_deleted_symbol_leaves_no_identifier(self, symbol: str) -> None:
        offenders = [
            str(py.relative_to(WORKSPACE))
            for py in _sources()
            if symbol in py.read_text(encoding="utf-8")
        ]
        assert not offenders, f"{symbol!r} still present in: {offenders}"
