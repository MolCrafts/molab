"""Public-API goldens for the lifecycle the docs describe (arch-own-09-docs).

No third-party runtime. Prints ``arch-own-09-docs: ok``.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import molab
from molab.knowledge import Finding
from molab.knowledge.knowledge_item import SourceRef
from molab.knowledge.write import write_knowledge
from molab.workflow import RunFailedError, Workflow, read_journal
from molab.workspace.prune import apply_execution_prune, plan_execution_prune
from molab.workspace.refs import parse_ref, qualify_run_id, ref_of

CALLS: list[str] = []
FLAG = Path()

wf = Workflow(name="cooling")


@wf.task
def a(x: int) -> int:
    CALLS.append("a")
    return x + 1


@wf.task(depends_on=["a"])
def b(a: int) -> int:
    if not FLAG.is_file():
        raise RuntimeError("flag missing")
    return a


def _die(message: str) -> None:
    raise SystemExit(message)


def main() -> None:
    global FLAG
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        FLAG = root / "flag"
        ws = molab.Workspace(root=root, name="lab")
        experiment = ws.add_project("p").add_experiment("e")
        experiment.define(wf, params={"x": [1]})
        if experiment.workflow_kind != "code":
            _die(f"workflow_kind {experiment.workflow_kind}")
        ir_path = Path(experiment.experiment_dir) / "workflow.ir.json"
        if not ir_path.is_file():
            _die("workflow.ir.json missing")
        ir = json.loads(ir_path.read_text(encoding="utf-8"))
        if "workflow_digest" in ir or "workflow_id" in ir:
            _die("document carries an identity")
        runs = list(experiment.list_runs())
        if len(runs) != 1:
            _die(f"expected one run, got {len(runs)}")
        run = runs[0]
        if run.path.name != "x=1":
            _die(f"run dir {run.path.name}")

        try:
            run.execute(wf)
        except RunFailedError:
            pass
        else:
            _die("e01 should fail")
        FLAG.write_text("ok", encoding="utf-8")
        run.execute(wf, resume=True)
        if CALLS.count("a") != 1:
            _die(f"stage a ran {CALLS.count('a')} times")
        e02 = run.execution("e02")
        if e02.mode.value != "resume" or e02.based_on_execution_id != "e01":
            _die("e02 is not a resume of e01")
        journal = read_journal(run, "e02")
        if journal is None:
            _die("missing journal")
        if journal.get("based_on_execution_id") != "e01":
            _die("journal predecessor")
        digest = journal.get("workflow_digest")
        if digest != run.execution("e02").workflow_digest or not str(digest).startswith("sha256:"):
            _die(f"digest {digest}")
        if "workflow_id" in journal:
            _die("journal workflow_id")

        run.execute(wf, rerun=True)
        plan = plan_execution_prune(run, execution_ids=["e01"])
        apply_execution_prune(run, plan)
        e01_dir = Path(run.execution_dir("e01"))
        if not (e01_dir / "execution.json").is_file() or not (e01_dir / "workflow.json").is_file():
            _die("prune removed the record")
        if run.execution("e01").pruned_at is None:
            _die("pruned_at unset")

        run.execute(wf, rerun=True)
        ids = [item.id for item in run.executions]
        modes = [item.mode.value for item in run.executions]
        statuses = [item.status.value for item in run.executions]
        if ids != ["e01", "e02", "e03", "e04"]:
            _die(f"ids {ids}")
        if modes != ["initial", "resume", "rerun", "rerun"]:
            _die(f"modes {modes}")
        if statuses != ["failed", "succeeded", "succeeded", "succeeded"]:
            _die(f"statuses {statuses}")
        if run.status_label != "succeeded" or run.has_failures is not True:
            _die("status projection")

        if run.machine_dir() != Path(ws.root) / ".molab" / "runs" / run.id:
            _die("machine_dir")
        if not (run.machine_dir() / "cache").is_dir():
            _die("cache missing")
        if (Path(ws.root) / ".molab" / "cache").exists():
            _die("path-keyed cache")

        for path in Path(ws.root).rglob("*"):
            if path.name in {"assets.json", "fresh.json", "job.json", "error.txt"}:
                _die(f"retired file {path}")
            if path.parent.name.startswith("e0") and path.name == "results.json":
                _die(f"attempt-root results {path}")
        for run_dir in (Path(ws.root)).rglob("*"):
            if (
                run_dir.is_dir()
                and run_dir.parent.name == "runs"
                and run_dir.name.startswith("run-")
            ):
                _die(f"legacy run dir {run_dir.name}")

        ref = str(ref_of(run))
        write_knowledge(
            experiment,
            name="TG result",
            of=Finding,
            sources=[SourceRef.of(run)],
            created_by="docs",
            text=f"# TG result\n\n{ref}\n",
        )
        doc = Path(experiment.experiment_dir) / "knowledges" / "tg-result.md"
        if not doc.is_file():
            _die(f"finding missing at {doc}")
        body = doc.read_text(encoding="utf-8")
        if ref not in body:
            _die("finding lacks the run ref")
        found = ws.find(parse_ref(ref))
        if found.id != run.id:
            _die("find")
        if str(qualify_run_id(ws, run.id)) != ref:
            _die("qualify_run_id")

    print("arch-own-09-docs: ok")


if __name__ == "__main__":
    main()
