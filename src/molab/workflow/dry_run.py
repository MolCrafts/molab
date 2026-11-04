"""Walk a compiled workflow without calling task bodies.

A dry run reports the order the engine would consider and every declared
branch. It does not choose a branch, and it does not read or write a cache.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

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


__all__ = ["DryRunReport", "DryRunWave", "simulate"]
