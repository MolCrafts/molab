"""``molab check`` / ``molab validate`` — the one home of the agent-facing rules (D91).

Coding agents (Claude Code, Codex) write files into a workspace directly. A
hook in ``molcrafts-harness`` forwards each write, and each session's start
and stop, here; it holds no rule of its own. This service composes the
workspace layout law and the knowledge document law (neither may name the
other) and answers three questions:

* :func:`check_workspace` — the whole report: the workspace validator with
  the knowledge container declared at every host level, plus the knowledge
  validator's issues.
* :func:`check_path` — would this one write keep the tree legal? It refuses a
  write that molab owns (a record's frontmatter, an attempt's record and
  evidence, machine state) or that adds a new stray, and says which molab
  command does the job instead. An edit to a stray that already exists is
  allowed: that is old debt, not a new mess.
* :func:`check_tree` — the tree, against a snapshot. A session takes a
  snapshot when it starts (``--snapshot``) and asks at its end which errors
  are new (``--since``); ``--new-only`` asks against the workspace's
  persistent baseline. So an agent is held to what it changed, never to a
  workspace's history.

Every answer is a :class:`Verdict`, whose JSON is the harness contract::

    {
        "in_workspace": bool,
        "allowed": bool,
        "rule": str | null,
        "reason": str,
        "command": str | null,
        "path": str | null,
        "root": str | null,
        "issues": [{"rule", "severity", "path", "hint"}, ...],
    }

``root`` is the workspace directory with symlinks resolved, so a hook can
tell two paths belong to one workspace. It is null outside a workspace.

Machine state (snapshots, the baseline) lives under the workspace's
``.molab/``; snapshots older than :data:`SNAPSHOT_TTL` are dropped whenever
one is written.
"""

from __future__ import annotations

import json
import os
import posixpath
import re
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Final

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from molab.workspace import Workspace
    from molab.workspace.fs import FileSystem
    from molab.workspace.validate import ValidationReport, Violation

__all__ = [
    "BASELINE_FILENAME",
    "SNAPSHOT_DIRNAME",
    "SNAPSHOT_TTL",
    "CheckIssue",
    "Verdict",
    "baseline_path",
    "check_path",
    "check_tree",
    "check_workspace",
    "error_keys",
    "host_extra",
    "new_errors",
    "read_error_keys",
    "since",
    "snapshot",
    "snapshot_name",
    "write_baseline",
]

#: Directory under the workspace's ``.molab/`` that holds session snapshots.
SNAPSHOT_DIRNAME: Final = "check"
#: The workspace's persistent baseline, under ``.molab/``.
BASELINE_FILENAME: Final = "validate-baseline.json"
#: A snapshot older than this is deleted when another is written.
SNAPSHOT_TTL: Final = timedelta(days=30)

_NAME_UNSAFE = re.compile(r"[^A-Za-z0-9_-]")
_NO_SNAPSHOT = "no snapshot; cannot tell what is new"


class CheckIssue(BaseModel):
    """One finding as the harness reads it."""

    model_config = ConfigDict(frozen=True)

    rule: str
    severity: str
    path: str
    hint: str


class Verdict(BaseModel):
    """molab's answer to a hook: may this change (or this tree) stand?

    ``in_workspace`` is False when the path is not inside a molab workspace;
    such a path is always allowed. A refusal names the ``rule`` it breaks,
    the ``reason`` in words, and the molab ``command`` to use instead.
    """

    model_config = ConfigDict(frozen=True)

    in_workspace: bool
    allowed: bool
    rule: str | None = None
    reason: str = ""
    command: str | None = None
    path: str | None = None
    root: str | None = None
    issues: tuple[CheckIssue, ...] = ()


# ── the composed report ──────────────────────────────────────────────────────


def host_extra() -> Mapping[str, frozenset[str]]:
    """The knowledge container, declared legal at every host level."""
    from molab.knowledge.naming import KNOWLEDGE_CONTAINER
    from molab.workspace.validate import HOST_LEVELS

    return {level: frozenset({KNOWLEDGE_CONTAINER}) for level in HOST_LEVELS}


def check_workspace(ws: Workspace, *, now: datetime | None = None) -> ValidationReport:
    """The workspace report with the knowledge issues folded in. Writes nothing.

    Args:
        ws: The workspace.
        now: The reference time for age rules; the current time when omitted.

    Returns:
        A :class:`~molab.workspace.validate.ValidationReport` whose
        ``to_dict()`` keeps the keys ``molab validate --json`` always had.
    """
    from molab.knowledge.validate import validate_knowledge
    from molab.workspace.validate import ValidationReport, Violation, validate_workspace

    report = validate_workspace(ws.resolve(), fs=ws.fs, extra=host_extra(), now=now)
    folded = tuple(Violation.model_validate(item) for item in validate_knowledge(ws, fs=ws.fs))
    return ValidationReport(root=report.root, violations=(*report.violations, *folded))


def error_keys(report: ValidationReport) -> set[tuple[str, str]]:
    """The ``(rule, path)`` key of every error in *report*."""
    return {(item.rule, item.path) for item in report.errors}


def new_errors(report: ValidationReport, keys: Iterable[tuple[str, str]]) -> list[Violation]:
    """The errors of *report* whose ``(rule, path)`` is not in *keys*."""
    known = set(keys)
    return [item for item in report.errors if (item.rule, item.path) not in known]


# ── snapshots and the baseline ───────────────────────────────────────────────


def snapshot_name(name: str) -> str:
    """*name* with every character outside ``[A-Za-z0-9_-]`` replaced by ``_``."""
    cleaned = _NAME_UNSAFE.sub("_", name)[:128]
    return cleaned or "default"


def _machine_dir(ws: Workspace) -> Path:
    from molab.workspace import Workspace

    return Path(str(Workspace.machine_dir(ws.resolve())))


def _snapshot_path(ws: Workspace, name: str) -> Path:
    return _machine_dir(ws) / SNAPSHOT_DIRNAME / f"{snapshot_name(name)}.json"


def baseline_path(ws: Workspace) -> Path:
    """Where *ws*'s persistent baseline lives (``.molab/validate-baseline.json``)."""
    return _machine_dir(ws) / BASELINE_FILENAME


def _write_keys(path: Path, name: str, report: ValidationReport) -> None:
    from molab.atomicio import atomic_write_json

    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [{"rule": rule, "path": rel} for rule, rel in sorted(error_keys(report))]
    atomic_write_json(
        path,
        {"name": name, "taken_at": datetime.now(UTC).isoformat(), "errors": rows},
    )


def read_error_keys(path: Path) -> set[tuple[str, str]] | None:
    """The error keys a snapshot or baseline file holds; ``None`` when unreadable."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {(str(row["rule"]), str(row["path"])) for row in data["errors"]}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _drop_old_snapshots(directory: Path, keep: Path) -> None:
    cutoff = datetime.now(UTC).timestamp() - SNAPSHOT_TTL.total_seconds()
    for old in directory.glob("*.json"):
        if old == keep:
            continue
        try:
            if old.stat().st_mtime < cutoff:
                old.unlink()
        except OSError:
            continue


def snapshot(ws: Workspace, name: str, *, report: ValidationReport | None = None) -> Path:
    """Record the errors of *ws* right now as snapshot *name*; return its file.

    Snapshots older than :data:`SNAPSHOT_TTL` are deleted on the way.
    """
    return _take_snapshot(ws, name, report=report)


def _take_snapshot(ws: Workspace, name: str, *, report: ValidationReport | None = None) -> Path:
    path = _snapshot_path(ws, name)
    _write_keys(path, snapshot_name(name), report or check_workspace(ws))
    _drop_old_snapshots(path.parent, path)
    return path


def write_baseline(ws: Workspace, *, report: ValidationReport | None = None) -> Path:
    """Record the errors of *ws* right now as its persistent baseline; return its file."""
    path = baseline_path(ws)
    _write_keys(path, BASELINE_FILENAME, report or check_workspace(ws))
    return path


def _issues(items: Iterable[Violation]) -> tuple[CheckIssue, ...]:
    return tuple(
        CheckIssue(rule=item.rule, severity=item.severity, path=item.path, hint=item.hint)
        for item in items
    )


def since(ws: Workspace, name: str | None) -> Verdict:
    """The errors of *ws* that snapshot *name* did not have.

    A missing snapshot (or ``name=None``) falls back to the persistent
    baseline; with neither, nothing can be called new and the tree is
    allowed.
    """
    return _since(ws, name)


def _since(ws: Workspace, name: str | None) -> Verdict:
    root = _root_id(ws.resolve())
    keys: set[tuple[str, str]] | None = None
    source = ""
    if name is not None:
        keys = read_error_keys(_snapshot_path(ws, name))
        source = f"snapshot {snapshot_name(name)!r}"
    if keys is None:
        keys = read_error_keys(baseline_path(ws))
        source = "the workspace baseline"
    if keys is None:
        return Verdict(in_workspace=True, allowed=True, reason=_NO_SNAPSHOT, root=root)
    fresh = new_errors(check_workspace(ws), keys)
    if not fresh:
        return Verdict(
            in_workspace=True,
            allowed=True,
            reason=f"no new layout errors since {source}",
            root=root,
        )
    return Verdict(
        in_workspace=True,
        allowed=False,
        rule=fresh[0].rule,
        reason=f"{len(fresh)} new layout error(s) since {source}; fix them before finishing.",
        command="molab validate",
        root=root,
        issues=_issues(fresh),
    )


# ── the tree ─────────────────────────────────────────────────────────────────


def _absolute(path: str | os.PathLike[str]) -> str:
    """*path* made absolute against the cwd, lexically: symlinks keep their spelling."""
    return posixpath.normpath(posixpath.join(str(Path.cwd()), os.fspath(path)))


def _root_id(path: str | os.PathLike[str]) -> str:
    """The workspace directory with symlinks resolved, for a hook's identity key."""
    try:
        return os.path.realpath(os.fspath(path))
    except OSError:
        return os.fspath(path)


def _open(directory: str, fs: FileSystem) -> Workspace | None:
    from molab.workspace import Workspace

    root = Workspace.enclosing_root(directory, fs=fs)
    if root is None:
        return None
    return Workspace.load(str(root), fs=fs)


def check_tree(
    directory: str | os.PathLike[str] = ".",
    *,
    since: str | None = None,
    snapshot: str | None = None,
    new_only: bool = False,
) -> Verdict:
    """Check the workspace enclosing *directory*.

    Args:
        directory: Any directory inside the workspace.
        since: Report only errors that snapshot *since* did not have.
        snapshot: Record the current errors as snapshot *snapshot* (always
            allowed).
        new_only: Report only errors the persistent baseline did not have.

    Returns:
        The verdict. Outside a workspace, ``in_workspace=False`` and allowed.
    """
    from molab.workspace.fs_local import LocalFS

    fs = LocalFS()
    ws = _open(_absolute(directory), fs)
    if ws is None:
        return Verdict(in_workspace=False, allowed=True, reason="not inside a molab workspace")
    root = _root_id(ws.resolve())
    if snapshot is not None:
        report = check_workspace(ws)
        written = _take_snapshot(ws, snapshot, report=report)
        rel = os.path.relpath(written, str(ws.resolve()))
        return Verdict(
            in_workspace=True,
            allowed=True,
            reason=f"snapshot {snapshot_name(snapshot)!r}: {report.error_count} error(s) recorded",
            path=rel,
            root=root,
        )
    if since is not None:
        return _since(ws, since)
    if new_only:
        return _since(ws, None)
    report = check_workspace(ws)
    return Verdict(
        in_workspace=True,
        allowed=report.ok,
        rule=report.errors[0].rule if report.errors else None,
        reason=report.summary(),
        command=None if report.ok else "molab validate",
        root=root,
        issues=_issues((*report.errors, *report.warnings)),
    )


# ── one path ─────────────────────────────────────────────────────────────────

#: The container below each host level, and the level below each container.
_NEXT_LEVEL: Final = {
    "workspace": "projects",
    "project": "experiments",
    "experiment": "runs",
    "run": "executions",
    "projects": "project",
    "experiments": "experiment",
    "runs": "run",
    "executions": "execution",
}

_CREATE_COMMAND: Final = {
    "workspace": "molab init",
    "project": "molab project create NAME",
    "experiment": "molab experiment create {project} --name NAME",
    "run": "molab runs create {project} {experiment} --params '{{...}}'",
}

_LEGACY_LEVEL: Final = {
    "workspace.json": "workspace",
    "project.json": "project",
    "experiment.json": "experiment",
    "run.json": "run",
}


class _PathCheck:
    """One walk down a workspace-relative path, level by level."""

    def __init__(
        self, fs: FileSystem, root: str, parts: list[str], exists: bool, content: str | None
    ) -> None:
        self.fs = fs
        self.root = root
        self.parts = parts
        self.exists = exists
        self.content = content
        self.rel = "/".join(parts)
        self.workspace = _root_id(root)
        self.names: dict[str, str] = {}

    # -- answers ----------------------------------------------------------

    def allow(self, reason: str) -> Verdict:
        return Verdict(
            in_workspace=True, allowed=True, reason=reason, path=self.rel, root=self.workspace
        )

    def deny(self, rule: str, reason: str, command: str) -> Verdict:
        return Verdict(
            in_workspace=True,
            allowed=False,
            rule=rule,
            reason=reason,
            command=command,
            path=self.rel,
            root=self.workspace,
        )

    # -- command spellings ------------------------------------------------

    def _fill(self, template: str) -> str:
        return template.format(
            project=self.names.get("project", "PROJECT"),
            experiment=self.names.get("experiment", "EXPERIMENT"),
            run=self.names.get("run", "RUN"),
        )

    def _index_write(self, level: str) -> str:
        flags = []
        if level in ("project", "experiment", "run"):
            flags.append(f"-p {self.names.get('project', 'PROJECT')}")
        if level in ("experiment", "run"):
            flags.append(f"-e {self.names.get('experiment', 'EXPERIMENT')}")
        if level == "run":
            flags.append(f"--run {self.names.get('run', 'RUN')}")
        return " ".join(["molab index write", *flags, "--from FILE"])

    def _adopt(self) -> str:
        return self._fill(
            "molab runs adopt {project} {experiment} {run} --product TASK=PATH --log FILE"
        )

    def _scratch_hint(self) -> str:
        if "experiment" in self.names:
            from molab.workspace.naming import (
                EXPERIMENT_CONTAINER,
                PROJECT_CONTAINER,
                SCRATCH_CONTAINER,
            )

            return (
                f"{PROJECT_CONTAINER}/{self.names.get('project')}/{EXPERIMENT_CONTAINER}/"
                f"{self.names['experiment']}/{SCRATCH_CONTAINER}/"
            )
        return "<experiment>/scratch/"

    # -- rules ------------------------------------------------------------

    def _index(self, here: str, level: str) -> Verdict:
        from molab import frontmatter
        from molab.workspace.entity_record import UnmigratedLayoutError, read_record

        try:
            record = read_record(self.fs, here)
        except UnmigratedLayoutError:
            record = None
        if record is None:
            return self.deny(
                "index.create",
                "index.md here would create a record, and records are molab's to create.",
                self._fill(_CREATE_COMMAND[level]),
            )
        if self.content is None:
            return self.deny(
                "index.frontmatter",
                "index.md is this record's file and the new content cannot be seen; "
                "change its body through molab.",
                self._index_write(level),
            )
        current = self.fs.read_text(self.fs.join(here, self.parts[-1]))
        if frontmatter.split(self.content)[0] == frontmatter.split(current)[0]:
            return self.allow("only the body of index.md changes")
        return self.deny(
            "index.frontmatter",
            "The frontmatter of index.md is molab's record (canonical fields and the "
            "derived index: block); only the body may change.",
            self._index_write(level),
        )

    def _legacy(self, name: str, level: str) -> Verdict:
        command = (
            self._fill(_CREATE_COMMAND[_LEGACY_LEVEL[name]])
            if name in _LEGACY_LEVEL
            else self._index_write(level)
        )
        return self.deny(
            "layout.legacy_record",
            f"{name} is not a file in molab: a record is the frontmatter of index.md, "
            "which molab writes.",
            command,
        )

    def _knowledge(self, index: int, host_rel: str) -> Verdict:
        from molab.knowledge.validate import class_problem, classify_document

        rest = self.parts[index + 1 :]
        on = host_rel or "."
        write = f"molab knowledge write NAME TEXT --on {on} --class CLASS"
        rule = classify_document(rest[0], len(rest) > 1)
        if rule is not None:
            if self.exists:
                return self.allow("an existing entry; old debt, not a new one")
            return self.deny(
                rule,
                "knowledges/ holds markdown documents only.",
                write,
            )
        text = self.content
        if text is None and self.exists:
            text = self.fs.read_text(self.fs.join(self.root, self.rel))
        problem = class_problem(text or "")
        if problem is not None:
            return self.deny(
                "knowledge.class",
                f"A knowledge document names one of the six classes in its frontmatter: {problem}.",
                write,
            )
        return self.allow("a knowledge document with a known class")

    def run(self) -> Verdict:
        """Walk the path level by level; the first rule that decides, decides."""
        from molab.knowledge.naming import KNOWLEDGE_CONTAINER
        from molab.workspace.entity_record import INDEX_FILENAME, LEGACY_RECORD_FILES
        from molab.workspace.execution_dirs import OUT, WORK, execution_dir_names
        from molab.workspace.execution_repository import ATTEMPT_FILES, EXECUTION_RECORD_FILENAME
        from molab.workspace.history import MOLAB_DIR
        from molab.workspace.naming import (
            AGENT_GUIDE_FILENAME,
            ASSET_CONTAINER,
            CLAUDE_GUIDE_FILENAME,
            SCRATCH_CONTAINER,
            WORKFLOW_SCRIPT_FILENAME,
        )
        from molab.workspace.validate import HOST_LEVELS, classify_entry

        extra = host_extra()
        level = "workspace"
        for index, name in enumerate(self.parts):
            last = index == len(self.parts) - 1
            here = self.fs.join(self.root, *self.parts[:index]) if index else self.root
            is_dir = not last or self.fs.is_dir(self.fs.join(here, name))
            if level == "workspace" and name in (MOLAB_DIR, ".git"):
                command = "molab history sync" if name == ".git" else "molab validate"
                return self.deny(
                    "path.machine",
                    f"{name}/ is machine state; molab writes it.",
                    command,
                )
            # Places an agent may write, checked before any name-based refusal:
            # a solver's own meta.json / run.json under out/ or scratch/ is
            # science payload, not a record.
            if level == "workspace" and (
                name == ".claude"
                or (last and name in (AGENT_GUIDE_FILENAME, CLAUDE_GUIDE_FILENAME, ".gitignore"))
            ):
                return self.allow(f"{name} is the workspace's own to edit")
            if level == "experiment" and name == SCRATCH_CONTAINER and not last:
                return self.allow("scratch/ is the place for quick tests")
            if level == "experiment" and last and name == WORKFLOW_SCRIPT_FILENAME:
                return self.allow("the experiment's workflow script")
            if level == "execution" and name in (OUT.name, WORK.name) and not last:
                return self.allow(f"{name}/ is where a task writes")
            if level in HOST_LEVELS:
                if last and name == INDEX_FILENAME:
                    return self._index(here, level)
                if last and name in LEGACY_RECORD_FILES:
                    return self._legacy(name, level)
                if name == KNOWLEDGE_CONTAINER and not last:
                    return self._knowledge(index, "/".join(self.parts[:index]))
                if name == ASSET_CONTAINER and not last:
                    return self.deny(
                        "asset.owned",
                        "assets/ is molab's asset store: asset.json, versions/ and the "
                        "bytes are written when an asset is imported or promoted.",
                        self._fill("molab asset import NAME SRC --project {project}"),
                    )
            if level == "execution" and (
                (last and name in ATTEMPT_FILES) or (not last and name in execution_dir_names())
            ):
                return self.deny(
                    "execution.owned",
                    f"{name} belongs to the attempt's record; molab writes it. Record a job "
                    "that ran outside molab with `molab runs adopt`, or emit through the "
                    "workflow.",
                    self._adopt(),
                )
            rule = classify_entry(level, name, is_dir, extra=extra)
            if rule is not None:
                if self.exists:
                    return self.allow("an existing stray; old debt, not a new one")
                kind = "directory" if is_dir else "file"
                return self.deny(
                    rule,
                    f"{name!r} is not a legal {kind} at the {level} level. Put quick tests in "
                    f"{self._scratch_hint()} and record results with `molab runs adopt`.",
                    self._adopt(),
                )
            if last:
                return self.allow("a legal name at its level")
            following = _NEXT_LEVEL.get(level)
            if level == "executions" and not self.fs.is_file(
                self.fs.join(here, name, EXECUTION_RECORD_FILENAME)
            ):
                return self.deny(
                    "execution.owned",
                    f"There is no attempt {name!r}; attempts are created by molab. Record a job "
                    "that ran outside molab with `molab runs adopt`.",
                    self._adopt(),
                )
            if level in ("projects", "experiments", "runs", "executions"):
                self.names[_NEXT_LEVEL[level]] = name
                level = _NEXT_LEVEL[level]
            elif following is not None and name == following:
                level = following
            else:
                return self.allow("inside a legal directory")
        return self.allow("a legal path")


def check_path(
    path: str | os.PathLike[str], op: str = "write", content: str | None = None
) -> Verdict:
    """Would writing *content* to *path* keep the workspace legal? Reads only.

    Args:
        path: The file the agent is about to write or edit.
        op: ``write`` or ``edit``; the rules are the same, the word is kept
            for the record.
        content: The file's full content after the change, or ``None`` when
            the caller cannot know it.

    Returns:
        The verdict; outside a workspace, ``in_workspace=False`` and allowed.

    Raises:
        ValueError: *op* is not ``write`` or ``edit``.
    """
    from molab.workspace import Workspace
    from molab.workspace.fs_local import LocalFS

    if op not in ("write", "edit"):
        raise ValueError(f"op must be 'write' or 'edit', got {op!r}")
    fs = LocalFS()
    target = _absolute(path)
    root = Workspace.enclosing_root(target, fs=fs)
    if root is None:
        return Verdict(
            in_workspace=False,
            allowed=True,
            reason="not inside a molab workspace",
            path=str(path),
        )
    rel = posixpath.relpath(target, str(root))
    if rel == ".":
        return Verdict(
            in_workspace=True,
            allowed=True,
            reason="the workspace root",
            path=".",
            root=_root_id(root),
        )
    walk = _PathCheck(fs, str(root), rel.split("/"), fs.exists(target), content)
    return walk.run()
