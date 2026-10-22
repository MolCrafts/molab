"""Deleted knowledge product names must not import from molab.knowledge."""

from __future__ import annotations

import importlib
import importlib.util
import re
from pathlib import Path

import pytest

import molab.knowledge as knowledge

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
TESTS = ROOT / "tests"
WORKSPACE = (SRC / "molab" / "workspace").resolve()
SELF = Path(__file__).resolve()
RESIDUAL = (TESTS / "test_workspace" / "test_no_residual_refs.py").resolve()
# arch-own-09-docs: the vocabulary guard's samples name retired tokens on purpose.
DOCS_VOCAB = (TESTS / "test_docs_vocabulary.py").resolve()

DELETED_MODULES = (
    "molab.knowledge.bundle",
    "molab.knowledge.bundle_index",
    "molab.knowledge.types",
    "molab.knowledge.hooks",
    "molab.knowledge.note_meta",
)

RETIRED_TOKENS = (
    r"\bBundle\b",
    r"\bBundleIndex\b",
    r"\bbundle_index\b",
    r"molab\.knowledge\.bundle\b",
    r"\bKnowledgeItem\b",
    r"\bKnowledgeMeta\b",
    r"\bNoteMeta\b",
    r"\bnote_meta\b",
    r"\bregister_host_markers\b",
    r"\bregister_marker_filenames\b",
    r"\bregister_concept_type\b",
    r"\bresolve_concept_type\b",
    r"@concept_type\b",
    r"\bnon_concept_subdirs\b",
    r"molab\.knowledge\.types\b",
    r"molab\.knowledge\.hooks\b",
)

SERVER_RETIRED_TOKENS = (r"\bconcept_from_dir\b", r"\bread_meta_dict\b")
KNOWLEDGE_WORKSPACE_INTERNALS = (r"\bentity_json_names\b", r"\bWORKSPACE_RUN_KIND\b")


def _py_files(root: Path) -> list[Path]:
    return [path for path in root.rglob("*.py") if "__pycache__" not in path.parts]


def _hits(paths: list[Path], patterns: tuple[str, ...]) -> list[str]:
    compiled = [re.compile(pattern) for pattern in patterns]
    found: list[str] = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for pattern in compiled:
            if pattern.search(text):
                found.append(f"{path.relative_to(ROOT)}: {pattern.pattern}")
    return found


class TestRetiredVocabulary:
    def test_deleted_modules_are_gone(self) -> None:
        for name in DELETED_MODULES:
            assert importlib.util.find_spec(name) is None, name

    @pytest.mark.parametrize("pattern", RETIRED_TOKENS)
    def test_symbol_has_zero_residue(self, pattern: str) -> None:
        sources = [
            path
            for path in _py_files(SRC)
            if WORKSPACE not in path.resolve().parents and path.resolve() != WORKSPACE
        ]
        tests = [
            path for path in _py_files(TESTS) if path.resolve() not in {SELF, RESIDUAL, DOCS_VOCAB}
        ]
        assert _hits(sources + tests, (pattern,)) == []

    @pytest.mark.parametrize("pattern", SERVER_RETIRED_TOKENS)
    def test_server_and_knowledge_drop_directory_readers(self, pattern: str) -> None:
        roots = [SRC / "molab" / "server", SRC / "molab" / "knowledge"]
        paths = [path for root in roots for path in _py_files(root)]
        assert _hits(paths, (pattern,)) == []

    def test_knowledge_does_not_name_workspace_internals(self) -> None:
        assert _hits(_py_files(SRC / "molab" / "knowledge"), KNOWLEDGE_WORKSPACE_INTERNALS) == []

    def test_a_planted_import_is_detected(self) -> None:
        planted = TESTS / "_planted_retired_token.py"
        planted.write_text("from molab.knowledge.bundle import Bundle\n", encoding="utf-8")
        try:
            hits = _hits([planted], (r"\bBundle\b", r"molab\.knowledge\.bundle\b"))
        finally:
            planted.unlink(missing_ok=True)

        assert len(hits) == 2

    def test_a_planted_directory_reader_is_detected(self) -> None:
        planted = TESTS / "_planted_retired_token.py"
        planted.write_text("concept_from_dir(x)\n", encoding="utf-8")
        try:
            hits = _hits([planted], (r"\bconcept_from_dir\b",))
        finally:
            planted.unlink(missing_ok=True)

        assert len(hits) == 1


class TestLegacyNames:
    def test_bundle_is_not_public(self) -> None:
        import molab.workspace as workspace

        assert "Bundle" not in knowledge.__all__
        assert not hasattr(knowledge, "Bundle")
        assert "Bundle" not in workspace.__all__
        assert not hasattr(workspace, "Bundle")

    def test_index_types_are_not_public(self) -> None:
        import molab.workspace as workspace

        for name in ("Backlink", "BundleIndex", "ConceptIndexEntry", "ConceptNotFoundError"):
            assert name not in knowledge.__all__
            assert name not in workspace.__all__
            assert not hasattr(workspace, name)

    def test_reference_concept_is_not_public(self) -> None:
        assert "ReferenceConcept" not in knowledge.__all__
        assert not hasattr(knowledge, "ReferenceConcept")

    def test_workspace_knowledge_module_is_gone(self) -> None:
        # crossref-08: the workspace shed every knowledge verb — the module that
        # used to carry them is not merely shrunken, it does not exist.
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module("molab.workspace.knowledge")

    def test_workspace_knowledge_names_are_unreachable(self) -> None:
        import molab.workspace as workspace

        for name in ("HasKnowledge", "FailureAnalysis", "ProtocolNote", "Decision"):
            assert not hasattr(workspace, name)
