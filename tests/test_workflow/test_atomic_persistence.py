"""Invariant lock: node-journal writes route through ``FileStore.put``.

The byte exit is :class:`~molab.workspace.file_store.FileStore` (atomic via
:mod:`molab.atomicio`). This source scan pins that wiring: every journal
writer in ``_engine.persistence`` goes through ``_put_journal``, and
``_put_journal`` is a ``FileStore(journal_dir).put`` of ``JOURNAL_NAME``.
"""

from __future__ import annotations

import ast
from pathlib import Path

PERSISTENCE_FILE = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "molab"
    / "workflow"
    / "_engine"
    / "persistence.py"
)


def _function_source(name: str) -> str:
    text = PERSISTENCE_FILE.read_text()
    tree = ast.parse(text)
    node = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name),
        None,
    )
    assert node is not None, f"expected function {name}"
    return ast.get_source_segment(text, node) or ""


def test_put_journal_is_a_filestore_put() -> None:
    src = _function_source("_put_journal")
    assert "FileStore(journal_dir).put(JOURNAL_NAME" in src
    assert "write_text" not in src


def test_initial_journal_writes_via_put_journal() -> None:
    src = _function_source("write_initial_workflow_json")
    assert "_put_journal" in src, "write_initial_workflow_json must write via FileStore"
    assert "write_text" not in src


def test_coalesced_writer_flushes_via_put_journal() -> None:
    assert "_put_journal" in _function_source("_flush_locked")
    assert "_put_journal" in _function_source("open_execution_document")
