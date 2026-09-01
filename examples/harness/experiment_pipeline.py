"""NL experiment goal → task board → review gate → frozen plan → realization.

The flagship harness demo: one natural-language goal flows through the
two-phase ``PlanOrchestrator`` pipeline on one ``workspace.Run`` (the
earlier nine-step PlanMode/RunMode ledger is retired):

- **Phase 1 — interactive planning**: an agent loop places tasks with
  acceptance criteria on a task board; a form guard blocks a malformed
  board; the hard review gate freezes the approved plan and the
  ``plan_report_renderer`` agent emits the plan report. Offline, the loop
  is replaced by an in-file ``CannedBoardRunner`` (the ``PlanLoopRunner``
  seam) that writes the same board the production ``InteractiveLoop``
  would build.
- **Phase 2 — deterministic realization** (``RealizeBoard``): every board
  task gets its module generated (canned here) and its unit test REALLY
  run under pytest in an isolated tree, the greens are reduced into one
  ``workflow_source``, and the assembled workflow is compiled by the real
  ``molexp.workflow`` engine in an executor subprocess
  (``run_workflow.py --compile-only`` — no real science).

OFFLINE BY DEFAULT — zero network, zero API keys, deterministic: the
in-file :class:`CannedGateway` implements the public ``AgentGateway``
Protocol (the same seam the production ``RouterBackedAgentGateway`` plugs
into) and serves pre-authored responses for the plan agents. Only the LLM
is canned: the form guard, the review gate, per-task pytest, and the
compile subprocess all run for real — the canned experiment is a 1D random
walk whose diffusion coefficient follows Einstein's relation
D = MSD/(2·d·t) ≈ 0.5.

LIVE MODE — paste a DeepSeek key into ``API_KEY`` below (molexp reads LLM
keys from ``molexp.config``, registered in code, never from the
environment) and the same pipeline runs against the real model through
``RouterBackedAgentGateway`` with the production planning loop.

Run directly::

    python examples/harness/experiment_pipeline.py
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

import molexp
from molexp.harness import (
    AgentGateway,
    FileArtifactStore,
    LocalExecutor,
    PlanOrchestrator,
)
from molexp.harness.errors import AgentResponseNotRegisteredError
from molexp.harness.plan import (
    BoardTask,
    Difficulty,
    FeasibilityAnnotation,
    TaskBoard,
    board_path,
    read_board,
    write_board,
)
from molexp.harness.schemas import (
    AgentCallResult,
    AgentCallSpec,
    ExecutionResult,
    WorkflowSource,
)
from molexp.harness.stages import auto_grant_approver
from molexp.workspace import Workspace

MODEL = "deepseek:deepseek-v4-flash"
API_KEY = ""  # ← paste your DeepSeek key here for live mode (in-code key law)

GOAL = (
    "Estimate the diffusion coefficient of a 1D random walker from the "
    "mean squared displacement of an ensemble of seeded walks."
)

# ─────────────────────────────────────────────────────────────────────────────
# Phase 1, canned: the board the planning loop would build. Every task carries
# acceptance criteria (the form guard refuses a board without them).
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


class CannedBoardRunner:
    """In-file ``PlanLoopRunner`` — writes the canned board, no LLM.

    Production uses ``InteractiveLoopPlanRunner`` (the agent-layer
    ``InteractiveLoop`` driving the board tools); this stub exercises the
    same seam offline by writing the board the loop would have built.
    """

    def __init__(self, board: TaskBoard) -> None:
        self._board = board

    async def run_planning(
        self, *, ctx: Any, board: Any, tools: Any, hooks: Any, user_input: str
    ) -> None:
        del board, tools, hooks, user_input
        write_board(board_path(ctx.workspace_root), self._board)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2, canned codegen: REAL per-task modules + REAL pytest files. The
# realizer renames each module's top-level function to the task slug, runs its
# test under pytest in an isolated tree, then compiles the assembly for real.
# ─────────────────────────────────────────────────────────────────────────────

_TASK_MODULES = {
    "generate_walks": '''\
"""Seeded ±1-step random-walk ensemble (generated for the harness demo)."""

import random

SEED = 20260610
N_WALKERS = 200
N_STEPS = 400


async def generate_walks(ctx=None) -> dict:
    rng = random.Random(SEED)
    finals = []
    for _ in range(N_WALKERS):
        x = 0
        for _ in range(N_STEPS):
            x += 1 if rng.random() < 0.5 else -1
        finals.append(x)
    return {"displacements": finals, "n_steps": N_STEPS}
''',
    "compute_msd": '''\
"""Ensemble mean squared displacement (generated for the harness demo)."""


async def compute_msd(displacements, n_steps) -> dict:
    msd = sum(d * d for d in displacements) / len(displacements)
    return {"msd": msd, "n_steps": n_steps}
''',
    "estimate_d": '''\
"""Einstein relation D = MSD/(2 d t) in one dimension (generated)."""


async def estimate_d(msd, n_steps) -> dict:
    return {"diffusion_coefficient": msd / (2 * 1 * n_steps), "msd": msd}
''',
}

_TASK_TESTS = {
    "generate_walks": """\
import asyncio

from workflow.generate_walks import N_WALKERS, generate_walks


def test_same_seed_reproduces_the_same_displacements():
    a = asyncio.run(generate_walks())
    b = asyncio.run(generate_walks())
    assert a["displacements"] == b["displacements"]


def test_ensemble_has_200_walkers():
    out = asyncio.run(generate_walks())
    assert len(out["displacements"]) == N_WALKERS == 200
""",
    "compute_msd": """\
import asyncio

from workflow.compute_msd import compute_msd


def test_msd_is_positive_and_matches_hand_computation():
    out = asyncio.run(compute_msd([2, -2, 4], 400))
    assert out["msd"] == (4 + 4 + 16) / 3
    assert out["msd"] > 0
""",
    "estimate_d": """\
import asyncio

from workflow.estimate_d import estimate_d


def test_unit_time_walk_gives_d_half():
    out = asyncio.run(estimate_d(400.0, 400))
    assert abs(out["diffusion_coefficient"] - 0.5) < 1e-12
""",
}


def _slug_from_prompt(prompt_text: str) -> str:
    """The task slug the codegen prompt names (``slug: <identifier>``)."""
    match = re.search(r"^\s*slug:\s*([A-Za-z_][A-Za-z0-9_]*)\s*$", prompt_text, re.MULTILINE)
    if match is None:
        raise AgentResponseNotRegisteredError("codegen prompt carries no task slug")
    return match.group(1)


class CannedGateway:
    """In-file ``AgentGateway`` — the Protocol seam, with canned responses.

    Anyone can stand a backend behind ``molexp.harness.AgentGateway``: the
    only contract is ``async call(spec) -> AgentCallResult`` plus the
    persistence law the shipped gateways follow — persist the RAW response
    first (kind ``log``), then the PARSED output (the per-agent kind), both
    ``created_by="agent:<name>"`` with ``parent_ids`` mirroring the call's
    ``input_artifact_ids``, so lineage stays intact offline.
    """

    def __init__(self, store: FileArtifactStore) -> None:
        self._store = store
        self.calls: list[tuple[AgentCallSpec, AgentCallResult]] = []

    def _payload(self, spec: AgentCallSpec) -> tuple[str, dict]:
        """(output_kind, payload) for one agent call — the 'LLM output'."""
        if spec.agent_name == "plan_report_renderer":
            return (
                "plan_report",
                {
                    "title": "Random-walk diffusion — plan report",
                    "summary_md": (
                        "# Plan\n\nGenerate seeded walks, compute the ensemble MSD, "
                        "estimate D via Einstein's relation D = MSD/(2 d t)."
                    ),
                },
            )
        prompt = self._store.get(spec.input_artifact_ids[0]).decode("utf-8")
        slug = _slug_from_prompt(prompt)
        if spec.agent_name == "workflow_source_file_writer":
            return (
                "workflow_source_file",
                {
                    "source": _TASK_MODULES[slug],
                    "module_name": slug,
                    "bound_workflow_id": "bw-random-walk",
                    "symbols": [slug],
                },
            )
        if spec.agent_name == "test_code_file_writer":
            return (
                "test_source_file",
                {
                    "source": _TASK_TESTS[slug],
                    "module_name": f"test_{slug}",
                    "test_spec_id": f"ts-{slug}",
                    "bound_workflow_id": "bw-random-walk",
                    "symbols": [slug],
                },
            )
        raise AgentResponseNotRegisteredError(
            f"no canned response registered for agent {spec.agent_name!r}"
        )

    async def call(self, spec: AgentCallSpec) -> AgentCallResult:
        kind, payload = self._payload(spec)
        created_by = f"agent:{spec.agent_name}"
        raw_ref = self._store.put_text(
            kind="log",
            text=json.dumps(payload, sort_keys=True),
            created_by=created_by,
            parent_ids=list(spec.input_artifact_ids),
        )
        out_ref = self._store.put_json(
            kind=kind,
            obj=payload,
            created_by=created_by,
            parent_ids=list(spec.input_artifact_ids),
        )
        result = AgentCallResult(
            output_artifact=out_ref,
            raw_response_artifact=raw_ref,
            model="canned",
            usage={},
        )
        self.calls.append((spec, result))
        return result


def _live_gateway(store: FileArtifactStore) -> AgentGateway:
    """The same pipeline against a real LLM (paste API_KEY above)."""
    from molexp.agent import PydanticAIRouter  # public lazy re-export, never _pydanticai
    from molexp.agent.router import ModelTier
    from molexp.harness import RouterBackedAgentGateway
    from molexp.harness.gateways import (
        plan_agent_responses,
        plan_output_kinds,
        plan_system_prompts,
    )

    molexp.config["deepseek_api_key"] = API_KEY
    return RouterBackedAgentGateway(
        router=PydanticAIRouter(models=dict.fromkeys(ModelTier, MODEL)),
        artifact_store=store,
        agent_responses=plan_agent_responses(),
        output_kind_by_agent=plan_output_kinds(),
        system_prompt_by_agent=plan_system_prompts(),
        model=MODEL,
    )


def _assert_gateway_contract(gateway: CannedGateway) -> None:
    """Self-check: the in-file gateway really honors the persistence law."""
    assert isinstance(gateway, AgentGateway), "CannedGateway must satisfy the Protocol"
    spec, result = gateway.calls[0]
    assert result.raw_response_artifact is not None
    assert result.raw_response_artifact.kind == "log"
    assert result.output_artifact.parent_ids == list(spec.input_artifact_ids)
    assert result.raw_response_artifact.parent_ids == list(spec.input_artifact_ids)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        ws = Workspace(Path(tmp) / "lab", name="experiment-pipeline")
        ws.materialize()
        run = ws.add_project("demo").add_experiment("random-walk").add_run(params={})
        store = FileArtifactStore(root=run.run_dir / "artifacts")

        offline = not API_KEY
        gateway: AgentGateway
        if offline:
            gateway = CannedGateway(store)
            # Phase 1's planning loop is the CannedBoardRunner seam offline;
            # live mode uses the default InteractiveLoopPlanRunner.
            orch = PlanOrchestrator(
                loop_runner=CannedBoardRunner(_canned_board()),
                approve=auto_grant_approver,  # unattended demo opts in EXPLICITLY
                realize=True,
                executor=LocalExecutor(),  # real per-task pytest + real compile
            )
        else:
            gateway = _live_gateway(store)
            orch = PlanOrchestrator(approve=auto_grant_approver, realize=True)

        print(f"goal    : {GOAL}")
        print(
            f"mode    : {'offline (canned LLM, real gates + pytest + compile)' if offline else f'live ({MODEL})'}"
        )
        print(f"run     : {run.id}")

        result = asyncio.run(orch.run(run=run, user_input=GOAL, gateway=gateway))
        if isinstance(gateway, CannedGateway):
            _assert_gateway_contract(gateway)

        # Phase 1 left a reviewed, frozen plan + report on the store. (The
        # reachability probe grounds against molmcp; offline it annotates
        # every task unreachable — the review gate is what admits the plan.)
        board = read_board(board_path(run.run_dir))
        print("\ntask board (frozen after the review gate):")
        for task in board.tasks:
            probed = "annotated" if task.feasibility is not None else "unprobed"
            print(f"  {task.id:<16} feasibility={probed} acceptance={len(task.acceptance)}")
        for kind in ("frozen_experiment_plan", "plan_report"):
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
        execution = ExecutionResult.model_validate_json(store.get(exec_ref.id))
        assert execution.status == "succeeded"
        assert result.final_artifact is not None
        print(f"\ncompile : status={execution.status} mode={execution.metadata.get('mode')}")
        print(f"final   : {result.final_artifact.kind} ({result.final_artifact.id})")
        print(f"\nartifacts : {run.run_dir / 'artifacts'}")
        print(f"audit db  : {run.run_dir / 'events.jsonl'}  (events + artifact lineage)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
