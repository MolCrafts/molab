"""Repo-file goldens for drop-harness-02-docs.

The Python harness is deleted (D86, drop-harness-01-src); the public docs, the
README, the examples index, ``.claude/notes`` and CLAUDE.md must say so. These
goldens pin the repo files a later edit could silently regress.

1. The nine deleted doc paths are absent by ``os.path.lexists`` (a dangling
   symlink counts as present):
   ``docs/en/architecture/{agent,harness,plan-mode}.md``,
   ``docs/en/concept/agent.md``, ``docs/en/guide/plan-mode.md``,
   ``docs/zh/architecture/{plan-mode,agent}.md``, ``docs/zh/guide/plan-mode.md``,
   ``docs/zh/concept/agent.md``.
   1b. ``docs/`` holds no broken symlink.
2. No ``project.nav`` entry of ``zensical.toml`` / ``zensical.zh.toml`` ends in
   ``agent.md`` / ``harness.md`` / ``plan-mode.md``.
   2b. No ``docs/**/*.md`` links ``(concept|architecture|guide)/(agent|harness|plan-mode)``
   (file or directory form).
3. Zero hits of the harness-vocabulary regex in ``docs/**/*.md`` (except
   ``docs/*/development/``), ``README.md`` and ``examples/**/*.{py,md}``.
4. No ``examples/**/*.py`` imports ``molab.harness`` or ``molab.agent``.
5. CLAUDE.md: every line mentioning "harness" is a ``drop-harness`` reference;
   the harness/agent tokens are gone; ``ctx.files`` lands in
   ``executions/eNN/work/``; the D-1 / D-2 named
   exceptions, the three entry-point groups and the four inversion seams are
   present; the layout tree keeps its ``work/`` row. (D-6 was time-boxed until
   ``drop-harness-ui`` landed; since ce500be7 its sentence is asserted absent.)
6. The three harness notes are absent; ``integration.md`` has no "harness",
   no ChangeProposal / InteractiveLoop / AgentGateway, no reference to a
   deleted section, keeps "Workspace Copilot" + ``workspace/copilot.py`` and
   labels its retired invariants ``*Retired (D86).*``; the notes README names
   no deleted note.

Expected stdout (exactly this line, exit code 0):

    drop-harness-02-docs: ok

Provenance: goldens hard-coded from the spec
``.claude/specs/drop-harness-02-docs.md`` (Testing strategy, "Regression
example") and acceptance ac-006, recorded 2026-09-28 on branch
feat/knowledge-crossref. Reads repository files only — stdlib (pathlib, re,
tomllib, ast, os), no molab import, no subprocess, no network.
"""

from __future__ import annotations

import ast
import os
import re
import sys
import tomllib
from collections.abc import Iterator
from pathlib import Path

_GOLDEN_OK = "drop-harness-02-docs: ok"
_ROOT = Path(__file__).resolve().parent.parent

_DELETED_DOCS = (
    "docs/en/architecture/agent.md",
    "docs/en/architecture/harness.md",
    "docs/en/architecture/plan-mode.md",
    "docs/en/concept/agent.md",
    "docs/en/guide/plan-mode.md",
    "docs/zh/architecture/plan-mode.md",
    "docs/zh/guide/plan-mode.md",
    "docs/zh/architecture/agent.md",
    "docs/zh/concept/agent.md",
)
_NAV_FILES = ("zensical.toml", "zensical.zh.toml")
_NAV_DELETED_SUFFIXES = ("agent.md", "harness.md", "plan-mode.md")
_DOC_LINK = re.compile(r"(concept|architecture|guide)/(agent|harness|plan-mode)(\.md|/)")
_HARNESS_VOCAB = re.compile(
    r"molab (plan|agent|curate|harness)\b|molab\.harness|molab\.agent\b|agent\.model"
    r"|pydantic[-_]ai|molab\[agent"
)
_BANNED_IMPORT_PREFIXES = ("molab.harness", "molab.agent")

_CLAUDE_ABSENT = (
    "agent-assisted",
    "PydanticAI",
    "agent.model",
    "bridged into",
    "LLM keys",
    "register_folder_type",
    "Agent sessions still use",
    "plan-book",
    "arbitrary_types_allowed",
    "products under `executions/eNN/out/`",
    "Time-boxed exception (D-6",
)
_CLAUDE_PRESENT = (
    "D-1",
    "D-2",
    "molab.cli_plugins",
    "molab.server_plugins",
    "molab.ui_plugins",
    "set_run_executor",
    "metrics_seam",
    "set_workflow_executor",
    "set_concept_created_hook",
)

_DELETED_NOTES = (
    ".claude/notes/harness-plugins.md",
    ".claude/notes/harness-goal.md",
    ".claude/notes/vision-gap-2026-07.md",
)
_INTEGRATION_ABSENT = ("ChangeProposal", "InteractiveLoop", "AgentGateway")
_INTEGRATION_PRESENT = ("Workspace Copilot", "workspace/copilot.py", "*Retired (D86).*")
_DELETED_SECTION_REF = re.compile(r"§[68]\b|§7\.[2356]\b")
_NOTES_README_ABSENT = ("harness-plugins", "harness-goal", "vision-gap")


def _rel(path: Path) -> str:
    return path.relative_to(_ROOT).as_posix()


def _readable(root: Path, pattern: str) -> Iterator[Path]:
    """Files under ``root`` matching ``pattern``; broken symlinks are skipped (golden 1b)."""
    for path in sorted(root.rglob(pattern)):
        if path.is_symlink() and not path.exists():
            continue
        if path.is_file():
            yield path


def _hits(pattern: re.Pattern[str], paths: list[Path]) -> list[str]:
    found: list[str] = []
    for path in paths:
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                found.append(f"{_rel(path)}:{lineno}: {line.strip()}")
    return found


def _check_deleted_docs() -> None:
    alive = [p for p in _DELETED_DOCS if os.path.lexists(_ROOT / p)]
    assert alive == [], alive
    broken = [_rel(p) for p in (_ROOT / "docs").rglob("*") if p.is_symlink() and not p.exists()]
    assert broken == [], broken


def _nav_leaves(node: object) -> Iterator[str]:
    if isinstance(node, str):
        yield node
    elif isinstance(node, list):
        for item in node:
            yield from _nav_leaves(item)
    elif isinstance(node, dict):
        for value in node.values():
            yield from _nav_leaves(value)


def _check_nav() -> None:
    for name in _NAV_FILES:
        with (_ROOT / name).open("rb") as fh:
            nav = tomllib.load(fh)["project"]["nav"]
        leaves = list(_nav_leaves(nav))
        print(f"{name}: {len(leaves)} nav leaves", file=sys.stderr)
        stale = [leaf for leaf in leaves if leaf.endswith(_NAV_DELETED_SUFFIXES)]
        assert stale == [], (name, stale)
    links = _hits(_DOC_LINK, list(_readable(_ROOT / "docs", "*.md")))
    assert links == [], links


def _check_vocabulary() -> None:
    docs = [
        p
        for p in _readable(_ROOT / "docs", "*.md")
        if p.relative_to(_ROOT / "docs").parts[1:2] != ("development",)
    ]
    examples = [*_readable(_ROOT / "examples", "*.py"), *_readable(_ROOT / "examples", "*.md")]
    scanned = [*docs, _ROOT / "README.md", *examples]
    print(f"vocabulary scan: {len(scanned)} files", file=sys.stderr)
    hits = _hits(_HARNESS_VOCAB, scanned)
    for hit in hits:
        print(f"vocabulary hit: {hit}", file=sys.stderr)
    assert hits == [], hits


def _imported_modules(tree: ast.AST) -> Iterator[str]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None and node.level == 0:
            yield node.module


def _check_example_imports() -> None:
    bad: list[str] = []
    for path in _readable(_ROOT / "examples", "*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        bad.extend(
            f"{_rel(path)}: {module}"
            for module in _imported_modules(tree)
            if module.startswith(_BANNED_IMPORT_PREFIXES)
        )
    assert bad == [], bad


def _check_claude_md() -> None:
    path = _ROOT / "CLAUDE.md"
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    stray = [
        f"CLAUDE.md:{n}"
        for n, line in enumerate(lines, 1)
        if "harness" in line.lower() and "drop-harness" not in line
    ]
    assert stray == [], stray
    present_absent = [token for token in _CLAUDE_ABSENT if token in text]
    assert present_absent == [], present_absent
    missing = [token for token in _CLAUDE_PRESENT if token not in text]
    assert missing == [], missing
    assert any("ctx.files" in line and "executions/eNN/work/" in line for line in lines)
    assert any(re.search(r"[│├└]──\s+work/", line) for line in lines), "layout tree lost work/"


def _check_notes() -> None:
    alive = [p for p in _DELETED_NOTES if os.path.lexists(_ROOT / p)]
    assert alive == [], alive
    integration = (_ROOT / ".claude/notes/integration.md").read_text(encoding="utf-8")
    assert "harness" not in integration.lower()
    kept = [token for token in _INTEGRATION_ABSENT if token in integration]
    assert kept == [], kept
    ref = _DELETED_SECTION_REF.search(integration)
    assert ref is None, ref
    missing = [token for token in _INTEGRATION_PRESENT if token not in integration]
    assert missing == [], missing
    readme = (_ROOT / ".claude/notes/README.md").read_text(encoding="utf-8")
    named = [token for token in _NOTES_README_ABSENT if token in readme]
    assert named == [], named


def main() -> None:
    _check_deleted_docs()
    _check_nav()
    _check_vocabulary()
    _check_example_imports()
    _check_claude_md()
    _check_notes()
    print(_GOLDEN_OK)


if __name__ == "__main__":
    main()
