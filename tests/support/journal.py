"""``poison_node_output`` — rewrite one completed node's output in a journal.

This is the only node-journal (``executions/<execution_id>/workflow.json``)
writer the arch-own safety-net tests use, and it exists for one purpose:
proving seed provenance. Older suites still write journals directly
(``tests/test_workflow/test_resume_seed_integrity.py``,
``test_node_output_reader.py``, ``test_resume_from_ops.py``,
``tests/test_workspace/test_run_result_fallback.py``); a journal schema change
must update those too. The node cache under ``.molab/cache/`` hands
a recomputed node the very same value a seed would carry, so a test cannot
tell "seeded from the predecessor attempt" from "ran again" by looking at a
normal output. Replacing the predecessor's recorded output with a sentinel
makes the difference observable: a downstream result derived from the
sentinel can only have come from the journal.

Tests never *read* the journal to assert anything — they observe seeding
through the public API (``WorkflowResult.outputs``) or through files the
workflow itself wrote.

The helper targets the current journal shape: ``task_configs[]`` entries keyed
by ``task_id`` carrying ``status`` / ``outputs`` / ``snapshot_key``, plus the
document-level ``outputs`` map. ``snapshot_key`` is left untouched, so the
resume filter still accepts the poisoned value as a valid seed. When the
journal schema changes (arch-own-03b-journal) this helper changes with it.
"""

from __future__ import annotations

import json
from pathlib import Path

from molab._typing import JSONValue
from molab.atomicio import atomic_write_json


def poison_node_output(
    run_dir: str | Path,
    execution_id: str,
    task_id: str,
    value: JSONValue,
) -> None:
    """Rewrite *task_id*'s recorded output in *execution_id*'s journal to *value*.

    Raises ``LookupError`` when the journal has no completed record for
    *task_id* — poisoning a node that never completed would silently prove
    nothing.
    """
    path = Path(run_dir) / "executions" / execution_id / "workflow.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    tasks = document.get("task_configs", [])
    record = next(
        (
            task
            for task in tasks
            if isinstance(task, dict)
            and task.get("task_id") == task_id
            and task.get("status") == "completed"
        ),
        None,
    )
    if record is None:
        raise LookupError(f"{path} has no completed record for task {task_id!r}")
    record["outputs"] = value
    record.pop("outputs_lossy", None)
    outputs = document.get("outputs")
    if isinstance(outputs, dict) and task_id in outputs:
        outputs[task_id] = value
    atomic_write_json(path, document)
