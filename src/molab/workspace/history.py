"""Workspace history is git.

The files under a workspace are the **only** truth. Git is the audit log
over those files: every mutation ends in a commit whose trailers carry the
typed provenance fact (event / subject / agent / relations). Asking "what
happened to this run" is ``git log``; content-addressed storage is the git
object database; backup is ``git push`` or ``git bundle``.

Nothing in molab *reads* history to answer an operational question — a
sealed Execution keeps its own record in ``execution.json``, artifacts live
in the Execution that emitted them, assets live in the project's
``assets/``. History is therefore a soft dependency: a workspace with no
git, or a git that is momentarily locked by a sibling process, still runs
science correctly and simply records less.

Concurrency: writes are serialized by an advisory lock under
``.molab/locks/``. A worker that cannot take the lock quickly gives up and
leaves its files on disk — the next commit sweeps them in. Science never
blocks on git.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from mollog import get_logger
from pydantic import BaseModel, ConfigDict

from ._file_lock import FileLockTimeoutError, file_lock
from .execution_dirs import scratch_dirs
from .fs import PathArg

logger = get_logger(__name__)

MOLAB_DIR = ".molab"
"""Machine-only subtree: locks, caches, anything a human never opens."""

_TRAILER_EVENT = "Molab-Event"
_TRAILER_SUBJECT = "Molab-Subject"
_TRAILER_AGENT = "Molab-Agent"
_TRAILER_REL = "Molab-Rel"
_TRAILER_AT = "Molab-At"

_COMMIT_LOCK_TIMEOUT = 15.0

_GITIGNORE_HEAD = """\
# molab workspace history.
#
# Git holds the *record* of the science — entity files, parameters, execution
# state, logs, small products — so `git log` reads as a lab notebook and
# `git push` is the backup. It does not hold bulk payload: those bytes are
# reproducible, and versioning them would make the history unusable.

# Machine state.
.molab/
**/__pycache__/
*.pyc
"""

_GITIGNORE_BULK = """
# Trajectories, model weights, restarts, array dumps.
*.data
*.dump
*.restart
*.lammpstrj
*.dcd
*.xtc
*.trr
*.xyz
*.gen
*.h5
*.hdf5
*.npz
*.npy
*.pt
*.pth
*.ckpt
*.model
*.bin
*.zarr/
*.mrec/

# Solver logs that grow without bound; the run's own run.log is kept.
log.lammps
*.lammps.out
"""


def _scratch_rules() -> str:
    """Ignore rules for every attempt directory declared unversioned.

    Generated rather than written out, so a directory declared later cannot
    be left out of the history policy by omission.
    """
    lines = ["# Attempt directories whose bytes stay out of the history."]
    for directory in scratch_dirs():
        lines.append(f"# {directory.purpose}")
        # Scoped to an attempt on purpose. A bare ``**/out/`` would also
        # swallow an asset directory that happens to be called ``out``,
        # which is somebody else's data and not ours to ignore.
        lines.append(f"**/executions/*/{directory.name}/")
    return "\n".join(lines) + "\n"


def default_gitignore() -> str:
    """The workspace ``.gitignore``, with the scratch rules derived."""
    return f"{_GITIGNORE_HEAD}\n{_scratch_rules()}{_GITIGNORE_BULK}"


class AgentRef(BaseModel):
    """Person, software, workflow, or executor responsible for a fact."""

    model_config = ConfigDict(frozen=True)

    id: str
    type: Literal["person", "software", "workflow", "executor", "system"]
    name: str | None = None


SYSTEM_AGENT = AgentRef(id="molab", type="system", name="Molab")


class EntityRef(BaseModel):
    """Stable reference to a workspace entity."""

    model_config = ConfigDict(frozen=True)

    id: str
    type: str

    @property
    def urn(self) -> str:
        return f"urn:molab:{self.type}:{self.id}"


class Relation(BaseModel):
    """One directed, W3C-PROV-compatible relationship."""

    model_config = ConfigDict(frozen=True)

    predicate: str
    object: EntityRef


class HistoryEntry(BaseModel):
    """One commit read back as a provenance fact."""

    model_config = ConfigDict(frozen=True)

    commit: str
    event: str
    subject: EntityRef
    agent: AgentRef
    relations: tuple[Relation, ...] = ()
    occurred_at: datetime
    summary: str = ""

    def mentions(self, entity_id: str) -> bool:
        return self.subject.id == entity_id or any(
            relation.object.id == entity_id for relation in self.relations
        )


def _git_available() -> bool:
    return shutil.which("git") is not None


class GitHistory:
    """Append-only workspace history backed by a plain git repository."""

    def __init__(self, root: PathArg) -> None:
        self.root = Path(str(root))

    # ── repository ───────────────────────────────────────────────────────

    @property
    def git_dir(self) -> Path:
        return self.root / ".git"

    def enabled(self) -> bool:
        return _git_available() and self.git_dir.exists()

    def init(self) -> bool:
        """Create the repository and its ignore rules; idempotent."""
        if not _git_available():
            logger.debug("git not on PATH; workspace history disabled")
            return False
        if not self.git_dir.exists():
            self._git("init", "-q", "-b", "main", check=True)
        ignore = self.root / ".gitignore"
        if not ignore.exists():
            ignore.write_text(default_gitignore(), encoding="utf-8")
        return True

    # ── writing ──────────────────────────────────────────────────────────

    def record(
        self,
        event: str,
        *,
        subject: EntityRef,
        agent: AgentRef = SYSTEM_AGENT,
        relations: tuple[Relation, ...] = (),
        summary: str = "",
        paths: tuple[PathArg, ...] = (),
        occurred_at: datetime | None = None,
        stage: bool = True,
    ) -> str | None:
        """Commit *paths* with the fact encoded in the message trailers.

        ``stage=False`` records the fact alone, staging nothing and committing
        even though the tree is unchanged — how a fact that predates this
        repository is adopted into its history.

        Returns the commit sha, or ``None`` when nothing was recorded — no
        git, nothing staged, or a sibling process holds the lock. A ``None``
        return is never an error: the files are already on disk and the next
        commit will include them.
        """
        if not self.enabled():
            return None
        when = occurred_at or datetime.now(UTC)
        message = self._message(event, subject, agent, relations, summary, when)
        try:
            with file_lock(self._lock_path(), timeout=_COMMIT_LOCK_TIMEOUT):
                return self._commit(message, paths, when, stage=stage)
        except FileLockTimeoutError:
            logger.debug(f"history lock busy; leaving {event} for a later commit")
            return None
        except OSError as exc:  # pragma: no cover - defensive
            logger.warning(f"workspace history write failed: {exc}")
            return None

    def sweep(self, summary: str = "sync workspace") -> str | None:
        """Commit everything currently uncommitted under one generic fact."""
        return self.record(
            "WorkspaceSynced",
            subject=EntityRef(id=self.root.name, type="workspace"),
            summary=summary,
        )

    # ── reading ──────────────────────────────────────────────────────────

    def entries(
        self,
        *,
        entity_id: str | None = None,
        event: str | None = None,
        path: PathArg | None = None,
        limit: int | None = None,
    ) -> list[HistoryEntry]:
        """Facts newest-first, optionally narrowed by entity, event, or path."""
        if not self.enabled():
            return []
        args = ["log", "--format=%H%x1f%B%x1e"]
        if limit is not None:
            args.append(f"--max-count={limit * 4 if entity_id else limit}")
        if entity_id:
            args.append(f"--grep={entity_id}")
        if event:
            args.append(f"--grep=^{_TRAILER_EVENT}: {event}$")
            args.append("--all-match")
        if path is not None:
            args.extend(["--", str(path)])
        out = self._git(*args)
        if out is None:
            return []
        found: list[HistoryEntry] = []
        for chunk in out.split("\x1e"):
            record = chunk.strip("\n")
            if not record or "\x1f" not in record:
                continue
            sha, _, body = record.partition("\x1f")
            entry = _parse(sha.strip(), body)
            if entry is None:
                continue
            if entity_id and not entry.mentions(entity_id):
                continue
            found.append(entry)
            if limit is not None and len(found) >= limit:
                break
        return found

    def latest(self, *, entity_id: str, event: str) -> HistoryEntry | None:
        entries = self.entries(entity_id=entity_id, event=event, limit=1)
        return entries[0] if entries else None

    def show(self, commit: str, rel_path: PathArg) -> str | None:
        """Return a file's bytes as of *commit* (git is the content store)."""
        return self._git("show", f"{commit}:{rel_path}")

    # ── internals ────────────────────────────────────────────────────────

    def _lock_path(self) -> Path:
        lock_dir = self.root / MOLAB_DIR / "locks"
        lock_dir.mkdir(parents=True, exist_ok=True)
        return lock_dir / "history.lock"

    def _message(
        self,
        event: str,
        subject: EntityRef,
        agent: AgentRef,
        relations: tuple[Relation, ...],
        summary: str,
        when: datetime,
    ) -> str:
        headline = summary or f"{subject.type} {subject.id}"
        lines = [
            f"{event}: {headline}",
            "",
            f"{_TRAILER_EVENT}: {event}",
            f"{_TRAILER_SUBJECT}: {subject.type} {subject.id}",
            f"{_TRAILER_AGENT}: {agent.type} {agent.id}" + (f" {agent.name}" if agent.name else ""),
            f"{_TRAILER_AT}: {when.astimezone(UTC).isoformat()}",
        ]
        lines.extend(
            f"{_TRAILER_REL}: {rel.predicate} {rel.object.type} {rel.object.id}"
            for rel in relations
        )
        return "\n".join(lines) + "\n"

    def _commit(
        self,
        message: str,
        paths: tuple[PathArg, ...],
        when: datetime,
        *,
        stage: bool = True,
    ) -> str | None:
        if stage:
            pathspec = [str(p) for p in paths] or ["."]
            if self._git("add", "-A", "--", *pathspec) is None:
                return None
            if not self._git("diff", "--cached", "--name-only"):
                return None
        stamp = when.astimezone(UTC).isoformat()
        env = {
            "GIT_AUTHOR_DATE": stamp,
            "GIT_COMMITTER_DATE": stamp,
        }
        args = ["commit", "-q", "--no-verify", "-m", message]
        if not stage:
            args.insert(1, "--allow-empty")
        if self._git(*args, env=env) is None:
            return None
        return self._git("rev-parse", "HEAD")

    def _git(
        self, *args: str, check: bool = False, env: dict[str, str] | None = None
    ) -> str | None:
        cmd = [
            "git",
            "-c",
            "user.name=molab",
            "-c",
            "user.email=molab@localhost",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "core.hooksPath=/dev/null",
            *args,
        ]
        merged = {**os.environ, **(env or {})}
        try:
            proc = subprocess.run(
                cmd,
                cwd=self.root,
                capture_output=True,
                text=True,
                check=False,
                env=merged,
            )
        except OSError as exc:
            if check:
                raise
            logger.debug(f"git {args[0]} failed: {exc}")
            return None
        if proc.returncode != 0:
            if check:
                raise RuntimeError(f"git {args[0]} failed: {proc.stderr.strip()}")
            logger.debug(f"git {args[0]} exited {proc.returncode}: {proc.stderr.strip()}")
            return None
        return proc.stdout.strip()


def _parse(sha: str, body: str) -> HistoryEntry | None:
    event = ""
    subject: EntityRef | None = None
    agent = SYSTEM_AGENT
    relations: list[Relation] = []
    when = datetime.now(UTC)
    summary = ""
    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            continue
        key, sep, value = line.partition(": ")
        if not sep:
            continue
        if key == _TRAILER_EVENT:
            event = value
        elif key == _TRAILER_SUBJECT:
            kind, _, ident = value.partition(" ")
            subject = EntityRef(id=ident, type=kind)
        elif key == _TRAILER_AGENT:
            kind, _, rest = value.partition(" ")
            ident, _, display = rest.partition(" ")
            if kind in {"person", "software", "workflow", "executor", "system"}:
                agent = AgentRef(id=ident, type=kind, name=display or None)
        elif key == _TRAILER_REL:
            predicate, _, rest = value.partition(" ")
            kind, _, ident = rest.partition(" ")
            relations.append(Relation(predicate=predicate, object=EntityRef(id=ident, type=kind)))
        elif key == _TRAILER_AT:
            with contextlib.suppress(ValueError):
                when = datetime.fromisoformat(value)
    if not event or subject is None:
        return None
    first = body.strip().splitlines()[0] if body.strip() else ""
    if ": " in first:
        summary = first.split(": ", 1)[1]
    return HistoryEntry(
        commit=sha,
        event=event,
        subject=subject,
        agent=agent,
        relations=tuple(relations),
        occurred_at=when,
        summary=summary,
    )


__all__ = [
    "MOLAB_DIR",
    "SYSTEM_AGENT",
    "AgentRef",
    "EntityRef",
    "GitHistory",
    "HistoryEntry",
    "Relation",
    "default_gitignore",
    "push_workspace",
]


def push_workspace(workspace: str, remote: str) -> dict[str, str | None]:
    """Commit anything outstanding, then push the history — the backup verb."""
    history = GitHistory(workspace)
    commit = history.sweep()
    proc = subprocess.run(
        ["git", "push", remote, "HEAD"],
        cwd=history.root,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git push failed: {proc.stderr.strip()}")
    return {"commit": commit, "remote": remote}
