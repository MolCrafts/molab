"""Public-API golden for ``molab run`` resume and rerun.

Hard-coded golden from ``.claude/specs/arch-own-03h-cli.md`` (testing strategy,
2026-10-01). No third-party oracle. The healing script's ``stage_a`` appends
one line to ``stage_a.count`` per body call. After a failed first attempt the
workspace ``.molab`` directory is deleted, so a resume that leaves the count
unchanged seeded ``stage_a`` instead of recomputing it (a cache hit is
impossible). ``--rerun --fresh`` runs the body again.

Expected stdout (exactly these lines):

    exit codes: [1, 0, 0]
    modes: ['initial', 'resume', 'rerun']
    based_on: [None, 'e01', 'e02']
    statuses: ['failed', 'succeeded', 'succeeded']
    bypass_cache: [False, False, True]
    stage_a bodies: [1, 1, 2]
    result: 200

In-process temporary directory, ``typer.testing.CliRunner``, no subprocess,
no network. ``sys.modules["__main__"]`` is restored at the end.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

from typer.testing import CliRunner

import molab.cli
from molab.workspace import Workspace

# Provenance: goldens hard-coded from .claude/specs/arch-own-03h-cli.md
# (Testing strategy), 2026-10-01, no third-party oracle.
_EXPECTED = """\
exit codes: [1, 0, 0]
modes: ['initial', 'resume', 'rerun']
based_on: [None, 'e01', 'e02']
statuses: ['failed', 'succeeded', 'succeeded']
bypass_cache: [False, False, True]
stage_a bodies: [1, 1, 2]
result: 200
"""

_SCRIPT = """\
from pathlib import Path

import molab as me
from molab.workflow import Workflow

FLAG = Path({flag!r})
RESULT = Path({result!r})
STAGE_A_COUNT = Path({count!r})

wf = Workflow(name="healing")


@wf.task
def stage_a(seed: int) -> int:
    with STAGE_A_COUNT.open("a", encoding="utf-8") as handle:
        handle.write("call\\n")
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


def _molab(*args: str) -> int:
    result = CliRunner().invoke(molab.cli.app, list(args))
    return result.exit_code


def _bodies(path: Path) -> int:
    if not path.is_file():
        return 0
    return len([line for line in path.read_text(encoding="utf-8").splitlines() if line])


def _check(root: Path) -> str:
    ws_root = root / "ws"
    flag = root / "FLAG"
    result = root / "result.txt"
    count = root / "stage_a.count"
    script = root / "s.py"
    script.write_text(
        _SCRIPT.format(flag=str(flag), result=str(result), count=str(count)),
        encoding="utf-8",
    )

    codes = [_molab("run", str(script), "--local", "-ws", str(ws_root))]
    bodies = [_bodies(count)]

    flag.write_text("ok", encoding="utf-8")
    molab_dir = ws_root / ".molab"
    if molab_dir.exists():
        shutil.rmtree(molab_dir)

    codes.append(_molab("run", str(script), "--resume", "--local", "-ws", str(ws_root)))
    bodies.append(_bodies(count))

    codes.append(_molab("run", str(script), "--rerun", "--fresh", "--local", "-ws", str(ws_root)))
    bodies.append(_bodies(count))

    ws = Workspace.load(ws_root)
    [project] = ws.list_projects()
    [experiment] = project.list_experiments()
    [run] = experiment.list_runs()
    executions = run.executions
    result_text = result.read_text(encoding="utf-8").strip() if result.is_file() else "<missing>"
    lines = [
        f"exit codes: {codes}",
        f"modes: {[item.mode.value for item in executions]}",
        f"based_on: {[item.based_on_execution_id for item in executions]}",
        f"statuses: {[item.status.value for item in executions]}",
        f"bypass_cache: {[item.bypass_cache for item in executions]}",
        f"stage_a bodies: {bodies}",
        f"result: {result_text}",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    saved_main = sys.modules.get("__main__")
    saved_path = list(sys.path)
    saved_cwd = Path.cwd()
    saved_ceiling = os.environ.get("GIT_CEILING_DIRECTORIES")
    try:
        with tempfile.TemporaryDirectory() as raw:
            os.environ["GIT_CEILING_DIRECTORIES"] = raw
            os.chdir(raw)
            try:
                actual = _check(Path(raw))
            finally:
                os.chdir(saved_cwd)
    finally:
        if saved_main is not None:
            sys.modules["__main__"] = saved_main
        else:
            sys.modules.pop("__main__", None)
        sys.path[:] = saved_path
        if saved_ceiling is None:
            os.environ.pop("GIT_CEILING_DIRECTORIES", None)
        else:
            os.environ["GIT_CEILING_DIRECTORIES"] = saved_ceiling
    if actual != _EXPECTED:
        sys.stderr.write(actual)
        return 1
    sys.stdout.write(actual)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
