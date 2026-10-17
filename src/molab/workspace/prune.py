"""Two-phase execution pruning — plan which bulk to remove, then apply it.

This is the ONE prune core. Only the CLI (``molab runs prune``) calls it;
the server has no prune route. An *execution* is one attempt at a Run
(``executions/e01``).
Callers *select* attempts, by explicit ids or by status.
:func:`plan_execution_prune` turns the selection into a reviewable
:class:`ExecutionPrunePlan`, and :func:`apply_execution_prune` removes exactly
the directories the plan lists. Nothing is selected at apply time. Apply only
re-checks that each attempt is sealed.

Pruning removes **bulk only**, meaning reproducible bytes such as trajectories
and scratch, and it keeps every record: no ``execution.json`` and no
``executions/<id>/`` directory is ever deleted. The removable set comes from
data, not from matching names: it is the directories whose
``ExecutionDir.prunable`` is True
(:func:`~molab.workspace.execution_dirs.prunable_dirs`, which gives ``out/``,
``work/``, ``jobs/`` and ``checkpoints/``). Solver output under ``out/`` and
scheduler stdout/stderr under ``jobs/`` therefore go with the bulk. Other
entries survive, including ``execution.json``, the node journal
(``workflow.json``), the attempt's ``run.log`` and ``artifacts/``. So does the
run-level ``source/``, which lies outside every execution directory. Because
the record survives, the next attempt's id (``max(seq) + 1``) never reuses a
pruned one.

The two phases are the safety contract:

* **Plan is where refusal lives.** Selecting any attempt that is not *sealed*
  (finished and frozen by ``ExecutionRepository.seal``) raises
  ``LivePruneRefusedError``. That covers an attempt that is still active
  (queued, running or finalizing) and one that is terminal but was never
  sealed, so the caller never gets a plan it must second-guess. The caller
  must first reap a *zombie*, meaning an attempt still recorded as
  ``running`` after its owning process has died
  (``run_reaper.reap_zombie_run``). Prune never guesses that an attempt is a
  zombie.
* **Apply is mechanical.** Per entry, it re-checks the seal before touching
  bytes, removes each planned directory that still exists and stamps the
  sealed record (``pruned_at`` / ``pruned_dirs``) through
  ``ExecutionRepository.mark_pruned``. It returns how many directories it
  removed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from .domain import ACTIVE_EXECUTION_STATUSES
from .execution_dirs import prunable_dirs

if TYPE_CHECKING:
    from .run import Run

__all__ = [
    "ExecutionPruneEntry",
    "ExecutionPrunePlan",
    "LivePruneRefusedError",
    "apply_execution_prune",
    "plan_execution_prune",
]


class LivePruneRefusedError(RuntimeError):
    """A selected execution is not sealed.

    Either still active (queued, running or finalizing) — cancel the attempt
    first (``run.cancel()`` / ``molab runs cancel``) or wait for it to
    finish — or terminal but never sealed, which cannot carry the prune stamp.
    Raised at **plan** time.
    """


class ExecutionPruneEntry(BaseModel):
    """One execution attempt selected for pruning."""

    model_config = ConfigDict(frozen=True)

    execution_id: str
    status: str
    dirs: tuple[str, ...] = ()
    """Prunable directories of this attempt that existed at plan time, sorted.

    Exactly what :func:`apply_execution_prune` removes and stamps; empty when
    the attempt holds no bulk.
    """


class ExecutionPrunePlan(BaseModel):
    """The reviewable outcome of :func:`plan_execution_prune`.

    ``entries`` is exactly what :func:`apply_execution_prune` will remove —
    the plan is the contract, not a suggestion.
    """

    model_config = ConfigDict(frozen=True)

    run_id: str
    entries: tuple[ExecutionPruneEntry, ...] = ()


def plan_execution_prune(
    run: Run,
    *,
    execution_ids: list[str] | None = None,
    statuses: list[str] | None = None,
) -> ExecutionPrunePlan:
    """Select execution attempts of *run* and the bulk each would lose.

    Selection follows a fixed precedence. Explicit *execution_ids* win when
    given. Otherwise *statuses* filters the history (case-insensitive). With
    neither, **every** attempt is selected, which is the CLI's ``all``. Only
    sealed attempts may be selected, and every attempt's record is kept. The
    plan lists only the prunable directories that exist on disk right now.

    Args:
        run: The run whose execution history is being pruned.
        execution_ids: Explicit attempt ids to prune. Unknown ids raise
            ``KeyError`` — a plan must never silently narrow the request.
        statuses: Status names (``"failed"``, ``"cancelled"``, …) selecting
            attempts by their recorded status.

    Returns:
        The frozen plan, with one entry per selected attempt. An entry's
        ``dirs`` may be empty when the attempt holds no bulk, and the plan has
        no entries when nothing matched. Planning is read-only.

    Raises:
        KeyError: An explicit ``execution_id`` is not in the run's history.
        LivePruneRefusedError: A selected attempt is not sealed — queued,
            running or finalizing (pruning a live attempt's files out from
            under it is never allowed), or terminal but unsealed.
    """
    history = list(run.executions)
    by_id = {rec.id: rec for rec in history}

    if execution_ids is not None:
        unknown = [eid for eid in execution_ids if eid not in by_id]
        if unknown:
            raise KeyError(
                f"execution id(s) {unknown!r} not found under run {run.id!r}; "
                f"known: {sorted(by_id)}"
            )
        selected = [by_id[eid] for eid in execution_ids]
    elif statuses is not None:
        wanted = {s.lower() for s in statuses}
        selected = [rec for rec in history if rec.status.value.lower() in wanted]
    else:
        selected = history

    # Refusal lives at PLAN time: only a sealed attempt is prunable history,
    # because only a sealed record can carry the prune stamp. An active one is
    # live state (a stale ``running`` one is reaped by the caller first); a
    # terminal-but-unsealed one would lose its bytes and then fail to stamp.
    live = [rec for rec in selected if rec.status in ACTIVE_EXECUTION_STATUSES]
    unsealed = [
        rec for rec in selected if not rec.sealed and rec.status not in ACTIVE_EXECUTION_STATUSES
    ]
    if live or unsealed:
        reasons: list[str] = []
        if live:
            described = ", ".join(f"{rec.id}={rec.status.value}" for rec in live)
            reasons.append(
                f"{len(live)} selected execution(s) of run {run.id!r} are still active "
                f"({described}); cancel them first or wait for them to finish"
            )
        if unsealed:
            described = ", ".join(f"{rec.id}={rec.status.value}" for rec in unsealed)
            reasons.append(
                f"{len(unsealed)} selected execution(s) of run {run.id!r} are terminal but "
                f"not sealed ({described}); only a sealed attempt can be pruned"
            )
        raise LivePruneRefusedError("; ".join(reasons))

    repo = run._execution_repository()
    fs = repo.fs
    candidates = {d.name for d in prunable_dirs()}
    entries: list[ExecutionPruneEntry] = []
    for rec in selected:
        execution_dir = repo.execution_dir(rec.id)
        try:
            listing = fs.scandir(execution_dir, with_stat=False)
        except FileNotFoundError:
            listing = []
        present = tuple(
            sorted(entry.name for entry in listing if entry.is_dir and entry.name in candidates)
        )
        entries.append(
            ExecutionPruneEntry(execution_id=rec.id, status=rec.status.value, dirs=present)
        )
    return ExecutionPrunePlan(run_id=run.id, entries=tuple(entries))


def apply_execution_prune(run: Run, plan: ExecutionPrunePlan) -> int:
    """Remove exactly the directories *plan* lists; return the removed count.

    Entries are applied in order. An entry with no ``dirs`` is skipped. For
    every other entry, the attempt's seal is re-checked first. Then each
    directory in ``entry.dirs`` that still exists is removed, and the sealed
    record is stamped with ``entry.dirs`` through
    ``ExecutionRepository.mark_pruned``. The plan, not the disk, is the
    contract: a directory that vanished since planning is still recorded as
    pruned, but it is not counted. No record is deleted. ``execution.json`` is
    only updated with the stamp, and ``workflow.json``, ``run.log`` and
    ``artifacts/`` are left alone.

    Pass a plan from :func:`plan_execution_prune`. A hand-built entry is
    re-validated before removal: one that names a non-prunable directory
    raises ``ValueError`` and nothing of that entry is removed.

    Args:
        run: The run the plan was built for.
        plan: The :class:`ExecutionPrunePlan` to execute.

    Returns:
        How many directories were actually removed from disk.

    Raises:
        ValueError: *plan* was built for a different run (raised before
            anything is touched). Also raised when a planned attempt is not
            sealed, or when an entry names a directory that is not prunable;
            that entry's bytes are left untouched, but entries earlier in the
            plan have already been applied.
        KeyError: A planned attempt no longer exists under *run*.
    """
    if plan.run_id != run.id:
        raise ValueError(f"plan was built for run {plan.run_id!r}, not {run.id!r}")

    repo = run._execution_repository()
    fs = repo.fs
    allowed = {d.name for d in prunable_dirs()}
    removed_dirs = 0
    for entry in plan.entries:
        if not entry.dirs:
            continue
        # A hand-built entry may name a non-bulk directory; ``mark_pruned``
        # would reject it only after the bytes are gone, so refuse it here.
        refused = sorted(set(entry.dirs) - allowed)
        if refused:
            raise ValueError(
                f"Execution {entry.execution_id!r} of run {run.id!r}: not prunable "
                f"execution dir(s) {refused!r}; prunable: {sorted(allowed)}"
            )
        # Re-check the seal before any byte goes: ``mark_pruned`` refuses an
        # unsealed record, and bulk removed without its stamp is lost silently.
        if not repo.get(entry.execution_id).sealed:
            raise ValueError(
                f"Execution {entry.execution_id!r} of run {run.id!r} is not sealed; "
                "refusing to remove its bulk"
            )
        execution_dir = repo.execution_dir(entry.execution_id)
        for name in entry.dirs:
            path = fs.join(execution_dir, name)
            if fs.exists(path):
                fs.remove(path, recursive=True)
                removed_dirs += 1
        repo.mark_pruned(entry.execution_id, entry.dirs)
    return removed_dirs
