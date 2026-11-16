"""AST helpers for layout-literal scans.

Pure functions: this module does not import molab. Later guards may add
keyword-only parameters after ``allowed``; the first two parameters stay
positional.
"""

from __future__ import annotations

import ast


def docstring_constants(tree: ast.Module) -> set[int]:
    """The ``id()`` of every docstring constant node — prose, never a criterion.

    Same rule as the knowledge-residue scan: a module, class, or function
    docstring is the first statement and a string constant.
    """
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


def _allowed_literal_ids(
    tree: ast.Module,
    module_name: str,
    allowed: frozenset[tuple[str, str]],
) -> set[int]:
    """``id()`` of each top-level ``CONST = "<literal>"`` named in ``allowed``."""
    names = {const for mod, const in allowed if mod == module_name}
    if not names:
        return set()
    found: set[int] = set()
    for stmt in tree.body:
        if not isinstance(stmt, ast.Assign) or not isinstance(stmt.value, ast.Constant):
            continue
        if not isinstance(stmt.value.value, str):
            continue
        if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
            continue
        if stmt.targets[0].id in names:
            found.add(id(stmt.value))
    return found


def _literal_names(text: str, exact: frozenset[str]) -> list[str]:
    """Exact name, or a ``/`` path segment that is an exact name.

    A single segment that is not itself an exact name is prose
    (``"coalesced workflow.json flush failed for "``) and is not reported.
    """
    if text in exact:
        return [text]
    parts = text.split("/")
    if len(parts) <= 1:
        return []
    found: list[str] = []
    seen: set[str] = set()
    for part in parts:
        if part in exact and part not in seen:
            seen.add(part)
            found.append(part)
    return found


def layout_literal_offenders(
    source: str,
    module_name: str,
    *,
    exact: frozenset[str],
    allowed: frozenset[tuple[str, str]] = frozenset(),
) -> list[tuple[int, str]]:
    """``(lineno, name)`` for non-docstring string literals that name a layout segment.

    ``allowed`` entries are ``(module_name, "CONST")``: that module's top-level
    ``CONST = "<literal>"`` assignment is not an offender. F-string literal
    pieces are scanned; a docstring constant is not.
    """
    tree = ast.parse(source)
    skip = docstring_constants(tree)
    skip.update(_allowed_literal_ids(tree, module_name, allowed))
    offenders: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if id(node) in skip:
            continue
        offenders.extend((node.lineno, name) for name in _literal_names(node.value, exact))
    return offenders
