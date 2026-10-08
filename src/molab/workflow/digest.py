"""Content-addressed identity of a compiled workflow.

:func:`compute_workflow_digest` hashes what a workflow *does*, not what it
is called. The digest is ``"sha256:" + 64 hex`` over one canonical JSON
document (``json.dumps(sort_keys=True, separators=(",", ":"))``) holding:

* ``tasks`` — sorted by name; each entry is ``{name, depends_on (sorted),
  task_type (the registry slug, or null), snapshot_key
  (``TaskSnapshot.key``: AST-normalized code + config), dependent_params
  (the AST-normalized hash of the task's ``dependent_params`` callable, or
  null)}``. ``dependent_params`` is folded in because it changes a task's
  effective config while the task's own snapshot does not cover it;
* ``entries`` — sorted;
* ``control_edges`` / ``branch_edges`` — sorted edge tuples;
* ``loops`` — ``{body (declaration order), until, max_iters, on_exit}`` each,
  the list sorted by each entry's canonical JSON;
* ``parallels`` — ``{map_over, body, join}`` each, sorted the same way.

Deliberately excluded, because none of them changes what a run computes:

* ``name`` / ``version_label`` — labels for people;
* ``mode`` — no engine behaviour reads it;
* ``max_concurrency`` — how wide a task runs is not its identity (the same
  law as the node cache);
* ``position`` — editor-canvas metadata.

The digest is computed over the lowered task list (after the CFG lowering has
injected the ``wf.parallel`` join dependency), so it is a pure function of the
declarations. Declaration order does not matter; a changed task body does —
which a topology-only hash never noticed, since it hashed the body's qualname
(``"function"`` for every decorator task).
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

from .snapshot import TaskSnapshot

if TYPE_CHECKING:
    from .compiled import CompiledWorkflow

__all__ = ["compute_workflow_digest"]


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _dependent_params_hashes(compiled: CompiledWorkflow) -> dict[str, str | None]:
    """Hash each task's ``dependent_params`` callable (``None`` when it has none).

    Uses the same AST-normalized hasher as the task body
    (:meth:`TaskSnapshot._hash_callable`), so formatting and comments do not
    count and a changed function body does.

    Args:
        compiled: The compiled workflow.

    Returns:
        ``task_name -> hash`` for every task, ``None`` where no
        ``dependent_params`` is declared.
    """
    hashes: dict[str, str | None] = {}
    for reg in compiled._tasks:
        fn = reg.dependent_params
        hashes[reg.name] = (
            TaskSnapshot._hash_callable(fn, f"{reg.name}.dependent_params", reg.name)
            if fn is not None
            else None
        )
    return hashes


def compute_workflow_digest(compiled: CompiledWorkflow) -> str:
    """Return the content-addressed identity of *compiled*.

    See the module docstring for the hashed and the excluded fields.

    Args:
        compiled: The compiled workflow.

    Returns:
        ``"sha256:"`` followed by 64 lowercase hex digits. Equal for two
        workflows that differ only in declaration order, name, version label,
        mode, parallel width or canvas positions.
    """
    dependent = compiled.dependent_params_hashes
    tasks = [
        {
            "name": reg.name,
            "depends_on": sorted(reg.depends_on),
            "task_type": reg.task_type,
            "snapshot_key": compiled.snapshots[reg.name].key,
            "dependent_params": dependent.get(reg.name),
        }
        for reg in sorted(compiled._tasks, key=lambda r: r.name)
    ]
    loops = sorted(
        (
            {
                "body": list(loop.body),
                "until": loop.until,
                "max_iters": loop.max_iters,
                "on_exit": loop.on_exit,
            }
            for loop in compiled._loops
        ),
        key=_canonical,
    )
    parallels = sorted(
        (
            {"map_over": par.map_over, "body": par.body, "join": par.join}
            for par in compiled._parallels
        ),
        key=_canonical,
    )
    document = {
        "tasks": tasks,
        "entries": sorted(compiled._entries),
        "control_edges": sorted(list(edge) for edge in compiled._control_edges),
        "branch_edges": sorted(list(edge) for edge in compiled._branch_edges),
        "loops": loops,
        "parallels": parallels,
    }
    return "sha256:" + hashlib.sha256(_canonical(document).encode()).hexdigest()
