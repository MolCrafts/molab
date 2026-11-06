"""A ``CommandTask`` child attaches to its parent's execution (D94).

The child is a real Python process: ``molab.track()`` returns an attached
tracker, its ``molab.print`` lines reach ``stdout.log`` once (through the
parent's capture), its scalars land in the WAL tagged with the task, and its
file is staged and then registered by the owner when it seals. The child
never writes ``execution.json``.
"""

from __future__ import annotations

import json
import os
import sys
import textwrap
from pathlib import Path

import molab
from molab.workflow import CommandTask, Workflow, WorkflowResult
from molab.workspace import tracking

_CHILD = textwrap.dedent(
    """
    import json, os, sys
    import molab
    from molab import print

    record = os.path.join(os.environ["MOLAB_EXECUTION_DIR"], "execution.json")
    before = os.stat(record)
    t = molab.track()
    print("child line", type(t).__name__)
    t.metrics.scalar("loss", 0.5, 1)
    t.metrics.scalar("loss", 0.25, 2)
    t.register(b"payload", title="child.bin", media_type="application/octet-stream", tags={"k": "v"})
    after = os.stat(record)
    sys.stderr.write(json.dumps({
        "env": {k: os.environ.get(k) for k in ("MOLAB_TASK", "MOLAB_STDIO_CAPTURED", "KEEP")},
        "record_untouched": (before.st_mtime_ns, before.st_ino) == (after.st_mtime_ns, after.st_ino),
    }) + "\\n")
    """
)


def _run(tmp_path: Path, env: dict[str, str] | None = None) -> molab.Run:
    ws = molab.Workspace(tmp_path / "ws", name="lab")
    run = ws.add_project("demo").add_experiment("child").add_run(params={"i": 0})
    wf = Workflow(name="child")
    wf.add(CommandTask([sys.executable, "-c", _CHILD], env=env), name="fit")
    result = run.execute(wf)
    assert isinstance(result, WorkflowResult)
    assert result.status == "succeeded", result
    return run


def _report(exec_dir: Path) -> dict:
    lines = (exec_dir / "stderr.log").read_text(encoding="utf-8").splitlines()
    return json.loads(next(line for line in lines if line.startswith("{")))


def test_child_metrics_print_and_asset_reach_the_sealed_parent(tmp_path: Path) -> None:
    from molab.workspace.asset_repository import assets_produced_by
    from molab.workspace.domain import ExecutionOrigin

    run = _run(tmp_path)
    exec_dir = run.execution_dir("e01")
    record = run.executions[-1]
    assert record.sealed

    stdout = (exec_dir / "stdout.log").read_text(encoding="utf-8")
    assert stdout.count("child line AttachedTracker") == 1

    wal = [json.loads(line) for line in (exec_dir / "metrics.mlp.jsonl").read_text().splitlines()]
    assert [(r["k"], r["s"], r["v"]) for r in wal] == [("loss", 1, 0.5), ("loss", 2, 0.25)]
    assert all(r["tags"]["task"] == "fit" for r in wal)

    (child,) = [
        asset
        for asset in assets_produced_by(run.experiment.project.workspace, "e01")
        if asset.title == "child.bin"
    ]
    assert child.tags["k"] == "v"
    assert child.tags["staged_by"] == "child"
    assert child.media_type == "application/octet-stream"
    assert isinstance(child.origin, ExecutionOrigin)
    assert child.origin.task == "fit"
    assert Path(run.asset_path(child.id)).read_bytes() == b"payload"

    report = _report(exec_dir)
    assert report["record_untouched"], "the child must not write execution.json"
    assert report["env"]["MOLAB_TASK"] == "fit"
    assert report["env"]["MOLAB_STDIO_CAPTURED"] == "1"
    on_disk = json.loads((exec_dir / "execution.json").read_text())
    assert "artifacts" not in on_disk


def test_a_user_env_wins_and_still_attaches(tmp_path: Path) -> None:
    env = {**os.environ, "KEEP": "yes", tracking.TASK_ENV: "mine"}
    run = _run(tmp_path, env=env)
    report = _report(run.execution_dir("e01"))
    assert report["env"]["KEEP"] == "yes"
    assert report["env"]["MOLAB_TASK"] == "mine"
    from molab.workspace.asset_repository import assets_produced_by
    from molab.workspace.domain import ExecutionOrigin

    (child,) = [
        asset
        for asset in assets_produced_by(run.experiment.project.workspace, "e01")
        if asset.title == "child.bin"
    ]
    assert isinstance(child.origin, ExecutionOrigin)
    assert child.origin.task == "mine"
