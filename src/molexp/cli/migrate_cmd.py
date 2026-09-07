"""``molexp migrate`` — restructure an old workspace into the current layout.

Reads a source workspace and writes a new one whose paths a person can read:
experiments named by their name, runs named by their parameters, attempts
numbered ``e01`` / ``e02``. Every fragment that only re-encoded something
already on disk is dropped — the derived children indexes, the provenance
event tree, the artifact index, the content-addressed side store — and the
facts the event tree carried are adopted as the new repository's first
commits, so ``git log`` still answers what happened before the move.

Bulk payloads (``work/``, artifact and asset bytes) are **hard-linked**, so
the new workspace costs metadata only and the source tree stays intact as a
fallback until the operator deletes it. A hard link means the two names are
one file: replacing a file in the archive is private, but *appending* to one
would write through into the source. Every append in molexp goes through
``FileStore``, which breaks the link first — see ``_unshare`` there.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import typer

from molexp.cli._common import rprint
from molexp.workspace.execution_dirs import ARTIFACTS, OUT, WORK
from molexp.workspace.history import (
    AgentRef,
    EntityRef,
    GitHistory,
    Relation,
    default_gitignore,
)
from molexp.workspace.naming import entity_slug, execution_slug, run_slug

migrate_app = typer.Typer(help="Restructure a workspace into the current layout")

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


def _created_at(payload: dict[str, Any], fallback: str) -> str:
    value = payload.get("created_at")
    return value if isinstance(value, str) else fallback


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
    target_root: Path,
    report: Report,
) -> dict[str, Any]:
    """Fold one attempt's scattered sidecars into a single ``execution.json``."""
    state = _read_json(src / "execution.json")
    environment = _read_json(src / "environment.json")
    exception = _read_json(src / "exception.json")
    job = _read_json(src / "job.json")
    slug = execution_slug(seq)
    dst.mkdir(parents=True, exist_ok=True)

    # Products: the bytes become `artifacts/`, the records become one inline list.
    artifacts: list[dict[str, Any]] = []
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
            record.pop("schema_version", None)
            record["name"] = name
            record["path"] = (dst / out_rel).relative_to(target_root).as_posix()
            record.setdefault("source_path", record.get("source_path") or f"{OUT.name}/{out_name}")
            record["execution_id"] = slug
            record["run_id"] = run_id
            record["project_id"] = project_id
            artifacts.append(record)
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

    created = _created_at(state, datetime.now(UTC).isoformat())
    error = state.get("error") or (exception or None)
    executor = state.get("executor") or ({"job": job} if job else {})
    if isinstance(environment.get("environment"), dict):
        environment = environment["environment"]
    if environment and not state.get("environment"):
        state["environment"] = environment
    # An attempt with no state file never recorded how it ended. That is
    # "interrupted", never "succeeded" — the migration must not invent a
    # result the source tree does not claim.
    status = str(state.get("status") or "interrupted")
    sealed = state.get("sealed_event_id") is not None or status in {
        "succeeded",
        "failed",
        "cancelled",
        "interrupted",
    }
    record = {
        "id": slug,
        "seq": seq,
        "run_id": run_id,
        "project_id": project_id,
        "mode": state.get("mode") or ("initial" if seq == 1 else "rerun"),
        "status": status,
        "created_at": created,
        "started_at": state.get("started_at") or created,
        "finished_at": state.get("finished_at"),
        "created_by": state.get("created_by")
        or {"id": "molexp", "type": "system", "name": "MolExp"},
        "based_on_execution_id": execution_slug(seq - 1)
        if seq > 1 and state.get("based_on_execution_id")
        else None,
        "checkpoint_artifact_id": state.get("checkpoint_artifact_id"),
        "executor": executor,
        "environment": state.get("environment") or {},
        "observed_input_ids": state.get("observed_input_ids") or [],
        "artifacts": artifacts,
        "evidence": [],
        "declaration_diff": {},
        "error": error,
        "sealed_at": state.get("finished_at") if sealed else None,
        "sealed_commit": None,
    }
    _write_json(dst / "execution.json", _stamp(record))
    report.executions += 1
    return record


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
    from molexp.workspace.naming import disambiguate

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
            key=lambda d: (_created_at(_read_json(d / "execution.json"), ""), d.name),
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
                target_root=target_root,
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
    from molexp.workspace.naming import disambiguate

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
    from molexp.workspace.naming import disambiguate

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
OVERSIZE_EVIDENCE_BYTES = 1 << 20


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
                id=str(agent_raw.get("id", "molexp")), type=agent_type, name=agent_raw.get("name")
            )
            if agent_type in {"person", "software", "workflow", "executor", "system"}
            else AgentRef(id=str(agent_raw.get("id", "molexp")), type="system")
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


@migrate_app.callback(invoke_without_command=True)
def migrate(
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
