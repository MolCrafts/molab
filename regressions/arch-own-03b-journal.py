"""Public-API goldens for arch-own-03b-journal.

A compiled workflow's content digest, and the node journal the workflow layer
writes into the directory the workspace hands it:

1. ``compute_workflow_digest`` is ``sha256:<64 hex>``, independent of
   declaration order and workflow name, and changes with a task body.
2. A bare run is not an Execution: ``execution_id`` is ``None``.
3. e01 (``double`` → ``triple`` → ``summarize``, which fails while a flag is
   set) writes a schema-3 journal with the workflow digest and no top-level
   ``status`` / ``outputs`` / ``error``; its completed outputs are the resume
   seeds, and a workflow whose ``double`` body changed gets none (the gate is
   transitive: ``triple`` is dropped with its changed upstream).
4. e02, a RESUME based on e01 seeded from ``read_resume_seeds``, skips
   ``double`` and ``triple`` and runs only ``summarize``.

Expected stdout (exactly these lines, exit code 0):

    digest format ok: True
    digest order/name independent: True
    digest body sensitive: True
    bare run execution_id: None
    e01 journal: schema=3 id=e01 based_on=None digest_ok=True
    e01 no top-level status/outputs/error: True
    e01 outputs: {'double': 6, 'triple': 18}
    e01 resume seeds: {'double': 6, 'triple': 18}
    e01 seeds if double changed: {}
    e02 journal: schema=3 id=e02 based_on=e01 digest_ok=True
    e02 outputs: {'double': 6, 'summarize': 'got 18', 'triple': 18}
    body runs: double=1 triple=1 summarize=2
    arch-own-03b-journal: ok

Provenance: goldens hard-coded from the acceptance file
``.claude/specs/arch-own-03b-journal.acceptance.md`` (ac-021) and molab's own
behaviour (no third-party oracle), recorded 2026-09-29 on branch
feat/knowledge-crossref. The workspace is an in-process temporary directory —
no subprocess, no network, no third-party runtime.
"""

from __future__ import annotations

import asyncio
import re
import tempfile
from collections.abc import Callable
from pathlib import Path

from molab.workflow import (
    CompiledWorkflow,
    Workflow,
    WorkflowCompiler,
    WorkflowRuntime,
    compute_workflow_digest,
    read_journal,
    read_outputs,
    read_resume_seeds,
)
from molab.workspace import Workspace
from molab.workspace.domain import ExecutionMode

RUNS: dict[str, int] = {"double": 0, "triple": 0, "summarize": 0}
FAIL = {"summarize": True}


def double(x: int) -> int:
    RUNS["double"] += 1
    return x * 2


def double_v2(x: int) -> int:
    RUNS["double"] += 1
    return x + x + 0


def triple(double: int) -> int:
    RUNS["triple"] += 1
    return double * 3


def summarize(triple: int) -> str:
    RUNS["summarize"] += 1
    if FAIL["summarize"]:
        raise RuntimeError("summarize is not ready")
    return f"got {triple}"


def _compile(
    name: str, *, double_body: Callable[[int], int] = double, reverse: bool = False
) -> CompiledWorkflow:
    wf = Workflow(name=name)
    steps = [
        (double_body, "double", None),
        (triple, "triple", ["double"]),
        (summarize, "summarize", ["triple"]),
    ]
    for body, task, deps in reversed(steps) if reverse else steps:
        wf.add(body, name=task, depends_on=deps)
    return WorkflowCompiler().compile(wf)


def _sorted(mapping: dict) -> dict:
    return dict(sorted(mapping.items()))


def _header(doc: dict, digest: str) -> str:
    return (
        f"schema={doc['schema_version']} id={doc['execution_id']} "
        f"based_on={doc['based_on_execution_id']} "
        f"digest_ok={doc['workflow_digest'] == digest}"
    )


def _check(root: Path) -> None:
    v1 = _compile("pipeline")
    v2 = _compile("pipeline", double_body=double_v2)
    digest = compute_workflow_digest(v1)
    print(f"digest format ok: {re.fullmatch(r'sha256:[0-9a-f]{64}', digest) is not None}")
    same = compute_workflow_digest(_compile("renamed", reverse=True)) == digest
    print(f"digest order/name independent: {same}")
    print(f"digest body sensitive: {compute_workflow_digest(v2) != digest}")

    bare = asyncio.run(WorkflowRuntime().execute(v1, config={"x": 3}))
    print(f"bare run execution_id: {bare.execution_id}")
    for key in RUNS:
        RUNS[key] = 0

    ws = Workspace(root=root / "lab", name="Lab")
    run = ws.add_project("p").add_experiment("e").add_run(params={"x": 3})

    with run.start() as ctx:
        e01 = asyncio.run(WorkflowRuntime().execute(v1, run_context=ctx))
    assert e01.status == "failed"
    doc = read_journal(run, "e01")
    assert doc is not None
    print(f"e01 journal: {_header(doc, v1.workflow_digest)}")
    print(f"e01 no top-level status/outputs/error: {not {'status', 'outputs', 'error'} & set(doc)}")
    print(f"e01 outputs: {_sorted(read_outputs(run, 'e01'))}")
    seeds = read_resume_seeds(run, "e01", v1)
    print(f"e01 resume seeds: {_sorted(seeds)}")
    print(f"e01 seeds if double changed: {read_resume_seeds(run, 'e01', v2)}")

    FAIL["summarize"] = False
    with run.start(mode=ExecutionMode.RESUME, based_on_execution_id="e01") as ctx:
        e02 = asyncio.run(WorkflowRuntime().execute(v1, run_context=ctx, seed_outputs=seeds))
    assert e02.status == "succeeded"
    doc = read_journal(run, "e02")
    assert doc is not None
    print(f"e02 journal: {_header(doc, v1.workflow_digest)}")
    print(f"e02 outputs: {_sorted(read_outputs(run, 'e02'))}")
    print(
        f"body runs: double={RUNS['double']} triple={RUNS['triple']} summarize={RUNS['summarize']}"
    )


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _check(Path(tmp))
    print("arch-own-03b-journal: ok")


if __name__ == "__main__":
    main()
