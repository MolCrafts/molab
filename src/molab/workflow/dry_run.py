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

    Args:
        compiled: A compiled workflow.

    Returns:
        The waves and the declared branches.
    """
    regs = compiled.registration_by_name
    pending = set(regs)
    waves: list[DryRunWave] = []
    while pending:
        ready = tuple(
            sorted(
                name for name in pending if all(dep not in pending for dep in regs[name].depends_on)
            )
        )
        if not ready:
            waves.append(DryRunWave(tuple(sorted(pending))))
            break
        waves.append(DryRunWave(ready))
        pending.difference_update(ready)
    return DryRunReport(
        name=compiled.name,
        waves=tuple(waves),
        branches=tuple(compiled._branch_edges),
    )


__all__ = ["DryRunReport", "DryRunWave", "simulate"]
