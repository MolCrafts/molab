"""Public-API goldens for arch-own-02c-dispatch.

``molab run`` records every attempt it dispatches as an ``Execution`` created
before the workflow starts, and a local ``--rerun --fresh`` opens a new
attempt instead of a run-level ``fresh.json`` marker:

1. A healing script ``s.py`` (``stage_b`` fails until ``FLAG`` exists) is run
   with ``molab run s.py --local -ws <tmp>``: exit 1, and the run holds one
   INITIAL ``e01`` that failed, did not bypass the cache, and captured
   ``s.py`` as its source entrypoint.
2. ``FLAG`` is written and ``molab run s.py --local --rerun --fresh`` exits 0
   with a RERUN ``e02`` based on ``e01`` that succeeded and bypassed the
   cache.
3. The script is recorded on the attempt (``e02.environment["script"]``),
   not in ``run.json``, and no ``fresh.json`` exists anywhere under the run.

Expected stdout (exactly these lines, exit code 0):

    e01 initial failed False s.py
    e02 rerun succeeded True e01
    env.script=s.py run.json.script=None fresh.json=0

Provenance: goldens hard-coded from molab's own behaviour (no third-party
oracle), recorded 2026-09-26 on branch feat/knowledge-crossref. The workspace
is an in-process temporary directory driven through typer's ``CliRunner`` —
no subprocess, no network, no third-party runtime.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

from typer.testing import CliRunner

import molab.cli
from molab.workspace import Workspace

# The healing workflow as a ``molab run`` script: stage_b fails until FLAG
# exists, then writes stage_a * 100 to RESULT (seed 1 -> "200").
_SCRIPT = """\
from pathlib import Path

import molab as me
from molab.workflow import Workflow

FLAG = Path({flag!r})
RESULT = Path({result!r})

wf = Workflow(name="healing")


@wf.task
def stage_a(seed: int) -> int:
    return seed + 1


@wf.task(depends_on=["stage_a"])
def stage_b(stage_a: int) -> str:
    if not FLAG.exists():
        raise RuntimeError("FLAG missing")
    RESULT.write_text(str(stage_a * 100))
    return str(stage_a * 100)


ws = me.Workspace(name="lab")
ws.add_project("p").add_experiment("e").define(wf, params={{"seed": [1]}})
"""

_GOLDEN = (
    "e01 initial failed False s.py",
    "e02 rerun succeeded True e01",
    "env.script=s.py run.json.script=None fresh.json=0",
)


def _emit(lines: list[str], line: str) -> None:
    expected = _GOLDEN[len(lines)]
    assert line == expected, f"{line!r} != {expected!r}"
    lines.append(line)


def _molab(*args: str) -> int:
    result = CliRunner().invoke(molab.cli.app, list(args))
    print(f"$ molab {' '.join(args)} -> {result.exit_code}", file=sys.stderr)
    print(result.output, file=sys.stderr)
    return result.exit_code


def _check(root: Path) -> list[str]:
    lines: list[str] = []
    flag = root / "healed"
    script = root / "s.py"
    script.write_text(
        _SCRIPT.format(flag=str(flag), result=str(root / "result.txt")), encoding="utf-8"
    )

    code = _molab("run", str(script), "--local", "-ws", str(root))
    assert code == 1, code

    flag.write_text("ok", encoding="utf-8")
    code = _molab("run", str(script), "--local", "--rerun", "--fresh", "-ws", str(root))
    assert code == 0, code

    ws = Workspace.load(root)
    [project] = ws.list_projects()
    [experiment] = project.list_experiments()
    [run] = experiment.list_runs()
    first, second = run.executions

    entrypoint = first.source.entrypoint if first.source is not None else None
    _emit(
        lines,
        f"{first.id} {first.mode.value} {first.status.value} {first.bypass_cache} {entrypoint}",
    )
    _emit(
        lines,
        f"{second.id} {second.mode.value} {second.status.value} "
        f"{second.bypass_cache} {second.based_on_execution_id}",
    )

    run_dir = Path(run.run_dir)
    env_script = second.environment.get("script")
    env_name = Path(str(env_script)).name if env_script is not None else None
    run_json = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    fresh = len(list(run_dir.rglob("fresh.json")))
    _emit(
        lines,
        f"env.script={env_name} run.json.script={run_json.get('script')} fresh.json={fresh}",
    )

    assert len(lines) == len(_GOLDEN), lines
    return lines


def main() -> None:
    saved_main = sys.modules.get("__main__")
    saved_path = list(sys.path)
    saved_cwd = Path.cwd()
    try:
        with tempfile.TemporaryDirectory() as raw:
            os.environ["GIT_CEILING_DIRECTORIES"] = raw
            os.chdir(raw)
            try:
                lines = _check(Path(raw))
            finally:
                os.chdir(saved_cwd)
    finally:
        if saved_main is not None:
            sys.modules["__main__"] = saved_main
        sys.path[:] = saved_path
    for line in lines:
        print(line)


if __name__ == "__main__":
    main()
