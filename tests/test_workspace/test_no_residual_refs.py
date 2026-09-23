"""Residual-reference guard for the workspace-slim-01 deletion spec.

Asserts the deleted unwired subsystems leave zero trace in the shipped
source tree: no symbol definitions, no imports, no ``__all__`` entries,
and no orphaned module files. Scans ``src/molab/`` only — test files
referencing removed symbols are deleted separately.

It also carries the knowledge-crossref-09 residue: the six forwarder shells
the workspace shed, the knowledge names that left its public surface, and the
duplicated markdown-edge machinery. Those are asserted by **attribute and
import**, never by a substring scan — ``Note`` / ``append_link`` / ``LinkScan``
all legitimately live on in ``molab.knowledge``, and the workspace still writes
``knowledges/`` directories and reads its ``KnowledgeRef`` / ``ContextFocus``
read-models, so a text scan would report the cut several times over. Prose
mentions of knowledge are out of scope for this guard.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

import molab

SRC = Path(molab.__file__).resolve().parent  # .../src/molab
TESTS = Path(__file__).resolve().parents[1]  # .../tests


def _py_files(root: Path = SRC) -> list[Path]:
    return [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]


# Distinctive symbols that must not appear anywhere under src/molab/ after the cut.
DELETED_SYMBOLS = [
    "RunFingerprint",
    "_hash_payload",
    "_environment_signature",
    "_FINGERPRINT_HASH_HEX_LEN",
    "CheckpointState",
    "OutputAsset",
    "ExecutionStateAsset",
    "_register_channel",
    "resumed_step",
    "checkpoint_step",
    "last_step",
    # workspace-slim-02: the bare-pathlib container-index mechanism — the
    # entity *.json is the sole truth source, the catalog the derived index.
    "_rebuild_container_index",
    "_refresh_runs_index",
    "_refresh_executions_index",
    "_refresh_experiments_index",
    "_refresh_projects_index",
    # JSON-only identity + one children-index (plural).
    "META_YAML_FILENAME",
    "_legacy_index_filename",
    "_drop_legacy_index",
    "_LEGACY_META_YAML",
    "_LEGACY_METADATA_FILENAME",
    "_LEGACY_INDEX_FILE",
    "from_yaml",
    "write_ref_meta",
    "LEGACY_AGENT_MODEL_KEY",
    "_LEGACY_TASK_FILE",
    "ReadOnlyStateView",
    "_normalize_legacy_status",
    "_atomic_write_json",
    "CROSS_HOST_HEARTBEAT_STALE_SECONDS",
    "_migrate_scope_columns",
    "_migrate_artifact_edges",
]

DELETED_FILES = [
    SRC / "workspace" / "checkpoint.py",
    SRC / "workspace" / "resume_policy.py",
    SRC / "workspace" / "assets" / "output.py",
    SRC / "workspace" / "assets" / "execution.py",
    SRC / "tree_monitor.py",
    # knowledge-crossref-09: the six forwarder shells the workspace shed.
    # ``bundle_index.py`` is deliberately absent — it is still imported by
    # ``workspace_context.py`` and is deleted by the follow-up member.
    SRC / "workspace" / "edges.py",
    SRC / "workspace" / "concepts.py",
    SRC / "workspace" / "concept_meta.py",
    SRC / "workspace" / "note_meta.py",
    SRC / "workspace" / "reference_meta.py",
    SRC / "workspace" / "zotero_concepts.py",
]

#: The knowledge names the workspace's public surface no longer carries.
DELETED_PUBLIC_NAMES = (
    "DEFAULT_EDGE_ROLE",
    "Edge",
    "EdgeRole",
    "Literature",
    "Note",
    "NoteMeta",
    "ReferenceMeta",
    "ZoteroItem",
    "ConceptNotFoundError",
    "KnowledgeNotFoundError",
)

#: The duplicated markdown-edge machinery: two module attributes and the three
#: ``Folder`` methods that read them.
DELETED_FOLDER_MODULE_ATTRS = ("LinkScan", "append_link")
DELETED_FOLDER_METHODS = ("links", "out_edges", "typed_out_edges")

#: Shell modules no source or test file may import any more.
DELETED_SHELL_MODULES = (
    "molab.workspace.edges",
    "molab.workspace.concepts",
    "molab.workspace.concept_meta",
    "molab.workspace.note_meta",
    "molab.workspace.reference_meta",
    "molab.workspace.zotero_concepts",
)


@pytest.mark.parametrize("symbol", DELETED_SYMBOLS)
def test_symbol_has_zero_residue(symbol: str) -> None:
    offenders = [
        str(p.relative_to(SRC)) for p in _py_files() if symbol in p.read_text(encoding="utf-8")
    ]
    assert not offenders, f"{symbol!r} still referenced in: {offenders}"


@pytest.mark.parametrize("path", DELETED_FILES)
def test_deleted_module_absent(path: Path) -> None:
    assert not path.exists(), f"{path} should have been deleted"


@pytest.mark.parametrize(
    "name", ["RunFingerprint", "OutputAsset", "ExecutionStateAsset", *DELETED_PUBLIC_NAMES]
)
def test_public_export_removed(name: str) -> None:
    mod = importlib.import_module("molab.workspace")
    assert not hasattr(mod, name), f"molab.workspace still exports {name}"
    assert name not in getattr(mod, "__all__", []), f"{name} still in molab.workspace.__all__"


@pytest.mark.parametrize("name", DELETED_FOLDER_MODULE_ATTRS)
def test_folder_module_attr_removed(name: str) -> None:
    folder = importlib.import_module("molab.workspace.folder")
    assert not hasattr(folder, name), f"molab.workspace.folder still defines {name}"


@pytest.mark.parametrize("name", DELETED_FOLDER_METHODS)
def test_folder_method_removed(name: str) -> None:
    folder = importlib.import_module("molab.workspace.folder")
    assert not hasattr(folder.Folder, name), f"Folder.{name} still exists"


@pytest.mark.parametrize("name", ["KnowledgeNotFoundError", "ConceptNotFoundError"])
def test_workspace_errors_carries_no_knowledge_alias(name: str) -> None:
    errors = importlib.import_module("molab.workspace.errors")
    assert not hasattr(errors, name), f"molab.workspace.errors still aliases {name}"
    assert name not in errors.__all__


def _imported_modules(path: Path) -> list[tuple[int, str]]:
    """Every ``(lineno, dotted name)`` *path* imports, from an AST scan."""
    out: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out += [(node.lineno, alias.name) for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.append((node.lineno, node.module))
            out += [(node.lineno, f"{node.module}.{alias.name}") for alias in node.names]
    return out


def test_no_importer_of_a_deleted_shell_or_name_survives() -> None:
    """No file under ``src/`` or ``tests/`` imports a shed shell, or one of the
    knowledge names that left ``molab.workspace``."""
    banned = set(DELETED_SHELL_MODULES) | {f"molab.workspace.{n}" for n in DELETED_PUBLIC_NAMES}
    offenders = [
        f"{path}:{lineno}: {module}"
        for root in (SRC, TESTS)
        for path in _py_files(root)
        for lineno, module in _imported_modules(path)
        if module in banned
    ]
    assert not offenders, "still importing a deleted workspace shell or name:\n  " + "\n  ".join(
        offenders
    )
