"""Layer firewall for ``molexp.knowledge`` — the standalone OKF library.

``molexp.knowledge`` owns the Open Knowledge Format: the concept-type registry,
the path-is-identity ``Concept``, typed edges, and the ``Bundle`` façade. Its
defining property is that **it needs no workspace**: a group wiki is just a
directory, and opening one must not drag workspace storage, an SSH transport, or
an LLM SDK into the process.

So its source may import only stdlib, its own third-party deps
(pydantic / pyyaml / pathspec), and the layer-0 cross-layer primitives. Anything
else — ``molexp.workspace`` (a *peer*, not a parent) or any upstream layer — is
an architectural defect.

This is an **allowlist**, deliberately. The previous denylist named the layers
that were forbidden, which silently permitted every module nobody had thought to
add yet. Stating what is allowed means a new molexp dependency has to be argued
for here before it can appear.

This is an **AST static scan**, not a runtime ``sys.modules`` probe: importing
any ``molexp.X`` submodule first runs the eager ``molexp/__init__.py``, which
loads workspace, so a runtime probe is unsatisfiable. The source law is the one
that matters, and it is checkable today. Mirrors
``tests/test_workspace/test_import_guard.py``.
"""

from __future__ import annotations

import ast
from pathlib import Path

KNOWLEDGE_ROOT = Path(__file__).resolve().parents[2] / "src" / "molexp" / "knowledge"

#: The only ``molexp.*`` modules the OKF library may import: layer-0 primitives
#: that are themselves dependency-light and citable from any layer.
ALLOWED_MOLEXP_PREFIXES: tuple[str, ...] = (
    "molexp.knowledge",  # itself
    "molexp._typing",
    "molexp.fs",
    "molexp.gitignore",
    "molexp.ids",
    "molexp.path",
    "molexp.atomicio",
)


def _molexp_imports(source: str) -> list[str]:
    """Every ``molexp.*`` module name imported by *source*."""
    names: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.append(node.module)
    return [n for n in names if n == "molexp" or n.startswith("molexp.")]


def _offenders(source: str) -> list[str]:
    return [m for m in _molexp_imports(source) if not m.startswith(ALLOWED_MOLEXP_PREFIXES)]


def test_knowledge_imports_only_layer_zero_primitives() -> None:
    hits: list[tuple[str, str]] = []
    for py in sorted(KNOWLEDGE_ROOT.rglob("*.py")):
        if "__pycache__" in py.parts:
            continue
        hits += [(py.name, mod) for mod in _offenders(py.read_text(encoding="utf-8"))]
    assert hits == [], f"molexp.knowledge may not import these: {hits}"


def test_scanner_detects_planted_violations() -> None:
    # Negative control: the scanner must catch the imports it exists to ban —
    # the peer storage layer, an upstream layer, and a bare ``import molexp``.
    assert _offenders("from molexp.workspace.folder import Folder") == ["molexp.workspace.folder"]
    assert _offenders("import molexp.workflow.compiler") == ["molexp.workflow.compiler"]
    assert _offenders("import molexp") == ["molexp"]
    assert _offenders("from molexp.harness.stages import Stage") == ["molexp.harness.stages"]


def test_allowlist_admits_the_primitives_actually_used() -> None:
    # The allowlist is only meaningful if it is not so narrow that the library
    # cannot express itself, nor so wide that it admits a storage layer.
    assert _offenders("from molexp.fs import FileSystem, LocalFileSystem") == []
    assert _offenders("from molexp.ids import slugify") == []
    assert _offenders("from molexp.gitignore import load_gitignore_matcher") == []
