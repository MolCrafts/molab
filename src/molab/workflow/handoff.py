"""Continue a later workflow from an earlier run.

:func:`handoff_seeds` copies completed task outputs whose names exist on the
next workflow. :func:`handoff_cache` reads the earlier run's node cache and
writes this run's own. The runtime applies both when ``resume_from`` is set.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .protocols import TaskOutput

if TYPE_CHECKING:
    from molab.workspace.run import Run

    from .cache import Caching
    from .compiled import CompiledWorkflow
    from .protocols import RunContextLike

_NODE_CACHE_DIRNAME = "cache"


def handoff_seeds(previous: Run, compiled: CompiledWorkflow) -> dict[str, TaskOutput]:
    """Completed outputs of *previous* that this workflow still has.

    The latest attempt that recorded any completed output wins. Names the
    next workflow does not register are dropped.

    Args:
        previous: A workspace run whose attempts have a node journal.
        compiled: The workflow about to run.

    Returns:
        ``{task_name: output}`` safe to pass as ``seed_outputs``.
    """
    from ._engine.persistence import read_outputs

    names = set(compiled.registration_by_name)
    for record in reversed(list(previous.executions)):
        outputs = read_outputs(previous, record.id)
        shared = {name: outputs[name] for name in outputs if name in names}
        if shared:
            return shared
    return {}


def handoff_cache(previous: object, run_context: RunContextLike | None) -> Caching | None:
    """A cache that reads *previous* and writes the current run.

    Returns ``None`` when either run has no machine-state cache directory
    to point at. The caller then keeps the ordinary per-run cache.
    """
    from .cache import Caching
    from .cache_store import FileCacheStore, ReadThroughCacheStore

    previous_dir = _cache_dir(previous)
    if previous_dir is None:
        return None
    current = _cache_dir(getattr(run_context, "run", None) if run_context is not None else None)
    if current is None:
        return None
    return Caching(
        store=ReadThroughCacheStore(FileCacheStore(current), FileCacheStore(previous_dir))
    )


def _cache_dir(run: object | None) -> Path | None:
    machine_dir = getattr(run, "machine_dir", None)
    if not callable(machine_dir):
        return None
    try:
        return Path(machine_dir()) / _NODE_CACHE_DIRNAME
    except (TypeError, OSError):
        return None


__all__ = ["handoff_cache", "handoff_seeds"]
