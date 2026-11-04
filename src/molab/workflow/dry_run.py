"""Walk a compiled workflow without calling task bodies.

A dry run reports the order the engine would consider and every declared
branch. It does not choose a branch, and it does not read or write a cache.

:func:`report_from_compiled` is the document ``molab workflow dry-run`` prints
and ``GET …/workflow/dry-run`` returns. :func:`compiled_for_simulation` builds
the compiled workflow that document needs from a stored IR, so the server can
walk a code experiment's stored graph without importing its script: a graph
snapshot carries no task bodies, and each task gets a stub that raises if it
is ever invoked.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .._typing import JSONValue

if TYPE_CHECKING:
    from .compiled import CompiledWorkflow


@dataclass(frozen=True)
class DryRunWave:
    """Tasks that are ready in the same step, because their dependencies are done."""

    tasks: tuple[str, ...]


@dataclass(frozen=True)
class DryRunReport:
    """The simulated walk of one compiled workflow.

    Attributes:
        name: Workflow name.
        waves: Ready tasks, earliest wave first. Tasks inside a wave can run
            together. A cycle's remaining tasks are one final wave.
        branches: Declared ``(source, label, target)`` routes. None is taken.
    """

    name: str
    waves: tuple[DryRunWave, ...]
    branches: tuple[tuple[str, str, str], ...]


def simulate(compiled: CompiledWorkflow) -> DryRunReport:
    """Return the walk of *compiled* without executing a task.

    A task is ready when its data dependencies and its forward control
    sources are done. Back-edges (``wf.loop``) do not hold the first pass,
    and no branch is taken. The same :class:`ExecutionPlan` the engine runs.

    Args:
        compiled: A compiled workflow.

    Returns:
        The waves and the declared branches.
    """
    from ._engine.plan import START

    plan = compiled.graph
    regs = compiled.registration_by_name
    back_by_target: dict[str, set[str]] = {}
    for src, tgt in plan.back_edges:
        back_by_target.setdefault(tgt, set()).add(src)
    pending = set(regs)
    waves: list[DryRunWave] = []
    while pending:
        ready: list[str] = []
        for name in pending:
            sources = set(plan.in_sources.get(name, ())) - {START}
            sources |= set(regs[name].depends_on)
            sources -= back_by_target.get(name, set())
            parallel = plan.parallel_by_body.get(name)
            if parallel is not None:
                sources.add(parallel.map_over)
            if sources & pending:
                continue
            ready.append(name)
        if not ready:
            waves.append(DryRunWave(tuple(sorted(pending))))
            break
        waves.append(DryRunWave(tuple(sorted(ready))))
        pending.difference_update(ready)
    return DryRunReport(
        name=compiled.name,
        waves=tuple(waves),
        branches=tuple(compiled._branch_edges),
    )


def report_from_compiled(
    compiled: CompiledWorkflow,
    *,
    experiment: Mapping[str, JSONValue],
    runs: Sequence[Mapping[str, JSONValue]],
) -> dict[str, JSONValue]:
    """The dry-run document of *compiled* for one experiment.

    The workflow layer knows nothing of experiments or runs; the caller hands
    in what it knows (the experiment's identity, one parameter mapping per
    run it would dispatch) and gets the one document both the CLI and the
    HTTP route emit.

    Args:
        compiled: The workflow to walk.
        experiment: The experiment's facts (``id``, ``name``, ``path`` …),
            copied as given.
        runs: One parameter mapping per run, in dispatch order.

    Returns:
        ``{experiment, workflow: {name}, waves: [[task, …], …], branches:
        [{source, label, target}, …], runs: [{params: {…}}, …], tasks:
        [{name, depends_on: […]}, …]}``. Tasks are in registration order and
        a task's ``depends_on`` is what the compiler settled on (declared and
        inferred); a wave is sorted by name.
    """
    report = simulate(compiled)
    return {
        "experiment": dict(experiment),
        "workflow": {"name": report.name},
        "waves": [list(wave.tasks) for wave in report.waves],
        "branches": [
            {"source": source, "label": label, "target": target}
            for source, label, target in report.branches
        ],
        "runs": [{"params": dict(params)} for params in runs],
        "tasks": [
            {"name": name, "depends_on": list(registration.depends_on)}
            for name, registration in compiled.registration_by_name.items()
        ],
    }


def compiled_for_simulation(document: Mapping[str, JSONValue]) -> CompiledWorkflow:
    """Compile a stored workflow IR for :func:`simulate`, never for execution.

    A wire IR (``task_configs`` / ``links``, what a document experiment
    stores) compiles through the codec with its registered task types. A
    graph snapshot (``tasks`` / ``edges``, what a code experiment stores
    beside its script) carries no bodies: each task gets a stub that raises
    if invoked, so the result walks but must not run.

    Args:
        document: The experiment's ``workflow.ir.json`` object.

    Returns:
        A compiled workflow whose topology is the document's.

    Raises:
        ValueError: The document is neither IR shape, is malformed, or names
            an unregistered task type.
        WorkflowError: The topology does not compile.
    """
    if "task_configs" in document:
        from .codec import default_codec

        try:
            return default_codec.ir_to_spec(document)
        except KeyError as exc:
            detail = exc.args[0] if exc.args else "unregistered task_type"
            raise ValueError(detail) from exc
    if "tasks" not in document:
        raise ValueError(
            "not a workflow document: expected task_configs/links (wire IR) "
            "or tasks/edges (graph snapshot)"
        )

    from pydantic import ValidationError

    from ._graph_decl import LoopDecl, ParallelDecl, TaskRegistration, _BoundaryStubTask
    from .compiler import compile_registrations
    from .ir import WorkflowGraphIR

    try:
        graph = WorkflowGraphIR.model_validate(document)
    except ValidationError as exc:
        raise ValueError(f"malformed workflow graph snapshot: {exc}") from exc
    tasks = [
        TaskRegistration(
            name=task.name,
            fn_or_class=_BoundaryStubTask(task.name),
            depends_on=list(task.depends_on),
            is_actor=task.is_actor,
            task_type=task.task_type,
        )
        for task in graph.tasks
    ]
    return compile_registrations(
        name=graph.name,
        version_label=graph.version,
        tasks=tasks,
        mode=graph.mode,
        entries=graph.entries,
        control_edges=graph.control_edges,
        branch_edges=graph.branch_edges,
        loops=tuple(
            LoopDecl(loop.body, loop.until, loop.max_iters, loop.on_exit) for loop in graph.loops
        ),
        parallels=tuple(
            ParallelDecl(par.map_over, par.body, par.join, par.max_concurrency)
            for par in graph.parallels
        ),
    )


__all__ = [
    "DryRunReport",
    "DryRunWave",
    "compiled_for_simulation",
    "report_from_compiled",
    "simulate",
]
