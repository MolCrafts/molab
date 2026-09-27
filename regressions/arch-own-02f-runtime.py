"""Public-API goldens for arch-own-02f-runtime.

The runtime no longer mints execution ids or reads a ``fresh.json`` sidecar:

1. run1 (p1/e1) executes normally and warms a shared ``Caching`` store — the
   task body runs once (counter 1).
2. run2 (p2/e2) pre-allocates its attempt with
   ``run2.create_execution(bypass_cache=True)`` and executes under
   ``run2.start(execution_id=e.id)`` with **no** ``bypass_cache`` kwarg. The
   request recorded on the Execution is honoured: the body runs again despite
   the warm cache (counter 2), and the record still says ``bypass_cache=True``.
3. A bare ``execute(c)`` has no Execution, so ``result.execution_id`` is
   ``None``; ``execute(c, run_dir=...)`` without a run context is refused with
   ``ValueError`` (the runtime does not invent an attempt id for a directory).
4. No ``fresh.json`` is written anywhere, and ``WorkflowRuntime`` has no
   ``make_execution_id`` attribute.

Expected stdout (exactly these lines, exit code 0):

    e01 True 2
    None ValueError
    arch-own-02f-runtime: ok

Provenance: goldens hard-coded from molab's own behaviour (no third-party
oracle), recorded 2026-09-27 on branch feat/knowledge-crossref. The workspace
is an in-process temporary directory — no subprocess, no network, no
third-party runtime.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

from molab.workflow import (
    Caching,
    CompiledWorkflow,
    TaskContext,
    Workflow,
    WorkflowCompiler,
    WorkflowRuntime,
)
from molab.workspace import Workspace

_GOLDEN_BYPASS = "e01 True 2"
_GOLDEN_BARE = "None ValueError"
_GOLDEN_OK = "arch-own-02f-runtime: ok"

_COUNTER: dict[str, int] = {"step": 0}


def _compiled() -> CompiledWorkflow:
    wf = Workflow(name="arch-own-02f-counted")

    @wf.task
    async def step(ctx: TaskContext) -> int:
        del ctx  # the body only counts its own invocations
        _COUNTER["step"] += 1
        return 42

    return WorkflowCompiler().compile(wf)


async def _check(tmp: Path) -> list[str]:
    ws = Workspace(tmp / "lab", name="Lab")
    ws.materialize()
    compiled = _compiled()
    cache = Caching(store_dir=tmp / "cache")

    run1 = ws.add_project("p1").add_experiment("e1").add_run(params={})
    with run1.start() as ctx1:
        await WorkflowRuntime().execute(compiled, run_context=ctx1, cache=cache)
    print(f"warm counter={_COUNTER['step']}", file=sys.stderr)
    assert _COUNTER["step"] == 1, _COUNTER["step"]

    run2 = ws.add_project("p2").add_experiment("e2").add_run(params={})
    e = run2.create_execution(bypass_cache=True)
    with run2.start(execution_id=e.id) as ctx2:
        result2 = await WorkflowRuntime().execute(compiled, run_context=ctx2, cache=cache)
    print(f"run2 execution_id={result2.execution_id}", file=sys.stderr)
    bypass_line = f"{e.id} {run2.executions[-1].bypass_cache} {_COUNTER['step']}"
    assert bypass_line == _GOLDEN_BYPASS, f"{bypass_line!r} != {_GOLDEN_BYPASS!r}"

    bare = await WorkflowRuntime().execute(compiled)
    try:
        await WorkflowRuntime().execute(compiled, run_dir=tmp / "bare")
    except Exception as exc:  # the type name is the golden
        print(f"run_dir-only execute raised: {exc!r}", file=sys.stderr)
        raised = type(exc).__name__
    else:
        raised = "<no exception>"
    bare_line = f"{bare.execution_id} {raised}"
    assert bare_line == _GOLDEN_BARE, f"{bare_line!r} != {_GOLDEN_BARE!r}"

    fresh = sorted(str(p) for p in tmp.rglob("fresh.json"))
    assert not fresh, fresh
    assert not hasattr(WorkflowRuntime, "make_execution_id")

    return [bypass_line, bare_line, _GOLDEN_OK]


def main() -> None:
    saved_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as raw:
        os.environ["GIT_CEILING_DIRECTORIES"] = raw
        os.chdir(raw)
        try:
            lines = asyncio.run(_check(Path(raw)))
        finally:
            os.chdir(saved_cwd)
    for line in lines:
        print(line)


if __name__ == "__main__":
    main()
