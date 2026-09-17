"""Unit tests for the cross-layer ``molab.ids`` primitive module.

``molab.ids`` holds the pure id / slug / content-hash helpers promoted
out of ``molab.workspace.utils`` (okf-01-01) so the ``molab.knowledge``
bottom layer can cite them without importing workspace.
"""

from __future__ import annotations

import ast
from pathlib import Path

import molab.ids as ids
from molab.ids import (
    compute_content_hash,
    slugify,
)


def test_slugify_lowercases_hyphenates_collapses() -> None:
    assert slugify("Hello   World") == "hello-world"
    assert slugify("My_Cool  Project!!") == "my-cool-project"
    assert slugify("a---b") == "a-b"


def test_compute_content_hash_file_prefix_and_stability(tmp_path: Path) -> None:
    f1 = tmp_path / "a.bin"
    f2 = tmp_path / "b.bin"
    f1.write_bytes(b"identical bytes")
    f2.write_bytes(b"identical bytes")
    h1 = compute_content_hash(f1)
    h2 = compute_content_hash(f2)
    assert h1.startswith("sha256:")
    assert h1 == h2  # stable for identical bytes


def test_source_imports_no_workspace_or_upstream_layer() -> None:
    """The primitive must not import workspace or any upstream layer.

    Asserted at the AST level on the module's own source — the
    enforceable layer-independence invariant (a runtime ``sys.modules``
    probe is confounded by the eager ``molab/__init__.py``). Mirrors
    ``tests/test_workspace/test_import_guard.py``.
    """
    forbidden = (
        "molab.workspace",
        "molab.workflow",
        "molab.harness",
        "molab.server",
        "molab.cli",
        "molab.plugins",
        "molab.sweep",
    )
    source = Path(ids.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            offenders += [a.name for a in node.names if a.name.startswith(forbidden)]
        elif isinstance(node, ast.ImportFrom) and node.module and node.module.startswith(forbidden):
            offenders.append(node.module)
    assert offenders == [], f"molab.ids imports forbidden modules: {offenders}"
