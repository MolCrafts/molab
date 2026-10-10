"""Public-API goldens for arch-own-03c-cache.

The workflow node cache is located by run identity and keyed by every input,
including the task's effective config:

1. With no ``cache=``, a workspace run's node cache lives in
   ``run.machine_dir() / "cache"`` (``<ws>/.molab/runs/<run-id>/cache``), and
   neither the old ``<ws>/.molab/cache`` nor ``<run_dir>/.cache`` appears.
2. Run A (``step(dt) -> dt * 10``) over five attempts: an equal profile hits,
   a different ``dt`` misses (the baseline served a stale ``10.0`` here), a
   profile that differs only by name hits, and the worker shape (config taken
   from the record, no ``run_dir`` injected) hits too.
3. Run B (``src -> {"Tg": 2.0}``, ``mech(T)`` with a ``dependent_params``
   overlay ``T = factor * Tg``): changing ``factor`` misses ``mech`` (the
   baseline served a stale ``1.0``) while ``src`` still hits.

Expected stdout (exactly these lines, exit code 0):

    cache_dir_is_machine_dir: True
    e01 dt=1.0 out=10.0 calls=1
    e02 dt=1.0 out=10.0 calls=1
    e03 dt=2.0 out=20.0 calls=2
    e04 dt=1.0 profile=b out=10.0 calls=2
    e05 record-config dt=1.0 out=10.0 calls=2 run_dir_in_config=False
    dep e01 factor=0.5 out=1.0 mech_calls=1 src_calls=1
    dep e02 factor=2.0 out=4.0 mech_calls=2 src_calls=1
    legacy_paths_absent: True
    arch-own-03c-cache: ok

Provenance: goldens hard-coded from the acceptance file
``.claude/specs/arch-own-03c-cache.acceptance.md`` (ac-010) and molab's own
behaviour (no third-party oracle), recorded 2026-09-29 on branch
feat/knowledge-crossref. The workspace is an in-process temporary directory —
no subprocess, no network, no third-party runtime.
"""

from __future__ import annotations

import asyncio
import tempfile
from collections.abc import Callable
from pathlib import Path

from molab.profile import ProfileConfig
from molab.workflow import CompiledWorkflow, Workflow, WorkflowCompiler, WorkflowRuntime
from molab.workspace import Workspace
from molab.workspace.domain import ExecutionMode

CALLS: dict[str, int] = {"step": 0, "src": 0, "mech": 0}


def step(dt: float) -> float:
    CALLS["step"] += 1
    return dt * 10


def src() -> dict:
    CALLS["src"] += 1
    return {"Tg": 2.0}


def mech(T: float) -> float:
    CALLS["mech"] += 1
    return T


def build(factor: float) -> CompiledWorkflow:
    def overlay(prev: dict) -> dict:
        return {"T": factor * prev["src"].output["Tg"]}

    wf = Workflow(name="dependent")
    wf.add(src, name="src")
    wf.add(mech, name="mech", depends_on=["src"], dependent_params=overlay)
    return WorkflowCompiler().compile(wf)


def _execute(compiled: CompiledWorkflow, ctx: object) -> dict:
    result = asyncio.run(WorkflowRuntime().execute(compiled, run_context=ctx))
    assert result.status == "succeeded", result
    return result.outputs


def _check(root: Path) -> None:
    ws = Workspace(root=root, name="Lab")
    experiment = ws.add_project("p").add_experiment("e")

    wf = Workflow(name="single")
    wf.add(step, name="step")
    single = WorkflowCompiler().compile(wf)

    run = experiment.add_run(params={"seed": 1})
    attempts: list[tuple[str, ProfileConfig, ExecutionMode, str]] = [
        ("e01", ProfileConfig({"dt": 1.0}, name="a"), ExecutionMode.INITIAL, ""),
        ("e02", ProfileConfig({"dt": 1.0}, name="a"), ExecutionMode.RERUN, ""),
        ("e03", ProfileConfig({"dt": 2.0}, name="a"), ExecutionMode.RERUN, ""),
        ("e04", ProfileConfig({"dt": 1.0}, name="b"), ExecutionMode.RERUN, " profile=b"),
    ]
    lines: list[str] = []
    for label, cfg, mode, extra in attempts:
        with run.start(cfg, mode=mode) as ctx:
            assert ctx.id == label, ctx.id
            out = _execute(single, ctx)["step"]
        lines.append(f"{label} dt={cfg['dt']}{extra} out={out} calls={CALLS['step']}")

    run.create_execution(
        mode=ExecutionMode.RERUN, profile_config=ProfileConfig({"dt": 1.0}, name="a")
    )
    with run.start(execution_id="e05") as ctx:
        run_dir_in_config = "run_dir" in ctx.config
        out = _execute(single, ctx)["step"]
    lines.append(
        f"e05 record-config dt=1.0 out={out} calls={CALLS['step']} "
        f"run_dir_in_config={run_dir_in_config}"
    )

    machine_dir = run.machine_dir()
    cache_dir = machine_dir / "cache"
    print(
        "cache_dir_is_machine_dir: "
        f"{machine_dir == root / '.molab' / 'runs' / run.id and any(cache_dir.glob('*.json'))}"
    )
    for line in lines:
        print(line)

    dep_run = experiment.add_run(params={"seed": 2})
    dep_attempts: list[tuple[str, float, ExecutionMode]] = [
        ("e01", 0.5, ExecutionMode.INITIAL),
        ("e02", 2.0, ExecutionMode.RERUN),
    ]
    for label, factor, mode in dep_attempts:
        with dep_run.start(mode=mode) as ctx:
            assert ctx.id == label, ctx.id
            out = _execute(build(factor), ctx)["mech"]
        print(
            f"dep {label} factor={factor} out={out} "
            f"mech_calls={CALLS['mech']} src_calls={CALLS['src']}"
        )

    legacy: list[Callable[[], bool]] = [
        lambda: (root / ".molab" / "cache").exists(),
        lambda: (Path(run.run_dir) / ".cache").exists(),
        lambda: (Path(dep_run.run_dir) / ".cache").exists(),
    ]
    print(f"legacy_paths_absent: {not any(probe() for probe in legacy)}")


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _check(Path(tmp) / "lab")
    print("arch-own-03c-cache: ok")


if __name__ == "__main__":
    main()
