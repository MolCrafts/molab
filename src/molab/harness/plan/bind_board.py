"""Deterministic ``TaskBoard`` → ``BoundWorkflow`` + ``experiment_spec`` materialization.

Phase-2 realization expects a ``bound_workflow`` and ``experiment_spec``
artifact. The planning loop produces an :class:`ExperimentPlan` (opaque
spec + board); this module is the single conversion seam so realization
never re-implements board→bound mapping.
"""

from __future__ import annotations

from itertools import pairwise
from typing import TYPE_CHECKING

from molab.harness.plan.experiment_plan import ExperimentPlan
from molab.harness.schemas.bound_workflow import (
    BoundTask,
    BoundWorkflow,
    ExecutionEnvironment,
    ResourcePolicy,
)
from molab.harness.schemas.workflow_ir import DependencyEdge, PlanTaskIR, PlanWorkflowIR
from molab.workspace.utils import generate_id

if TYPE_CHECKING:
    from molab.harness.schemas import PlanArtifactRef
    from molab.harness.store.artifact_store import ArtifactStore

__all__ = [
    "board_plan_to_bound_workflow",
    "board_plan_to_workflow_ir",
    "materialize_plan_for_realization",
]


def board_plan_to_workflow_ir(plan: ExperimentPlan, *, ir_id: str | None = None) -> PlanWorkflowIR:
    """Project a frozen experiment plan into a minimal :class:`PlanWorkflowIR`.

    The board realization path needs a ``workflow_ir`` artifact —
    :class:`~molab.harness.stages.materialize_execution.MaterializeExecution`
    reads its ``inputs`` for the driver params — but the emergent planning
    loop produces only spec + board. This deterministic projection mirrors
    :func:`board_plan_to_bound_workflow` (same task ids, same sequential
    edges) with empty inputs: the board carries no sweep axes yet, and the
    projection invents no science.
    """
    tasks = [
        PlanTaskIR(
            id=task.id,
            name=task.name,
            purpose=task.name,
            task_type="capability",
            inputs={},
            outputs={"result": f"{task.id}.result"},
            acceptance_criteria=list(task.acceptance),
        )
        for task in plan.board.tasks
    ]
    edges = [
        DependencyEdge(source_task_id=left.id, target_task_id=right.id)
        for left, right in pairwise(tasks)
    ]
    spec = dict(plan.spec)
    return PlanWorkflowIR(
        id=ir_id or f"wir-{generate_id()}",
        name=str(spec.get("title") or spec.get("id") or "experiment"),
        objective=str(spec.get("objective") or spec.get("title") or ""),
        inputs={},
        tasks=tasks,
        edges=edges,
        expected_outputs=[],
    )


def board_plan_to_bound_workflow(
    plan: ExperimentPlan,
    *,
    workflow_ir_id: str | None = None,
    bound_id: str | None = None,
) -> BoundWorkflow:
    """Project a frozen experiment plan into a minimal :class:`BoundWorkflow`.

    Each board task becomes a :class:`BoundTask`. Capability identity prefers
    the first feasibility ``probed_refs`` entry when present; otherwise a
    stable placeholder ``board.<task_id>`` is used so realization can still
    attempt codegen (and block with an intervention if it cannot green).

    Edges are sequential in board order (t0 → t1 → …) when there are 2+
    tasks — a conservative default until the planner records explicit deps.
    """
    tasks: list[BoundTask] = []
    for task in plan.board.tasks:
        refs = ()
        if task.feasibility is not None:
            refs = task.feasibility.probed_refs
        cap = refs[0] if refs else f"board.{task.id}"
        package, _, callable_name = cap.partition(":")
        if not callable_name:
            package, callable_name = "molab", cap.replace(".", "_")
        tasks.append(
            BoundTask(
                id=task.id,
                ir_task_id=task.id,
                capability_id=cap,
                package=package or "molab",
                callable=callable_name or task.id,
                parameters={},
                inputs={},
                outputs={"result": f"{task.id}.result"},
                side_effects=[],
                tests=list(task.acceptance),
                provenance={
                    "source": "plan_board",
                    "task_name": task.name,
                },
            )
        )

    edges: list[DependencyEdge] = [
        DependencyEdge(source_task_id=left.id, target_task_id=right.id)
        for left, right in pairwise(tasks)
    ]

    return BoundWorkflow(
        id=bound_id or f"bw-{generate_id()}",
        workflow_ir_id=workflow_ir_id or f"wir-{generate_id()}",
        tasks=tasks,
        edges=edges,
        execution_backend="local",
        environment=ExecutionEnvironment(),
        resource_policy=ResourcePolicy(
            backend="local",
            max_runtime_s=3600,
            denied_paths=["/", "~/.ssh"],
        ),
        review_flags=[],
    )


def materialize_plan_for_realization(
    plan: ExperimentPlan,
    store: ArtifactStore,
    *,
    created_by: str,
    parent_ids: tuple[str, ...] = (),
) -> tuple[PlanArtifactRef, PlanArtifactRef, PlanArtifactRef]:
    """Persist ``experiment_spec`` + ``workflow_ir`` + ``bound_workflow``.

    Everything :class:`RealizeBoard` and its compile tail
    (``MaterializeExecution`` requires an upstream ``workflow_ir``) need,
    from the one conversion seam.

    Returns:
        ``(experiment_spec_ref, workflow_ir_ref, bound_workflow_ref)``.
    """
    parents = list(parent_ids)
    spec_obj = dict(plan.spec)
    if "id" not in spec_obj:
        spec_obj["id"] = str(spec_obj.get("title") or "experiment")
    spec_ref = store.put_json(
        kind="experiment_spec",
        obj=spec_obj,
        created_by=created_by,
        parent_ids=parents,
    )
    ir = board_plan_to_workflow_ir(plan)
    ir_ref = store.put_json(
        kind="workflow_ir",
        obj=ir.model_dump(mode="json"),
        created_by=created_by,
        parent_ids=[spec_ref.id, *parents],
    )
    bound = board_plan_to_bound_workflow(plan, workflow_ir_id=ir.id)
    bound_ref = store.put_json(
        kind="bound_workflow",
        obj=bound.model_dump(mode="json"),
        created_by=created_by,
        parent_ids=[spec_ref.id, ir_ref.id, *parents],
    )
    return spec_ref, ir_ref, bound_ref
