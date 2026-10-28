"""``molab agents sync`` — the workspace's guide for coding agents, rendered from code.

A coding agent opening a workspace reads the root ``AGENTS.md`` (Claude Code
reads ``CLAUDE.md``, which imports it with a ``@AGENTS.md`` line). molab owns
one marked block of that file, between :data:`BEGIN_MARKER` and
:data:`END_MARKER`, and rewrites only that block; everything outside it is the
user's. The block is rendered from the same constants the writers and the
validator use — the naming law, the declared attempt directories and their
purposes, the six knowledge classes — so it cannot describe a layout molab
does not write. The "to do X, run Y" table lists only commands that exist;
a test resolves each one in the CLI.

:func:`sync_agent_files` is the whole sync, and it is idempotent: the block,
the ``@AGENTS.md`` line, the missing managed ``.gitignore`` rules, and the
validation baseline when there is none (D91).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Final

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from molab.workspace import Workspace

__all__ = [
    "AGENT_COMMANDS",
    "AGENT_PYTHON",
    "BEGIN_MARKER",
    "CLAUDE_IMPORT_LINE",
    "END_MARKER",
    "AgentSyncResult",
    "render_agent_guide",
    "splice_block",
    "sync_agent_files",
]

BEGIN_MARKER: Final = "<!-- molab:begin -->"
END_MARKER: Final = "<!-- molab:end -->"
CLAUDE_IMPORT_LINE: Final = "@AGENTS.md"

#: ``(what you want to do, the molab command that does it)``. Every command
#: here resolves in the ``molab`` CLI (pinned by a test).
AGENT_COMMANDS: Final[tuple[tuple[str, str], ...]] = (
    ("See where things are", "molab index show [-p P] [-e E] [--run R] --frontmatter"),
    ("Create a project", "molab project create NAME"),
    ("Create an experiment", "molab experiment create PROJECT --name NAME"),
    ("Create a run", "molab runs create PROJECT EXPERIMENT --params '{...}'"),
    ("Execute a workflow", "molab run workflow.py"),
    (
        "Record a job that ran outside molab",
        "molab runs adopt PROJECT EXPERIMENT RUN --product TASK=PATH --log FILE "
        "--job FILE --source FILE [--params '{...}']",
    ),
    (
        "Write the narrative of a record",
        "molab index write [-p P] [-e E] [--run R] --from FILE",
    ),
    (
        "Write a knowledge document",
        "molab knowledge write NAME TEXT --on HOST --class CLASS --created-by AGENT",
    ),
    ("Import external data", "molab asset import TITLE PATH --project PROJECT"),
    ("Empty old scratch entries", "molab scratch clean --older-than 7d"),
    ("Rebuild every derived index block", "molab index sync"),
    ("Ask whether a write is legal", "molab check path PATH --op write --json"),
    ("Check your changes before finishing", "molab validate --new-only"),
)

#: ``(what you want to do, the Python line that does it)``, rendered in the
#: same table after :data:`AGENT_COMMANDS`. Every name imported here exists
#: at the top level of ``molab`` (pinned by a test).
AGENT_PYTHON: Final[tuple[tuple[str, str], ...]] = (
    # D92: copied into the current execution's stdout.log / stderr.log.
    ("Print into the run's record", "from molab import print"),
)


class AgentSyncResult(BaseModel):
    """What one :func:`sync_agent_files` changed."""

    model_config = ConfigDict(frozen=True)

    agents_written: bool
    claude_written: bool
    ignore_rules_added: tuple[str, ...] = ()
    baseline_written: bool = False


def _md(text: str) -> str:
    """An RST-flavoured docstring line as markdown (double backticks -> single)."""
    return text.replace("``", "`")


def _layout() -> str:
    from molab.knowledge.naming import KNOWLEDGE_CONTAINER
    from molab.workspace.entity_record import INDEX_FILENAME
    from molab.workspace.execution_dirs import list_execution_dirs
    from molab.workspace.execution_repository import EXECUTION_RECORD_FILENAME
    from molab.workspace.naming import (
        AGENT_GUIDE_FILENAME,
        ASSET_CONTAINER,
        CLAUDE_GUIDE_FILENAME,
        EXECUTION_CONTAINER,
        EXPERIMENT_CONTAINER,
        PROJECT_CONTAINER,
        RUN_CONTAINER,
        SCRATCH_CONTAINER,
        WORKFLOW_SCRIPT_FILENAME,
        execution_slug,
    )

    rows: list[tuple[str, str]] = [
        ("./", ""),
        (f"├── {INDEX_FILENAME}", "workspace record + narrative; start here"),
        (f"├── {AGENT_GUIDE_FILENAME}, {CLAUDE_GUIDE_FILENAME}", "this guide"),
        (f"├── {KNOWLEDGE_CONTAINER}/<slug>.md", "knowledge documents (also at every level below)"),
        (f"└── {PROJECT_CONTAINER}/<project>/", "directory name = slug of the project name"),
        (f"    ├── {INDEX_FILENAME}", "project record"),
        (f"    ├── {ASSET_CONTAINER}/", "imported data (molab asset import)"),
        (f"    └── {EXPERIMENT_CONTAINER}/<experiment>/", ""),
        (f"        ├── {INDEX_FILENAME}", "experiment record"),
        (f"        ├── {WORKFLOW_SCRIPT_FILENAME}", "the experiment's workflow script"),
        (f"        ├── {SCRATCH_CONTAINER}/", "quick tests only; disposable, gitignored"),
        (f"        └── {RUN_CONTAINER}/<key=value_…>/", "directory name = the run's parameters"),
        (f"            ├── {INDEX_FILENAME}", "run record (parameters) + attempt list"),
        (f"            └── {EXECUTION_CONTAINER}/{execution_slug(1)}/", "one attempt"),
        (f"                ├── {EXECUTION_RECORD_FILENAME}", "the attempt record (molab's)"),
        ("                ├── run.log, traceback.txt", "the attempt's log and failure"),
    ]
    dirs = list_execution_dirs()
    for position, directory in enumerate(dirs):
        branch = "└──" if position == len(dirs) - 1 else "├──"
        rows.append((f"                {branch} {directory.name}/", _md(directory.purpose)))
    width = max(len(left) for left, _ in rows) + 2
    lines = [f"{left:<{width}}{note}".rstrip() if note else left for left, note in rows]
    return "\n".join(lines)


def _knowledge_classes() -> str:
    from molab.knowledge.concepts import _PRODUCTS

    lines = ["| class | what it is |", "|---|---|"]
    for name, klass in _PRODUCTS.items():
        doc = (klass.__doc__ or "").strip().splitlines()
        lines.append(f"| `{name}` | {_md(doc[0]) if doc else ''} |")
    return "\n".join(lines)


def _commands() -> str:
    lines = ["| to | run |", "|---|---|"]
    lines.extend(f"| {task} | `{command}` |" for task, command in AGENT_COMMANDS + AGENT_PYTHON)
    return "\n".join(lines)


def render_agent_guide(ws: Workspace) -> str:
    """The managed block of ``AGENTS.md`` for *ws*, markers included."""
    from molab.knowledge.naming import KNOWLEDGE_CONTAINER
    from molab.workspace.naming import SCRATCH_CONTAINER

    name = ws.metadata.name
    sections = [
        BEGIN_MARKER,
        f"## molab workspace: {name}",
        "",
        "molab writes this block (`molab agents sync`) and rewrites it; keep your own "
        "notes outside the markers. Every rule below is checked by `molab check`, "
        "which the molcrafts-harness hooks call before each write and when a session "
        "ends.",
        "",
        "### Find your way",
        "",
        "Start at `./index.md`. Its YAML frontmatter has an `index:` block: follow "
        "`index.children[].path` down to each project, experiment and run. A run's "
        "`index.executions[]` lists its attempts (`path`, `status`, `out`, `artifacts`). "
        f"`index.{KNOWLEDGE_CONTAINER}` lists a level's knowledge documents. An "
        "experiment's `index.entrypoint` names its workflow code.",
        "",
        "### The frontmatter is molab's",
        "",
        "The frontmatter of each `index.md` is that level's record plus the derived "
        "`index:` block. molab writes both; edit only the body below the closing "
        "`---` (or use `molab index write`). Never write `index.md` to create a "
        "record, a `<kind>.json` / `meta.json` record, or anything an attempt owns "
        "(`execution.json`, logs, `source/`, `artifacts/`, `jobs/`, `checkpoints/`); "
        "use the command in the table below.",
        "",
        "### Layout",
        "",
        "```text",
        _layout(),
        "```",
        "",
        "Anything else at a level is a stray, and `molab validate` reports it.",
        "",
        f"### `{SCRATCH_CONTAINER}/`",
        "",
        f"Each experiment may have a `{SCRATCH_CONTAINER}/` for quick tests: a smoke run, "
        "a throwaway plot. Nothing in it is cited and it is not in git. A long job, "
        "or anything a result depends on, becomes a run: execute it through molab, "
        "or record a finished job with `molab runs adopt`. `molab scratch clean` "
        "empties old entries.",
        "",
        "### Knowledge documents",
        "",
        f"A document is `<level>/{KNOWLEDGE_CONTAINER}/<slug>.md` whose frontmatter "
        "names one of six classes (`class:`). Write them with `molab knowledge write`.",
        "",
        _knowledge_classes(),
        "",
        "### To do this, run that",
        "",
        _commands(),
        "",
        "Before you finish, run `molab validate --new-only` and fix what it reports.",
        END_MARKER,
    ]
    return "\n".join(sections) + "\n"


def splice_block(text: str, block: str) -> str:
    """*text* with its managed block replaced by *block* (appended when absent).

    Everything outside the markers is kept byte for byte.
    """
    start = text.find(BEGIN_MARKER)
    end = text.find(END_MARKER, start + len(BEGIN_MARKER)) if start >= 0 else -1
    if start >= 0 and end >= 0:
        tail = text[end + len(END_MARKER) :]
        if tail.startswith("\n"):
            tail = tail[1:]
        return f"{text[:start]}{block}{tail}"
    if not text:
        return block
    separator = "" if text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
    return f"{text}{separator}{block}"


def _write_if_changed(path: Path, text: str) -> bool:
    from molab.atomicio import atomic_write_text

    try:
        current = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        current = None
    if current == text:
        return False
    atomic_write_text(path, text)
    return True


def sync_agent_files(ws: Workspace) -> AgentSyncResult:
    """Bring *ws*'s agent files up to date; idempotent. Local workspaces only.

    * ``AGENTS.md``: the managed block rendered by :func:`render_agent_guide`,
      everything outside the markers preserved.
    * ``CLAUDE.md``: gains a ``@AGENTS.md`` line when it has none.
    * ``.gitignore``: the managed rules it lacks are appended.
    * ``.molab/validate-baseline.json``: written when absent, so ``molab
      validate --new-only`` holds agents to what they add, not to old debt.

    Raises:
        NotImplementedError: *ws* is not on the local filesystem.
    """
    from molab.workspace.fs_local import LocalFileSystem
    from molab.workspace.history import GitHistory
    from molab.workspace.naming import AGENT_GUIDE_FILENAME, CLAUDE_GUIDE_FILENAME

    from .workspace_check import baseline_path, write_baseline

    if not isinstance(ws.fs, LocalFileSystem):
        raise NotImplementedError("molab agents sync writes local files; the workspace is remote")
    root = Path(str(ws.resolve()))
    agents = root / AGENT_GUIDE_FILENAME
    try:
        current = agents.read_text(encoding="utf-8")
    except FileNotFoundError:
        current = ""
    agents_written = _write_if_changed(agents, splice_block(current, render_agent_guide(ws)))

    claude = root / CLAUDE_GUIDE_FILENAME
    try:
        memory = claude.read_text(encoding="utf-8")
    except FileNotFoundError:
        memory = ""
    claude_written = False
    if CLAUDE_IMPORT_LINE not in {line.strip() for line in memory.splitlines()}:
        prefix = memory if not memory or memory.endswith("\n") else f"{memory}\n"
        claude_written = _write_if_changed(claude, f"{prefix}{CLAUDE_IMPORT_LINE}\n")

    added = GitHistory(root).ensure_ignore_rules()
    baseline_written = False
    if not baseline_path(ws).exists():
        write_baseline(ws)
        baseline_written = True
    return AgentSyncResult(
        agents_written=agents_written,
        claude_written=claude_written,
        ignore_rules_added=added,
        baseline_written=baseline_written,
    )
