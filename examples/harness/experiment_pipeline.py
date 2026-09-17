"""NL experiment goal → task board → review gate → frozen plan → realization.

The flagship harness demo: one natural-language goal flows through the
two-phase :class:`molab.harness.Plan` pipeline on one ``workspace.Run``:

- **Phase 1 — interactive planning**: a board draft places tasks with
  acceptance criteria on a task board; a form guard blocks a malformed
  board; the hard review gate freezes the approved plan and the
  ``plan_report_renderer`` agent emits the plan report. Offline, the draft
  is replaced by an in-file ``draft=`` callable that writes the same board
  the production agentic planner would build.
- **Phase 2 — deterministic realization** (``RealizeBoard``): every board
  task gets its module generated (canned here), its unit test is run
  through the injected executor (``DryRunExecutor`` offline — the real
  pytest/compile subprocesses are skipped), the greens are reduced into one
  ``workflow_source``, and the assembled workflow is compiled by the real
  ``molab.workflow`` engine (``run_workflow.py --compile-only`` — no real
  science) via ``CompileWorkflow``.

OFFLINE BY DEFAULT — zero network, zero API keys, deterministic: the
in-file :class:`StubAgentGateway` implements the public ``AgentGateway``
Protocol (the same seam the production ``RouterBackedAgentGateway`` plugs
into) and serves pre-authored responses for the plan agents. Only the LLM
is canned: the form guard, the review gate, and the plan workflow all run
for real — the canned experiment is a 1D random walk whose diffusion
coefficient follows Einstein's relation D = MSD/(2·d·t) ≈ 0.5.

LIVE MODE — paste a DeepSeek key into ``API_KEY`` below (molab reads LLM
keys from ``molab.config``, registered in code, never from the
environment) and the same pipeline runs against the real model through
``RouterBackedAgentGateway`` with the production planning loop.

Run directly::

    python examples/harness/experiment_pipeline.py
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path
from typing import Any

from molab.harness import DryRunExecutor, FileArtifactStore, ModeResult
from molab.harness.gateways.stub import StubAgentGateway
from molab.harness.modes.plan import Plan
from molab.harness.plan import (
    FROZEN_PLAN_KIND,
    BoardTask,
    Difficulty,
    FeasibilityAnnotation,
    TaskBoard,
    board_path,
    read_board,
    write_board,
)
from molab.harness.schemas import WorkflowSource
from molab.harness.stages import auto_grant_approver
from molab.harness.store.paths import harness_artifact_root
from molab.workspace import Workspace

MODEL = "deepseek:deepseek-v4-flash"
API_KEY = ""  # ← paste your DeepSeek key here for live mode (in-code key law)

GOAL = (
    "Estimate the diffusion coefficient of a 1D random walker from the "
    "mean squared displacement of an ensemble of seeded walks."
)

# ─────────────────────────────────────────────────────────────────────────────
# Phase 1, canned: the board the planning loop would build. Every task carries
# acceptance criteria (the form guard refuses a board without them) and a
# feasibility annotation (the review gate requires every task to be grounded).
# ─────────────────────────────────────────────────────────────────────────────


def _canned_board() -> TaskBoard:
    def _task(tid: str, name: str, acceptance: tuple[str, ...]) -> BoardTask:
        return BoardTask(
            id=tid,
            name=name,
            acceptance=acceptance,
            feasibility=FeasibilityAnnotation(
                reachable=True, difficulty=Difficulty.TRIVIAL, rationale="pure-python stdlib"
            ),
        )

    return TaskBoard(
        version=1,
        tasks=(
            _task(
                "generate_walks",
                "Generate seeded random walks",
                ("same seed reproduces the same displacements", "ensemble has 200 walkers"),
            ),
            _task(
                "compute_msd",
                "Compute the ensemble MSD",
                ("MSD is positive", "MSD matches the hand-computed mean of squares"),
            ),
            _task(
                "estimate_d",
                "Estimate D via Einstein's relation",
                ("D = MSD/(2 d t)", "unit-time ±1 walk gives D ≈ 0.5"),
            ),
        ),
    )


class CannedDraft:
    """In-file ``draft=`` seam — writes the canned board, no LLM.

    Production uses the agentic planner (``create_experiment_plan`` driving
    the board tools); this stub exercises the same seam offline by writing
    the board the planner would have built.
    """

    def __init__(self, board: TaskBoard) -> None:
        self._board = board

    async def __call__(self, *, ctx: Any, user_input: str) -> None:
        del user_input
        write_board(board_path(ctx.workspace_root), self._board)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2, canned codegen: generic per-task module + pytest snippets. The
# realizer renames each module's top-level function to the task slug and runs
# its test through the executor (dry-run offline); the greens are reduced into
# one ``workflow_source`` and the assembly is compiled by the real engine.
# ─────────────────────────────────────────────────────────────────────────────

_TASK_MODULE_SRC = "async def make_task(ctx) -> dict:\n    return {}\n"
_TASK_TEST_SRC = "def test_it():\n    assert True\n"


def _register_codegen(stub: StubAgentGateway) -> None:
    """Per-call responders returning generic (renamed-downstream) source."""

    def _wf(spec, store):
        return stub.make_response(
            {
                "source": _TASK_MODULE_SRC,
                "module_name": "m",
                "bound_workflow_id": "bw-random-walk",
                "symbols": [],
            },
            output_kind="workflow_source_file",
        )

    def _test(spec, store):
        return stub.make_response(
            {
                "source": _TASK_TEST_SRC,
                "module_name": "test_m",
                "test_spec_id": "ts-random-walk",
                "bound_workflow_id": "bw-random-walk",
                "symbols": [],
            },
            output_kind="test_source_file",
        )

    stub.register_responder("workflow_source_file_writer", _wf)
    stub.register_responder("test_code_file_writer", _test)


def _offline_gateway(run) -> StubAgentGateway:
    """A ``StubAgentGateway`` serving pre-authored plan-agent responses."""
    gw = StubAgentGateway(FileArtifactStore(root=harness_artifact_root(run.run_dir)))
    gw.register(
        "plan_report_renderer",
        output={
            "title": "Random-walk diffusion — plan report",
            "summary_md": (
                "# Plan\n\nGenerate seeded walks, compute the ensemble MSD, "
                "estimate D via Einstein's relation D = MSD/(2 d t)."
            ),
        },
        output_kind="plan_report",
        raw_text="rendered plan report",
    )
    _register_codegen(gw)
    return gw


def _live_gateway(run) -> object:
    """The same pipeline against a real LLM (paste API_KEY above)."""
    from molab.agent import PydanticAIRouter  # public lazy re-export, never _pydanticai
    from molab.agent.router import ModelTier

    import molab
    from molab.harness import RouterBackedAgentGateway
    from molab.harness.gateways import (
        plan_agent_responses,
        plan_output_kinds,
        plan_system_prompts,
    )

    molab.config["deepseek_api_key"] = API_KEY
    return RouterBackedAgentGateway(
        router=PydanticAIRouter(models=dict.fromkeys(ModelTier, MODEL)),
        artifact_store=FileArtifactStore(root=harness_artifact_root(run.run_dir)),
        agent_responses=plan_agent_responses(),
        output_kind_by_agent=plan_output_kinds(),
        system_prompt_by_agent=plan_system_prompts(),
        model=MODEL,
    )


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        ws = Workspace(Path(tmp) / "lab", name="experiment-pipeline")
        run = (
            ws.add_project("demo")
            .add_experiment("random-walk")
            .add_run(params={"mode": "plan"}, id="exp-pipeline")
        )

        offline = not API_KEY
        gateway = _offline_gateway(run) if offline else _live_gateway(run)
        plan = Plan(
            draft=CannedDraft(_canned_board()),
            approve=auto_grant_approver,  # unattended demo opts in EXPLICITLY
            realize=True,
            executor=DryRunExecutor(),  # offline: skip the real pytest + compile subprocess
        )

        print(f"goal    : {GOAL}")
        print(
            f"mode    : {'offline (canned LLM, real gates + plan workflow)' if offline else f'live ({MODEL})'}"
        )
        print(f"run     : {run.id}")

        result = asyncio.run(plan.run(run=run, user_input=GOAL, gateway=gateway))
        assert isinstance(result, ModeResult)
        store = FileArtifactStore.open_execution(run, result.execution_id)

        # Phase 1 left a reviewed, frozen plan + report on the store. (The
        # reachability probe grounds against molmcp; offline it annotates
        # every task unreachable — the review gate is what admits the plan.)
        board = read_board(
            board_path(Path(run.run_dir) / "executions" / result.execution_id / "work")
        )
        print("\ntask board (frozen after the review gate):")
        for task in board.tasks:
            probed = "annotated" if task.feasibility is not None else "unprobed"
            print(f"  {task.id:<16} feasibility={probed} acceptance={len(task.acceptance)}")
        for kind in (FROZEN_PLAN_KIND, "plan_report"):
            ref = store.latest_by_kind(kind)
            assert ref is not None, f"missing {kind} artifact"
            print(f"  {kind:<22} {ref.id}")

        # Phase 2 reduced the greens into one workflow_source (assembly +
        # one file per task) and compiled it for real (--compile-only).
        wf_ref = store.latest_by_kind("workflow_source")
        assert wf_ref is not None
        wf = WorkflowSource.model_validate_json(store.get(wf_ref.id))
        print("\nrealized workflow_source files:")
        for file in wf.files:
            print(f"  {file.path}")
        assert "def build_workflow" in wf.source

        exec_ref = store.latest_by_kind("execution_result")
        assert exec_ref is not None
        import json

        execution = json.loads(store.get(exec_ref.id).decode("utf-8"))
        assert execution["status"] == "succeeded"
        assert result.final_artifact is not None
        print(
            f"\ncompile : status={execution['status']} mode={execution.get('metadata', {}).get('mode')}"
        )
        print(f"final   : {result.final_artifact.kind} ({result.final_artifact.id})")
        print(f"\nartifacts : {run.run_dir}")
        print(f"events    : {run.run_dir / 'executions' / result.execution_id / 'events.jsonl'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
