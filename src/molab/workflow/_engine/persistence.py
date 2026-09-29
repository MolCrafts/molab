"""The node journal: one execution's canonical per-node record, owned by workflow.

Every persisting execution writes one journal, :data:`JOURNAL_NAME`
(``workflow.json``), into the directory the workspace hands the runtime —
``run_context.execution_dir``. The workflow layer never composes that path;
the workspace owns the layout and supplies the directory and its
``FileSystem``.

**Header** (schema :data:`JOURNAL_SCHEMA_VERSION` = 3, the workflow layer's
own version, unrelated to ``MOLAB_SCHEMA_VERSION``): the compiled IR expanded
at the top level (``task_configs`` + ``links`` and the IR's own keys), then
``schema_version``, ``execution_id``, ``workflow_digest``
(:attr:`CompiledWorkflow.workflow_digest`), ``workflow_name``,
``based_on_execution_id``, ``started_at`` and ``finished_at``. The two
timestamps are the **engine-run window**, not the attempt window: the
attempt's times live on the Execution record (``execution.json``). There is
no top-level ``status`` / ``outputs`` / ``error`` — an attempt's status
belongs to ``execution.json`` alone.

**Body**: ``task_configs[]`` records keyed by ``task_id`` carry ``status``
(``pending`` / ``running`` / ``completed`` / ``failed`` / ``skipped``),
``outputs`` (JSON-rendered), ``outputs_lossy`` (the original was not
JSON-safe, so the stored value is a truncated rendering), ``error``,
``started_at`` / ``finished_at``, and — on completion — ``snapshot_key``
(``TaskSnapshot.key``) and ``dependent_params_hash``.

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
:func:`read_resume_seeds`) take a workspace ``Run`` and read through the
workspace's ``FileSystem``, so they work on a remote workspace too.

**The seed gate** (:func:`_verify_seeds`) is the one place a resume seed is
trusted. A seed survives only when its task is *verified*: its record is
``completed`` and not lossy, its ``snapshot_key`` and ``dependent_params_hash``
equal the live task's, and every upstream is itself verified (or never fired
in the predecessor — ``pending`` / ``skipped``, e.g. an unchosen branch). The
rule is transitive, so a changed upstream drops every seed downstream of it.
Fast path: when the journal's ``workflow_digest`` equals the live digest, no
record is lossy and every seed has a ``completed`` record, the seeds are kept
without the full evaluation — equal digests imply equal per-task keys.
"""

from __future__ import annotations

import copy
import json
import os
import threading
from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mollog import get_logger

from ..._typing import JSONValue

if TYPE_CHECKING:
    from collections.abc import Mapping

    from molab.fs import FileSystem
    from molab.workspace.run import Run

    from ..compiled import CompiledWorkflow
    from ..protocols import TaskOutput

logger = get_logger(__name__)

_LOCK = threading.Lock()

#: The journal's file name inside the execution directory.
JOURNAL_NAME = "workflow.json"

#: The journal's schema version (the workflow layer's own).
JOURNAL_SCHEMA_VERSION = 3


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


def _workflow_json_path(run_dir: Path, execution_id: str) -> Path:
    """Legacy-reader path (``read_node_outputs`` only)."""
    return run_dir / "executions" / execution_id / JOURNAL_NAME


def _now() -> str:
    return datetime.now().isoformat()


def _is_json_safe(value: Any) -> bool:  # noqa: ANN401
    """True iff *value* round-trips through ``json.dumps`` without coercion."""
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return False
    return True


def _jsonable(value: Any) -> JSONValue:  # noqa: ANN401
    """Return a compact JSON-safe representation of a task output.

    LOSSY for non-JSON-safe values (truncated to 20 keys/items, remainder
    str-ified). Callers persisting task outputs must record the fidelity
    flag (see :func:`mark_task_status` ``outputs_lossy``) so the resume
    seeding path never trusts a truncated value as a real task output.
    """
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        pass
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in list(value.items())[:20]}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in list(value)[:20]]
    return str(value)


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


def _completed_outputs(
    doc: Mapping[str, JSONValue] | None, execution_id: str | None
) -> dict[str, TaskOutput]:
    """``{task: output}`` for every ``completed`` record that carries ``outputs``.

    A lossy record (``outputs_lossy``) is omitted with a warning: its value is
    a truncated rendering, and seeding or returning it would corrupt whatever
    consumes it.
    """
    if doc is None:
        return {}
    outputs: dict[str, TaskOutput] = {}
    for task in _iter_dicts(doc.get("task_configs", [])):
        if task.get("status") != "completed" or "outputs" not in task:
            continue
        name = _task_id(task)
        if name is None:
            continue
        if task.get("outputs_lossy"):
            logger.warning(
                f"resume: persisted output of task {name!r} in execution "
                f"{execution_id!r} is lossy (the original value was not "
                f"JSON-safe and was truncated for observability); the node "
                f"will be recomputed instead of seeded"
            )
            continue
        outputs[name] = task["outputs"]
    return outputs


def _workspace_fs(run: Run) -> FileSystem:
    return run.experiment.project.workspace.fs


def _journal_path(run: Run, execution_id: str) -> Path:
    return run.execution_dir(execution_id) / JOURNAL_NAME


def read_journal(run: Run, execution_id: str) -> dict[str, JSONValue] | None:
    """Read one attempt's node journal through the workspace ``FileSystem``.

    Args:
        run: The workspace run.
        execution_id: The attempt id (``e01``).

    Returns:
        The journal document, or ``None`` when the attempt has no journal or
        it is malformed / not a JSON object.
    """
    return _load(_workspace_fs(run), _journal_path(run, execution_id))


def read_outputs(run: Run, execution_id: str) -> dict[str, TaskOutput]:
    """Return the completed-node outputs one attempt recorded.

    Only ``completed`` records carrying an ``outputs`` value count; lossy
    records are omitted with a warning.

    Args:
        run: The workspace run.
        execution_id: The attempt id (``e01``).

    Returns:
        ``{task_name: output}``; empty when there is no readable journal.
    """
    return _completed_outputs(read_journal(run, execution_id), execution_id)


def read_resume_seeds(
    run: Run, based_on_execution_id: str, compiled: CompiledWorkflow
) -> dict[str, TaskOutput]:
    """Return the predecessor's outputs that are safe to seed into *compiled*.

    The completed outputs of *based_on_execution_id*, filtered through the
    transitive seed gate (see the module docstring).

    Args:
        run: The workspace run.
        based_on_execution_id: The predecessor attempt.
        compiled: The workflow about to run.

    Returns:
        The verified seeds; ``{}`` when the predecessor has no journal.
    """
    doc = read_journal(run, based_on_execution_id)
    if doc is None:
        return {}
    return _verify_seeds(
        doc,
        _completed_outputs(doc, based_on_execution_id),
        compiled,
        execution_id=based_on_execution_id,
    )


def read_node_outputs(
    run_dir: str | os.PathLike[str] | None, execution_id: str | None
) -> dict[str, TaskOutput]:
    """Legacy local reader: completed outputs of ``<run_dir>/executions/<id>``.

    Kept for the CLI worker and resume paths until they read through
    :func:`read_outputs`. Non-raising: ``{}`` for a missing id / run dir /
    journal, malformed JSON, or a non-object top level.
    """
    if run_dir is None or execution_id is None:
        return {}
    from molab.fs import LocalFileSystem

    doc = _load(LocalFileSystem(), _workflow_json_path(Path(run_dir), execution_id))
    return _completed_outputs(doc, execution_id)


def last_resumable_execution_id(run: Run) -> str | None:
    """Return the execution_id of the most recent non-succeeded execution.

    ``resume`` reopens this execution and seeds it with the node outputs already
    persisted there. Returns ``None`` when the run has no execution to reopen —
    the caller errors (no fallback to a fresh execution).
    """
    for record in reversed(run.executions):
        if record.status.value != "succeeded":
            return record.id
    return None


def seed_from_execution(run: Run) -> tuple[str | None, dict[str, TaskOutput] | None]:
    """Build ``resume`` seeds from *run*'s last resumable execution.

    Returns ``(execution_id, seed_outputs)``; ``(None, None)`` when there is
    no execution to reopen, ``(execution_id, None)`` when it recorded no
    completed node. The runtime's seed gate verifies the seeds against the
    context's ``based_on_execution_id`` journal.
    """
    execution_id = last_resumable_execution_id(run)
    if execution_id is None:
        return None, None
    return execution_id, read_node_outputs(run.run_dir, execution_id) or None


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

    Returns:
        The verified subset of *seeds*.
    """
    if doc is None:
        return dict(seeds)
    records = _records(doc)
    if (
        doc.get("workflow_digest") == compiled.workflow_digest
        and not any(record.get("outputs_lossy") for record in records.values())
        and all(name in records and records[name].get("status") == "completed" for name in seeds)
    ):
        return dict(seeds)

    snapshots = compiled.snapshots
    dependent = compiled.dependent_params_hashes
    ups, back, order = _seed_upstreams(compiled)
    recurrent = compiled.graph.recurrent

    reasons: dict[str, str] = {}

    def _own_failure(name: str) -> str | None:
        record = records.get(name)
        if record is None:
            return "the persisted execution document has no record for it"
        if record.get("status") != "completed":
            return f"its persisted record is {record.get('status')!r}, not completed"
        if record.get("outputs_lossy"):
            return "its persisted output is lossy (original was not JSON-safe)"
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
) -> dict[str, JSONValue]:
    header: dict[str, JSONValue] = {
        "schema_version": JOURNAL_SCHEMA_VERSION,
        "execution_id": execution_id,
        "workflow_digest": compiled.workflow_digest if compiled is not None else None,
        "workflow_name": compiled.name if compiled is not None else None,
        "based_on_execution_id": based_on_execution_id,
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


def write_initial_workflow_json(
    journal_dir: Path | None,
    *,
    execution_id: str,
    compiled: CompiledWorkflow | None = None,
    based_on_execution_id: str | None = None,
) -> None:
    """Write a fresh journal into *journal_dir* (no-op when ``None``)."""
    if journal_dir is None:
        return
    _put_journal(
        Path(journal_dir),
        _initial_document(execution_id, compiled, based_on_execution_id),
    )


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
    document = _initial_document(execution_id, compiled, based_on_execution_id)
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
    output: Any = None,  # noqa: ANN401
    error: str | None = None,
    snapshot_key: str | None = None,
    dependent_params_hash: str | None = None,
) -> None:
    """Update one task record and its adjacent links in the journal.

    ``snapshot_key`` and ``dependent_params_hash`` are the task's identity at
    completion; the seed gate compares them with the live workflow. A
    non-JSON-safe output is stored through the lossy :func:`_jsonable`
    rendering and flagged ``outputs_lossy``; such a value is never a seed.

    ``completed`` and ``failed`` flush synchronously; ``running`` is
    coalesced (see :data:`WORKFLOW_JSON_MAX_STALENESS_S`). No-op when
    *journal_dir* is ``None``.
    """

    def _apply(data: dict[str, JSONValue]) -> None:
        now = _now()
        for task in _iter_dicts(data.get("task_configs", [])):
            if _task_id(task) == task_name:
                task["status"] = status
                if status == "running":
                    task["started_at"] = task.get("started_at") or now
                elif status in {"completed", "failed", "skipped"}:
                    task["finished_at"] = now
                if output is not None:
                    lossy = not _is_json_safe(output)
                    task["outputs"] = _jsonable(output)
                    if lossy:
                        task["outputs_lossy"] = True
                    else:
                        task.pop("outputs_lossy", None)
                if snapshot_key is not None:
                    task["snapshot_key"] = snapshot_key
                if dependent_params_hash is not None:
                    task["dependent_params_hash"] = dependent_params_hash
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

    _mutate_document(journal_dir, _apply, flush=status in {"completed", "failed"})


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
