"""Validate a workspace tree against the frozen layout + OKF laws.

Read-only. The layout law lives in one place — the ``Folder`` family and the
on-disk contract it derives (container subdir, human-readable directory
names, one ``index.md`` record per level whose frontmatter carries ``type``).
This module is that law expressed as a checker, so a tree assembled by hand,
by an adoption tool, by an agent, or by an older molab can be held to the
same standard the writers obey.

The checker answers one question — *does this tree conform?* — and never
repairs. Every finding carries a stable dotted ``rule`` id so callers can
filter, and a severity so a caller can distinguish a broken tree from a
merely incomplete one:

* ``error``   — the layout law is violated; readers may mis-resolve the tree.
* ``warning`` — legal but untidy, or lazily-created state is absent.

Every level has a closed set of legal names (:func:`classify_entry`), derived
from the naming constants: anything else at that level — a directory **or a
file** — is ``layout.stray``. A layer above workspace may declare a container
of its own at the host levels through ``extra``; workspace does not name it.
The directory tree *is* the index: a level's children are exactly its entity
subdirectories. The one derived thing is the ``index:`` block of each record
(D89), and the checker holds it to a fresh projection of the tree
(``index.drift``). It also enforces that every path segment is legible — a
Run's directory names its parameters (``run.slug``), an Execution's names its
attempt (``execution.id_mismatch``) — and that an experiment's ``scratch/``
does not quietly become storage (``scratch.stale``, D90).
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final, Literal

from pydantic import BaseModel, ConfigDict, ValidationError, computed_field

from .entity_record import (
    ENTITY_FILENAME,
    INDEX_FILENAME,
    RESERVED_INDEX_KEYS,
    EntityRecord,
    legacy_record_files,
    read_record,
    read_type,
)
from .execution_dirs import execution_dir_names
from .fs_local import LocalFileSystem
from .history import MOLAB_DIR
from .models import ExperimentMetadata, ProjectMetadata, RunMetadata, WorkspaceMetadata
from .naming import (
    AGENT_GUIDE_FILENAME,
    ASSET_CONTAINER,
    CLAUDE_GUIDE_FILENAME,
    EXECUTION_CONTAINER,
    EXPERIMENT_CONTAINER,
    PROJECT_CONTAINER,
    RUN_CONTAINER,
    SCRATCH_CONTAINER,
    WORKFLOW_SCRIPT_FILENAME,
    run_slug,
)

if TYPE_CHECKING:
    from pathlib import Path

    from .fs import DirEntry, FileSystem, PathArg
    from .workspace import Workspace

Severity = Literal["error", "warning"]

#: A position in the tree whose entries have a closed set of legal names.
#: The four record levels, the three child containers, an attempt container
#: and one attempt.
Level = Literal[
    "workspace",
    "project",
    "experiment",
    "run",
    "projects",
    "experiments",
    "runs",
    "executions",
    "execution",
]

#: The levels that host records (and may host a container declared through
#: ``extra``).
HOST_LEVELS: Final = ("workspace", "project", "experiment", "run")

#: An entry of an experiment's ``scratch/`` older than this is ``scratch.stale``.
SCRATCH_STALE_AFTER: Final = timedelta(days=14)

_NO_EXTRA: Mapping[str, frozenset[str]] = MappingProxyType({})

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

_EXECUTION_RE = re.compile(r"^e\d+$")
_LEGACY_EXECUTION_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

#: level -> the record ``type`` its ``index.md`` carries
_LEVEL_TYPE: dict[str, str] = {
    "workspace": "workspace.root",
    "project": "workspace.project",
    "experiment": "workspace.experiment",
    "run": "workspace.run",
}
#: level -> the model its canonical zone must validate against
_LEVEL_MODEL: dict[str, type[BaseModel]] = {
    "workspace": WorkspaceMetadata,
    "project": ProjectMetadata,
    "experiment": ExperimentMetadata,
    "run": RunMetadata,
}
#: Stable rule id → remediation hint naming the molab command to use. Keep
#: ids stable — callers filter / dispatch on them.
_RULE_HINTS: dict[str, str] = {
    "workspace.missing": "Create the workspace with `molab init <path>`.",
    "workspace.entity": (
        "Not a workspace root: no index.md record with type workspace.root. "
        "Run `molab init` here; do not nest a second workspace under an existing "
        "one — use `molab project create NAME` instead."
    ),
    "project.entity": (
        "No index.md record with type workspace.project. Create projects with "
        "`molab project create NAME` (add_project), which writes the record."
    ),
    "project.slug": (
        "Rename the directory to its kebab-case slug (e.g. mace-r2san; no prefix), "
        "then run `molab index sync`."
    ),
    "experiment.entity": (
        "No index.md record with type workspace.experiment. Create experiments "
        "with `molab experiment create PROJECT --name NAME`."
    ),
    "experiment.slug": (
        "Rename the experiment directory to its kebab-case slug (no prefix), then "
        "run `molab index sync`."
    ),
    "run.entity": (
        "No index.md record with type workspace.run. Create runs with "
        "`molab runs create PROJECT EXPERIMENT --params '{...}'`; do not leave a "
        "bare directory under runs/."
    ),
    "run.slug": (
        "A run directory is named after its parameters (key=value_…, a -N suffix "
        "on collision). Rename it to that name, then run `molab index sync`."
    ),
    "execution.name": (
        "Rename the attempt directory to its sequence number (e01, e02, …); the "
        "id in execution.json must match it. Record an outside job with "
        "`molab runs adopt`."
    ),
    "execution.legacy_name": (
        "Run `molab migrate layout <old> <new>` to rename legacy UUID attempt "
        "directories to e01, e02, …"
    ),
    "execution.id_mismatch": (
        "Rename the attempt directory back to the id in its execution.json. "
        "Attempts are recorded only by molab: `molab runs adopt` records one that "
        "ran outside molab."
    ),
    "index.frontmatter": (
        "The index.md frontmatter does not validate against its level's model; "
        "restore the fields molab wrote (`molab history log` shows them). Edit "
        "only the body, with `molab index write`."
    ),
    "index.drift": "The derived index: block disagrees with the tree; run `molab index sync`.",
    "layout.legacy_record": (
        "A <kind>.json / meta.json record is still on disk; run `molab migrate index`."
    ),
    "layout.stray": (
        "Only declared names live at each level (an execution holds its declared "
        "attempt directories and evidence files). Put quick tests in "
        "<experiment>/scratch/, record finished results with `molab runs adopt`, "
        "and move or remove anything else."
    ),
    "scratch.stale": (
        "scratch/ holds quick tests only. Clear old entries with "
        "`molab scratch clean --older-than 14d`; anything worth keeping becomes a "
        "run (`molab runs adopt`)."
    ),
}


def _legal_names(level: str) -> tuple[frozenset[str], frozenset[str]]:
    """``(directories, files)`` legal at a record level, from the naming constants."""
    from .execution_repository import ATTEMPT_FILES
    from .experiment import WORKFLOW_DOC_FILENAME

    if level == "workspace":
        return (
            frozenset({PROJECT_CONTAINER, MOLAB_DIR, ".git", ".claude", ASSET_CONTAINER}),
            frozenset(
                {
                    INDEX_FILENAME,
                    ".git",
                    ".gitignore",
                    AGENT_GUIDE_FILENAME,
                    CLAUDE_GUIDE_FILENAME,
                }
            ),
        )
    if level == "project":
        return frozenset({EXPERIMENT_CONTAINER, ASSET_CONTAINER}), frozenset({INDEX_FILENAME})
    if level == "experiment":
        return (
            # ``__pycache__`` is what importing ``workflow.py`` leaves beside it.
            frozenset({RUN_CONTAINER, SCRATCH_CONTAINER, ASSET_CONTAINER, "__pycache__"}),
            frozenset({INDEX_FILENAME, WORKFLOW_SCRIPT_FILENAME, WORKFLOW_DOC_FILENAME}),
        )
    if level == "run":
        return frozenset({EXECUTION_CONTAINER}), frozenset({INDEX_FILENAME})
    if level == "execution":
        return execution_dir_names(), ATTEMPT_FILES
    raise ValueError(f"unknown level {level!r}")


def classify_entry(
    level: str,
    name: str,
    is_dir: bool,
    *,
    extra: Mapping[str, frozenset[str]] = _NO_EXTRA,
) -> str | None:
    """Whether *name* may sit at *level*; the rule it breaks, or ``None``.

    Pure: no I/O, so a single-path check and the tree walk share it.

    Args:
        level: A :data:`Level` — a record level (``workspace`` / ``project`` /
            ``experiment`` / ``run``), a child container (``projects`` /
            ``experiments`` / ``runs``), the attempt container
            (``executions``) or one attempt (``execution``).
        name: The entry's name.
        is_dir: Whether the entry is a directory.
        extra: Level -> extra directory names a layer above workspace declares
            at that level (a container of its own). Workspace never names them.

    Returns:
        ``None`` when the entry is legal. Otherwise ``layout.stray``, or, under
        ``executions/``, ``execution.legacy_name`` (a legacy UUID attempt) /
        ``execution.name`` (any other non-attempt directory).

    Raises:
        ValueError: *level* is not a known level.
    """
    if level in (PROJECT_CONTAINER, EXPERIMENT_CONTAINER, RUN_CONTAINER):
        # A child directory is judged by its own record (``*.entity``).
        return None if is_dir else "layout.stray"
    if level == EXECUTION_CONTAINER:
        if not is_dir:
            return "layout.stray"
        if _EXECUTION_RE.match(name):
            return None
        if _LEGACY_EXECUTION_RE.match(name):
            return "execution.legacy_name"
        return "execution.name"
    directories, files = _legal_names(level)
    if is_dir and (name in directories or name in extra.get(level, frozenset())):
        return None
    if not is_dir and name in files:
        return None
    return "layout.stray"


def _hint_for(rule: str) -> str:
    """Look up a remediation hint; fall back to a generic agent instruction."""
    if rule in _RULE_HINTS:
        return _RULE_HINTS[rule]
    return (
        f"Inspect path against workspace_layout / the layout law; fix so rule "
        f"{rule!r} no longer fires, then re-run validate."
    )


class Violation(BaseModel):
    """One conformance finding, anchored at a workspace-relative path.

    ``rule`` is a stable filter key; ``hint`` is the remediation to attempt
    next.
    """

    model_config = ConfigDict(frozen=True)

    path: str
    rule: str
    detail: str
    severity: Severity = "error"
    hint: str = ""


class ValidationReport(BaseModel):
    """Structured outcome of :func:`validate_workspace`.

    Serializes cleanly via :meth:`model_dump` / :meth:`to_dict`. ``ok`` is True when there are no ``error`` severity
    findings; warnings never fail the tree.
    """

    model_config = ConfigDict(frozen=True)

    root: str
    violations: tuple[Violation, ...] = ()

    @property
    def errors(self) -> tuple[Violation, ...]:
        return tuple(v for v in self.violations if v.severity == "error")

    @property
    def warnings(self) -> tuple[Violation, ...]:
        return tuple(v for v in self.violations if v.severity == "warning")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def ok(self) -> bool:
        """True when nothing violates the layout law (warnings are allowed)."""
        return not self.errors

    @computed_field  # type: ignore[prop-decorator]
    @property
    def error_count(self) -> int:
        return len(self.errors)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def warning_count(self) -> int:
        return len(self.warnings)

    def summary(self) -> str:
        """One line fit for a CLI or a log."""
        if self.ok and not self.warnings:
            return f"{self.root}: conforms"
        return f"{self.root}: {len(self.errors)} error(s), {len(self.warnings)} warning(s)"

    def issues_by_rule(self) -> dict[str, list[Violation]]:
        """Group violations by stable ``rule`` id (agent dispatch helper)."""
        grouped: dict[str, list[Violation]] = {}
        for v in self.violations:
            grouped.setdefault(v.rule, []).append(v)
        return grouped

    def next_actions(self) -> list[str]:
        """Deduplicated remediation hints, errors first — agent to-do list."""
        seen: set[str] = set()
        actions: list[str] = []
        for bucket in (self.errors, self.warnings):
            for v in bucket:
                key = v.hint or v.rule
                if key in seen:
                    continue
                seen.add(key)
                actions.append(v.hint or _hint_for(v.rule))
        return actions

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready report.

        Shape::

            {
                "ok": bool,
                "root": str,
                "summary": str,
                "error_count": int,
                "warning_count": int,
                "violations": [{"path", "rule", "detail", "severity", "hint"}, ...],
                "next_actions": [str, ...],
            }
        """
        payload = self.model_dump(mode="json")
        payload["summary"] = self.summary()
        payload["next_actions"] = self.next_actions()
        return payload


class _Checker:
    """Walks the tree once, collecting violations."""

    def __init__(
        self,
        root: str,
        fs: FileSystem,
        extra: Mapping[str, frozenset[str]],
        now: datetime,
    ) -> None:
        self._root = root
        self._fs = fs
        self._extra = extra
        self._now = now
        self._found: list[Violation] = []

    # -- helpers ---------------------------------------------------------

    def _rel(self, path: str) -> str:
        prefix = self._root.rstrip("/") + "/"
        return path[len(prefix) :] if path.startswith(prefix) else path

    def _add(self, path: str, rule: str, detail: str, severity: Severity = "error") -> None:
        self._found.append(
            Violation(
                path=self._rel(path) or ".",
                rule=rule,
                detail=detail,
                severity=severity,
                hint=_hint_for(rule),
            )
        )

    def _entries(self, path: str) -> list[DirEntry]:
        """Every entry of *path*, by name; one ``scandir`` pass."""
        try:
            entries = self._fs.scandir(path, with_stat=False)
        except OSError:
            return []
        return sorted(entries, key=lambda entry: entry.name)

    def _check_level(self, path: str, level: str) -> list[DirEntry]:
        """Classify every entry of *path* at *level*; return the entries."""
        entries = self._entries(path)
        for entry in entries:
            rule = classify_entry(level, entry.name, entry.is_dir, extra=self._extra)
            if rule is None:
                continue
            child = self._fs.join(path, entry.name)
            if rule == "execution.legacy_name":
                self._add(
                    child,
                    rule,
                    (
                        f"{entry.name!r} is a legacy attempt UUID; run `molab migrate layout` "
                        "to rename it to eNN"
                    ),
                    severity="warning",
                )
            elif rule == "execution.name":
                self._add(
                    child,
                    rule,
                    f"{entry.name!r} is not an attempt number (e01, e02, …) or a legacy "
                    "attempt UUID",
                )
            else:
                kind = "directory" if entry.is_dir else "file"
                self._add(child, rule, f"{entry.name!r} is not a legal {kind} at the {level} level")
        return entries

    # -- per-level checks ------------------------------------------------

    def _check_concept(self, path: str, level: str) -> EntityRecord | None:
        """The ``index.md`` record of one concept directory: present, valid, in sync."""
        legacy = legacy_record_files(self._fs, path)
        if legacy:
            self._add(
                path,
                "layout.legacy_record",
                f"legacy record file(s) {', '.join(legacy)} still present",
            )
        expected = _LEVEL_TYPE[level]
        if read_type(self._fs, path) != expected:
            self._add(path, f"{level}.entity", f"no {ENTITY_FILENAME} record of type {expected}")
            return None
        record = read_record(self._fs, path)
        if record is None:  # pragma: no cover - read_type just saw it
            return None
        self._check_record(path, level, record)
        return record

    def _check_record(self, path: str, level: str, record: EntityRecord) -> None:
        from .index_projection import project_index_at

        model = _LEVEL_MODEL[level]
        data = {k: v for k, v in record.canonical.items() if k != "schema_version"}
        try:
            model.model_validate(data)
        except ValidationError as exc:
            self._add(
                path,
                "index.frontmatter",
                f"canonical zone fails {model.__name__}: {exc.error_count()} error(s)",
            )
        expected = project_index_at(self._fs, path, record.type, canonical=record.canonical)
        found = {k: v for k, v in record.index.items() if k in RESERVED_INDEX_KEYS}
        if found != expected:
            drifted = sorted(
                key for key in set(found) | set(expected) if found.get(key) != expected.get(key)
            )
            # Always a warning (D89): molab never reads the derived block, so a
            # stale one misleads a reader and breaks nothing. It goes stale by
            # design — a running attempt adds out/<task> dirs, someone makes
            # scratch/ — and an error would block every overlapping session.
            self._add(
                path,
                "index.drift",
                f"derived index keys differ: {', '.join(drifted)}",
                severity="warning",
            )

    def _check_run_slug(self, path: str, record: EntityRecord) -> None:
        """A run directory is its parameters (``run_slug``), maybe ``-N``-suffixed."""
        params = record.canonical.get("parameters")
        digest = record.canonical.get("definition_hash")
        expected = run_slug(
            params if isinstance(params, dict) else {},
            fallback=digest if isinstance(digest, str) else "",
        )
        name = self._fs.basename(path)
        if name == expected or re.fullmatch(rf"{re.escape(expected)}-\d+", name):
            return
        self._add(
            path,
            "run.slug",
            f"{name!r} is not the run's parameter name {expected!r}",
            severity="warning",
        )

    def _check_attempt_id(self, path: str) -> None:
        """An ``eNN`` directory carries the attempt whose ``execution.json`` id is ``eNN``."""
        from .execution_repository import EXECUTION_RECORD_FILENAME

        try:
            raw = self._fs.read_text(self._fs.join(path, EXECUTION_RECORD_FILENAME))
            recorded = json.loads(raw).get("id")
        except (OSError, ValueError, AttributeError):
            return
        name = self._fs.basename(path)
        if isinstance(recorded, str) and recorded != name:
            self._add(
                path,
                "execution.id_mismatch",
                f"directory {name!r} holds execution.json id {recorded!r}",
            )

    def _check_scratch(self, experiment: str) -> None:
        from .scratch import scratch_entries

        cutoff = self._now - SCRATCH_STALE_AFTER
        for name, path, mtime in scratch_entries(self._fs, experiment):
            modified = datetime.fromtimestamp(mtime, UTC)
            if modified < cutoff:
                age = (self._now - modified).days
                self._add(
                    path,
                    "scratch.stale",
                    f"scratch entry {name!r} untouched for {age} days",
                    severity="warning",
                )

    def _check_run(self, path: str) -> None:
        record = self._check_concept(path, "run")
        if record is not None:
            self._check_run_slug(path, record)
        self._check_level(path, "run")
        execs = self._fs.join(path, EXECUTION_CONTAINER)
        for entry in self._check_level(execs, EXECUTION_CONTAINER):
            if not entry.is_dir:
                continue
            attempt = self._fs.join(execs, entry.name)
            if _EXECUTION_RE.match(entry.name):
                self._check_attempt_id(attempt)
            self._check_level(attempt, "execution")

    def _check_experiment(self, path: str) -> None:
        self._check_concept(path, "experiment")
        self._check_level(path, "experiment")
        self._check_scratch(path)
        runs_dir = self._fs.join(path, RUN_CONTAINER)
        for entry in self._check_level(runs_dir, RUN_CONTAINER):
            if entry.is_dir:
                self._check_run(self._fs.join(runs_dir, entry.name))

    def _check_project(self, path: str) -> None:
        self._check_concept(path, "project")
        self._check_level(path, "project")
        experiments_dir = self._fs.join(path, EXPERIMENT_CONTAINER)
        for entry in self._check_level(experiments_dir, EXPERIMENT_CONTAINER):
            if not entry.is_dir:
                continue
            edir = self._fs.join(experiments_dir, entry.name)
            if not _SLUG_RE.match(entry.name):
                self._add(edir, "experiment.slug", f"{entry.name!r} is not a kebab-case slug")
            self._check_experiment(edir)

    # -- entry point -----------------------------------------------------

    def run(self) -> list[Violation]:
        root = self._root
        if not self._fs.is_dir(root):
            self._add(root, "workspace.missing", "not a directory")
            return self._found
        if read_type(self._fs, root) != _LEVEL_TYPE["workspace"]:
            legacy = legacy_record_files(self._fs, root)
            if legacy:
                self._add(
                    root,
                    "layout.legacy_record",
                    f"legacy record file(s) {', '.join(legacy)} still present",
                )
            self._add(
                root,
                "workspace.entity",
                f"no {ENTITY_FILENAME} record of type workspace.root — not a workspace root",
            )
            return self._found

        self._check_concept(root, "workspace")
        self._check_level(root, "workspace")

        projects_dir = self._fs.join(root, PROJECT_CONTAINER)
        for entry in self._check_level(projects_dir, PROJECT_CONTAINER):
            if not entry.is_dir:
                continue
            pdir = self._fs.join(projects_dir, entry.name)
            if not _SLUG_RE.match(entry.name):
                self._add(pdir, "project.slug", f"{entry.name!r} is not a kebab-case slug")
            self._check_project(pdir)

        return self._found


def validate_workspace(
    root: PathArg | Path | Workspace,
    *,
    fs: FileSystem | None = None,
    extra: Mapping[str, frozenset[str]] | None = None,
    now: datetime | None = None,
) -> ValidationReport:
    """Check *root* against the workspace layout + OKF laws. Writes nothing.

    Args:
        root: The workspace root directory, or a loaded ``Workspace``.
        fs: Filesystem to read through; defaults to the local one, so a remote
            workspace validates over its own transport.
        extra: Level -> extra directory names legal at that level (see
            :func:`classify_entry`). A layer above workspace passes the
            containers it owns; without it they are ``layout.stray``.
        now: The reference time for ``scratch.stale``; the current time when
            omitted.

    Returns:
        A :class:`ValidationReport`. ``report.ok`` is True when no ``error``
        was found; warnings never make a tree non-conforming.
    """
    from .workspace import Workspace

    if isinstance(root, Workspace):
        disk = fs or getattr(root, "fs", None)
        return validate_workspace(root.resolve(), fs=disk, extra=extra, now=now)
    filesystem = fs or LocalFileSystem()
    resolved = filesystem.resolve(root)
    checker = _Checker(resolved, filesystem, extra or _NO_EXTRA, now or datetime.now(UTC))
    violations = checker.run()
    return ValidationReport(root=resolved, violations=tuple(violations))


__all__ = [
    "HOST_LEVELS",
    "SCRATCH_STALE_AFTER",
    "Level",
    "Severity",
    "ValidationReport",
    "Violation",
    "classify_entry",
    "validate_workspace",
]
