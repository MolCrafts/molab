"""Transitional CLI boundary lock for the knowledge redirect (knowledge-crossref-07).

No module under ``src/molab/cli/`` may reach knowledge through
``molab.workspace``:

* the removed forwarder submodules
  (``molab.workspace.{bundle,bundle_index,edges,concepts,doc_embed,knowledge,
  knowledge_write,harvest}``) are banned outright;
* a knowledge-shaped name (``Bundle`` / ``Concept`` / ``Knowledge`` /
  ``harvest_run`` / ``write_knowledge`` / ``mount_note`` / ``summarize_entity``
  / ``EntitySummary`` / ``Edge`` / ``EdgeRole`` / ``extract_title``) may not be
  imported from ``molab.workspace`` — the CLI goes to ``molab.knowledge``, one
  layer up.

The read-model and entity surface stays reachable from ``molab.workspace``
(``Workspace`` / ``WorkspaceContext`` / ``KnowledgeRef`` / ``ContextFocus`` /
``Project`` / ``Experiment`` / ``Run`` / ``*NotFoundError`` / targets /
assets): those are shapes and records, not the knowledge layer.

This scan is **this member's transitional lock**. Once 08/09 delete the
workspace forwarders and 11 stands up the workspace-side absolute ban
(``tests/test_workspace/test_import_guard.py``) the removed modules list here
matches nothing, so the terminal gate is 11's guard, not this file.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CLI_ROOT = REPO_ROOT / "src" / "molab" / "cli"

#: Workspace submodules that only re-exported knowledge before the cutover.
REMOVED_FORWARDERS: frozenset[str] = frozenset(
    {
        "bundle",
        "bundle_index",
        "edges",
        "concepts",
        "doc_embed",
        "knowledge",
        "knowledge_write",
        "harvest",
    }
)

#: Knowledge-shaped names a CLI module must never import from ``molab.workspace``.
KNOWLEDGE_SHAPES: frozenset[str] = frozenset(
    {
        "Bundle",
        "Concept",
        "Knowledge",
        "harvest_run",
        "write_knowledge",
        "mount_note",
        "summarize_entity",
        "EntitySummary",
        "Edge",
        "EdgeRole",
        "extract_title",
    }
)

_WORKSPACE = "molab.workspace"


def _forwarder(module: str) -> str | None:
    """The removed-forwarder tail of *module*, or ``None`` when it is not one."""
    if not module.startswith(f"{_WORKSPACE}."):
        return None
    tail = module[len(_WORKSPACE) + 1 :].split(".", 1)[0]
    return tail if tail in REMOVED_FORWARDERS else None


def _offenders(source: str) -> list[tuple[int, str]]:
    """``(lineno, detail)`` for every knowledge-shaped ``molab.workspace`` import."""
    found: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if _forwarder(module):
                found.append((node.lineno, f"forwarder module {module}"))
            if module == _WORKSPACE or module.startswith(f"{_WORKSPACE}."):
                for alias in node.names:
                    if alias.name in KNOWLEDGE_SHAPES:
                        found.append((node.lineno, f"{alias.name} from {module}"))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if _forwarder(alias.name):
                    found.append((node.lineno, f"import {alias.name}"))
    return found


def _cli_sources() -> list[Path]:
    return [py for py in sorted(CLI_ROOT.rglob("*.py")) if "__pycache__" not in py.parts]


class TestCliKnowledgeBoundary:
    def test_no_cli_module_imports_a_knowledge_shape_from_workspace(self) -> None:
        hits: list[tuple[str, int, str]] = []
        for py in _cli_sources():
            for lineno, detail in _offenders(py.read_text(encoding="utf-8")):
                hits.append((py.relative_to(REPO_ROOT).as_posix(), lineno, detail))
        assert hits == [], f"knowledge-shaped molab.workspace imports in src/molab/cli: {hits}"

    def test_a_forwarder_module_import_is_caught(self) -> None:
        assert _offenders("from molab.workspace.bundle import Bundle") == [
            (1, "forwarder module molab.workspace.bundle"),
            (1, "Bundle from molab.workspace.bundle"),
        ]
        assert _offenders("import molab.workspace.knowledge") == [
            (1, "import molab.workspace.knowledge")
        ]

    def test_a_knowledge_shape_import_is_caught(self) -> None:
        assert _offenders("from molab.workspace import Knowledge") == [
            (1, "Knowledge from molab.workspace")
        ]

    def test_the_read_model_surface_is_accepted(self) -> None:
        allowed = (
            "from molab.workspace import Workspace, Project, Experiment, Run, ContextFocus\n"
            "from molab.workspace.workspace_context import KnowledgeRef, WorkspaceContext\n"
            "from molab.workspace.run import Run, RETRYABLE_STATUSES\n"
            "from molab.workspace.history import GitHistory\n"
            "from molab.workspace import ProjectNotFoundError\n"
        )
        assert _offenders(allowed) == []
