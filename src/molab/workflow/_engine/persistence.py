"""The node journal: one execution's canonical per-node record, owned by workflow.

Every persisting execution writes one journal, :data:`JOURNAL_NAME`
(``workflow.json``), into the directory the workspace hands the runtime —
``run_context.execution_dir``. The values the journal cites live in the run's
value store (:mod:`.values`), the directory the workspace hands out as
``run_context.values_dir`` / ``run.values_dir()``. The workflow layer never
composes either path.

**Header** (schema :data:`JOURNAL_SCHEMA_VERSION` = 4, the workflow layer's
own version, unrelated to ``MOLAB_SCHEMA_VERSION``): the compiled IR expanded
at the top level (``task_configs`` + ``links`` and the IR's own keys), then
``schema_version``, ``execution_id``, ``workflow_digest``
(:attr:`CompiledWorkflow.workflow_digest`), ``workflow_name``,
``based_on_execution_id``, ``selected_tasks`` (``null`` when the attempt runs
every task, else the tasks a partial rerun re-executes), ``seeded_from``
(``{task: {"execution_id", "ref"}}`` — the predecessor record each seeded
task's output came from), ``started_at`` and ``finished_at``. The two
timestamps are the **engine-run window**, not the attempt window: the
attempt's times live on the Execution record (``execution.json``). There is
no top-level ``status`` / ``outputs`` / ``error`` — an attempt's status
belongs to ``execution.json`` alone.

**Body**: ``task_configs[]`` records keyed by ``task_id`` carry ``status``
(``pending`` / ``running`` / ``completed`` / ``failed`` / ``skipped``),
``error``, ``reason`` (why a task was ``skipped``), ``queued_at`` (when the
engine launched it), ``started_at`` / ``finished_at`` (the span the body itself
ran, stamped by the executor — a task waiting for the inline lock or a pool
worker is queued, not running), ``executor`` (``thread`` / ``process`` / ``inline``) and
``worker_pid`` (the process the body ran in), and:

* ``input_refs`` — written when the task starts, so a failed task keeps it:
  ``{"upstream": {dep: ref}, "root": ref, "delivered": ref, "config": ref}``
  (keys present when the task received that input: each declared upstream it
  consumed, its engine-injected root inputs = run params, a trigger-delivered
  value, its effective config). ``inputs_unrecordable`` maps a slot to why it
  could not be stored.
* ``output_ref`` / ``output_encoding`` (``json`` / ``pickle``) /
  ``output_preview`` (pickled values only, a short ``repr``) — on completion;
  ``output_unrecordable`` says why there is none for a value that could not
  be stored.
* ``snapshot_key`` (``TaskSnapshot.key``) and ``dependent_params_hash`` — on
  completion; ``seeded_from`` (predecessor id) when the output was seeded.

Values are never inlined: a ref names the bytes in the value store, so an
upstream output and the downstream input it feeds are stored once. A journal
of an older schema (inline ``outputs``) is **legacy**: it is still served by
:func:`read_journal` as written, but :func:`read_outputs` and seeding ignore it
(a warning says so) — such an attempt cannot be resumed or partially rerun.

**Flush contract.** The runtime opens the journal with
:func:`open_execution_document` (written synchronously); from then on the
in-memory copy is authoritative. A node's completion or failure flushes
synchronously, so a finished node is on disk the moment it finishes. A
``running`` transition only marks the document dirty and is written within
:data:`WORKFLOW_JSON_MAX_STALENESS_S`. :func:`mark_workflow_finished` and the
runtime's ``finally``-path :func:`close_execution_document` flush too, so a
crash can lose only recent ``running`` marks. Writers target the local
directory of the executing host and go through
:class:`~molab.workspace.file_store.FileStore` (atomic put).

**Readers** (:func:`read_journal` / :func:`read_outputs` /
:func:`read_attempt_seeds`) take a workspace ``Run`` and read through the
workspace's ``FileSystem``, so they work on a remote workspace too.
:func:`read_journal` presents each record's value for the web app: ``outputs``
resolved from the store for a JSON value, ``outputs_pickled: true`` (beside the
stored ``output_preview``) for a pickled one.

**Seeding** has one path, :func:`read_attempt_seeds`, used by both a RESUME
(every completed task with a usable recorded output is a seed, pickled values
included; a failed task re-executes with the inputs its record shows) and a
partial RERUN (``select``: the selected tasks execute, every other completed
task is a seed, everything downstream of a selection is excluded).

**The seed gate** (:func:`_verify_seeds`) is the one place a seed is trusted.
A seed survives only when its task is *verified*: its record is ``completed``
with a usable recorded output, its ``snapshot_key`` and
``dependent_params_hash`` equal the live task's, and every upstream is itself
verified (or never fired in the predecessor — ``pending`` / ``skipped``, e.g.
an unchosen branch). The rule is transitive, so a changed upstream drops every
seed downstream of it. Fast path: when the journal's ``workflow_digest``
equals the live digest, no record is unusable and every seed has a
``completed`` record, the seeds are kept without the full evaluation — equal
digests imply equal per-task keys.
"""

from __future__ import annotations

import copy
import json
import os
import threading
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mollog import get_logger

from ..._typing import JSONValue
from ..types import BranchEdges
from .values import ValueStore

if TYPE_CHECKING:
    from molab.fs import FileSystem
    from molab.workspace.run import Run

    from ..compiled import CompiledWorkflow
    from ..protocols import TaskOutput

logger = get_logger(__name__)

_LOCK = threading.Lock()

#: The journal's file name inside the execution directory.
JOURNAL_NAME = "workflow.json"

#: The journal's schema version (the workflow layer's own). 4: records cite
#: values by ref into the run's value store; 3 and older inlined them.
JOURNAL_SCHEMA_VERSION = 4

#: The record keys describing a task's output (replaced together).
OUTPUT_KEYS: tuple[str, ...] = (
    "output_ref",
    "output_encoding",
    "output_preview",
    "output_unrecordable",
)

#: The record keys describing a task's inputs (replaced together).
INPUT_KEYS: tuple[str, ...] = ("input_refs", "inputs_unrecordable")

#: ``reason`` of a task a partial rerun does not run.
NOT_SELECTED_REASON = "not selected for this rerun"


class RecordedInputError(LookupError):
    """A partial rerun needs a recorded value the predecessor cannot supply."""


def _put_journal(journal_dir: Path, doc: dict | list) -> None:
    """Write *doc* as the journal in *journal_dir* via FileStore (atomic put)."""
    from molab.workspace.file_store import FileStore

    FileStore(journal_dir).put(JOURNAL_NAME, doc)


def _iter_dicts(value: JSONValue) -> Iterator[dict[str, JSONValue]]:
    """Yield only the ``dict`` items from a JSONValue expected to be a list."""
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                yield item


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _task_id(task: dict[str, JSONValue]) -> str | None:
    value = task.get("task_id", task.get("id"))
    return value if isinstance(value, str) else None


def _link_source(link: dict[str, JSONValue]) -> str | None:
    value = link.get("source", link.get("from"))
    return value if isinstance(value, str) else None


def _link_target(link: dict[str, JSONValue]) -> str | None:
    value = link.get("target", link.get("to"))
    return value if isinstance(value, str) else None


# ── Readers ──────────────────────────────────────────────────────────────────


def _load(fs: FileSystem, path: str | os.PathLike[str]) -> dict[str, JSONValue] | None:
    """Read one journal through *fs*.

    Returns ``None`` when the file is missing, unreadable, not JSON, or its
    top level is not an object.
    """
    try:
        if not fs.is_file(path):
            return None
        data = json.loads(fs.read_text(path))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _records(doc: Mapping[str, JSONValue]) -> dict[str, dict[str, JSONValue]]:
    records: dict[str, dict[str, JSONValue]] = {}
    for task in _iter_dicts(doc.get("task_configs", [])):
        name = _task_id(task)
        if name is not None:
            records[name] = task
    return records


def _is_legacy(doc: Mapping[str, JSONValue], execution_id: str | None) -> bool:
    """True (with a warning) for a journal older than refs-into-the-value-store."""
    version = doc.get("schema_version")
    if isinstance(version, int) and version >= JOURNAL_SCHEMA_VERSION:
        return False
    logger.warning(
        f"journal of execution {execution_id!r} is legacy (schema {version!r}, values "
        f"inline); its recorded outputs are not used — the attempt cannot be resumed "
        f"or partially rerun, rerun it from the top"
    )
    return True


def _workspace_fs(run: Run) -> FileSystem:
    return run.experiment.project.workspace.fs


def _journal_path(run: Run, execution_id: str) -> Path:
    return run.execution_dir(execution_id) / JOURNAL_NAME


def value_store(run: Run) -> ValueStore:
    """The run's value store, read through the workspace ``FileSystem``."""
    return ValueStore(run.values_dir(), fs=_workspace_fs(run))


def _load_value(store: ValueStore, ref: str) -> tuple[bool, Any]:
    """``(True, value)``, or ``(False, why)`` when *ref* cannot be loaded."""
    try:
        return True, store.get(ref)
    except Exception as exc:  # missing file, corrupt bytes, unpicklable class …
        return False, f"its recorded value {ref} cannot be loaded ({type(exc).__name__}: {exc})"


def _current(doc: dict[str, JSONValue] | None, execution_id: str | None) -> dict | None:
    """*doc* unless it is missing or legacy (a legacy journal is warned)."""
    if doc is None or _is_legacy(doc, execution_id):
        return None
    return doc


def _recorded_outputs(
    doc: Mapping[str, JSONValue] | None,
    store: ValueStore,
) -> tuple[dict[str, TaskOutput], dict[str, str]]:
    """``(outputs, unusable)`` of every ``completed`` record.

    ``outputs`` maps each task whose ``output_ref`` loads to its value;
    ``unusable`` maps each completed task whose output was not recorded
    (``output_unrecordable``) or does not load to why. A completed record with
    neither (a routing task) is in neither.
    """
    if doc is None:
        return {}, {}
    outputs: dict[str, TaskOutput] = {}
    unusable: dict[str, str] = {}
    for name, record in _records(doc).items():
        if record.get("status") != "completed":
            continue
        ref = record.get("output_ref")
        if isinstance(ref, str):
            ok, value = _load_value(store, ref)
            if ok:
                outputs[name] = value
            else:
                unusable[name] = value
        elif record.get("output_unrecordable"):
            unusable[name] = f"its output could not be recorded ({record['output_unrecordable']})"
    return outputs, unusable


def read_journal(run: Run, execution_id: str) -> dict[str, JSONValue] | None:
    """Read one attempt's node journal, presenting its recorded values.

    Each record citing an ``output_ref`` gains ``outputs`` (the value, loaded
    from the run's value store) when it is JSON, or ``outputs_pickled: true``
    when it is pickled (the stored ``output_preview`` describes it; nothing is
    unpickled here). A value that cannot be loaded gives ``outputs_missing``
    with the reason. A legacy journal is returned as written.

    Args:
        run: The workspace run.
        execution_id: The attempt id (``e01``).

    Returns:
        The presented journal, or ``None`` when the attempt has no journal or
        it is malformed / not a JSON object.
    """
    doc = _load(_workspace_fs(run), _journal_path(run, execution_id))
    if doc is None:
        return None
    version = doc.get("schema_version")
    if not isinstance(version, int) or version < JOURNAL_SCHEMA_VERSION:
        return doc
    store = value_store(run)
    for record in _records(doc).values():
        ref = record.get("output_ref")
        if not isinstance(ref, str):
            continue
        if record.get("output_encoding") == "pickle":
            record["outputs_pickled"] = True
            continue
        ok, value = _load_value(store, ref)
        record["outputs" if ok else "outputs_missing"] = value
    return doc


def read_outputs(run: Run, execution_id: str) -> dict[str, TaskOutput]:
    """Return the completed-node outputs one attempt recorded.

    Every ``completed`` record whose ``output_ref`` loads from the run's value
    store counts — pickled values included. A record whose value was not
    recorded or does not load is omitted with a warning.

    Args:
        run: The workspace run.
        execution_id: The attempt id (``e01``).

    Returns:
        ``{task_name: output}``; empty when there is no readable journal.
    """
    doc = _current(_load(_workspace_fs(run), _journal_path(run, execution_id)), execution_id)
    outputs, unusable = _recorded_outputs(doc, value_store(run))
    for name, why in unusable.items():
        logger.warning(f"output of task {name!r} in execution {execution_id!r} omitted: {why}")
    return outputs


@dataclass(frozen=True)
class AttemptSeeds:
    """What a new attempt takes from its predecessor's records.

    Built only by :func:`read_attempt_seeds`; consumed by
    ``WorkflowRuntime.execute(attempt_seeds=...)``.

    Attributes:
        based_on_execution_id: The predecessor attempt.
        outputs: ``{task: value}`` seeds — the task is not re-executed.
        records: ``{task: output fields}`` (``output_ref`` / ``output_encoding``
            / ``output_preview``) of each seed, copied into the new journal so
            a seed is never re-encoded.
        selected: The tasks a partial rerun executes; ``()`` runs every task.
        excluded: Tasks this attempt never launches (journalled ``skipped``).
        delivered: ``{task: value}`` the trigger-delivered input a selected
            task's record shows (it runs with no live trigger).
        expected_inputs: ``{task: input_refs}`` the predecessor recorded for a
            task this attempt executes; a different live input is warned.
    """

    based_on_execution_id: str
    outputs: Mapping[str, TaskOutput] = field(default_factory=dict)
    records: Mapping[str, Mapping[str, JSONValue]] = field(default_factory=dict)
    selected: tuple[str, ...] = ()
    excluded: frozenset[str] = frozenset()
    delivered: Mapping[str, TaskOutput] = field(default_factory=dict)
    expected_inputs: Mapping[str, Mapping[str, JSONValue]] = field(default_factory=dict)

    def seeded_from(self) -> dict[str, JSONValue]:
        """The journal header's ``seeded_from``: predecessor id + ref per seed."""
        return {
            name: {
                "execution_id": self.based_on_execution_id,
                "ref": self.records.get(name, {}).get("output_ref"),
            }
            for name in self.outputs
        }


def _downstream_of(selection: Sequence[str], ups: Mapping[str, set[str]]) -> set[str]:
    """Every task reachable forward from *selection*, the selection excluded."""
    children: dict[str, set[str]] = {}
    for name, sources in ups.items():
        for source in sources:
            children.setdefault(source, set()).add(name)
    seen: set[str] = set()
    frontier = list(selection)
    while frontier:
        for child in children.get(frontier.pop(), ()):
            if child not in seen:
                seen.add(child)
                frontier.append(child)
    return seen - set(selection)


def _why_not_seeded(
    name: str,
    records: Mapping[str, Mapping[str, JSONValue]],
    unusable: Mapping[str, str],
    reasons: Mapping[str, str],
) -> str:
    record = records.get(name)
    if record is None:
        return "the predecessor journal has no record of it"
    if record.get("status") != "completed":
        return f"its record is {record.get('status')!r}, not completed"
    if name in unusable:
        return unusable[name]
    if not isinstance(record.get("output_ref"), str):
        return "it recorded no output"
    return reasons.get(name, "its record cannot be verified")


def read_attempt_seeds(
    run: Run,
    based_on_execution_id: str,
    compiled: CompiledWorkflow,
    *,
    select: Sequence[str] = (),
) -> AttemptSeeds:
    """The one seeding path: resolve a predecessor's records into seeds.

    Every ``completed`` record of *based_on_execution_id* whose ``output_ref``
    loads from the run's value store is a candidate (pickled values
    included); candidates pass through the transitive seed gate. Without
    *select* (a RESUME) the verified candidates are the seeds and every other
    task executes — a task that failed re-executes from the same seeded
    upstream values its record shows. With *select* (a partial RERUN) the
    selected tasks execute, every verified non-selected task outside their
    downstream is a seed, and every other task is excluded.

    Args:
        run: The workspace run.
        based_on_execution_id: The predecessor attempt.
        compiled: The workflow about to run.
        select: The tasks a partial rerun executes.

    Returns:
        The :class:`AttemptSeeds`; no seeds when the predecessor has no
        (current-schema) journal.

    Raises:
        ValueError: *select* names a task the workflow does not have.
        RecordedInputError: A selected task needs an upstream (a declared
            dependency, or the ``map_over`` of a parallel body) or a recorded
            delivered input that the predecessor cannot supply.
    """
    selection = tuple(dict.fromkeys(select))
    registered = compiled.registration_by_name
    unknown = [name for name in selection if name not in registered]
    if unknown:
        raise ValueError(
            f"unknown task(s) {unknown} selected for rerun; the workflow has {sorted(registered)}"
        )
    doc = _current(
        _load(_workspace_fs(run), _journal_path(run, based_on_execution_id)),
        based_on_execution_id,
    )
    store = value_store(run)
    candidates, unusable = _recorded_outputs(doc, store)
    records = _records(doc) if doc is not None else {}
    reasons: dict[str, str] = {}
    verified = (
        _verify_seeds(
            doc,
            candidates,
            compiled,
            execution_id=based_on_execution_id,
            unusable=unusable,
            reasons=reasons,
        )
        if doc is not None
        else {}
    )

    def _output_fields(name: str) -> dict[str, JSONValue]:
        return {key: records[name][key] for key in OUTPUT_KEYS if key in records[name]}

    def _inputs(names: Sequence[str]) -> dict[str, Mapping[str, JSONValue]]:
        found: dict[str, Mapping[str, JSONValue]] = {}
        for name in names:
            refs = records.get(name, {}).get("input_refs")
            if isinstance(refs, dict):
                found[name] = refs
        return found

    if not selection:
        # A branch task re-decides its route on resume: its recorded value
        # alone cannot route (it carries no ``Next``), so it is not a seed.
        verified = {
            name: value
            for name, value in verified.items()
            if not isinstance(compiled.graph.out_edges.get(name), BranchEdges)
        }
        return AttemptSeeds(
            based_on_execution_id=based_on_execution_id,
            outputs=verified,
            records={name: _output_fields(name) for name in verified},
            expected_inputs=_inputs([name for name in registered if name not in verified]),
        )

    ups, _back, _order = _seed_upstreams(compiled)
    downstream = _downstream_of(selection, ups)
    seeds = {
        name: value
        for name, value in verified.items()
        if name not in selection and name not in downstream
    }
    plan = compiled.graph
    delivered: dict[str, TaskOutput] = {}
    for name in selection:
        needed = set(registered[name].depends_on)
        par = plan.parallel_by_body.get(name)
        if par is not None:
            needed.add(par.map_over)
        for upstream in sorted(needed - set(selection)):
            if upstream not in seeds:
                why = (
                    "it is downstream of another selected task, so its recorded output "
                    "may be stale and it is not run"
                    if upstream in downstream
                    else _why_not_seeded(upstream, records, unusable, reasons)
                )
                raise RecordedInputError(
                    f"cannot rerun {name!r} from execution {based_on_execution_id}'s "
                    f"record: upstream {upstream!r} has no usable recorded output ({why}); "
                    f"select it too (--task {upstream}) or rerun the whole workflow"
                )
        value = _selected_delivered(name, records, store, plan, seeds, selection)
        if value is not _NOTHING:
            delivered[name] = value
    excluded = frozenset(registered) - set(selection) - set(seeds)
    return AttemptSeeds(
        based_on_execution_id=based_on_execution_id,
        outputs=seeds,
        records={name: _output_fields(name) for name in seeds},
        selected=selection,
        excluded=excluded,
        delivered=delivered,
        expected_inputs=_inputs(selection),
    )


_NOTHING: Any = object()


def _selected_delivered(
    name: str,
    records: Mapping[str, Mapping[str, JSONValue]],
    store: ValueStore,
    plan: Any,  # noqa: ANN401 - ExecutionPlan
    seeds: Mapping[str, TaskOutput],
    selection: Sequence[str],
) -> Any:  # noqa: ANN401
    """The trigger-delivered input a selected task runs with, or ``_NOTHING``.

    Its record's ``input_refs.delivered`` when it shows one; otherwise, for a
    task that never started, the seeded outputs of its trigger sources (the
    values those edges carry). Sources inside the selection deliver live.
    """
    from .plan import START

    refs = records.get(name, {}).get("input_refs")
    if isinstance(refs, dict) and isinstance(refs.get("delivered"), str):
        ok, value = _load_value(store, refs["delivered"])
        if not ok:
            raise RecordedInputError(
                f"cannot rerun {name!r}: its recorded delivered input is unusable ({value})"
            )
        return value
    if isinstance(refs, dict):
        return _NOTHING  # it started and received no delivered value
    sources = set(plan.in_sources.get(name, ())) - {START}
    if sources & set(selection):
        return _NOTHING  # a selected source delivers live
    carried = {source: seeds[source] for source in sorted(sources) if source in seeds}
    if not carried:
        return _NOTHING
    return next(iter(carried.values())) if len(carried) == 1 else carried


# ── The seed gate ────────────────────────────────────────────────────────────


def _seed_upstreams(
    compiled: CompiledWorkflow,
) -> tuple[dict[str, set[str]], dict[str, set[str]], list[str]]:
    """Upstream relation used by the seed gate.

    Returns:
        ``(ups, back, order)``: ``ups[T]`` is ``depends_on(T)``, plus the forward
        trigger sources of ``T`` (without ``START``), plus the ``map_over`` task
        when ``T`` is a ``wf.parallel`` body; ``back[T]`` are the back-edge
        sources into ``T``; ``order`` is a topological order of the forward
        relation, ties broken by declaration order.
    """
    from .plan import START

    plan = compiled.graph
    names = [reg.name for reg in compiled._tasks]
    known = set(names)
    ups: dict[str, set[str]] = {}
    for reg in compiled._tasks:
        sources = set(reg.depends_on) | (set(plan.in_sources.get(reg.name, ())) - {START})
        par = plan.parallel_by_body.get(reg.name)
        if par is not None:
            sources.add(par.map_over)
        ups[reg.name] = {s for s in sources if s in known and s != reg.name}
    back: dict[str, set[str]] = {name: set() for name in names}
    for src, tgt in plan.back_edges:
        if tgt in back:
            back[tgt].add(src)

    remaining = {name: set(ups[name]) for name in names}
    order: list[str] = []
    placed: set[str] = set()
    while len(order) < len(names):
        ready = [n for n in names if n not in placed and not (remaining[n] - placed)]
        if not ready:
            # A forward cycle cannot come out of the lowering; stay total anyway.
            ready = [n for n in names if n not in placed]
        for name in ready:
            order.append(name)
            placed.add(name)
    return ups, back, order


def _verify_seeds(
    doc: Mapping[str, JSONValue] | None,
    seeds: Mapping[str, TaskOutput],
    compiled: CompiledWorkflow,
    *,
    execution_id: str | None,
    unusable: Mapping[str, str] | None = None,
    reasons: dict[str, str] | None = None,
) -> dict[str, TaskOutput]:
    """Keep only the seeds the predecessor journal *doc* can vouch for.

    The single seed gate (see the module docstring for the rule). Every
    dropped seed logs one warning naming the first failed condition; dropping
    is never an error — the node recomputes.

    Args:
        doc: The predecessor's journal; ``None`` passes *seeds* through
            unchanged (nothing to verify against, e.g. programmatic seeds).
        seeds: ``{task: output}`` candidates.
        compiled: The workflow about to run.
        execution_id: The predecessor's id (for the warnings).
        unusable: ``{task: why}`` for completed records whose recorded output
            cannot be used (not recorded, or does not load); each fails its
            own check, so everything downstream of it is dropped too.
        reasons: Filled with ``{task: why}`` for every task that is not
            verified, when given.

    Returns:
        The verified subset of *seeds*.
    """
    if doc is None:
        return dict(seeds)
    records = _records(doc)
    unusable = unusable or {}
    if (
        doc.get("workflow_digest") == compiled.workflow_digest
        and not unusable
        and not any(record.get("output_unrecordable") for record in records.values())
        and all(name in records and records[name].get("status") == "completed" for name in seeds)
    ):
        return dict(seeds)

    snapshots = compiled.snapshots
    dependent = compiled.dependent_params_hashes
    ups, back, order = _seed_upstreams(compiled)
    recurrent = compiled.graph.recurrent

    reasons = reasons if reasons is not None else {}

    def _own_failure(name: str) -> str | None:
        record = records.get(name)
        if record is None:
            return "the persisted execution document has no record for it"
        if record.get("status") != "completed":
            return f"its persisted record is {record.get('status')!r}, not completed"
        if name in unusable:
            return unusable[name]
        if record.get("output_unrecordable"):
            return f"its output could not be recorded ({record['output_unrecordable']})"
        persisted_key = record.get("snapshot_key")
        if not isinstance(persisted_key, str) or not persisted_key:
            return (
                "the persisted record carries no snapshot key (pre-upgrade "
                "workflow.json) so the output cannot be verified against the "
                "current task code"
            )
        live = snapshots.get(name)
        if live is None:
            return "the current workflow has no snapshot to verify it against"
        if persisted_key != live.key:
            return (
                "the task's code or config changed since the output was "
                "persisted (snapshot key mismatch)"
            )
        if record.get("dependent_params_hash") != dependent.get(name):
            return "its dependent_params function changed"
        return None

    verified: set[str] = set()
    for name in order:
        why = _own_failure(name)
        if why is None:
            verified.add(name)
        else:
            reasons[name] = why
    for name in seeds:
        if name not in ups and name not in reasons:
            why = _own_failure(name)
            reasons[name] = why or "the current workflow has no such task"

    def _fired_nothing(upstream: str) -> bool:
        record = records.get(upstream)
        return record is not None and record.get("status") in {"pending", "skipped"}

    changed = True
    while changed:
        changed = False
        for name in order:
            if name not in verified:
                continue
            sources = set(ups.get(name, ()))
            if name in recurrent:
                sources |= back.get(name, set())
            for upstream in sorted(sources):
                if upstream in verified or _fired_nothing(upstream):
                    continue
                verified.discard(name)
                reasons[name] = (
                    f"upstream {upstream!r} is not verified and will be recomputed, "
                    "so this output may be stale"
                )
                changed = True
                break

    kept: dict[str, TaskOutput] = {}
    for name, value in seeds.items():
        if name in verified:
            kept[name] = value
            continue
        logger.warning(
            f"resume: dropping seed for node {name!r} in execution "
            f"{execution_id!r} — {reasons.get(name, 'it cannot be verified')}; "
            "the node will be recomputed"
        )
    return kept


# ── Writers ──────────────────────────────────────────────────────────────────


def _initial_document(
    execution_id: str,
    compiled: CompiledWorkflow | None,
    based_on_execution_id: str | None,
    selected_tasks: Sequence[str] | None = None,
    seeded_from: Mapping[str, JSONValue] | None = None,
) -> dict[str, JSONValue]:
    """Journal header. ``workflow_digest`` is its only identity; the spread IR has none."""
    header: dict[str, JSONValue] = {
        "schema_version": JOURNAL_SCHEMA_VERSION,
        "execution_id": execution_id,
        "workflow_digest": compiled.workflow_digest if compiled is not None else None,
        "workflow_name": compiled.name if compiled is not None else None,
        "based_on_execution_id": based_on_execution_id,
        "selected_tasks": list(selected_tasks) if selected_tasks else None,
        "seeded_from": dict(seeded_from or {}),
        "started_at": _now(),
        "finished_at": None,
    }
    if compiled is None:
        return {**header, "task_configs": [], "links": []}

    # Observability serialization: tolerate slug-less tasks (decorator /
    # bare ``Task`` subclasses) — the journal is never round-tripped, so a
    # missing ``task_type`` must not crash the run.
    ir = copy.deepcopy(compiled.to_ir(strict=False))
    raw_tasks = ir.get("task_configs", [])
    raw_links = ir.get("links", [])
    tasks: list[JSONValue] = (
        [t for t in raw_tasks if isinstance(t, dict)] if isinstance(raw_tasks, list) else []
    )
    links: list[JSONValue] = (
        [ln for ln in raw_links if isinstance(ln, dict)] if isinstance(raw_links, list) else []
    )
    for task in tasks:
        if isinstance(task, dict):
            task["status"] = "pending"
    for link in links:
        if isinstance(link, dict):
            link["status"] = "pending"

    document: dict[str, JSONValue] = {**ir, **header}
    document["task_configs"] = tasks
    document["links"] = links
    return document


# ── Coalescing execution-document writer ─────────────────────────────────────

#: Maximum staleness (seconds) of the on-disk journal relative to the
#: in-memory authoritative document while an execution is live.
#:
#: This is a PERFORMANCE knob, NOT a correctness gate, and it applies only to
#: ``running`` transitions: completions and failures flush synchronously.
#: Coalescing turns the per-transition full-document rewrite into one write
#: per staleness window. Nothing in engine coordination ever waits on this
#: value — the flusher is a daemon ``threading.Timer`` on the write path only,
#: never a coroutine the scheduler blocks on.
WORKFLOW_JSON_MAX_STALENESS_S: float = 0.2


class _ExecutionDocumentWriter:
    """One live execution's authoritative in-memory journal + flush state.

    All mutation and serialization happen under ``self._lock``: marks arrive
    on the event-loop thread, the staleness timer fires on its own daemon
    thread. Disk writes go through FileStore (atomic put), so readers never
    observe a torn document.
    """

    def __init__(self, journal_dir: Path, document: dict[str, JSONValue]) -> None:
        self._journal_dir = journal_dir
        self._path = journal_dir / JOURNAL_NAME
        self._document = document
        self._lock = threading.Lock()
        self._dirty = False
        self._closed = False
        self._timer: threading.Timer | None = None

    def mutate(self, apply: Callable[[dict[str, JSONValue]], None], *, flush: bool) -> None:
        """Apply *apply* in memory; flush synchronously or within the staleness bound."""
        with self._lock:
            if self._closed:
                return
            apply(self._document)
            self._dirty = True
            if flush or WORKFLOW_JSON_MAX_STALENESS_S <= 0:
                self._flush_locked()
            elif self._timer is None:
                timer = threading.Timer(WORKFLOW_JSON_MAX_STALENESS_S, self._flush_on_timer)
                timer.daemon = True
                self._timer = timer
                timer.start()

    def _flush_on_timer(self) -> None:
        with self._lock:
            self._timer = None
            if self._closed or not self._dirty:
                return
            try:
                self._flush_locked()
            except Exception as exc:
                logger.warning(
                    f"coalesced journal flush failed for {self._path}: {type(exc).__name__}: {exc}"
                )

    def _flush_locked(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        _put_journal(self._journal_dir, self._document)
        self._dirty = False

    def close(self) -> None:
        """Final flush (if dirty) + stop the timer; the writer is dead after.

        Swallows (logs) write errors — ``close`` runs on the runtime's
        ``finally`` path and must never mask the engine's own exception.
        """
        with self._lock:
            if self._closed:
                return
            self._closed = True
            try:
                if self._dirty:
                    self._flush_locked()
            except Exception as exc:
                logger.warning(
                    f"final journal flush failed for {self._path}: {type(exc).__name__}: {exc}"
                )
            finally:
                if self._timer is not None:
                    self._timer.cancel()
                    self._timer = None

    def discard(self) -> None:
        """Drop pending state WITHOUT writing — the document was superseded."""
        with self._lock:
            self._closed = True
            self._dirty = False
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None


_WRITERS: dict[Path, _ExecutionDocumentWriter] = {}
_REGISTRY_LOCK = threading.Lock()


def _writer_for(journal_dir: Path) -> _ExecutionDocumentWriter | None:
    with _REGISTRY_LOCK:
        return _WRITERS.get(Path(journal_dir) / JOURNAL_NAME)


def open_execution_document(
    journal_dir: Path | None,
    *,
    execution_id: str,
    compiled: CompiledWorkflow | None,
    based_on_execution_id: str | None = None,
    selected_tasks: Sequence[str] | None = None,
    seeded_from: Mapping[str, JSONValue] | None = None,
) -> None:
    """Begin a coalesced-writer lifecycle for one execution's journal.

    Writes the initial document synchronously and registers the in-memory
    copy as authoritative: subsequent :func:`mark_task_status` /
    :func:`mark_workflow_finished` calls mutate it. Callers MUST pair this
    with :func:`close_execution_document` (the runtime does so in a
    ``finally``). Reopening a journal that already has a live writer discards
    the superseded writer without flushing it. No-op when *journal_dir* is
    ``None``.
    """
    if journal_dir is None:
        return
    journal_dir = Path(journal_dir)
    path = journal_dir / JOURNAL_NAME
    document = _initial_document(
        execution_id, compiled, based_on_execution_id, selected_tasks, seeded_from
    )
    with _REGISTRY_LOCK:
        prior = _WRITERS.pop(path, None)
    if prior is not None:
        prior.discard()
    _put_journal(journal_dir, document)
    with _REGISTRY_LOCK:
        _WRITERS[path] = _ExecutionDocumentWriter(journal_dir, document)


def close_execution_document(journal_dir: Path | None) -> None:
    """End a writer lifecycle: flush pending state and unregister.

    Idempotent and ``None``-tolerant so the runtime can call it from a
    ``finally`` however the execution ended.
    """
    if journal_dir is None:
        return
    with _REGISTRY_LOCK:
        writer = _WRITERS.pop(Path(journal_dir) / JOURNAL_NAME, None)
    if writer is not None:
        writer.close()


def _mutate_document(
    journal_dir: Path | None,
    mutate: Callable[[dict[str, JSONValue]], None],
    *,
    flush: bool = False,
) -> None:
    """Apply *mutate* to the journal in *journal_dir*.

    Routed through the registered in-memory writer when the journal was
    opened via :func:`open_execution_document`; otherwise a synchronous
    read-modify-write of an existing journal (a missing one is left alone).
    """
    if journal_dir is None:
        return
    journal_dir = Path(journal_dir)
    writer = _writer_for(journal_dir)
    if writer is not None:
        writer.mutate(mutate, flush=flush)
        return
    path = journal_dir / JOURNAL_NAME
    if not path.exists():
        return
    with _LOCK:
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            return
        if not isinstance(data, dict):
            return
        mutate(data)
        _put_journal(journal_dir, data)


def mark_task_status(
    journal_dir: Path | None,
    task_name: str,
    status: str,
    *,
    output: Mapping[str, JSONValue] | None = None,
    inputs: Mapping[str, JSONValue] | None = None,
    error: str | None = None,
    reason: str | None = None,
    seeded_from: str | None = None,
    snapshot_key: str | None = None,
    dependent_params_hash: str | None = None,
    runner: Mapping[str, JSONValue] | None = None,
    started: bool = False,
    ended: bool = False,
) -> None:
    """Update one task record and its adjacent links in the journal.

    *output* / *inputs* are record fields built by :mod:`.node_record`
    (:data:`OUTPUT_KEYS` / :data:`INPUT_KEYS`); each, when given, replaces the
    record's previous fields of its kind, so a loop iteration never leaves a
    stale ref behind. ``snapshot_key`` and ``dependent_params_hash`` are the
    task's identity at completion; the seed gate compares them with the live
    workflow. *reason* says why a task is ``skipped``; *seeded_from* names the
    predecessor a seeded output came from; *runner* (``executor`` /
    ``worker_pid``) says how and where the body ran.

    ``completed``, ``failed`` and ``skipped`` flush synchronously;
    ``running`` is coalesced (see :data:`WORKFLOW_JSON_MAX_STALENESS_S`).
    No-op when *journal_dir* is ``None``.
    """

    def _replace(task: dict[str, JSONValue], keys: tuple[str, ...], fields: Mapping) -> None:
        for key in keys:
            task.pop(key, None)
        task.update(fields)

    def _apply(data: dict[str, JSONValue]) -> None:
        now = _now()
        for task in _iter_dicts(data.get("task_configs", [])):
            if _task_id(task) == task_name:
                task["status"] = status
                if status == "running":
                    # Launched is not started: a task waiting for its turn
                    # (inline, a full pool) is only queued. ``started`` comes
                    # from the executor the moment the body begins, so the
                    # recorded span is computing time.
                    if ended:
                        # The body returned; the engine records the outcome
                        # when it next runs, which can be later (an inline
                        # body blocks it). The span ends here.
                        task["ended_at"] = now
                    else:
                        key = "started_at" if started else "queued_at"
                        task[key] = task.get(key) or now
                elif status in {"completed", "failed", "skipped"}:
                    task["finished_at"] = task.pop("ended_at", None) or now
                    # A body that never ran (a cache hit, a skip) still gets
                    # a span: zero long, at its finish.
                    task["started_at"] = task.get("started_at") or now
                if output is not None:
                    _replace(task, OUTPUT_KEYS, output)
                if inputs is not None:
                    _replace(task, INPUT_KEYS, inputs)
                if snapshot_key is not None:
                    task["snapshot_key"] = snapshot_key
                if dependent_params_hash is not None:
                    task["dependent_params_hash"] = dependent_params_hash
                if seeded_from is not None:
                    task["seeded_from"] = seeded_from
                if reason is not None:
                    task["reason"] = reason
                if runner is not None:
                    task.update(runner)
                if error:
                    task["error"] = error
        for link in _iter_dicts(data.get("links", [])):
            if _link_target(link) == task_name and status == "running":
                link["status"] = "running"
            if _link_target(link) == task_name and status in {"completed", "skipped"}:
                link["status"] = "completed"
            if _link_source(link) == task_name and status == "completed":
                link["status"] = "running"
            if (
                _link_source(link) == task_name or _link_target(link) == task_name
            ) and status == "failed":
                link["status"] = "failed"

    _mutate_document(journal_dir, _apply, flush=status in {"completed", "failed", "skipped"})


def mark_workflow_finished(journal_dir: Path | None, *, succeeded: bool) -> None:
    """Close the engine-run window and end the writer lifecycle.

    Writes ``finished_at`` only (the attempt's status lives in
    ``execution.json``). On success, links still ``running`` are marked
    ``completed``. Flushes synchronously, then closes the writer. No-op when
    *journal_dir* is ``None``.
    """

    def _apply(data: dict[str, JSONValue]) -> None:
        data["finished_at"] = _now()
        if succeeded:
            for link in _iter_dicts(data.get("links", [])):
                if link.get("status") == "running":
                    link["status"] = "completed"

    _mutate_document(journal_dir, _apply, flush=True)
    close_execution_document(journal_dir)
