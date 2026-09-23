"""Validate a workspace tree against the frozen layout + OKF laws.

Read-only. The layout law lives in one place — the ``Folder`` family and the
on-disk contract it derives (container subdir, human-readable directory
names, the singular entity filename, the per-concept ``meta.json`` marker).
This module is that law expressed as a checker, so a tree assembled by hand,
by an adoption tool, or by an older molab can be held to the same standard
the writers obey.

The checker answers one question — *does this tree conform?* — and never
repairs. Every finding carries a stable dotted ``rule`` id so callers can
filter, and a severity so a caller can distinguish a broken tree from a
merely incomplete one:

* ``error``   — the layout law is violated; readers may mis-resolve the tree.
* ``warning`` — legal but lazily-created state is absent.

There is nothing derived left to disagree with: the directory tree *is* the
index, so a level's children are exactly its entity subdirectories. What the
checker enforces instead is that every path segment is legible — a Run's
directory names its parameters, an Execution's names its attempt number —
and that machine state never leaks into a scientific directory.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, computed_field

from .execution_dirs import execution_dir_names
from .fs_local import LocalFileSystem

if TYPE_CHECKING:
    from pathlib import Path

    from .fs import FileSystem, PathArg
    from .workspace import Workspace

Severity = Literal["error", "warning"]

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

META_JSON = "meta.json"
_EXECUTION_RE = re.compile(r"^e\d+$")

#: Structural container subdirs per level — directories that hold children or
#: payload rather than being Concepts themselves, so they carry no meta.json.
_CONTAINERS: dict[str, frozenset[str]] = {
    "workspace": frozenset({"projects", "assets", "knowledges"}),
    "project": frozenset({"experiments", "assets", "knowledges"}),
    "experiment": frozenset({"runs", "assets", "knowledges"}),
    "run": frozenset(
        {
            "executions",
            "plan",
            "source",
            "assets",
            "knowledges",
            "harness",
        }
    ),
}

#: Per-attempt dirs under ``executions/<id>/``. Products, logs, scheduler
#: jobs and scratch live here — never at the run root. Read from the
#: declarations so a directory cannot be legal on disk yet illegal here.
_EXECUTION_CONTAINERS = execution_dir_names()

#: level -> entity filename (singular — lives on the concept's own directory)
_ENTITY_FILE: dict[str, str] = {
    "workspace": "workspace.json",
    "project": "project.json",
    "experiment": "experiment.json",
    "run": "run.json",
}
#: Stable rule id → agent-facing remediation. Keep ids stable — MCP tools
#: and agent loops filter / dispatch on them.
_RULE_HINTS: dict[str, str] = {
    "workspace.missing": (
        "Create the directory, then call materialize_workspace / "
        "Workspace(...).materialize() so workspace.json exists "
        "(OKF type lives on that file)."
    ),
    "workspace.entity": (
        "Not a workspace root. materialize_workspace(path=…) or "
        "Workspace(root).materialize(); do not nest a second workspace under "
        "an existing one — use add_project instead."
    ),
    "project.entity": (
        "Missing project.json. Prefer add_project(name=…) (create-or-get) so "
        "the entity file is written; hand-written dirs need project.json + meta.json."
    ),
    "project.slug": (
        "Rename the directory to a kebab-case slug (e.g. mace-r2san); ids are "
        "slug(name) with no prefix."
    ),
    "experiment.entity": (
        "Missing experiment.json. Use add_experiment(project_id, name) or "
        "write experiment.json + meta.json under experiments/<slug>/."
    ),
    "experiment.slug": ("Rename the experiment directory to a kebab-case slug (no prefix)."),
    "run.entity": (
        "Missing run.json. Scaffold with experiment.add_run(params=…); do not "
        "leave a bare directory under runs/ without the entity file."
    ),
    "execution.name": (
        "Rename the attempt directory to its sequence number (e01, e02, …); "
        "the id in execution.json must match it."
    ),
    "concept.marker": (
        "Stamp type on workspace.json / project.json / experiment.json / "
        "run.json. Notes and other Folders use meta.json."
    ),
    "layout.stray": (
        "Move with ws.wp.mv(src, dst) / me.wp.mv(ws, src, dst) under the "
        "four-tier tree (e.g. projects/<id>/assets/…), or add meta.json to "
        "make it an OKF Concept, or ws.wp.rm(path, recursive=True) if disposable."
    ),
}


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

    Designed for agent loops and MCP tools: ``rule`` is a stable filter key,
    ``hint`` is the remediation the agent should attempt next.
    """

    model_config = ConfigDict(frozen=True)

    path: str
    rule: str
    detail: str
    severity: Severity = "error"
    hint: str = ""


class ValidationReport(BaseModel):
    """Structured outcome of :func:`validate_workspace`.

    Serializes cleanly for MCP / agent tools via :meth:`model_dump` /
    :meth:`to_dict`. ``ok`` is True when there are no ``error`` severity
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
        """JSON-ready report for MCP tools and agent loops.

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
    """Walks the four tiers once, collecting violations."""

    def __init__(self, root: str, fs: FileSystem) -> None:
        self._root = root
        self._fs = fs
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

    def _subdirs(self, path: str) -> list[str]:
        if not self._fs.is_dir(path):
            return []
        names = sorted(self._fs.listdir(path))
        return [
            n for n in names if not n.startswith(".") and self._fs.is_dir(self._fs.join(path, n))
        ]

    # -- per-level checks ------------------------------------------------

    def _has_concept_marker(self, path: str) -> bool:
        return self._fs.is_file(self._fs.join(path, META_JSON))

    def _entity_has_type(self, path: str, entity: str) -> bool:
        fpath = self._fs.join(path, entity)
        if not self._fs.is_file(fpath):
            return False
        try:
            payload = json.loads(self._fs.read_text(fpath))
        except (OSError, ValueError):
            return False
        return isinstance(payload, dict) and bool(payload.get("type"))

    def _check_concept(self, path: str, level: str) -> None:
        """Entity file + OKF marker for one concept directory."""
        entity = _ENTITY_FILE[level]
        if not self._fs.is_file(self._fs.join(path, entity)):
            self._add(path, f"{level}.entity", f"missing {entity}")
        if not self._entity_has_type(path, entity):
            self._add(path, "concept.marker", f"missing type on {entity}")

    def _check_strays(self, path: str, level: str) -> None:
        """Every child dir is a known container or a Concept (has meta.json)."""
        allowed = _CONTAINERS[level]
        for name in self._subdirs(path):
            if name in allowed:
                continue
            child = self._fs.join(path, name)
            if self._has_concept_marker(child):
                continue  # a Concept may mount at any Folder
            self._add(
                child,
                "layout.stray",
                f"{name!r} is neither a container {sorted(allowed)} nor a Concept (no {META_JSON})",
            )

    def _check_execution(self, path: str) -> None:
        """Every child of an execution dir is a known attempt container."""
        for name in self._subdirs(path):
            if name in _EXECUTION_CONTAINERS:
                continue
            child = self._fs.join(path, name)
            self._add(
                child,
                "layout.stray",
                f"{name!r} is not an execution container {sorted(_EXECUTION_CONTAINERS)}",
            )

    def _check_run(self, path: str) -> None:
        self._check_concept(path, "run")
        self._check_strays(path, "run")
        execs = self._fs.join(path, "executions")
        if not self._fs.is_dir(execs):
            return
        for name in self._subdirs(execs):
            attempt = self._fs.join(execs, name)
            if not _EXECUTION_RE.match(name):
                self._add(
                    attempt,
                    "execution.name",
                    f"{name!r} is not an attempt number (e01, e02, …)",
                )
            self._check_execution(attempt)

    # -- entry point -----------------------------------------------------

    def run(self) -> list[Violation]:
        root = self._root
        if not self._fs.is_dir(root):
            self._add(root, "workspace.missing", "not a directory")
            return self._found
        if not self._fs.is_file(self._fs.join(root, _ENTITY_FILE["workspace"])):
            self._add(root, "workspace.entity", "missing workspace.json — not a workspace root")
            return self._found

        self._check_concept(root, "workspace")
        self._check_strays(root, "workspace")

        projects_dir = self._fs.join(root, "projects")
        project_dirs = self._subdirs(projects_dir)

        for pname in project_dirs:
            pdir = self._fs.join(projects_dir, pname)
            if not _SLUG_RE.match(pname):
                self._add(pdir, "project.slug", f"{pname!r} is not a kebab-case slug")
            self._check_concept(pdir, "project")
            self._check_strays(pdir, "project")

            experiments_dir = self._fs.join(pdir, "experiments")
            experiment_dirs = self._subdirs(experiments_dir)

            for ename in experiment_dirs:
                edir = self._fs.join(experiments_dir, ename)
                if not _SLUG_RE.match(ename):
                    self._add(edir, "experiment.slug", f"{ename!r} is not a kebab-case slug")
                self._check_concept(edir, "experiment")
                self._check_strays(edir, "experiment")

                runs_dir = self._fs.join(edir, "runs")
                run_dirs = self._subdirs(runs_dir)

                for rname in run_dirs:
                    self._check_run(self._fs.join(runs_dir, rname))

        return self._found


def validate_workspace(
    root: PathArg | Path | Workspace, *, fs: FileSystem | None = None
) -> ValidationReport:
    """Check *root* against the workspace layout + OKF laws. Writes nothing.

    Args:
        root: The workspace root directory, or a loaded ``Workspace``.
        fs: Filesystem to read through; defaults to the local one, so a remote
            workspace validates over its own transport.

    Returns:
        A :class:`ValidationReport`. ``report.ok`` is True when no ``error``
        was found; warnings never make a tree non-conforming.
    """
    from .workspace import Workspace

    if isinstance(root, Workspace):
        disk = fs or getattr(root, "fs", None)
        return validate_workspace(root.resolve(), fs=disk)
    filesystem = fs or LocalFileSystem()
    resolved = filesystem.resolve(root)
    violations = _Checker(resolved, filesystem).run()
    return ValidationReport(root=resolved, violations=tuple(violations))
