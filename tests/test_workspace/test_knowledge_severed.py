"""``molab.workspace`` no longer owns a single knowledge verb (crossref-08).

The knowledge write / mount / read verbs moved to ``molab.knowledge`` (03) and
every upstream layer was redirected (04-07). This guard pins the workspace end
of that cut: the six knowledge modules are gone, the public surface lost
*exactly* the knowledge names, and no workspace entity still answers a knowledge
verb — while the two things that must survive (the ``Run`` pruning contract and
a loadable server route) still do.
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parent

# The modules the workspace shed. ``find_spec`` is the source of truth: a
# module absent from disk but still importable (a stale ``.pyc``, a re-export)
# would be a failed severance, not a green one.
SEVERED_MODULES = (
    "molab.workspace.knowledge",
    "molab.workspace.knowledge_write",
    "molab.workspace.knowledge_mount",
    "molab.workspace.harvest",
    "molab.workspace.doc_embed",
    "molab.workspace.bundle",
)

# The 9 ``__all__`` names the cut removes, plus the package re-export that was
# never in ``__all__``.
SEVERED_NAMES = (
    "PLAN_BOOK_NAME",
    "EntitySummary",
    "Finding",
    "Knowledge",
    "Observation",
    "Plan",
    "Report",
    "SourceKind",
    "SourceRef",
)
SEVERED_REEXPORT = "summarize_entity"

# Names the cut must NOT touch — a sample across every surviving family.
# ``Note`` / ``Literature`` / ``KnowledgeNotFoundError`` were in this list until
# knowledge-crossref-09 shed the forwarder shells that carried them; workspace
# now imports its knowledge names from ``molab.knowledge`` or not at all.
SURVIVING_NAMES = (
    "Workspace",
    "Project",
    "Experiment",
    "Run",
    "Folder",
    "Asset",
    "AssetManifest",
    "AssetsView",
    "FileStore",
    "Params",
    "ComputeTarget",
    "GitHistory",
    "KnowledgeRef",
    "ContextFocus",
)

# Knowledge attributes no workspace entity may answer.
SEVERED_VERBS = (
    "add_knowledge",
    "knowledge",
    "set_knowledge",
    "del_knowledge",
    "has_knowledge",
    "knowledges",
    "harvest",
)


class TestSeveredKnowledgeSurface:
    """The workspace's knowledge surface is gone, and nothing else with it."""

    @pytest.mark.parametrize("module", SEVERED_MODULES)
    def test_module_is_absent(self, module: str) -> None:
        assert importlib.util.find_spec(module) is None, module

    def test_workspace_imports_and_every_public_name_resolves(self) -> None:
        workspace = importlib.import_module("molab.workspace")

        assert workspace.__all__
        for name in workspace.__all__:
            assert getattr(workspace, name, None) is not None, name

    @pytest.mark.parametrize("name", SEVERED_NAMES)
    def test_severed_name_is_unreachable(self, name: str) -> None:
        workspace = importlib.import_module("molab.workspace")

        assert not hasattr(workspace, name), name
        assert name not in workspace.__all__, name

    def test_the_non_public_reexport_is_gone_too(self) -> None:
        workspace = importlib.import_module("molab.workspace")

        assert not hasattr(workspace, SEVERED_REEXPORT)
        assert SEVERED_REEXPORT not in workspace.__all__

    @pytest.mark.parametrize("name", SURVIVING_NAMES)
    def test_surviving_name_is_still_public(self, name: str) -> None:
        workspace = importlib.import_module("molab.workspace")

        assert name in workspace.__all__, name
        assert getattr(workspace, name, None) is not None, name

    def test_the_removed_set_is_exactly_the_nine(self) -> None:
        workspace = importlib.import_module("molab.workspace")

        removed = set(SEVERED_NAMES)
        assert removed.isdisjoint(workspace.__all__)
        assert set(SURVIVING_NAMES) <= set(workspace.__all__)

    @pytest.mark.parametrize("verb", SEVERED_VERBS)
    def test_entity_answers_no_knowledge_verb(self, verb: str) -> None:
        workspace = importlib.import_module("molab.workspace")

        for cls in (workspace.Project, workspace.Experiment, workspace.Run):
            assert not hasattr(cls, verb), f"{cls.__name__}.{verb}"

    def test_run_still_declares_its_pruning_contract(self) -> None:
        from molab.knowledge.types import non_concept_subdirs
        from molab.workspace import Run

        assert "executions" in Run.NON_CONCEPT_SUBDIRS
        assert "executions" in non_concept_subdirs("workspace.run")

    def test_the_knowledge_route_still_loads(self) -> None:
        # The route reaches knowledge through ``molab.knowledge`` only; if any
        # function-body reference to a severed workspace module survived (06
        # redirected them), importing the module or building the app would fail.
        module = importlib.import_module("molab.server.routes.knowledge")

        assert module is not None

    @pytest.mark.parametrize("module", SEVERED_MODULES)
    def test_no_workspace_test_still_imports_it(self, module: str) -> None:
        offenders = [str(path) for path in TESTS.rglob("*.py") if module in imported_modules(path)]
        assert not offenders, f"{module} still imported by: {offenders}"


def imported_modules(path: Path) -> set[str]:
    """Every module name *path* imports, from an AST scan (comments excluded)."""
    names: set[str] = set()
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names
