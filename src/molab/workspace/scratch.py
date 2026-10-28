"""Experiment scratch (D90): the disposable tier, and its two-phase clean.

Every experiment may hold a ``scratch/`` directory beside ``runs/``
(:data:`~molab.workspace.naming.SCRATCH_CONTAINER`). It is where a quick test
goes: a smoke run of a script, a throwaway plot, a probe of an input file.
The contract is that nothing in it is cited. A long job, or anything a result
depends on, becomes a run — ``molab runs adopt`` records one that ran outside
molab. So scratch is gitignored, never listed as a child, and emptied by age.

The clean follows the prune core's shape (``prune.plan_execution_prune`` /
``apply_execution_prune``):

* :func:`plan_scratch_clean` selects the **top-level** entries of each
  experiment's scratch whose newest modification (the entry itself or
  anything under it) is older than a cutoff, and returns a reviewable
  :class:`ScratchCleanPlan`. Planning is read-only.
* :func:`apply_scratch_clean` removes exactly the planned entries. It selects
  nothing; it re-checks that each entry is still older than the cutoff, so an
  entry touched after planning is kept.

An entry's age is its newest mtime, not its own: a directory's mtime moves
only when its direct children change, so a long test writing deep inside it
would otherwise look abandoned.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from .naming import SCRATCH_CONTAINER

if TYPE_CHECKING:
    from .experiment import Experiment
    from .fs import FileSystem, PathArg
    from .workspace import Workspace

__all__ = [
    "ScratchCleanPlan",
    "ScratchEntry",
    "apply_scratch_clean",
    "newest_mtime",
    "plan_scratch_clean",
    "scratch_entries",
]


class ScratchEntry(BaseModel):
    """One top-level entry of an experiment's ``scratch/``."""

    model_config = ConfigDict(frozen=True)

    path: str
    """Workspace-relative POSIX path of the entry."""
    experiment: str
    """Workspace-relative POSIX path of the experiment that holds it."""
    modified_at: datetime
    """Newest modification time of the entry or anything under it (UTC)."""


class ScratchCleanPlan(BaseModel):
    """The reviewable outcome of :func:`plan_scratch_clean`.

    ``entries`` is exactly what :func:`apply_scratch_clean` removes.
    """

    model_config = ConfigDict(frozen=True)

    cutoff: datetime
    """Entries whose newest modification is before this are selected (UTC)."""
    entries: tuple[ScratchEntry, ...] = ()


def newest_mtime(fs: FileSystem, path: PathArg) -> float:
    """The newest mtime of *path* and, for a directory, everything under it.

    One ``scandir(with_stat=True)`` per directory. Symlinks are not followed
    into, so a link loop cannot hang the walk. A path that vanishes mid-walk
    contributes nothing.
    """
    try:
        newest = fs.stat(path).mtime
    except OSError:
        return 0.0
    pending = [str(path)] if fs.is_dir(path) else []
    while pending:
        current = pending.pop()
        try:
            entries = fs.scandir(current, with_stat=True)
        except OSError:
            continue
        for entry in entries:
            newest = max(newest, entry.mtime)
            if entry.is_dir and not entry.is_symlink:
                pending.append(fs.join(current, entry.name))
    return newest


def scratch_entries(fs: FileSystem, experiment_dir: PathArg) -> list[tuple[str, str, float]]:
    """``(name, path, newest mtime)`` of each top-level scratch entry, by name.

    An experiment with no ``scratch/`` has no entries.
    """
    scratch = fs.join(experiment_dir, SCRATCH_CONTAINER)
    try:
        entries = fs.scandir(scratch, with_stat=False)
    except OSError:
        return []
    found: list[tuple[str, str, float]] = []
    for entry in sorted(entries, key=lambda item: item.name):
        path = fs.join(scratch, entry.name)
        found.append((entry.name, path, newest_mtime(fs, path)))
    return found


def _relative(root: str, path: str) -> str:
    prefix = root.rstrip("/") + "/"
    return path[len(prefix) :] if path.startswith(prefix) else path


def plan_scratch_clean(
    workspace: Workspace,
    *,
    older_than: timedelta,
    experiments: Iterable[Experiment] | None = None,
    now: datetime | None = None,
) -> ScratchCleanPlan:
    """Select the scratch entries older than *older_than*. Writes nothing.

    Args:
        workspace: The workspace whose experiments are scanned.
        older_than: Age past which an entry is selected; ``timedelta(0)``
            selects everything older than *now*.
        experiments: Limit the scan to these experiments; every experiment
            of every project when omitted.
        now: The reference time; the current time when omitted.

    Returns:
        The frozen plan. It has no entries when nothing is old enough.
    """
    fs = workspace.fs
    root = str(workspace.resolve())
    cutoff = (now or datetime.now(UTC)) - older_than
    chosen = (
        list(experiments)
        if experiments is not None
        else [exp for project in workspace.list_projects() for exp in project.list_experiments()]
    )
    selected: list[ScratchEntry] = []
    for experiment in chosen:
        experiment_dir = str(experiment.resolve())
        for _name, path, mtime in scratch_entries(fs, experiment_dir):
            modified = datetime.fromtimestamp(mtime, UTC)
            if modified < cutoff:
                selected.append(
                    ScratchEntry(
                        path=_relative(root, path),
                        experiment=_relative(root, experiment_dir),
                        modified_at=modified,
                    )
                )
    return ScratchCleanPlan(cutoff=cutoff, entries=tuple(selected))


def apply_scratch_clean(workspace: Workspace, plan: ScratchCleanPlan) -> int:
    """Remove exactly the entries *plan* lists; return how many were removed.

    An entry that is gone already, or whose newest modification is now past
    the plan's cutoff (touched after planning), is skipped. Each experiment
    that lost an entry has its derived ``index:`` refreshed, so its
    ``scratch`` flag follows the tree.
    """
    from .index_projection import refresh_index_at

    fs = workspace.fs
    root = str(workspace.resolve())
    removed = 0
    touched: list[str] = []
    for entry in plan.entries:
        path = fs.join(root, entry.path)
        if not fs.exists(path):
            continue
        if datetime.fromtimestamp(newest_mtime(fs, path), UTC) >= plan.cutoff:
            continue
        fs.remove(path, recursive=fs.is_dir(path))
        removed += 1
        if entry.experiment not in touched:
            touched.append(entry.experiment)
    for experiment in touched:
        try:
            refresh_index_at(fs, fs.join(root, experiment), lock_root=root)
        except Exception:  # navigation sugar never fails the clean
            continue
    return removed
