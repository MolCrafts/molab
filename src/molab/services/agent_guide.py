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
    "AGENT_CONTEXT",
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
    (
        "Preview what a workflow script would run, writing nothing",
        "molab workflow dry-run workflow.py --json",
    ),
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
        "molab knowledge write NAME TEXT --on HOST --class CLASS --source SOURCE --record JSON --created-by AGENT",
    ),
    (
        "Report back as a dispatched worker",
        "molab knowledge write NAME TEXT --on HOST --class Report --source SOURCE "
        '--record \'{"kind": "worker_report", ...}\' --created-by WORKER',
    ),
    ("Import external data", "molab asset import TITLE PATH --project PROJECT"),
    ("Empty old scratch entries", "molab scratch clean --older-than 7d"),
    ("Rebuild every derived index block", "molab index sync"),
    ("Ask whether a write is legal", "molab check path PATH --op write --json"),
    (
        "Ask whether a shell command's writes are legal",
        "molab check command --command COMMAND --cwd DIR --json",
    ),
    ("Check your changes before finishing", "molab validate --new-only"),
)

#: ``(what you want to do, the Python line that does it)``, rendered in the
#: same table after :data:`AGENT_COMMANDS`. Every name imported here exists
#: at the top level of ``molab`` (pinned by a test). Computation is offered
#: only as a workflow (``molab run``); ``molab.track()`` stays an API for code
#: molab does not run, not a path the guide steers agents to.
AGENT_PYTHON: Final[tuple[tuple[str, str], ...]] = (
    # D92: copied into the current execution's stdout.log / stderr.log.
    ("Print into the run's record", "from molab import print"),
)

#: ``(what you want to do, the call that does it)`` on the ``ctx`` molab hands
#: the code — ``run.start()``'s or a workflow task's — rendered after
#: :data:`AGENT_PYTHON`. Every call resolves on both contexts (pinned by a test).
AGENT_CONTEXT: Final[tuple[tuple[str, str], ...]] = (
    # D93: written live into executions/eNN/metrics.mlp.jsonl.
    ("Record training data", "ctx.metrics.scalar(...)"),
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
        VALUE_CONTAINER,
        WORKFLOW_LIB_CONTAINER,
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
        (f"    ├── {ASSET_CONTAINER}/<title>/", "imported files (molab asset import)"),
        (f"    └── {EXPERIMENT_CONTAINER}/<experiment>/", ""),
        (f"        ├── {INDEX_FILENAME}", "experiment record"),
        (f"        ├── {WORKFLOW_SCRIPT_FILENAME}", "the experiment's workflow script"),
        (
            f"        ├── {WORKFLOW_LIB_CONTAINER}/",
            "the workflow's own modules, once one file is too big",
        ),
        (
            f"        ├── {ASSET_CONTAINER}/<run>--<title>/",
            "a run's final products (ctx.register); a later attempt replaces them",
        ),
        (f"        ├── {SCRATCH_CONTAINER}/", "quick tests only; disposable, gitignored"),
        (f"        └── {RUN_CONTAINER}/<key=value_…>/", "directory name = the run's parameters"),
        (f"            ├── {INDEX_FILENAME}", "run record (parameters) + attempt list"),
        (
            f"            ├── {VALUE_CONTAINER}/<sha256>.json|.pkl",
            "every task input/output, stored once (molab's; journals cite them by ref)",
        ),
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


def _worker_records() -> str:
    """The two worker-round records, by class and ``kind``, with their fields."""
    from molab.knowledge.worker_report import WORKER_RECORD_CLASSES, BriefRecord, WorkerReportRecord

    models = {"worker_report": WorkerReportRecord, "brief": BriefRecord}
    lines = ["| class | `kind` | record fields |", "|---|---|---|"]
    for kind, owner in WORKER_RECORD_CLASSES.items():
        fields = ", ".join(f"`{name}`" for name in models[kind].model_fields if name != "kind")
        lines.append(f"| `{owner}` | `{kind}` | {fields} |")
    return "\n".join(lines)


def _commands() -> str:
    lines = ["| to | run |", "|---|---|"]
    rows = AGENT_COMMANDS + AGENT_PYTHON + AGENT_CONTEXT
    lines.extend(f"| {task} | `{command}` |" for task, command in rows)
    return "\n".join(lines)


def render_agent_guide(ws: Workspace) -> str:
    """The managed block of ``AGENTS.md`` for *ws*, markers included."""
    from molab.knowledge.naming import KNOWLEDGE_CONTAINER
    from molab.workspace.naming import (
        SCRATCH_CONTAINER,
        WORKFLOW_LIB_CONTAINER,
        WORKFLOW_SCRIPT_FILENAME,
    )

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
        "### Tools",
        "",
        "Prefer the MolCrafts tool that owns the step: molpy for structure, force "
        "fields and trajectories, molplot for figures, molvis for molecules, molq for "
        "jobs, and molab for this workspace. Reading, searching, editing, git, "
        "interpreters, package managers, and tests stay available. When a MolCrafts "
        "API for a step is missing, report that gap and continue the rest of the task.",
        "",
        "### Find your way",
        "",
        "Start at `./index.md`. Its YAML frontmatter has an `index:` block: follow "
        "`index.children[].path` down to each project, experiment and run. A run's "
        "`index.executions[]` lists its attempts (`path`, `status`, `out`). "
        f"`index.{KNOWLEDGE_CONTAINER}` lists a level's knowledge documents. An "
        "experiment's `index.entrypoint` names its workflow code.",
        "",
        "### The frontmatter is molab's",
        "",
        "The frontmatter of each `index.md` is that level's record plus the derived "
        "`index:` block. molab writes both; edit only the body below the closing "
        "`---` (or use `molab index write`). Never write `index.md` to create a "
        "record, a `<kind>.json` / `meta.json` record, or anything an attempt owns "
        "(`execution.json`, logs, `metrics.mlp.jsonl`, `source/`, `jobs/`, `checkpoints/`); "
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
        "### Keep the workspace tidy",
        "",
        "- Register only final products with `ctx.register`: structures, force fields, "
        "solver inputs, figures. Logs and per-task evidence stay in the attempt's `out/`; "
        "molab refuses a log.",
        "- A run's product has one slot, `assets/<run>--<title>/`. Re-running replaces it "
        "and keeps its `molab:asset/<id>`, so a citation always names the current bytes.",
        "- One subject is one document. Rewrite it under the same name; never add `-v2`. "
        "Delete a document that is wrong or superseded; git keeps the old text.",
        "- A Report cites the `molab:asset/<id>` of each product it describes, so molab's "
        "viewers render it. Never link a `localhost` server.",
        f"- When `{WORKFLOW_SCRIPT_FILENAME}` grows past a few hundred lines, move its tasks "
        f"into modules under `{WORKFLOW_LIB_CONTAINER}/`.",
        "- Create an experiment when its stage starts, not ahead of the roadmap.",
        "",
        "### Knowledge documents",
        "",
        f"A document is `<level>/{KNOWLEDGE_CONTAINER}/<slug>.md` whose frontmatter "
        "names one class (`class:`). The table is the set. Write them with `molab knowledge write`.",
        "",
        _knowledge_classes(),
        "",
        "#### Worker records",
        "",
        "A supervised worker round is two of those documents with a structured record: "
        "the `Note` you were dispatched with (`kind: brief` — the delegation, the round, "
        "the digest of its text, the documents it was compiled from, and the protocol you "
        "are held to) and the `Report` you write back (`kind: worker_report`). Report every "
        "acceptance check by name with its verdict, every product, every departure from the "
        "protocol, and every MolCrafts capability you needed and did not find; molab "
        "refuses a record with an unknown field or on the wrong class.",
        "",
        _worker_records(),
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
    from molab.workspace.fs_local import LocalFS
    from molab.workspace.history import GitHistory
    from molab.workspace.naming import AGENT_GUIDE_FILENAME, CLAUDE_GUIDE_FILENAME

    from .workspace_check import baseline_path, write_baseline

    if not isinstance(ws.fs, LocalFS):
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
