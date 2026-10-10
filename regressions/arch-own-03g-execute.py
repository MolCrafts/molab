"""Public-API golden for one-step execution history.

Hard-coded golden from ``.claude/specs/arch-own-03g-execute.acceptance.md``
ac-015, 2026-10-01, no third-party oracle. The healing workflow is the
shape in ``tests/test_workflow/test_execute_run.py`` (stage_a returns
``x + 1``; stage_b raises until FLAG exists, then returns ``stage_a * 100``).
In-process temporary directory; molab public API plus the stdlib only.
"""

from __future__ import annotations

import difflib
import sys
import tempfile
from pathlib import Path

from molab import Workflow, WorkflowCompiler, Workspace
from molab.workflow import RunFailedError, RunNotExecutableError
from molab.workflow.execute import execute_run
from molab.workflow.types import WorkflowResult
from molab.workspace.domain import Execution, ExecutionMode

# Provenance: goldens from .claude/specs/arch-own-03g-execute.acceptance.md
# ac-015, 2026-10-01, no third-party oracle.
_EXPECTED = [
    "e01 initial failed - False",
    "e02 resume succeeded e01 False",
    "e03 rerun succeeded e02 False",
    "e04 rerun succeeded e03 True",
    "e05 reproduce succeeded e04 True",
    "resume-after-success: RunNotExecutableError",
    "digest: 5/5 sha256",
    "arch-own-03g-execute: ok",
]


def _healing_wf(flag: Path) -> Workflow:
    wf = Workflow(name="healing")

    @wf.task
    def stage_a(x: int) -> int:
        return x + 1

    @wf.task(depends_on=["stage_a"])
    def stage_b(stage_a: int) -> int:
        if not Path(str(flag)).exists():
            raise RuntimeError("not healed yet")
        return stage_a * 100

    return wf


def _history(executions: list[Execution]) -> list[str]:
    return [
        f"{item.id} {item.mode.value} {item.status.value} "
        f"{item.based_on_execution_id or '-'} {item.bypass_cache}"
        for item in executions
    ]


def _assert_stage_b(result: WorkflowResult, attempt: str) -> None:
    got = result.outputs["stage_b"]
    if result.status != "succeeded" or got != 200:
        raise AssertionError(
            f"{attempt}: status={result.status!r} stage_b={got!r}, expected succeeded and 200"
        )


def _digest_line(executions: list[Execution], digest: str) -> str:
    ok = sum(
        1
        for item in executions
        if item.workflow_digest == digest
        and isinstance(item.workflow_digest, str)
        and item.workflow_digest.startswith("sha256:")
    )
    return f"digest: {ok}/{len(executions)} sha256"


def _fail(actual: list[str]) -> int:
    diff = "".join(
        difflib.unified_diff(
            [f"{line}\n" for line in _EXPECTED],
            [f"{line}\n" for line in actual],
            fromfile="expected",
            tofile="actual",
        )
    )
    sys.stderr.write(diff if diff.endswith("\n") or diff == "" else diff + "\n")
    return 1


def main() -> int:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        flag = root / "FLAG"
        wf = _healing_wf(flag)
        compiled = WorkflowCompiler().compile(wf)
        digest = compiled.workflow_digest
        assert isinstance(digest, str) and digest.startswith("sha256:")

        ws = Workspace(root / "ws", name="lab")
        run = ws.add_project("demo").add_experiment("pipeline").add_run(params={"x": 1})

        try:
            execute_run(compiled, run)
        except RunFailedError:
            pass
        else:
            raise AssertionError("e01: expected RunFailedError")

        flag.write_text("ok", encoding="utf-8")
        resumed = execute_run(compiled, run, resume=True)
        _assert_stage_b(resumed, "e02")

        rerun = execute_run(compiled, run, rerun=True)
        _assert_stage_b(rerun, "e03")

        fresh = execute_run(compiled, run, rerun=True, fresh=True)
        _assert_stage_b(fresh, "e04")

        record = run.create_execution(mode=ExecutionMode.REPRODUCE)
        reproduced = execute_run(compiled, run, execution_id=record.id)
        _assert_stage_b(reproduced, "e05")

        try:
            execute_run(compiled, run, resume=True)
        except RunNotExecutableError:
            resume_line = "resume-after-success: RunNotExecutableError"
        else:
            resume_line = "resume-after-success: <no error>"

        executions = run.executions
        body = [
            *_history(executions),
            resume_line,
            _digest_line(executions, digest),
        ]
        lines = [*body, "arch-own-03g-execute: ok"]
        if lines != _EXPECTED:
            return _fail(lines)
        assert lines == _EXPECTED
        print("\n".join(lines))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
