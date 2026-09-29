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

arch-own-01-cleanup extends it with the Phase-1 dead code: the run-context
family (``runcontext`` / ``run_context`` / ``run_lifecycle`` / ``run_assets``),
``workflow/_names.py``, ``WorkflowSnapshotRef``, ``derive_execution_id``,
``Run.delete_execution``, ``ExecutionContext.set_workflow``, ``CacheFolder`` /
``Workspace.cache`` and the Bundle's persisted index writes. ``set_workflow`` and
``RunLifecycle`` are substrings of live names, so they are asserted by attribute,
not by the substring scan.

drop-harness-01-src (D86) extends it with the Python harness and the core code
only the harness used: the ``set_workflow_recoverer`` seam, the Folder
``meta.json`` type table, the operator-config agent bridge, the host adapters
(``default_science_extras`` / ``MolqPlugin`` / ``MetricsPlugin`` /
``WorkspacePlugin``), ``workspace.curation``, the server shutdown flag,
``PLAN_BOOK_NAME`` and ``molab mcp``. ``MolqJobs`` is a substring of the live
``MolqJobsResponse``, so it is asserted by attribute, not by the substring scan.

arch-own-02h extends it with the run-level provenance it removed
(``Run.update_provenance``, ``snapshot_sources`` and the ``RunMetadata``
fields passed as kwargs), backfills 02f's fresh-marker names, and asserts that
no ``arch-own-02`` xfail is left in ``tests/``.
"""

from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path

import pytest

import molab
import molab.workflow
from molab.knowledge.bundle import Bundle
from molab.workspace.execution_context import ExecutionContext
from molab.workspace.run import Run
from molab.workspace.workspace import Workspace

SRC = Path(molab.__file__).resolve().parent  # .../src/molab
TESTS = Path(__file__).resolve().parents[1]  # .../tests
REPO = TESTS.parent


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
    # arch-own-01-cleanup: Phase-1 dead code.
    "CacheFolder",
    "WORKSPACE_CACHE_KIND",
    "as_cache_store",
    "WorkflowSnapshotRef",
    "derive_execution_id",
    "delete_execution",
    "RunAssets",
    "ContextStore",
    "SOURCES_FILENAME",
    "build_index",
    "_record_source",
    "INDEX_JSON_FILENAME",
    "INDEX_MD_FILENAME",
    # drop-harness-01-src: core code only the harness used.
    "set_workflow_recoverer",
    "get_workflow_recoverer",
    "WorkflowRecoverer",
    "register_folder_type",
    "class_for_folder_type",
    "_TYPE_TO_CLS",
    "bridge_operator_config",
    "configured_agent_model",
    "configured_api_keys",
    "resolve_configured_model",
    "_tier_map_from_raw",
    "AGENT_MODELS_KEY",
    "default_science_extras",
    "MolqPlugin",
    "MetricsPlugin",
    "WorkspacePlugin",
    "is_shutting_down",
    "wait_or_shutdown",
    "mark_shutting_down",
    "reset_shutdown_flag",
    "PLAN_BOOK_NAME",
    "mcp_config",
    # arch-own-02f: the fresh marker and caller-minted execution ids.
    "make_execution_id",
    "request_fresh_execution",
    "fresh_requested",
    "FRESH_MARKER_FILENAME",
    "fresh.json",
    # arch-own-02h: run-level provenance; ``=`` pins the kwarg spelling, so a
    # local ``executor_info = …`` or the ``source_snapshot`` module is not hit.
    "update_provenance",
    "snapshot_sources",
    "source_snapshot=",
    "executor_info=",
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
    # arch-own-01-cleanup: the dead run-context family, dead workflow modules
    # and the never-written workspace cache folder.
    SRC / "workspace" / "runcontext.py",
    SRC / "workspace" / "run_context.py",
    SRC / "workspace" / "run_lifecycle.py",
    SRC / "workspace" / "run_assets.py",
    SRC / "workflow" / "_names.py",
    SRC / "workflow" / "snapshot_ref.py",
    SRC / "workspace" / "cache" / "folder.py",
    SRC / "workspace" / "cache" / "__init__.py",
    # drop-harness-01-src: the harness tree and the core code only it used.
    SRC / "harness",
    SRC / "plugins" / "extras.py",
    SRC / "plugins" / "metrics" / "host.py",
    SRC / "plugins" / "submit_molq" / "host.py",
    SRC / "workspace" / "plugin.py",
    SRC / "workspace" / "curation",
    SRC / "server" / "shutdown.py",
    SRC / "cli" / "workspace" / "mcp_config.py",
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
    # arch-own-01-cleanup
    "molab.workspace.runcontext",
    "molab.workspace.run_context",
    "molab.workspace.run_lifecycle",
    "molab.workspace.run_assets",
    "molab.workspace.cache",
    "molab.workspace.cache.folder",
    "molab.workflow._names",
    "molab.workflow.snapshot_ref",
    # drop-harness-01-src
    "molab.plugins.extras",
    "molab.plugins.metrics.host",
    "molab.plugins.submit_molq.host",
    "molab.workspace.plugin",
    "molab.workspace.curation",
    "molab.server.shutdown",
    "molab.cli.workspace.mcp_config",
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


class TestArchOwn01DeletedAttributes:
    """arch-own-01-cleanup: the deleted methods / properties / exports are gone
    from the live classes, and the kept ``RunContext`` alias still resolves."""

    def test_execution_context_has_no_set_workflow(self) -> None:
        assert not hasattr(ExecutionContext, "set_workflow")

    def test_run_has_no_delete_execution(self) -> None:
        assert not hasattr(Run, "delete_execution")

    def test_workspace_has_no_cache(self) -> None:
        assert not hasattr(Workspace, "cache")

    def test_workflow_has_no_snapshot_ref_export(self) -> None:
        assert not hasattr(molab.workflow, "WorkflowSnapshotRef")

    def test_bundle_has_no_build_index(self) -> None:
        assert not hasattr(Bundle, "build_index")

    def test_bundle_search_has_no_rebuild_param(self) -> None:
        assert "rebuild" not in inspect.signature(Bundle.search).parameters

    def test_run_context_alias_is_execution_context(self) -> None:
        assert molab.RunContext is ExecutionContext


class TestDropHarnessResidue:
    """drop-harness-01-src (D86): nothing names the deleted Python harness."""

    def test_nothing_imports_the_harness(self) -> None:
        roots = (SRC, TESTS, REPO / "regressions", REPO / "examples")
        scanned = [path for root in roots for path in _py_files(root)]
        assert len(scanned) > 100, "guard the guard: a mistyped root makes this vacuous"
        offenders = [
            f"{path.relative_to(REPO)}:{lineno}: {module}"
            for path in scanned
            for lineno, module in _imported_modules(path)
            if module == "molab.harness" or module.startswith("molab.harness.")
        ]
        assert not offenders, "still importing the deleted harness:\n  " + "\n  ".join(offenders)

    def test_submit_molq_and_metrics_export_no_host_extra(self) -> None:
        submit_molq = importlib.import_module("molab.plugins.submit_molq")
        metrics = importlib.import_module("molab.plugins.metrics")
        for name in ("MolqJobs", "MolqPlugin"):
            assert not hasattr(submit_molq, name), f"submit_molq still exports {name}"
        assert not hasattr(metrics, "MetricsPlugin"), "metrics still exports MetricsPlugin"


def _xfail_reasons(path: Path) -> list[tuple[int, str]]:
    """``reason=`` string constants of every ``*.xfail(...)`` call in *path*."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr != "xfail":
            continue
        for kw in node.keywords:
            if (
                kw.arg == "reason"
                and isinstance(kw.value, ast.Constant)
                and isinstance(kw.value.value, str)
            ):
                found.append((node.lineno, kw.value.value))
    return found


def test_no_arch_own_02_xfail_remains() -> None:
    files = _py_files(TESTS)
    assert any(_xfail_reasons(p) for p in files), "guard the guard: no xfail found at all"
    offenders = [
        f"{path.relative_to(REPO)}:{lineno}: {reason}"
        for path in files
        for lineno, reason in _xfail_reasons(path)
        if reason.startswith("arch-own-02")
    ]
    assert not offenders, "arch-own-02 xfails left:\n  " + "\n  ".join(offenders)
