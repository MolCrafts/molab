"""Public-API goldens for arch-own-03e-routes.

The server's run routes stop parsing files they do not own:
``GET …/executions/{id}/workflow`` returns the node journal through
``molab.workflow.read_journal`` and ``GET …/executions/{id}/outputs`` reads
driver results through ``Run.results``.

1. Workspace ``lab`` / project ``demo`` / experiment ``pipeline``; run
   ``x=3`` executes the two-task ``pipeline`` workflow
   (``double(x) = x * 2``, ``summarize(double) = f"got {double}"``).
2. ``GET …/executions/e01/workflow`` reports status ``succeeded`` and the
   journal: name ``pipeline``, execution ``e01``, no ``based_on``, the
   compiled workflow's digest, and per-task (status, outputs)
   ``{"double": ("completed", 6), "summarize": ("completed", "got 6")}``;
   the journal has no top-level ``status``.
3. Run ``x=1`` is a driver attempt calling ``ctx.set_result("energy", -1.5)``;
   ``GET …/executions/e01/outputs`` reports ``results == {"energy": -1.5}``.

The script prints ``arch-own-03e-routes: ok`` last and exits 0, or prints the
differences and exits 1.

Provenance: goldens hard-coded from the acceptance file
``.claude/specs/arch-own-03e-routes.acceptance.md`` (ac-007) and molab's own
behaviour (no third-party oracle), recorded 2026-09-29 on branch
feat/knowledge-crossref. In-process ``TestClient`` in a temporary directory —
no network, no third-party runtime.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from molab import Workspace
from molab.server.app import create_app
from molab.server.dependencies import set_workspace_path_override
from molab.workflow import Workflow, WorkflowCompiler

EXPECTED_TASKS = {"double": ("completed", 6), "summarize": ("completed", "got 6")}


def _pipeline() -> Workflow:
    wf = Workflow(name="pipeline")

    @wf.task
    def double(x: int) -> int:
        return x * 2

    @wf.task(depends_on=["double"])
    def summarize(double: int) -> str:
        return f"got {double}"

    return wf


def main() -> int:
    problems: list[str] = []

    def check(label: str, got: object, expected: object) -> None:
        if got != expected:
            problems.append(f"{label}: got {got!r}, expected {expected!r}")

    with tempfile.TemporaryDirectory() as tmp:
        ws = Workspace(Path(tmp) / "lab", name="lab")
        exp = ws.add_project("demo").add_experiment("pipeline")
        run = exp.add_run(params={"x": 3})
        compiled = WorkflowCompiler().compile(_pipeline())
        run.execute(compiled)
        driver = exp.add_run(params={"x": 1})
        with driver.start() as ctx:
            ctx.set_result("energy", -1.5)

        base = f"/api/projects/{exp.project.id}/experiments/{exp.id}/runs"
        set_workspace_path_override(Path(str(ws.root)))
        try:
            with TestClient(create_app(serve_static=False)) as client:
                wf_resp = client.get(f"{base}/{run.id}/executions/e01/workflow")
                out_resp = client.get(f"{base}/{driver.id}/executions/e01/outputs")
        finally:
            set_workspace_path_override(None)

        check("workflow HTTP status", wf_resp.status_code, 200)
        check("outputs HTTP status", out_resp.status_code, 200)
        if wf_resp.status_code == 200:
            body = wf_resp.json()
            check("status", body["status"], "succeeded")
            journal = body["workflow"]
            if not isinstance(journal, dict):
                problems.append(f"workflow: got {journal!r}, expected a journal dict")
            else:
                print(f"workflow_name={journal['workflow_name']!r}")
                check("workflow_name", journal["workflow_name"], "pipeline")
                check("execution_id", journal["execution_id"], "e01")
                check("based_on_execution_id", journal["based_on_execution_id"], None)
                tasks = {t["task_id"]: (t["status"], t["outputs"]) for t in journal["task_configs"]}
                print(f"tasks={tasks!r}")
                check("tasks", tasks, EXPECTED_TASKS)
                digest = journal["workflow_digest"]
                check("workflow_digest", digest, compiled.workflow_digest)
                check("digest prefix", digest[:7], "sha256:")
                check("digest length", len(digest), 71)
                check("top-level status in journal", "status" in journal, False)
        if out_resp.status_code == 200:
            results = out_resp.json()["results"]
            print(f"results={results!r}")
            check("results", results, {"energy": -1.5})

    if problems:
        for problem in problems:
            print(f"MISMATCH: {problem}")
        return 1
    print("arch-own-03e-routes: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
