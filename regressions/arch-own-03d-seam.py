"""Public-API goldens for arch-own-03d-seam.

Workspace no longer parses the workflow node journal: ``Run.get_result`` and
``RunSet.collect`` reach node outputs through the run-executor seam, which the
composition root ``molab/__init__`` wires lazily at ``import molab``.

1. Subprocess A builds workspace ``lab`` / project ``p`` / experiment ``e``:
   ``run1`` (``seed=1``) executes a one-task workflow (``train`` returns
   ``{"loss": 0.125}``); ``run2`` (``seed=2``) is a driver-side attempt that
   calls ``ctx.set_result("train", "driver")``.
2. Subprocess B only does ``import sys, molab``, loads the workspace and
   reads both runs. Driver results come back without loading
   ``molab.workflow``; the first node-output read loads it through the seam.
3. The parent checks that ``molab.workspace.execution_results`` is gone and
   that the seam Protocol and the workflow factory both carry
   ``read_outputs``.

Expected stdout of subprocess B (exactly these lines):

    before workflow_loaded=False
    run1 e01 results={}
    run2 e01 results={'train': 'driver'}
    run2 e01 get_result train='driver'
    still workflow_loaded=False
    run1 e01 get_result train={'loss': 0.125}
    run1 e01 get_result nope=None
    after workflow_loaded=True
    collect run1 seed=1 train={'loss': 0.125} status=succeeded error=None

The script prints ``arch-own-03d-seam: ok`` last and exits 0, or prints the
difference and exits 1.

Provenance: goldens hard-coded from the acceptance file
``.claude/specs/arch-own-03d-seam.acceptance.md`` (ac-012) and molab's own
behaviour (no third-party oracle), recorded 2026-09-29 on branch
feat/knowledge-crossref. Two ``sys.executable -c`` subprocesses in a temporary
directory — no network, no third-party runtime.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

from molab.workflow.execute import workspace_run_executor
from molab.workspace.run import RunWorkflowExecutor

EXPECTED = [
    "before workflow_loaded=False",
    "run1 e01 results={}",
    "run2 e01 results={'train': 'driver'}",
    "run2 e01 get_result train='driver'",
    "still workflow_loaded=False",
    "run1 e01 get_result train={'loss': 0.125}",
    "run1 e01 get_result nope=None",
    "after workflow_loaded=True",
    "collect run1 seed=1 train={'loss': 0.125} status=succeeded error=None",
]

WRITER = """
import molab
from molab.workflow import Workflow, WorkflowCompiler

wf = Workflow(name="single")


@wf.task
def train() -> dict:
    return {"loss": 0.125}


ws = molab.Workspace(ROOT, name="lab")
exp = ws.add_project("p").add_experiment("e")
run1 = exp.add_run(params={"seed": 1})
run1.execute(WorkflowCompiler().compile(wf))
run2 = exp.add_run(params={"seed": 2})
with run2.start() as ctx:
    ctx.set_result("train", "driver")
"""

READER = """
import sys, molab
from molab.workspace.runset import RunSet

ws = molab.Workspace.load(ROOT)
runs = {r.parameters["seed"]: r for r in ws.get_project("p").get_experiment("e").list_runs()}
run1, run2 = runs[1], runs[2]
print(f"before workflow_loaded={'molab.workflow' in sys.modules}")
print(f"run1 e01 results={run1.results('e01')!r}")
print(f"run2 e01 results={run2.results('e01')!r}")
print(f"run2 e01 get_result train={run2.get_result('train', execution_id='e01')!r}")
print(f"still workflow_loaded={'molab.workflow' in sys.modules}")
print(f"run1 e01 get_result train={run1.get_result('train', execution_id='e01')!r}")
print(f"run1 e01 get_result nope={run1.get_result('nope', execution_id='e01')!r}")
print(f"after workflow_loaded={'molab.workflow' in sys.modules}")
[rec] = RunSet([run1]).collect().to_records()
print(
    f"collect run1 seed={rec['seed']!r} train={rec['train']!r} "
    f"status={rec['status']} error={rec['error']!r}"
)
"""


def _child(code: str, root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", f"ROOT = {str(root)!r}\n{code}"],
        capture_output=True,
        text=True,
        check=False,
    )


def main() -> int:
    problems: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "lab"
        writer = _child(WRITER, root)
        if writer.returncode != 0:
            print(f"subprocess A failed:\n{writer.stderr}")
            return 1
        reader = _child(READER, root)
        if reader.returncode != 0:
            print(f"subprocess B failed:\n{reader.stderr}")
            return 1
        lines = reader.stdout.splitlines()
        for line in lines:
            print(line)
        if lines != EXPECTED:
            problems.append(f"subprocess B stdout:\n  got      {lines}\n  expected {EXPECTED}")

    if importlib.util.find_spec("molab.workspace.execution_results") is not None:
        problems.append("molab.workspace.execution_results still importable")
    if "read_outputs" not in dir(RunWorkflowExecutor):
        problems.append("RunWorkflowExecutor lacks read_outputs")
    if not callable(getattr(workspace_run_executor(), "read_outputs", None)):
        problems.append("workspace_run_executor().read_outputs is not callable")

    if problems:
        for problem in problems:
            print(f"MISMATCH: {problem}")
        return 1
    print("arch-own-03d-seam: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
