"""Public-API goldens for arch-own-01-cleanup.

Pruning removes bulk only and keeps the record; the dead legacy surfaces are
gone:

1. e01 writes under ``ctx.task_workdir("md")`` then raises -> e01 ``failed``.
2. e02 (RERUN) ``ctx.files.put`` + ``ctx.emit_artifact`` -> e02 ``succeeded``.
3. ``plan_execution_prune(run, statuses=["failed"])`` entries are
   ``[("e01", ("out",))]``; ``apply_execution_prune`` returns ``1``.
4. e01 keeps ``execution.json`` and ``run.log``; ``out/`` is gone;
   ``pruned_dirs == ("out",)``.
5. A further RERUN is allocated ``"e03"`` (a pruned id is never reused).
6. A queued e04 (``ExecutionRepository.create``) makes
   ``plan_execution_prune(run)`` raise ``LivePruneRefusedError``.
7. ``{d.name for d in prunable_dirs()} == {"checkpoints", "jobs", "out", "work"}``.
8. ``ws.cache`` is gone; ``molab.workspace.runcontext``,
   ``molab.workflow.snapshot_ref`` and ``molab.workspace.cache`` do not
   resolve; ``molab.RunContext is ExecutionContext``.

Provenance: goldens hard-coded from molab's own behaviour (no third-party
oracle), recorded 2026-09-26 on branch feat/knowledge-crossref. The workspace
is an in-process temporary directory — no network, no subprocess.
"""

from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

import molab
from molab.workspace import AgentRef, Run, Workspace
from molab.workspace.domain import ExecutionMode
from molab.workspace.execution_context import ExecutionContext
from molab.workspace.execution_dirs import prunable_dirs
from molab.workspace.execution_repository import ExecutionRepository
from molab.workspace.prune import (
    LivePruneRefusedError,
    apply_execution_prune,
    plan_execution_prune,
)

_PRUNE_ENTRIES_GOLDEN = [("e01", ("out",))]
_PRUNE_REMOVED_GOLDEN = 1
_PRUNED_DIRS_GOLDEN = ("out",)
_NEXT_ID_GOLDEN = "e03"
_QUEUED_ID_GOLDEN = "e04"
_PRUNABLE_GOLDEN = {"checkpoints", "jobs", "out", "work"}
_GONE_MODULES = (
    "molab.workspace.runcontext",
    "molab.workflow.snapshot_ref",
    "molab.workspace.cache",
)


def _statuses(run: Run) -> dict[str, str]:
    return {e.id: e.status.value for e in run.executions}


def _check_prune(root: Path) -> None:
    ws = Workspace(root / "ws-prune", name="lab")
    project = ws.add_project("demo")
    run = project.add_experiment("prune").add_run(params={"x": 1})

    try:
        with run.start() as ctx:
            (ctx.task_workdir("md") / "traj.xyz").write_text("1\n\nH 0 0 0\n")
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    else:
        raise AssertionError("e01 body should raise")
    assert _statuses(run) == {"e01": "failed"}, _statuses(run)
    print(f"[1] e01: {_statuses(run)['e01']}")

    with run.start(mode=ExecutionMode.RERUN) as ctx:
        ctx.files.put("note.txt", "hello")
        ctx.emit_artifact({"a": 1}, name="m.json")
    assert _statuses(run) == {"e01": "failed", "e02": "succeeded"}, _statuses(run)
    print(f"[2] e02 (rerun): {_statuses(run)['e02']}")

    plan = plan_execution_prune(run, statuses=["failed"])
    entries = [(e.execution_id, e.dirs) for e in plan.entries]
    assert entries == _PRUNE_ENTRIES_GOLDEN, entries
    removed = apply_execution_prune(run, plan)
    assert removed == _PRUNE_REMOVED_GOLDEN, removed
    print(f"[3] prune plan entries: {entries}, removed: {removed}")

    e01_dir = Path(str(run.run_dir)) / "executions" / "e01"
    assert (e01_dir / "execution.json").is_file(), sorted(p.name for p in e01_dir.iterdir())
    assert (e01_dir / "run.log").is_file(), sorted(p.name for p in e01_dir.iterdir())
    assert not (e01_dir / "out").exists(), sorted(p.name for p in e01_dir.iterdir())
    e01 = next(e for e in run.executions if e.id == "e01")
    assert e01.pruned_dirs == _PRUNED_DIRS_GOLDEN, e01.pruned_dirs
    assert e01.pruned_at is not None
    print(f"[4] e01 kept execution.json + run.log, pruned_dirs: {e01.pruned_dirs}")

    with run.start(mode=ExecutionMode.RERUN) as ctx:
        next_id = ctx.id
    assert next_id == _NEXT_ID_GOLDEN, next_id
    print(f"[5] next rerun id: {next_id}")

    repo = ExecutionRepository(ws.root, run.run_dir, run_id=run.id, project_id=project.id, fs=ws.fs)
    queued = repo.create(
        mode=ExecutionMode.RERUN,
        created_by=AgentRef(id="test", type="person", name="test"),
    )
    assert (queued.id, queued.status.value) == (_QUEUED_ID_GOLDEN, "queued"), queued
    try:
        plan_execution_prune(run)
    except LivePruneRefusedError as exc:
        print(f"[6] queued {queued.id} -> LivePruneRefusedError: {exc}")
    else:
        raise AssertionError("prune with a queued attempt must be refused")


def _check_surfaces(root: Path) -> None:
    names = {d.name for d in prunable_dirs()}
    assert names == _PRUNABLE_GOLDEN, names
    print(f"[7] prunable_dirs: {sorted(names)}")

    ws = Workspace(root / "ws-surface", name="lab")
    assert not hasattr(ws, "cache")
    for module in _GONE_MODULES:
        assert importlib.util.find_spec(module) is None, module
    assert molab.RunContext is ExecutionContext
    print(f"[8] ws.cache gone; unresolvable: {list(_GONE_MODULES)}; RunContext is ExecutionContext")


def main() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        _check_prune(root)
        _check_surfaces(root)
    print("arch-own-01-cleanup: ok")


if __name__ == "__main__":
    main()
