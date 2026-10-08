"""``molab migrate`` — restructure an old workspace into the current layout.

``knowledge`` moves legacy knowledge documents into ``knowledges/<stem>.md``
and rewrites their links. It is opt-in and supports ``--dry-run``.

Reads a source workspace and writes a new one whose paths a person can read:
experiments named by their name, runs named by their parameters, attempts
numbered ``e01`` / ``e02``. Every fragment that only re-encoded something
already on disk is dropped — the derived children indexes, the provenance
event tree, the artifact index, the content-addressed side store — and the
facts the event tree carried are adopted as the new repository's first
commits, so ``git log`` still answers what happened before the move.
``assets`` rewrites legacy asset records in place and drops dead manifests.

Bulk payloads (``work/``, artifact and asset bytes) are **hard-linked**, so
the new workspace costs metadata only and the source tree stays intact as a
fallback until the operator deletes it. A hard link means the two names are
one file: replacing a file in the archive is private, but *appending* to one
would write through into the source. Every append in molab goes through
``FileStore``, which breaks the link first — see ``_unshare`` there.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Annotated, Any

import typer

from molab.cli._common import rprint
from molab.fs import DirEntry, FileSystem
from molab.knowledge.knowledge_item import SourceRef
from molab.services.workflow_kind import classify_legacy_workflow
from molab.workspace import Workspace
from molab.workspace.artifact_repository import AssetRepository
from molab.workspace.domain import Asset, Execution
from molab.workspace.execution_dirs import ARTIFACTS, OUT, WORK
from molab.workspace.execution_repository import (
    fold_legacy_attempt,
    legacy_attempt_created_at,
)
from molab.workspace.history import (
    MAX_RECORD_BYTES,
    AgentRef,
    EntityRef,
    GitHistory,
    Relation,
    default_gitignore,
)
from molab.workspace.naming import entity_slug, execution_slug, run_slug
from molab.workspace.refs import MolabRef

migrate_app = typer.Typer(
    help=(
        "Restructure a workspace layout, rebrand molexp → molab machine dirs, "
        "bind legacy experiments (workflow-kind), rewrite legacy assets, "
        "or migrate knowledge documents"
    ),
    no_args_is_help=True,
)

#: Machine-only or derived paths that do not survive the move.
_DROP_NAMES = {
    "index",
    "provenance",
    "content",
    "__pycache__",
    ".molq",
    ".ruff_cache",
    ".pytest_cache",
    "projects.json",
    "experiments.json",
    "runs.json",
    "knowledges.json",
    "assets.json",
    "logs",
    "ops",
    "alive",
}

_DROP_SUFFIXES = (".lock", ".pyc")

_JOB_FILES = {
    "manifest.json": ".json",
    "run_slurm.sh": ".sh",
    "stdout.log": ".out",
    "stderr.log": ".err",
}


@dataclass
class Report:
    """What the migration did, counted so the operator can sanity-check it."""

    projects: int = 0
    experiments: int = 0
    runs: int = 0
    executions: int = 0
    artifacts: int = 0
    linked_files: int = 0
    copied_files: int = 0
    dropped: dict[str, int] = field(default_factory=dict)

    def drop(self, kind: str) -> None:
        self.dropped[kind] = self.dropped.get(kind, 0) + 1


def _read_json(path: Path) -> dict[str, Any]:
    """Read a sidecar, dropping the ``schema_version`` envelope it was wrapped in."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {key: value for key, value in payload.items() if key != "schema_version"}


def _link(src: Path, dst: Path, report: Report) -> None:
    """Hard-link *src* to *dst*, copying only when the link cannot be made."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return
    try:
        os.link(src, dst)
        report.linked_files += 1
    except OSError:
        shutil.copy2(src, dst)
        report.copied_files += 1


def _link_tree(src: Path, dst: Path, report: Report) -> None:
    for item in sorted(src.rglob("*")):
        if item.is_dir():
            (dst / item.relative_to(src)).mkdir(parents=True, exist_ok=True)
        elif item.is_file():
            _link(item, dst / item.relative_to(src), report)


def _keep(name: str) -> bool:
    if name in _DROP_NAMES or name.startswith(".backup-"):
        return False
    return not name.endswith(_DROP_SUFFIXES)


def _carry_extras(src: Path, dst: Path, report: Report, *, skip: set[str]) -> None:
    """Move a level's own loose files and unknown subtrees across verbatim."""
    for item in sorted(src.iterdir()):
        if item.name in skip:
            continue
        if not _keep(item.name):
            report.drop(item.name if item.name in _DROP_NAMES else "scratch")
            continue
        if item.is_dir():
            _link_tree(item, dst / item.name, report)
        elif item.is_file():
            _link(item, dst / item.name, report)


def _stamp(payload: dict[str, Any], **fields: object) -> dict[str, Any]:
    return {
        "schema_version": 3,
        **{k: v for k, v in payload.items() if k != "schema_version"},
        **fields,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _cas_payload(source_root: Path, digest: str, kind: str) -> Path | None:
    bare = str(digest).removeprefix("sha256:")
    if len(bare) < 2:
        return None
    obj = source_root / "content" / "sha256" / bare[:2] / bare
    candidate = obj / ("tree" if kind == "directory" else "payload")
    return candidate if candidate.exists() else None


def _migrate_execution(
    src: Path,
    dst: Path,
    *,
    seq: int,
    run_id: str,
    project_id: str,
    source_root: Path,
    _target_root: Path,
    report: Report,
) -> Execution:
    """Carry one attempt's bytes across, then fold its record in the workspace.

    The byte work (hard links, log merge, job flattening) lives here; the
    record fold — legacy sidecars into one ``execution.json`` — is
    ``fold_legacy_attempt``, the repository's own versioned write.
    """
    dst.mkdir(parents=True, exist_ok=True)

    # Products: the bytes become `artifacts/`; the records ride into the fold.
    artifacts: list[tuple[dict[str, object], str]] = []
    art_dir = src / "artifacts"
    if art_dir.is_dir():
        for item in sorted(art_dir.iterdir()):
            if item.is_file():
                _link(item, dst / ARTIFACTS.name / item.name, report)
                continue
            record = _read_json(item / "artifact.json")
            if not record:
                continue
            name = str(record.get("name") or item.name)
            content = record.get("content") or {}
            payload = _cas_payload(
                source_root, str(content.get("digest", "")), str(content.get("kind", "file"))
            )
            out_name = Path(name).name
            # A registered product lands in the promoted tier; the old
            # layout's ``work/`` becomes ``out/``, so that is where the
            # record says it came from.
            out_rel = f"{ARTIFACTS.name}/{out_name}"
            if payload is not None:
                if payload.is_dir():
                    _link_tree(payload, dst / out_rel, report)
                else:
                    _link(payload, dst / out_rel, report)
            elif (art_dir / out_name).exists():
                _link(art_dir / out_name, dst / out_rel, report)
            artifacts.append((record, out_rel))
            report.artifacts += 1

    # Evidence: one log, not four files.
    log_parts: list[str] = []
    for name in ("runtime.log", "run.log", "traceback.txt", "error.txt"):
        candidate = src / name
        if candidate.is_file():
            log_parts.append(
                f"--- {name} ---\n{candidate.read_text(encoding='utf-8', errors='replace')}"
            )
    legacy_logs = src / "logs"
    if legacy_logs.is_dir():
        for item in sorted(legacy_logs.glob("*.log")):
            log_parts.append(
                f"--- logs/{item.name} ---\n{item.read_text(encoding='utf-8', errors='replace')}"
            )
    if log_parts:
        (dst / "run.log").write_text("\n".join(log_parts), encoding="utf-8")

    if (src / "workflow.json").is_file():
        _link(src / "workflow.json", dst / "workflow.json", report)

    # Scheduler jobs: flat files, not a directory per job id.
    jobs_dir = src / "jobs"
    if jobs_dir.is_dir():
        for job_dir in sorted(jobs_dir.iterdir()):
            if not job_dir.is_dir():
                continue
            for filename, suffix in _JOB_FILES.items():
                candidate = job_dir / filename
                if candidate.is_file():
                    _link(candidate, dst / "jobs" / f"{job_dir.name}{suffix}", report)
            report.drop("jobs/<id>/")

    # An old workspace's ``work/`` held everything the attempt wrote, scratch
    # and simulation output alike. It cannot be split apart after the fact, so
    # it becomes ``out/`` — the tier that is kept — never the one declared
    # safe to delete whole.
    if (src / WORK.name).is_dir():
        _link_tree(src / WORK.name, dst / OUT.name, report)

    execution = fold_legacy_attempt(
        src,
        dst,
        seq=seq,
        run_id=run_id,
        project_id=project_id,
        artifacts=artifacts,
    )
    report.executions += 1
    return execution


def _migrate_run(
    src: Path,
    runs_root: Path,
    *,
    taken: set[str],
    project_id: str,
    source_root: Path,
    target_root: Path,
    report: Report,
) -> None:
    definition = _read_json(src / "run.json")
    if not definition:
        report.drop("run-without-run.json")
        return
    params = definition.get("parameters") or {}
    slug = run_slug(params, fallback=str(definition.get("definition_hash", "")))
    from molab.workspace.naming import disambiguate

    slug = disambiguate(slug, taken)
    taken.add(slug)
    dst = runs_root / slug
    dst.mkdir(parents=True, exist_ok=True)
    definition.setdefault("id", slug)
    _write_json(dst / "run.json", _stamp(definition, type="workspace.run"))
    report.runs += 1

    src_execs = src / "executions"
    last_attempt: Path | None = None
    if src_execs.is_dir():
        ordered = sorted(
            (d for d in src_execs.iterdir() if d.is_dir()),
            key=lambda d: (legacy_attempt_created_at(d), d.name),
        )
        for index, exec_dir in enumerate(ordered, start=1):
            last_attempt = dst / "executions" / execution_slug(index)
            _migrate_execution(
                exec_dir,
                dst / "executions" / execution_slug(index),
                seq=index,
                run_id=str(definition.get("id", slug)),
                project_id=project_id,
                source_root=source_root,
                _target_root=target_root,
                report=report,
            )
    # Scheduler output a human dropped at the run root belongs to an attempt.
    stray_jobs = sorted(d for d in src.iterdir() if d.is_dir() and d.name.startswith("jobs"))
    for job_dir in stray_jobs:
        target = (last_attempt or dst / "executions" / execution_slug(1)) / "jobs"
        for item in sorted(job_dir.iterdir()):
            if item.is_file():
                suffix = _JOB_FILES.get(item.name, f"-{item.name}")
                _link(item, target / f"{job_dir.name}{suffix}", report)
        report.drop("run-root jobs/")

    _carry_extras(
        src,
        dst,
        report,
        skip={"run.json", "executions", "cache", "source", *(d.name for d in stray_jobs)},
    )


def _migrate_experiment(
    src: Path,
    experiments_root: Path,
    *,
    taken: set[str],
    project_id: str,
    source_root: Path,
    target_root: Path,
    report: Report,
) -> None:
    metadata = _read_json(src / "experiment.json")
    name = str(metadata.get("name") or src.name)
    from molab.workspace.naming import disambiguate

    slug = disambiguate(entity_slug(name, fallback=src.name), taken)
    taken.add(slug)
    dst = experiments_root / slug
    dst.mkdir(parents=True, exist_ok=True)
    if metadata:
        metadata.setdefault("id", src.name)
        _write_json(
            dst / "experiment.json",
            _stamp(metadata, name=name, type="workspace.experiment"),
        )
    else:
        _write_json(
            dst / "experiment.json",
            _stamp(
                {
                    "id": src.name,
                    "name": name,
                    "type": "workspace.experiment",
                    "created_at": datetime.now(UTC).isoformat(),
                    "revision": 1,
                    "revision_id": src.name,
                    "definition_hash": "sha256:" + "0" * 64,
                }
            ),
        )
    report.experiments += 1

    run_slugs: set[str] = set()
    runs_dir = src / "runs"
    if runs_dir.is_dir():
        for run_dir in sorted(d for d in runs_dir.iterdir() if d.is_dir()):
            _migrate_run(
                run_dir,
                dst / "runs",
                taken=run_slugs,
                project_id=project_id,
                source_root=source_root,
                target_root=target_root,
                report=report,
            )
    _carry_extras(src, dst, report, skip={"experiment.json", "runs"})


def _migrate_project(
    src: Path,
    projects_root: Path,
    *,
    taken: set[str],
    source_root: Path,
    target_root: Path,
    report: Report,
) -> None:
    metadata = _read_json(src / "project.json")
    name = str(metadata.get("name") or src.name)
    metadata.setdefault("id", src.name)
    from molab.workspace.naming import disambiguate

    slug = disambiguate(entity_slug(name, fallback=src.name), taken)
    taken.add(slug)
    dst = projects_root / slug
    dst.mkdir(parents=True, exist_ok=True)
    _write_json(dst / "project.json", _stamp(metadata, name=name, type="workspace.project"))
    report.projects += 1

    exp_slugs: set[str] = set()
    experiments_dir = src / "experiments"
    if experiments_dir.is_dir():
        for exp_dir in sorted(d for d in experiments_dir.iterdir() if d.is_dir()):
            if not _keep(exp_dir.name):
                report.drop(exp_dir.name)
                continue
            _migrate_experiment(
                exp_dir,
                dst / "experiments",
                taken=exp_slugs,
                project_id=str(metadata.get("id") or slug),
                source_root=source_root,
                target_root=target_root,
                report=report,
            )
    _carry_extras(src, dst, report, skip={"project.json", "experiments"})


def migrate_workspace(source: Path, target: Path) -> Report:
    """Rewrite *source* into *target* under the current layout."""
    source = source.resolve()
    target = target.resolve()
    if target.exists() and any(target.iterdir()):
        raise typer.BadParameter(f"{target} already exists and is not empty")
    target.mkdir(parents=True, exist_ok=True)

    report = Report()
    workspace = _read_json(source / "workspace.json")
    workspace.setdefault("id", target.name)
    workspace.setdefault("name", str(workspace["id"]))
    _write_json(target / "workspace.json", _stamp(workspace, type="workspace.root"))

    project_slugs: set[str] = set()
    projects_dir = source / "projects"
    if projects_dir.is_dir():
        for project_dir in sorted(d for d in projects_dir.iterdir() if d.is_dir()):
            _migrate_project(
                project_dir,
                target / "projects",
                taken=project_slugs,
                source_root=source,
                target_root=target,
                report=report,
            )
    _carry_extras(source, target, report, skip={"workspace.json", "projects"})

    _write_gitignore(target, report)
    return report


#: A solver log this large is bulk output, not a record; git holds the record.
OVERSIZE_EVIDENCE_BYTES = MAX_RECORD_BYTES


def _write_gitignore(target: Path, report: Report) -> None:
    """Write the ignore rules, naming the oversize files this tree actually has.

    Patterns cover the formats that are always bulk. Size cannot be expressed
    as a pattern, so any remaining file over :data:`OVERSIZE_EVIDENCE_BYTES`
    is listed explicitly — visible, and trivially un-ignored if the operator
    decides that one matters.
    """
    lines = [default_gitignore()]
    oversize = sorted(
        item.relative_to(target).as_posix()
        for item in target.rglob("*")
        if item.is_file()
        and not item.is_symlink()
        and item.stat().st_size > OVERSIZE_EVIDENCE_BYTES
        and "/work/" not in f"/{item.relative_to(target).as_posix()}"
    )
    if oversize:
        lines.append(
            f"\n# Oversize solver output found while migrating "
            f"(> {OVERSIZE_EVIDENCE_BYTES // (1 << 20)} MiB each). The files are "
            f"on disk; only their bytes stay out of the history.\n"
        )
        lines.extend(f"/{path}\n" for path in oversize)
        report.drop(f"oversize evidence, kept on disk: {len(oversize)} file(s)")
    (target / ".gitignore").write_text("".join(lines), encoding="utf-8")


def replay_history(source: Path, target: Path) -> int:
    """Adopt the source's provenance events as this repository's first commits.

    The events describe work that happened before the new tree existed, so
    each becomes an empty commit carrying the same typed fact — oldest first,
    ending just before the commit that lays down the migrated files. ``git
    log`` therefore still answers "what happened to this run", with the
    original ids; only Execution ids are re-numbered by the migration, so a
    pre-migration attempt is cited by the id it had at the time.

    Returns the number of facts adopted.
    """
    events_root = source / "provenance" / "events"
    if not events_root.is_dir():
        return 0
    history = GitHistory(target)
    if not history.enabled():
        return 0

    facts: list[tuple[str, dict[str, Any]]] = []
    for path in sorted(events_root.rglob("*.json")):
        event = _read_json(path)
        occurred = event.get("occurred_at")
        if event.get("event_type") and isinstance(occurred, str):
            facts.append((occurred, event))
    facts.sort(key=lambda item: item[0])

    adopted = 0
    for occurred, event in facts:
        subject = event.get("subject") or {}
        if not subject.get("id"):
            continue
        agent_raw = event.get("agent") or {}
        agent_type = str(agent_raw.get("type", "system"))
        agent = (
            AgentRef(
                id=str(agent_raw.get("id", "molab")), type=agent_type, name=agent_raw.get("name")
            )
            if agent_type in {"person", "software", "workflow", "executor", "system"}
            else AgentRef(id=str(agent_raw.get("id", "molab")), type="system")
        )
        relations = tuple(
            Relation(
                predicate=str(item.get("predicate", "relatedTo")),
                object=EntityRef(
                    id=str((item.get("object") or {}).get("id", "")),
                    type=str((item.get("object") or {}).get("type", "entity")),
                ),
            )
            for item in event.get("relations") or ()
            if (item.get("object") or {}).get("id")
        )
        commit = history.record(
            str(event["event_type"]),
            subject=EntityRef(id=str(subject["id"]), type=str(subject.get("type", "entity"))),
            agent=agent,
            relations=relations,
            summary=f"{subject.get('type', 'entity')} {subject['id']} (before migration)",
            occurred_at=datetime.fromisoformat(occurred),
            stage=False,
        )
        if commit is not None:
            adopted += 1
    return adopted


# Pre-rename machine-dir spellings. Runtime code only writes ``.molab`` /
# ``~/.molab``; these literals exist solely so ``migrate brand`` can find an
# un-migrated tree. Do not teach the rest of molab to read them again.
_LEGACY_MACHINE_DIR = ".molexp"
_CURRENT_MACHINE_DIR = ".molab"


@dataclass
class BrandReport:
    """What ``migrate brand`` changed on disk."""

    workspace_dir_renamed: bool = False
    gitignore_updated: bool = False
    home_renamed: bool = False
    notes: list[str] = field(default_factory=list)


def migrate_brand(
    workspace: Path,
    *,
    home: Path | None = None,
    migrate_home: bool = True,
) -> BrandReport:
    """Hard-cut a workspace (and optionally ``$HOME``) from molexp → molab names.

    Renames ``<workspace>/.molexp`` → ``.molab``, rewrites ``.molexp/`` lines in
    ``.gitignore`` to ``.molab/``, and by default renames ``~/.molexp`` →
    ``~/.molab``. Refuses to merge when the destination already exists.
    Does **not** rewrite historical ``Molexp-*`` git trailers.
    """
    report = BrandReport()
    root = workspace.expanduser().resolve()
    if not root.is_dir():
        raise typer.BadParameter(f"{root} is not a directory")

    old_machine = root / _LEGACY_MACHINE_DIR
    new_machine = root / _CURRENT_MACHINE_DIR
    if old_machine.exists():
        if new_machine.exists():
            raise typer.BadParameter(
                f"both {_LEGACY_MACHINE_DIR}/ and {_CURRENT_MACHINE_DIR}/ exist under "
                f"{root}; remove or merge by hand before re-running"
            )
        old_machine.rename(new_machine)
        report.workspace_dir_renamed = True
    elif new_machine.exists():
        report.notes.append(f"{_CURRENT_MACHINE_DIR}/ already present — skipped")
    else:
        report.notes.append(f"no {_LEGACY_MACHINE_DIR}/ under {root} — skipped")

    gitignore = root / ".gitignore"
    if gitignore.is_file():
        text = gitignore.read_text(encoding="utf-8")
        updated = text.replace(f"{_LEGACY_MACHINE_DIR}/", f"{_CURRENT_MACHINE_DIR}/")
        # Also catch a bare ``.molexp`` line without trailing slash.
        updated = updated.replace(f"\n{_LEGACY_MACHINE_DIR}\n", f"\n{_CURRENT_MACHINE_DIR}\n")
        if updated != text:
            gitignore.write_text(updated, encoding="utf-8")
            report.gitignore_updated = True

    if migrate_home:
        home_root = (home if home is not None else Path.home()).expanduser().resolve()
        old_home = home_root / _LEGACY_MACHINE_DIR
        new_home = home_root / _CURRENT_MACHINE_DIR
        if old_home.exists():
            if new_home.exists():
                raise typer.BadParameter(
                    f"both {old_home} and {new_home} exist; refuse to merge — "
                    "move one aside and re-run"
                )
            old_home.rename(new_home)
            report.home_renamed = True
        elif new_home.exists():
            report.notes.append(f"{new_home} already present — skipped")
        else:
            report.notes.append(f"no {old_home} — skipped")

    return report


@migrate_app.command("brand")
def migrate_brand_cmd(
    workspace: Annotated[
        Path,
        typer.Argument(help="Workspace root to rebrand in place"),
    ] = Path(),
    home: Annotated[
        bool,
        typer.Option("--home/--no-home", help="Also rename ~/.molexp → ~/.molab"),
    ] = True,
) -> None:
    """Rename .molexp → .molab (workspace + optional home); no trailer rewrite."""
    report = migrate_brand(workspace, migrate_home=home)
    rprint(f"[green]OK[/green] brand migrate {workspace.expanduser().resolve()}")
    if report.workspace_dir_renamed:
        rprint(f"  renamed {_LEGACY_MACHINE_DIR}/ → {_CURRENT_MACHINE_DIR}/")
    if report.gitignore_updated:
        rprint("  updated .gitignore machine-dir pattern")
    if report.home_renamed:
        rprint(f"  renamed ~/{_LEGACY_MACHINE_DIR} → ~/{_CURRENT_MACHINE_DIR}")
    for note in report.notes:
        rprint(f"  {note}")


@migrate_app.command("layout")
def migrate_layout_cmd(
    source: Annotated[Path, typer.Argument(help="Workspace to read")],
    target: Annotated[Path, typer.Argument(help="Workspace to write (must not exist)")],
    commit: Annotated[bool, typer.Option(help="git init + one commit over the new tree")] = True,
) -> None:
    """Restructure SOURCE into TARGET; bulk payloads are hard-linked."""
    report = migrate_workspace(source, target)
    adopted = 0
    if commit:
        history = GitHistory(target)
        if history.init():
            adopted = replay_history(source.resolve(), target.resolve())
            history.sweep(f"migrate {source.name} -> {target.name}")

    rprint(f"[green]OK[/green] {source} -> {target}")
    if adopted:
        rprint(f"  {adopted} pre-migration fact(s) adopted into the history")
    rprint(
        f"  {report.projects} project(s), {report.experiments} experiment(s), "
        f"{report.runs} run(s), {report.executions} execution(s), "
        f"{report.artifacts} artifact(s)"
    )
    rprint(f"  {report.linked_files} file(s) hard-linked, {report.copied_files} copied")
    if report.dropped:
        summary = ", ".join(f"{name} x{count}" for name, count in sorted(report.dropped.items()))
        rprint(f"  dropped: {summary}")


@dataclass
class WorkflowKindReport:
    """What ``migrate workflow-kind`` classified. ``dry_run`` writes nothing."""

    code: int = 0
    document: int = 0
    unbound: int = 0
    skipped: int = 0
    notes: list[str] = field(default_factory=list)
    dry_run: bool = False


def migrate_workflow_kind(workspace: Path, *, dry_run: bool = False) -> WorkflowKindReport:
    """Bind legacy experiments in place through ``Experiment.bind_workflow``.

    Experiments that already have ``workflow_kind`` are counted as skipped
    and left untouched. A classification with no kind stays unbound. Dry-run
    counts the same way and writes nothing. The only write is
    ``Experiment.bind_workflow``.

    Args:
        workspace: Workspace root to open with ``Workspace.load``.
        dry_run: When true, classify only.

    Returns:
        Counts, per-experiment notes, and whether this was a dry run.

    Raises:
        typer.BadParameter: *workspace* is not an existing directory.
    """
    report = WorkflowKindReport(dry_run=dry_run)
    root = workspace.expanduser().resolve()
    if not root.is_dir():
        raise typer.BadParameter(f"{root} is not a directory")

    ws = Workspace.load(root)
    for project in ws.list_projects():
        for exp in project.list_experiments():
            if exp.workflow_kind is not None:
                report.skipped += 1
                continue
            classified = classify_legacy_workflow(exp)
            if classified.note:
                report.notes.append(f"{project.name}/{exp.name}: {classified.note}")
            if classified.kind is None:
                report.unbound += 1
                continue
            if classified.kind == "code":
                report.code += 1
            else:
                report.document += 1
            if not dry_run:
                exp.bind_workflow(
                    classified.kind,
                    entrypoint=classified.entrypoint,
                    document=classified.document,
                )
    return report


@migrate_app.command("workflow-kind")
def migrate_workflow_kind_cmd(
    workspace: Annotated[
        Path,
        typer.Argument(help="Workspace root to classify in place"),
    ] = Path(),
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Classify only; write nothing"),
    ] = False,
) -> None:
    """Bind legacy experiments to a workflow kind. ``--dry-run`` writes nothing."""
    report = migrate_workflow_kind(workspace, dry_run=dry_run)
    suffix = " (dry run)" if report.dry_run else ""
    rprint(f"[green]OK[/green] workflow-kind{suffix} {workspace.expanduser().resolve()}")
    rprint(f"code: {report.code}")
    rprint(f"document: {report.document}")
    rprint(f"unbound: {report.unbound}")
    rprint(f"skipped: {report.skipped}")
    for note in report.notes:
        rprint(note)


def migrate_assets(workspace: Path, *, dry_run: bool = False):
    """Rewrite legacy asset records in *workspace*.

    Args:
        workspace: Workspace root to open with ``Workspace.load``.
        dry_run: When true, report only.

    Returns:
        The migration report. Paths are relative to the workspace root.

    Raises:
        typer.BadParameter: *workspace* is not a molab workspace.
    """
    from molab.workspace.artifact_repository import migrate_legacy_assets

    root = workspace.expanduser().resolve()
    try:
        loaded = Workspace.load(root)
    except FileNotFoundError as exc:
        raise typer.BadParameter(f"{root} is not a molab workspace") from exc
    return migrate_legacy_assets(loaded, dry_run=dry_run)


@migrate_app.command("assets")
def migrate_assets_cmd(
    workspace: Annotated[
        Path,
        typer.Argument(help="Workspace root whose asset records to rewrite"),
    ] = Path(),
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Report only; write nothing"),
    ] = False,
) -> None:
    """Rewrite legacy asset records and drop dead manifests. ``--dry-run`` writes nothing."""
    report = migrate_assets(workspace, dry_run=dry_run)
    root = workspace.expanduser().resolve()
    if report.dry_run:
        rprint(f"[yellow]DRY-RUN[/yellow] assets {root}")
    else:
        rprint(f"[green]OK[/green] assets {root}")
    rprint(f"rewritten: {len(report.rewritten)}")
    rprint(f"manifests removed: {len(report.manifests_removed)}")
    for path in (*report.rewritten, *report.manifests_removed):
        rprint(f"  {path}")
    if report.commit:
        rprint(f"commit: {report.commit}")
    for asset_id in report.unresolved:
        rprint(f"asset {asset_id}: source artifact no longer exists - delete or re-promote it")
    if report.unresolved:
        raise typer.Exit(1)


# Pre-canonical knowledge spellings. Runtime code only writes
# ``knowledges/<stem>.md``; these literals exist solely so ``migrate knowledge``
# can find an un-migrated tree. Do not teach the rest of molab to read them again.
_LEGACY_HEAD_FILES = {
    "note.json": "Note",
    "literature.json": "Literature",
    "report.json": "Report",
    "finding.json": "Finding",
    "plan.json": "Plan",
    "observation.json": "Observation",
}
_LEGACY_INDEX = "index.md"
_LEGACY_REFERENCES_DIR = "references"
_LEGACY_REFERENCES_MARKER = ("meta.json", "bundle.references")

_SCHEME_TARGET = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


@dataclass
class _KnowledgeDoc:
    """One legacy or canonical document in the migration plan."""

    form: str
    host: Path
    old: Path
    stem: str
    original: str
    dest: Path | None = None
    head_name: str | None = None
    head_sources: list[dict[str, object]] = field(default_factory=list)
    final: str = ""
    rewritten: int = 0


@dataclass
class KnowledgeReport:
    """What ``migrate knowledge`` would change, or did change."""

    dry_run: bool = False
    moved: list[tuple[str, str]] = field(default_factory=list)
    relinked: list[str] = field(default_factory=list)
    links_rewritten: int = 0
    sources_folded: int = 0
    unresolved: list[tuple[str, str]] = field(default_factory=list)
    ambiguous: list[tuple[str, str, tuple[str, ...]]] = field(default_factory=list)
    collisions: list[tuple[str, str]] = field(default_factory=list)
    leftovers: list[str] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    commit: str | None = None

    @property
    def changed(self) -> bool:
        """True when a document moved or a canonical document was rewritten."""
        return bool(self.moved or self.relinked)


def migrate_knowledge(workspace: Path, *, dry_run: bool = False) -> KnowledgeReport:
    """Move legacy knowledge documents into ``knowledges/<stem>.md``.

    Plans every rewrite before touching disk. ``dry_run`` returns that plan
    and writes nothing. A real run performs each move, content write and
    legacy deletion through knowledge verbs, then records one
    ``knowledge.migrated`` commit when anything changed.

    Args:
        workspace: Workspace root. A path inside a workspace, or outside
            every workspace, is refused.
        dry_run: Report the plan and write nothing.

    Returns:
        The plan, filled in the same way for a dry run and a real run.

    Raises:
        typer.BadParameter: *workspace* is not a workspace root.
    """
    root = _knowledge_require_root(workspace)
    report = KnowledgeReport(dry_run=dry_run)
    loaded = Workspace.load(root)
    docs, markers = _knowledge_discover(loaded, report)
    _knowledge_assign(loaded, docs, report)
    moves = _knowledge_moves(docs)
    index, by_id, by_digest = _knowledge_entity_index(loaded)
    for doc in docs:
        _knowledge_compose(loaded, doc, report, moves, index, by_id, by_digest)
    if dry_run:
        return report
    touched = _knowledge_apply(loaded, docs, markers, report)
    if touched:
        report.commit = _knowledge_commit(loaded, touched)
    return report


def _knowledge_require_root(workspace: Path) -> Path:
    """The workspace root, or a typed refusal naming the root to pass."""
    root = Path(workspace).expanduser().resolve()
    found = Workspace.enclosing_root(root)
    if found is None:
        raise typer.BadParameter(f"{root} is not inside a molab workspace")
    if Path(found).resolve() != root:
        raise typer.BadParameter(f"{root} lies inside workspace {found}; pass the workspace root")
    return root


def _knowledge_rel(root: Path, path: Path) -> str:
    """Workspace-relative POSIX spelling of *path*."""
    return PurePosixPath(os.path.relpath(path, root)).as_posix()


def _knowledge_norm(path: object) -> str:
    """Lexical absolute spelling used as an index key."""
    return os.path.normpath(str(path))


def _knowledge_entries(fs: FileSystem, directory: Path) -> list[DirEntry]:
    """One listing of *directory*. A missing path is an empty listing."""
    try:
        return fs.scandir(directory, with_stat=False)
    except (FileNotFoundError, NotADirectoryError):
        return []


def _knowledge_read(fs: FileSystem, path: Path) -> str:
    """File text through the workspace filesystem."""
    return str(fs.read_text(path))


def _knowledge_stem(name: str) -> str:
    """Filename stem, keeping case and inner dots."""
    suffix = PurePosixPath(name).suffix.lower()
    if suffix in {".md", ".mdx"}:
        return name[: -len(suffix)]
    return name


def _knowledge_frontmatter(text: str) -> tuple[dict[str, object], str | None]:
    """Parsed frontmatter, or a skip reason when a fence does not split."""
    from molab.knowledge.frontmatter import split_frontmatter

    if not text.startswith("---"):
        return {}, None
    meta, _body = split_frontmatter(text)
    if not meta:
        return {}, "malformed frontmatter"
    return meta, None


def _knowledge_class_name(meta: dict[str, object]) -> str | None:
    """A frontmatter ``class`` that names a knowledge class, else ``None``."""
    from molab.knowledge import parse_class

    name = meta.get("class")
    if not isinstance(name, str) or name == "":
        return None
    try:
        parse_class(name)
    except ValueError:
        return None
    return name


def _knowledge_discover(
    workspace: Workspace,
    report: KnowledgeReport,
) -> tuple[list[_KnowledgeDoc], list[Path]]:
    """Legacy and canonical documents, plus reference dirs that carry the marker."""
    docs: list[_KnowledgeDoc] = []
    markers: list[Path] = []
    root = Path(workspace.root)
    for host_raw in Workspace.list_hosts(workspace.root, fs=workspace.fs):
        host = Path(str(host_raw))
        docs.extend(_knowledge_host_files(workspace, root, host, report))
        found, marked = _knowledge_references(workspace, root, host, report)
        docs.extend(found)
        if marked is not None:
            markers.append(marked)
        docs.extend(_knowledge_container(workspace, root, host, report))
    return docs, markers


def _knowledge_host_files(
    workspace: Workspace,
    root: Path,
    host: Path,
    report: KnowledgeReport,
) -> list[_KnowledgeDoc]:
    """Host-level markdown whose frontmatter names a knowledge class."""
    from molab.knowledge.naming import KNOWLEDGE_CONTAINER, is_knowledge_file

    fs = workspace.fs
    docs: list[_KnowledgeDoc] = []
    for entry in _knowledge_entries(fs, host):
        if entry.name in {KNOWLEDGE_CONTAINER, _LEGACY_REFERENCES_DIR} or not entry.is_file:
            continue
        if not is_knowledge_file(entry.name):
            continue
        path = Path(fs.join(host, entry.name))
        name = entry.name
        text = _knowledge_read(fs, path)
        meta, reason = _knowledge_frontmatter(text)
        rel = _knowledge_rel(root, path)
        if reason is not None:
            report.skipped.append((rel, reason))
            continue
        if _knowledge_class_name(meta) is None:
            report.skipped.append((rel, "no knowledge class"))
            continue
        docs.append(
            _KnowledgeDoc(form="a", host=host, old=path, stem=_knowledge_stem(name), original=text)
        )
    return docs


def _knowledge_references(
    workspace: Workspace,
    root: Path,
    host: Path,
    report: KnowledgeReport,
) -> tuple[list[_KnowledgeDoc], Path | None]:
    """``references/<key>.md`` files and ``references/<key>/`` literature dirs."""
    from molab.knowledge.naming import is_knowledge_file

    fs = workspace.fs
    refs = Path(fs.join(host, _LEGACY_REFERENCES_DIR))
    docs: list[_KnowledgeDoc] = []
    for entry in _knowledge_entries(fs, refs):
        path = Path(fs.join(refs, entry.name))
        if entry.is_file and is_knowledge_file(entry.name):
            doc = _knowledge_reference_file(fs, root, host, path, entry.name, report)
            if doc is not None:
                docs.append(doc)
        elif entry.is_dir:
            doc = _knowledge_literature_dir(fs, host, path, entry.name)
            if doc is not None:
                docs.append(doc)
    marker = _knowledge_marker(fs, refs)
    return docs, marker


def _knowledge_reference_file(
    fs: FileSystem,
    root: Path,
    host: Path,
    path: Path,
    name: str,
    report: KnowledgeReport,
) -> _KnowledgeDoc | None:
    """One ``references/<key>.md``, defaulting a missing class to Literature."""
    text = _knowledge_read(fs, path)
    meta, reason = _knowledge_frontmatter(text)
    if reason is not None:
        report.skipped.append((_knowledge_rel(root, path), reason))
        return None
    if "class" in meta and _knowledge_class_name(meta) is None:
        report.skipped.append((_knowledge_rel(root, path), "no knowledge class"))
        return None
    if _knowledge_class_name(meta) is None:
        text = _knowledge_with_class(text, meta, "Literature")
    return _KnowledgeDoc(form="b", host=host, old=path, stem=_knowledge_stem(name), original=text)


def _knowledge_with_class(text: str, meta: dict[str, object], class_name: str) -> str:
    """Ensure *text* carries a knowledge ``class``."""
    from molab.knowledge.frontmatter import dump_frontmatter, split_frontmatter

    _meta, body = split_frontmatter(text)
    merged = dict(meta)
    merged["class"] = class_name
    return dump_frontmatter(merged, body if meta else text)


def _knowledge_literature_dir(
    fs: FileSystem, host: Path, path: Path, name: str
) -> _KnowledgeDoc | None:
    """One ``references/<key>/literature.json`` plus its ``index.md``."""
    head_path = Path(fs.join(path, "literature.json"))
    if not fs.is_file(head_path):
        return None
    return _knowledge_headed_dir(fs, host, path, name, "literature.json", "c")


def _knowledge_container(
    workspace: Workspace,
    root: Path,
    host: Path,
    report: KnowledgeReport,
) -> list[_KnowledgeDoc]:
    """Canonical markdown and directory-form documents under ``knowledges/``."""
    from molab.knowledge.naming import KNOWLEDGE_CONTAINER, is_knowledge_file

    fs = workspace.fs
    container = Path(fs.join(host, KNOWLEDGE_CONTAINER))
    docs: list[_KnowledgeDoc] = []
    for entry in _knowledge_entries(fs, container):
        path = Path(fs.join(container, entry.name))
        if entry.is_file and is_knowledge_file(entry.name):
            doc = _knowledge_canonical(fs, root, host, path, entry.name, report)
            if doc is not None:
                docs.append(doc)
        elif entry.is_dir:
            doc = _knowledge_directory_form(fs, root, host, path, entry.name, report)
            if doc is not None:
                docs.append(doc)
    return docs


def _knowledge_canonical(
    fs: FileSystem,
    root: Path,
    host: Path,
    path: Path,
    name: str,
    report: KnowledgeReport,
) -> _KnowledgeDoc | None:
    """One ``knowledges/*.md`` to relink in place."""
    text = _knowledge_read(fs, path)
    meta, reason = _knowledge_frontmatter(text)
    rel = _knowledge_rel(root, path)
    if reason is not None:
        report.skipped.append((rel, reason))
        return None
    if _knowledge_class_name(meta) is None:
        report.skipped.append((rel, "no knowledge class"))
        return None
    return _KnowledgeDoc(
        form="e", host=host, old=path, stem=_knowledge_stem(name), original=text, dest=path
    )


def _knowledge_directory_form(
    fs: FileSystem,
    root: Path,
    host: Path,
    path: Path,
    name: str,
    report: KnowledgeReport,
) -> _KnowledgeDoc | None:
    """A directory holding exactly one class-named head."""
    names = {entry.name for entry in _knowledge_entries(fs, path)}
    heads = [name for name in names if name in _LEGACY_HEAD_FILES]
    if len(heads) != 1:
        if _LEGACY_INDEX in names:
            report.skipped.append((_knowledge_rel(root, path), "no knowledge class"))
        return None
    return _knowledge_headed_dir(fs, host, path, name, heads[0], "d")


def _knowledge_headed_dir(
    fs: FileSystem,
    host: Path,
    path: Path,
    name: str,
    head_name: str,
    form: str,
) -> _KnowledgeDoc:
    """Fold a class-named head and ``index.md`` into one markdown document."""
    from molab.knowledge.frontmatter import dump_frontmatter

    payload = json.loads(_knowledge_read(fs, Path(fs.join(path, head_name))))
    if not isinstance(payload, dict):
        payload = {}
    raw_sources = payload.get("sources")
    source_rows = raw_sources if isinstance(raw_sources, list) else []
    rows: list[dict[str, object]] = []
    for row in source_rows:
        if isinstance(row, dict):
            rows.append({str(key): value for key, value in row.items()})
    index_path = Path(fs.join(path, _LEGACY_INDEX))
    body = _knowledge_read(fs, index_path) if fs.is_file(index_path) else ""
    kept = {
        str(key): value
        for key, value in payload.items()
        if key not in {"sources", "type", "kind", "id"}
    }
    kept["class"] = _LEGACY_HEAD_FILES[head_name]
    text = dump_frontmatter(kept, body)
    return _KnowledgeDoc(
        form=form,
        host=host,
        old=path,
        stem=name,
        original=text,
        head_name=head_name,
        head_sources=rows,
    )


def _knowledge_marker(fs: FileSystem, refs: Path) -> Path | None:
    """The references directory when its marker names the legacy bundle."""
    marker_name, marker_type = _LEGACY_REFERENCES_MARKER
    path = Path(fs.join(refs, marker_name))
    if not fs.is_file(path):
        return None
    payload = json.loads(_knowledge_read(fs, path))
    if isinstance(payload, dict) and payload.get("type") == marker_type:
        return refs
    return None


def _knowledge_assign(
    workspace: Workspace,
    docs: list[_KnowledgeDoc],
    report: KnowledgeReport,
) -> None:
    """Give each legacy document a free ``<stem>.md`` under its host."""
    from molab.knowledge.naming import KNOWLEDGE_CONTAINER
    from molab.workspace.naming import disambiguate

    root = Path(workspace.root)
    by_host: dict[str, list[_KnowledgeDoc]] = {}
    for doc in docs:
        by_host.setdefault(_knowledge_norm(doc.host), []).append(doc)
    for host_key, group in by_host.items():
        host = Path(host_key)
        container = host / KNOWLEDGE_CONTAINER
        taken = {doc.stem for doc in group if doc.form == "e"}
        for entry in _knowledge_entries(workspace.fs, container):
            if entry.is_file:
                taken.add(_knowledge_stem(entry.name))
        for doc in group:
            if doc.form == "e":
                continue
            asked = doc.stem
            actual = disambiguate(asked, taken)
            taken.add(actual)
            doc.dest = container / f"{actual}.md"
            doc.stem = actual
            if actual != asked:
                report.collisions.append(
                    (
                        _knowledge_rel(root, container / f"{asked}.md"),
                        _knowledge_rel(root, doc.dest),
                    )
                )


def _knowledge_moves(docs: list[_KnowledgeDoc]) -> dict[str, str]:
    """Absolute old path → absolute new file, for files, dirs and index files."""
    moves: dict[str, str] = {}
    for doc in docs:
        if doc.dest is None or _knowledge_norm(doc.old) == _knowledge_norm(doc.dest):
            continue
        dest = _knowledge_norm(doc.dest)
        if doc.form in {"a", "b"}:
            moves[_knowledge_norm(doc.old)] = dest
        else:
            moves[_knowledge_norm(doc.old)] = dest
            moves[_knowledge_norm(doc.old / _LEGACY_INDEX)] = dest
    return moves


def _knowledge_entity_index(
    workspace: Workspace,
) -> tuple[dict[str, MolabRef], dict[str, list[MolabRef]], dict[str, list[MolabRef]]]:
    """Absolute path → reference, plus artifact id and digest maps."""
    from molab.workspace.artifact_repository import scan_asset_repositories, walk_artifacts
    from molab.workspace.refs import MolabRef

    index: dict[str, MolabRef] = {}
    by_id: dict[str, list[MolabRef]] = {}
    by_digest: dict[str, list[MolabRef]] = {}
    for project in workspace.list_projects():
        index[_knowledge_norm(project.resolve())] = MolabRef(project_id=project.id)
        for experiment in project.list_experiments():
            index[_knowledge_norm(experiment.resolve())] = MolabRef(experiment_id=experiment.id)
            for run in experiment.list_runs():
                index[_knowledge_norm(run.resolve())] = MolabRef(
                    experiment_id=experiment.id, run_id=run.id
                )
                for execution in run.executions:
                    index[_knowledge_norm(run.execution_dir(execution.id))] = MolabRef(
                        experiment_id=experiment.id,
                        run_id=run.id,
                        execution_id=execution.id,
                    )
    for loc in walk_artifacts(workspace):
        ref = MolabRef(
            experiment_id=loc.experiment_id,
            run_id=loc.run_id,
            artifact_id=loc.artifact.id,
        )
        if loc.location:
            index[_knowledge_norm(loc.location)] = ref
        by_id.setdefault(loc.artifact.id, []).append(ref)
        by_digest.setdefault(loc.artifact.content.digest, []).append(ref)
    for repo in scan_asset_repositories(workspace):
        for asset in repo.list():
            _knowledge_index_asset(index, repo, asset)
    return index, by_id, by_digest


def _knowledge_index_asset(index: dict[str, MolabRef], repo: AssetRepository, asset: Asset) -> None:
    """Map one asset payload path when the repository can name it."""
    from molab.workspace.refs import MolabRef

    try:
        payload = repo.payload_path(asset.id)
    except (KeyError, LookupError, OSError, ValueError):
        return
    if "://" in payload:
        return
    index[_knowledge_norm(payload)] = MolabRef(asset_id=asset.id)


def _knowledge_compose(
    workspace: Workspace,
    doc: _KnowledgeDoc,
    report: KnowledgeReport,
    moves: dict[str, str],
    index: dict[str, MolabRef],
    by_id: dict[str, list[MolabRef]],
    by_digest: dict[str, list[MolabRef]],
) -> None:
    """Fill *doc.final* and the report counters. No disk writes."""
    from molab.knowledge.concept import append_source_links, retarget_links
    from molab.knowledge.frontmatter import dump_frontmatter, split_frontmatter

    if doc.dest is None:
        return
    root = Path(workspace.root)
    old_base = doc.old if doc.form in {"c", "d"} else doc.old.parent
    old_dir = _knowledge_norm(old_base)
    new_dir = _knowledge_norm(doc.dest.parent)
    meta, body = split_frontmatter(doc.original)
    rows = _knowledge_rows(meta, doc.head_sources)
    meta.pop("sources", None)
    qualified, leftover = _knowledge_qualify(
        workspace, rows, _knowledge_rel(root, doc.dest), new_dir, by_id, by_digest, report
    )
    report.sources_folded += len(qualified)

    def _rewrite(target: str, image: bool) -> str | None:
        return _knowledge_rewrite(
            target, image, old_dir=old_dir, new_dir=new_dir, moves=moves, index=index
        )

    rewritten, count = retarget_links(body, _rewrite)
    doc.rewritten = count
    report.links_rewritten += count
    extended, _appended = append_source_links(rewritten, qualified, base_dir=new_dir)
    if leftover:
        meta["sources"] = leftover
    if count == 0 and not qualified and not leftover:
        doc.final = doc.original
    else:
        doc.final = dump_frontmatter(meta, extended)
    if doc.form == "e":
        if doc.final != doc.original:
            report.relinked.append(_knowledge_rel(root, doc.dest))
    else:
        report.moved.append((_knowledge_rel(root, doc.old), _knowledge_rel(root, doc.dest)))


def _knowledge_rows(
    meta: dict[str, object], extra: list[dict[str, object]]
) -> list[dict[str, object]]:
    """Frontmatter ``sources`` plus head rows, de-duplicated on kind/ref/span."""
    rows: list[dict[str, object]] = []
    raw = meta.get("sources")
    if isinstance(raw, list):
        for row in raw:
            if isinstance(row, dict):
                rows.append({str(key): value for key, value in row.items()})
    rows.extend(extra)
    seen: set[tuple[str, str, object]] = set()
    unique: list[dict[str, object]] = []
    for row in rows:
        key = (str(row.get("kind") or ""), str(row.get("ref") or ""), row.get("span"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def _knowledge_qualify(
    workspace: Workspace,
    rows: list[dict[str, object]],
    doc_rel: str,
    new_dir: str,
    by_id: dict[str, list[MolabRef]],
    by_digest: dict[str, list[MolabRef]],
    report: KnowledgeReport,
) -> tuple[list[SourceRef], list[dict[str, object]]]:
    """Qualified sources, and the rows that stay in frontmatter."""
    experiment_id = ""
    for row in rows:
        if str(row.get("kind") or "") == "experiment":
            experiment_id = _knowledge_experiment_id(str(row.get("ref") or ""))
            break
    qualified: list[SourceRef] = []
    leftover: list[dict[str, object]] = []
    for row in rows:
        source = _knowledge_qualify_row(
            workspace, row, doc_rel, new_dir, experiment_id, by_id, by_digest, report
        )
        if source is None:
            leftover.append(row)
        else:
            qualified.append(source)
    return qualified, leftover


def _knowledge_experiment_id(ref: str) -> str:
    """Bare experiment id, or the experiment segment of a reference."""
    from molab.workspace.refs import is_ref, parse_ref

    if is_ref(ref):
        parsed = parse_ref(ref)
        if parsed.experiment_id:
            return parsed.experiment_id
    return ref


def _knowledge_span(row: dict[str, object]) -> str | None:
    span = row.get("span")
    if span is None or span == "":
        return None
    return str(span)


def _knowledge_qualify_row(
    workspace: Workspace,
    row: dict[str, object],
    doc_rel: str,
    new_dir: str,
    experiment_id: str,
    by_id: dict[str, list[MolabRef]],
    by_digest: dict[str, list[MolabRef]],
    report: KnowledgeReport,
) -> SourceRef | None:
    """One source row as a ``SourceRef``, or ``None`` when it stays unresolved."""
    from typing import cast

    from pydantic import ValidationError

    from molab.knowledge.knowledge_item import SourceKind, SourceRef
    from molab.workspace.refs import is_ref, parse_ref

    kind = str(row.get("kind") or "")
    ref = str(row.get("ref") or "")
    span = _knowledge_span(row)
    label = f"{kind}:{ref}"
    if is_ref(ref):
        try:
            chosen = cast(SourceKind, kind or parse_ref(ref).kind)
            return SourceRef(kind=chosen, ref=ref, span=span)
        except (ValueError, ValidationError):
            report.unresolved.append((doc_rel, label))
            return None
    if kind == "run":
        return _knowledge_qualify_run(workspace, ref, span, experiment_id, doc_rel, report)
    if kind == "experiment":
        return _knowledge_qualify_experiment(workspace, ref, span, doc_rel, report)
    if kind == "artifact":
        return _knowledge_qualify_artifact(workspace, ref, span, doc_rel, by_id, by_digest, report)
    if kind in {"reference", "file", "agent_action", "decision"}:
        try:
            source = SourceRef(kind=kind, ref=ref, span=span)
            source.link_target(new_dir)
        except (ValueError, ValidationError):
            report.unresolved.append((doc_rel, label))
            return None
        return source
    report.unresolved.append((doc_rel, label))
    return None


def _knowledge_qualify_run(
    workspace: Workspace,
    ref: str,
    span: str | None,
    experiment_id: str,
    doc_rel: str,
    report: KnowledgeReport,
) -> SourceRef | None:
    """Qualify a bare run id, preferring the document's experiment source."""
    from molab.knowledge.knowledge_item import SourceRef
    from molab.workspace.refs import AmbiguousRefError, MolabRef, RefNotFoundError, qualify_run_id

    label = f"run:{ref}"
    if experiment_id:
        built = MolabRef(experiment_id=experiment_id, run_id=ref)
        try:
            workspace.find(built)
        except RefNotFoundError:
            report.unresolved.append((doc_rel, label))
            return None
        except AmbiguousRefError as exc:
            report.ambiguous.append((doc_rel, label, tuple(str(item) for item in exc.candidates)))
            return None
        return SourceRef(kind="run", ref=str(built), span=span)
    try:
        built = qualify_run_id(workspace, ref)
    except RefNotFoundError:
        report.unresolved.append((doc_rel, label))
        return None
    except AmbiguousRefError as exc:
        report.ambiguous.append((doc_rel, label, tuple(str(item) for item in exc.candidates)))
        return None
    return SourceRef(kind="run", ref=str(built), span=span)


def _knowledge_qualify_experiment(
    workspace: Workspace,
    ref: str,
    span: str | None,
    doc_rel: str,
    report: KnowledgeReport,
) -> SourceRef | None:
    """Qualify a bare experiment id."""
    from molab.knowledge.knowledge_item import SourceRef
    from molab.workspace.refs import AmbiguousRefError, MolabRef, RefNotFoundError

    built = MolabRef(experiment_id=_knowledge_experiment_id(ref))
    try:
        workspace.find(built)
    except RefNotFoundError:
        report.unresolved.append((doc_rel, f"experiment:{ref}"))
        return None
    except AmbiguousRefError as exc:
        report.ambiguous.append(
            (doc_rel, f"experiment:{ref}", tuple(str(item) for item in exc.candidates))
        )
        return None
    return SourceRef(kind="experiment", ref=str(built), span=span)


def _knowledge_qualify_artifact(
    workspace: Workspace,
    ref: str,
    span: str | None,
    doc_rel: str,
    by_id: dict[str, list[MolabRef]],
    by_digest: dict[str, list[MolabRef]],
    report: KnowledgeReport,
) -> SourceRef | None:
    """Match an artifact id or content digest, then confirm it with ``find``."""
    from molab.knowledge.knowledge_item import SourceRef
    from molab.workspace.refs import AmbiguousRefError, RefNotFoundError

    hits = by_id.get(ref) or by_digest.get(ref) or []
    label = f"artifact:{ref}"
    if len(hits) > 1:
        report.ambiguous.append((doc_rel, label, tuple(str(item) for item in hits)))
        return None
    if len(hits) == 1:
        try:
            workspace.find(hits[0])
        except RefNotFoundError:
            report.unresolved.append((doc_rel, label))
            return None
        except AmbiguousRefError as exc:
            report.ambiguous.append((doc_rel, label, tuple(str(item) for item in exc.candidates)))
            return None
        return SourceRef(kind="artifact", ref=str(hits[0]), span=span)
    report.unresolved.append((doc_rel, label))
    return None


def _knowledge_rewrite(
    target: str,
    image: bool,
    *,
    old_dir: str,
    new_dir: str,
    moves: dict[str, str],
    index: dict[str, MolabRef],
) -> str | None:
    """New target for one link, or ``None`` to leave it alone."""
    if target.startswith("#") or _SCHEME_TARGET.match(target) or Path(target).is_absolute():
        return None
    path, sep, frag = target.partition("#")
    absolute = _knowledge_norm(Path(old_dir) / path)
    if absolute in moves:
        updated = _knowledge_posix_rel(moves[absolute], new_dir)
    elif not image and absolute in index:
        updated = str(index[absolute])
    elif old_dir != new_dir:
        updated = _knowledge_posix_rel(absolute, new_dir)
    else:
        return None
    if sep:
        return f"{updated}#{frag}"
    return updated


def _knowledge_posix_rel(path: str, start: str) -> str:
    """POSIX relative path from *start* to *path*."""
    return PurePosixPath(os.path.relpath(path, start)).as_posix()


def _knowledge_apply(
    workspace: Workspace,
    docs: list[_KnowledgeDoc],
    markers: list[Path],
    report: KnowledgeReport,
) -> list[Path]:
    """Move, write and delete through knowledge verbs.

    Returns the files this run wrote or removed. A directory that still holds
    an attachment is not included, so a later commit cannot stage it.
    """
    from molab.knowledge.concept import Concept, remove_legacy_files

    fs = workspace.fs
    root = Path(workspace.root)
    touched: list[Path] = []
    for doc in docs:
        if doc.dest is None:
            continue
        if doc.form in {"a", "b"}:
            handle = Concept.open(doc.old, fs=fs)
            handle.move_to(doc.host, stem=doc.stem, relink=False)
            Concept.write_document(handle.path, doc.final, fs=fs)
            touched.extend((doc.dest, doc.old))
        elif doc.form in {"c", "d"}:
            Concept.write_document(doc.dest, doc.final, fs=fs)
            names = [name for name in (doc.head_name, _LEGACY_INDEX) if name]
            left = remove_legacy_files(doc.old, names, fs=fs)
            touched.append(doc.dest)
            touched.extend(doc.old / name for name in names)
            if left:
                report.leftovers.append(_knowledge_rel(root, doc.old))
        elif doc.final != doc.original:
            Concept.write_document(doc.dest, doc.final, fs=fs)
            touched.append(doc.dest)
    marker_name = _LEGACY_REFERENCES_MARKER[0]
    for refs in markers:
        left = remove_legacy_files(refs, [marker_name], fs=fs)
        touched.append(refs / marker_name)
        if left:
            report.leftovers.append(_knowledge_rel(root, refs))
    return touched


def _knowledge_commit(workspace: Workspace, paths: list[Path]) -> str | None:
    """One ``knowledge.migrated`` commit covering the files this run touched."""
    from molab.workspace.history import EntityRef, GitHistory

    if not paths:
        return None
    return GitHistory(workspace.root).record(
        "knowledge.migrated",
        subject=EntityRef(id=workspace.id, type="workspace"),
        summary="migrate knowledge documents",
        paths=tuple(paths),
    )


@migrate_app.command("knowledge")
def migrate_knowledge_cmd(
    workspace: Annotated[
        Path,
        typer.Argument(help="Workspace root whose knowledge documents to migrate"),
    ] = Path(),
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Report the plan; write nothing"),
    ] = False,
) -> None:
    """Move legacy knowledge documents into knowledges/<stem>.md. ``--dry-run`` writes nothing."""
    root = workspace.expanduser().resolve()
    report = migrate_knowledge(workspace, dry_run=dry_run)
    if report.dry_run:
        rprint(f"[yellow]DRY-RUN[/yellow] knowledge {root}")
    else:
        rprint(f"[green]OK[/green] knowledge {root}")
    for old, new in report.moved:
        rprint(f"  {old} -> {new}")
    rprint(f"moved: {len(report.moved)}")
    rprint(f"relinked: {len(report.relinked)}")
    rprint(f"links rewritten: {report.links_rewritten}")
    rprint(f"sources folded: {report.sources_folded}")
    for intended, actual in report.collisions:
        rprint(f"collision: {intended} -> {actual}")
    for doc, label in report.unresolved:
        rprint(f"unresolved: {doc} {label}")
    for doc, label, _candidates in report.ambiguous:
        rprint(f"ambiguous: {doc} {label}")
    for leftover in report.leftovers:
        rprint(f"leftover: {leftover}")
    for path, reason in report.skipped:
        rprint(f"skipped: {path} {reason}")
    if report.commit:
        rprint(f"commit: {report.commit}")
