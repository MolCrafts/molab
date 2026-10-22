"""Retired documentation vocabulary must not return to the docs or to src prose.

The symbol-level guards own the retired identifiers. This file owns the prose
that describes those identifiers as if they were still the design.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "molab"

ROOTS: dict[str, Path] = {
    "docs/en": ROOT / "docs" / "en",
    "docs/zh": ROOT / "docs" / "zh",
    "CLAUDE.md": ROOT / "CLAUDE.md",
    ".claude/notes": ROOT / ".claude" / "notes",
}

# Decision log: dated historical facts. architecture.md is scanned.
EXCLUDED: dict[str, str] = {
    ".claude/notes/notes.md": "decision log: dated historical facts",
}

RETIRED: dict[str, re.Pattern[str]] = {
    "assets-manifest": re.compile(
        r"assets\.json|AssetManifest|assets\.scan|\bscan_assets\b|DataAssetLibrary|\bAssetsView\b"
    ),
    "bundle": re.compile(r"\bBundle(Index)?\b|\bbundle_index\b"),
    "workflow-snapshot": re.compile(r"workflow_snapshot|WorkflowSnapshotRef"),
    "fresh-marker": re.compile(
        r"fresh\.json|make_execution_id|request_fresh_execution|fresh_requested"
    ),
    "workflow-source-string": re.compile(
        r"(Experiment|ExperimentMetadata|experiment|metadata)\.workflow_source"
        r'|"workflow_source"\s*:|\bworkflow_type\b|\bworkflowType\b'
    ),
    "knowledge-dir-head": re.compile(
        r"knowledges/<[^>]+>/|\b(note|literature|report|finding|observation|plan)\.json\b"
        r"|(?=.*\bknowledges/)(?=.*(?<![\w-])index\.md)"
    ),
    "run-path-id": re.compile(r"run-<|runs/run-|exec-<"),
    "reference-store": re.compile(r"ReferenceStore"),
    "retry-mode": re.compile(r"ExecutionMode\.RETRY|\bRETRY\b|\bretry mode\b|mode=[\"']retry"),
    "five-modes": re.compile(r"\bfive (execution )?modes\b", re.IGNORECASE),
    "resume-reopens": re.compile(
        r"resum\w*[^.\n]{0,40}reopen|reopen\w*[^.\n]{0,40}(execution|attempt)",
        re.IGNORECASE,
    ),
    "recoverer-seam": re.compile(
        r"set_workflow_recoverer|get_workflow_recoverer|\bWorkflowRecoverer\b|PlanWorkflowRecoverer"
    ),
    "path-keyed-cache": re.compile(
        r'run_dir/cache|run_dir / "cache"|\.molab/cache\b|ws\.cache|CacheFolder'
    ),
    "concept-registry": re.compile(
        r"@concept_type|\bregister_concept_type\b|\bresolve_concept_type\b|\bconcept_type_of\b"
        r"|(?i:concept[- ]type registry)"
    ),
    "workflow-identity": re.compile(
        r"\bworkflow_id\b|WorkflowVersion|TaskTopologyEntry|_stable_workflow_id"
    ),
    "journal-legacy": re.compile(
        r"read_node_outputs|seed_from_execution|last_resumable_execution_id"
        r"|filter_resume_seeds|execution_results"
    ),
    "run-exec-fields": re.compile(
        r"ErrorInfo|error\.txt|update_provenance|snapshot_sources|delete_execution"
    ),
    "knowledge-shapes": re.compile(r"KnowledgeItem|KnowledgeMeta|NoteMeta|note_meta"),
}

# Exact literal removed before the named pattern runs. (span, reason)
ALLOWED_SPANS: dict[str, tuple[str, str]] = {
    "workflow-snapshot": (
        '"workflow_snapshot": None',
        "frozen hash key of compute_run_definition_hash (arch-own-04e, D45)",
    ),
    "retry-mode": (
        "`ExecutionMode.RETRY` is stored as `RERUN`",
        "03a normalizes the legacy input mode to RERUN",
    ),
    "run-exec-fields": (
        "`ErrorInfo` (removed; read `Execution.error`)",
        "D82 Removed API list entry",
    ),
}

MIGRATE_LINE_EXEMPT = frozenset(
    {"assets-manifest", "knowledge-dir-head", "fresh-marker", "run-exec-fields"}
)

SRC_RETIRED: dict[str, re.Pattern[str]] = {
    "run-path-id": re.compile(r"runs/run-|run-<"),
    "path-keyed-cache": re.compile(r'run_dir / "cache"|run_dir/cache|\.molab/cache/'),
    "children-index": re.compile(r"children[- ]index"),
    "agent-store": re.compile(r"molab\.agent\.mcp\.store"),
    "resume-reopens": re.compile(
        r"resum\w*[^.\n]{0,40}reopen|reopen\w*[^.\n]{0,40}(execution|attempt)",
        re.IGNORECASE,
    ),
    "content-addressed-workdir": re.compile(r"content-addressed (scratch|workdir)"),
    "knowledge-dir-head": re.compile(r"knowledges/<[^>]+>/"),
    "five-modes": re.compile(r"\bfive (execution )?modes\b", re.IGNORECASE),
}

# Filled with the migrate_cmd.py legacy readers that still name old shapes.
# Each reason names the legacy shape that reader still has to mention.
SRC_ALLOWLIST: dict[tuple[str, str], str] = {
    ("cli/migrate_cmd.py", "<module-docstring>"): (
        "migrate layout still names the derived children index it drops"
    ),
}

_MIGRATE_MARK = "`molab migrate"


def _scrub(line: str, key: str) -> str:
    span = ALLOWED_SPANS.get(key)
    if span is not None:
        line = line.replace(span[0], "")
    return line


def _doc_keys(line: str) -> list[str]:
    migrate = _MIGRATE_MARK in line
    found: list[str] = []
    for key, pattern in RETIRED.items():
        if migrate and key in MIGRATE_LINE_EXEMPT:
            continue
        if pattern.search(_scrub(line, key)):
            found.append(key)
    return found


def _src_keys(line: str) -> list[str]:
    return [key for key, pattern in SRC_RETIRED.items() if pattern.search(line)]


def _rel(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def _require_roots(roots: dict[str, Path]) -> None:
    missing = [label for label, path in roots.items() if not path.exists()]
    if missing:
        raise AssertionError(f"missing documentation root: {', '.join(missing)}")


def _require_named_files(table: dict[str, str], *, label: str) -> None:
    missing = [key for key in table if not (ROOT / key).is_file()]
    if missing:
        raise AssertionError(f"{label} names a missing file: {', '.join(missing)}")


def _doc_files(roots: dict[str, Path] | None = None) -> list[Path]:
    chosen = roots if roots is not None else ROOTS
    _require_roots(chosen)
    _require_named_files(EXCLUDED, label="EXCLUDED")
    seen: set[Path] = set()
    files: list[Path] = []
    for root in chosen.values():
        candidates = (
            [root] if root.is_file() else [path for path in root.rglob("*") if path.is_file()]
        )
        for path in candidates:
            if path.suffix != ".md" and path.name != "CLAUDE.md":
                continue
            real = path.resolve()
            if real in seen:
                continue
            seen.add(real)
            if _rel(real) in EXCLUDED:
                continue
            files.append(real)
    return files


def _doc_offenders(files: list[Path] | None = None) -> list[str]:
    offenders: list[str] = []
    for path in files if files is not None else _doc_files():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for key in _doc_keys(line):
                offenders.append(f"{_rel(path)}:{number}: {key}")
    return offenders


def _module_spans(tree: ast.AST) -> dict[str, tuple[int, int]]:
    spans: dict[str, tuple[int, int]] = {}
    body = getattr(tree, "body", [])
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(getattr(body[0], "value", None), ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        node = body[0]
        spans["<module-docstring>"] = (node.lineno, node.end_lineno or node.lineno)
    for node in body:
        name: str | None = None
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = node.name
        elif (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            name = node.targets[0].id
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name = node.target.id
        if name is not None:
            spans[name] = (node.lineno, getattr(node, "end_lineno", None) or node.lineno)
    return spans


def _symbol_at(spans: dict[str, tuple[int, int]], line: int) -> str | None:
    for name, (start, end) in spans.items():
        if start <= line <= end:
            return name
    return None


def _source_offenders(
    text: str,
    rel: str,
    allowlist: dict[tuple[str, str], str],
) -> list[str]:
    tree = ast.parse(text)
    spans = _module_spans(tree)
    offenders: list[str] = []
    for number, line in enumerate(text.splitlines(), start=1):
        symbol = _symbol_at(spans, number)
        for key in _src_keys(line):
            if symbol is not None and (rel, symbol) in allowlist:
                continue
            offenders.append(f"{rel}:{number}: {key}")
    return offenders


def _src_files() -> list[Path]:
    return [path for path in SRC.rglob("*.py") if "__pycache__" not in path.parts]


def _allowlist_stale(allowlist: dict[tuple[str, str], str]) -> list[str]:
    stale: list[str] = []
    for (rel, symbol), reason in allowlist.items():
        path = SRC / rel
        if not path.is_file():
            stale.append(f"{rel}:{symbol}: missing file")
            continue
        if not reason.strip():
            stale.append(f"{rel}:{symbol}: empty reason")
        spans = _module_spans(ast.parse(path.read_text(encoding="utf-8")))
        if symbol not in spans:
            stale.append(f"{rel}:{symbol}: not a module-level symbol")
    return stale


class TestVocabularyDetectors:
    @pytest.mark.parametrize(
        ("line", "key"),
        [
            ("per-scope `assets.json` manifest", "assets-manifest"),
            ("`Bundle.walk`", "bundle"),
            ("`RunMetadata.workflow_snapshot` is a read-only legacy field", "workflow-snapshot"),
            ("`executions/<id>/fresh.json`", "fresh-marker"),
            ('"workflow_source": "train.py"', "workflow-source-string"),
            ("`knowledges/<id>/` + `note.json` + `index.md`", "knowledge-dir-head"),
            ("runs/run-<id>/", "run-path-id"),
            ("`exec-<run_id>[-N]`", "run-path-id"),
            ("`ReferenceStore`", "reference-store"),
            ("`RETRY` after a failure", "retry-mode"),
            ("five execution modes", "five-modes"),
            ("`--resume` reopens the existing execution", "resume-reopens"),
            (
                "| `--resume` | `failed` / `cancelled` | Reopens the existing execution |",
                "resume-reopens",
            ),
            ("`set_workflow_recoverer`", "recoverer-seam"),
            ("cache at `run_dir/cache`", "path-keyed-cache"),
            ("`.molab/cache/<run-path>/`", "path-keyed-cache"),
            ("`@concept_type`", "concept-registry"),
            ("the concept-type registry", "concept-registry"),
            ("`register_concept_type`", "concept-registry"),
            ("`workflow_id` (topology hash)", "workflow-identity"),
            ("`read_node_outputs`", "journal-legacy"),
            ("`error.txt`", "run-exec-fields"),
            ("`KnowledgeItem`", "knowledge-shapes"),
        ],
    )
    def test_positive_sample_hits_its_key(self, line: str, key: str) -> None:
        assert key in _doc_keys(line)

    @pytest.mark.parametrize(
        "line",
        [
            "Bundled SPA preview",
            "Bundles with a mismatched version",
            "RETRYABLE_STATUSES",
            "Agent(retries=N)",
            "`ExecutionMode.RETRY` is stored as `RERUN`",
            "[Guide](../guide/index.md)",
            "knowledges/tg-index.md",
            "├── index.md   ← workspace narrative",
            "task_board.json",
            "reduces the greens into a single `workflow_source` / `test_source`",
            "<scope>/assets/<dir>/asset.json",
            "reopen the workspace explorer",
            "target_workflow_id",
            "bound_workflow_id",
            '`"workflow_snapshot": None`',
            "`ErrorInfo` (removed; read `Execution.error`)",
            "`.molab/runs/<run-id>/cache/`",
            '`search(q, concept_type="Finding")`',
            "four execution modes",
            "read_journal",
            "the asset store",
            "knowledge document",
        ],
    )
    def test_negative_sample_hits_nothing(self, line: str) -> None:
        assert _doc_keys(line) == []

    def test_migrate_line_exempts_only_the_legacy_shape_it_names(self) -> None:
        assets = "`molab migrate assets` rewrites every per-scope `assets.json`"
        knowledge = "`molab migrate knowledge` folds `knowledges/<id>/` + `note.json`"
        layout = "`molab migrate layout` drops `fresh.json` and `error.txt`"
        assert "assets-manifest" not in _doc_keys(assets)
        assert "knowledge-dir-head" not in _doc_keys(knowledge)
        assert "fresh-marker" not in _doc_keys(layout)
        assert "run-exec-fields" not in _doc_keys(layout)
        bare = "per-scope assets.json manifest"
        assert "assets-manifest" in _doc_keys(bare)
        kept = "`molab migrate layout` keeps `workflow_snapshot`"
        assert "workflow-snapshot" in _doc_keys(kept)

    @pytest.mark.parametrize(
        ("line", "key"),
        [
            ("content-addressed workdir", "content-addressed-workdir"),
            ("children-index", "children-index"),
            ("children index", "children-index"),
            ("molab.agent.mcp.store", "agent-store"),
            ("runs/run-001", "run-path-id"),
            ('cache at run_dir / "cache"', "path-keyed-cache"),
            ("knowledges/<id>/note.md", "knowledge-dir-head"),
            ("five execution modes", "five-modes"),
            ("--resume reopens the existing execution", "resume-reopens"),
        ],
    )
    def test_source_positive_sample(self, line: str, key: str) -> None:
        assert key in _src_keys(line)

    def test_source_negative_samples(self) -> None:
        assert _src_keys("`.molab/runs/<run-id>/cache/`") == []
        assert _src_keys("knowledges/tg-index.md") == []
        assert _src_keys("four execution modes") == []
        assert _src_keys("reopen the workspace explorer") == []

    def test_allowlist_is_a_symbol_span_not_a_file_exemption(self) -> None:
        text = '''"""Migrate layout."""

_LEGACY_X = "children index"

def cmd():
    typer.Option(help="children index")
'''
        allow = {("cli/migrate_cmd.py", "_LEGACY_X"): "reads the legacy children index"}
        hits = _source_offenders(text, "cli/migrate_cmd.py", allow)
        assert hits == ["cli/migrate_cmd.py:6: children-index"]
        stale = _allowlist_stale({("cli/migrate_cmd.py", "missing_symbol"): "reads fresh.json"})
        assert stale == ["cli/migrate_cmd.py:missing_symbol: not a module-level symbol"]

    def test_tables_name_real_keys(self) -> None:
        assert set(ALLOWED_SPANS) <= set(RETIRED)
        assert set(RETIRED) >= MIGRATE_LINE_EXEMPT
        for key, (span, reason) in ALLOWED_SPANS.items():
            assert span
            assert reason
            assert key in RETIRED


class TestDocsVocabulary:
    def test_roots_and_exclusions_exist(self) -> None:
        _require_roots(ROOTS)
        _require_named_files(EXCLUDED, label="EXCLUDED")

    def test_a_missing_root_fails(self) -> None:
        with pytest.raises(AssertionError, match="missing documentation root"):
            _require_roots({"missing": ROOT / "no-such-docs-root"})

    def test_an_exclusion_that_names_nothing_fails(self) -> None:
        with pytest.raises(AssertionError, match="names a missing file"):
            _require_named_files({"no-such.md": "absent"}, label="EXCLUDED")

    def test_a_resolved_path_is_scanned_once(self) -> None:
        files = _doc_files()
        assert len(files) == len(set(files))

    def test_docs_have_no_retired_vocabulary(self) -> None:
        offenders = _doc_offenders()
        assert offenders == []


class TestSourceDocstringVocabulary:
    def test_allowlist_names_real_symbols(self) -> None:
        assert _allowlist_stale(SRC_ALLOWLIST) == []

    def test_source_prose_has_no_retired_vocabulary(self) -> None:
        offenders: list[str] = []
        for path in _src_files():
            rel = path.relative_to(SRC).as_posix()
            offenders.extend(
                _source_offenders(path.read_text(encoding="utf-8"), rel, SRC_ALLOWLIST)
            )
        assert offenders == []
