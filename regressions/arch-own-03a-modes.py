"""Public-API goldens for arch-own-03a-modes.

One set of Execution creation rules, two public path accessors, and a
start-time workflow digest:

1. e01: a body raising ``RuntimeError`` seals the first attempt ``failed``.
2. e02: ``run.start(mode=RESUME)`` with no checkpoint and no based_on resumes
   the latest attempt (e01).
3. ``create_execution(mode=RESUME)`` after a succeeded e02 raises
   ``ValueError``.
4. e03: ``run.start(mode=RERUN)`` after a success is allowed.
5. e04: ``run.start(mode=RETRY)`` is stored as ``rerun``.
6. e05: ``create_execution(mode=REPRODUCE, bypass_cache=False)`` is QUEUED and
   records ``bypass_cache=True``.
7. ``create_execution(mode=RERUN)`` while e05 is queued raises ``ValueError``.
8. ``run.execution_dir("e05")`` is ``<run>/executions/e05``; starting e05 by id
   with ``workflow_digest=`` records the digest.
9. ``run.machine_dir()`` is ``<root>/.molab/runs/<run-id>`` and is not created.

Expected stdout (exactly these lines, exit code 0):

    resume after success: refused
    rerun while e05 queued: refused
    e01 initial failed None bypass_cache=False
    e02 resume succeeded e01 bypass_cache=False
    e03 rerun succeeded e02 bypass_cache=False
    e04 rerun succeeded e03 bypass_cache=False
    e05 reproduce succeeded e04 bypass_cache=True
    e05 workflow_digest=sha256:abababababababababababababababababababababababababababababababab
    machine_dir: .molab/runs/<run-id> (not created)
    arch-own-03a-modes: ok

Provenance: goldens hard-coded from the spec
``.claude/specs/arch-own-03a-modes.md`` (Testing strategy, "回归示例
``regressions/arch-own-03a-modes.py``") and molab's own behaviour (no
third-party oracle), recorded 2026-09-29 on branch feat/knowledge-crossref.
The workspace is an in-process temporary directory — no subprocess, no
network, no third-party runtime.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from molab.workspace import Workspace
from molab.workspace.domain import ExecutionMode

DIGEST = "sha256:" + "ab" * 32


def _refused(label: str, fn: object) -> None:
    try:
        fn()  # type: ignore[operator]
    except ValueError:
        print(f"{label}: refused")
        return
    raise AssertionError(f"{label}: expected ValueError")


def _check(root: Path) -> None:
    ws = Workspace(root=root / "lab", name="Lab")
    run = ws.add_project("p").add_experiment("e").add_run(params={"seed": 1})

    try:
        with run.start():
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    with run.start(mode=ExecutionMode.RESUME):
        pass
    _refused("resume after success", lambda: run.create_execution(mode=ExecutionMode.RESUME))
    with run.start(mode=ExecutionMode.RERUN):
        pass
    with run.start(mode=ExecutionMode.RETRY):
        pass
    e05 = run.create_execution(mode=ExecutionMode.REPRODUCE, bypass_cache=False)
    assert (e05.id, e05.status.value) == ("e05", "queued")
    _refused("rerun while e05 queued", lambda: run.create_execution(mode=ExecutionMode.RERUN))

    assert run.execution_dir("e05") == Path(run.run_dir) / "executions" / "e05"
    with run.start(execution_id="e05", workflow_digest=DIGEST):
        pass

    for item in run.executions:
        print(
            f"{item.id} {item.mode.value} {item.status.value} "
            f"{item.based_on_execution_id} bypass_cache={item.bypass_cache}"
        )
    print(f"e05 workflow_digest={run.execution('e05').workflow_digest}")

    machine = run.machine_dir()
    assert machine.relative_to(Path(str(ws.root))) == Path(".molab/runs") / run.id
    assert not machine.exists()
    print("machine_dir: .molab/runs/<run-id> (not created)")
    print("arch-own-03a-modes: ok")


def main() -> None:
    with tempfile.TemporaryDirectory() as raw:
        _check(Path(raw))


if __name__ == "__main__":
    main()
