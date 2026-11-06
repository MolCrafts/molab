"""Build a task's journal record fields: its inputs and its output, by ref.

The engine calls :func:`input_fields` when a task starts (so a failed task
keeps them) and :func:`output_fields` when it completes; both hand the result
to :func:`.persistence.mark_task_status`. Values go into the run's value store
(:mod:`.values`) through ``deps.values``; a record never holds a value.

An upstream's output ref is remembered in ``state.output_records`` when it
completes (or arrives as a seed), and a downstream input names that same
ref instead of encoding the value again — this is what stores an upstream
output and the downstream input it feeds once, and what keeps a seeded
(possibly non-deterministically pickled) value on its original ref.

The input slots mirror what the body receives and what the node cache keys
on (:func:`.node_cache._cache_inputs`): each declared upstream, the
engine-injected root inputs (run params; the per-attempt ``workdir`` is not
an input), a trigger-delivered value, and the effective config.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from mollog import get_logger

from .node import NO_OUTPUT
from .node_cache import _canonical_config, _canonical_root_inputs
from .values import UnrecordableValueError, preview

if TYPE_CHECKING:
    from ..protocols import JSONMapping, JSONValue, TaskInput, TaskOutput
    from .state import WorkflowDeps, WorkflowState
    from .values import ValueStore

logger = get_logger(__name__)


def _recording(deps: WorkflowDeps) -> ValueStore | None:
    """The value store, when this execution writes a journal."""
    return deps.values if deps.journal_dir is not None else None


def output_fields(
    deps: WorkflowDeps, state: WorkflowState, name: str, value: TaskOutput
) -> dict[str, JSONValue] | None:
    """Store *name*'s output and return its record fields (``None``: no journal).

    A seeded task keeps the fields its seed arrived with. An unrecordable
    value yields ``output_unrecordable`` (logged): that node cannot be re-run
    or resumed from the record.
    """
    store = _recording(deps)
    if store is None:
        return None
    if name in state.seeded and name in state.output_records:
        return dict(state.output_records[name])
    received = state.encoded_outputs.pop(name, None)
    try:
        if received is not None and received[0] is value:
            # A worker process encoded it: store those bytes as they are.
            encoding = received[2]
            ref = store.put_bytes(received[1], encoding)
        else:
            ref, encoding = store.put_encoded(value)
    except UnrecordableValueError as exc:
        logger.warning(f"output of task {name!r} is not recorded: {exc}")
        state.output_records.pop(name, None)
        return {"output_unrecordable": str(exc)}
    fields: dict[str, JSONValue] = {"output_ref": ref, "output_encoding": encoding}
    if encoding == "pickle":
        fields["output_preview"] = preview(value)
    state.output_records[name] = fields
    return fields


def _upstream_ref(store: ValueStore, state: WorkflowState, dep: str) -> str:
    fields = state.output_records.get(dep)
    ref = fields.get("output_ref") if fields else None
    if isinstance(ref, str):
        return ref
    return store.put(state.results.get(dep))


def input_fields(
    deps: WorkflowDeps,
    state: WorkflowState,
    name: str,
    *,
    delivered: TaskInput = NO_OUTPUT,
    effective_config: JSONMapping | None = None,
    upstream: tuple[str, ...] | None = None,
) -> dict[str, JSONValue] | None:
    """Store *name*'s runtime inputs and return its record fields.

    Args:
        deps: The execution's deps (``values`` / ``journal_dir``).
        state: The live state (upstream values and their refs).
        name: The task about to run.
        delivered: The trigger-delivered value, if one was carried.
        effective_config: The task's resolved config.
        upstream: The upstream tasks it consumes; ``None`` means its declared
            ``depends_on``.

    Returns:
        ``{"input_refs": {...}}`` plus ``inputs_unrecordable`` when a slot
        could not be stored; ``None`` when this execution writes no journal.
    """
    store = _recording(deps)
    if store is None:
        return None
    if upstream is None:
        registration = deps.registration_by_name.get(name)
        upstream = tuple(registration.depends_on) if registration is not None else ()
    refs: dict[str, JSONValue] = {}
    problems: dict[str, JSONValue] = {}

    def _slot(slot: str, value: object) -> None:
        try:
            refs[slot] = store.put(value)
        except UnrecordableValueError as exc:
            problems[slot] = str(exc)

    if upstream:
        ups: dict[str, JSONValue] = {}
        for dep in upstream:
            try:
                ups[dep] = _upstream_ref(store, state, dep)
            except UnrecordableValueError as exc:
                problems[f"upstream.{dep}"] = str(exc)
        refs["upstream"] = ups
    if name in state.root_inputs:
        _slot("root", _canonical_root_inputs(state.root_inputs[name]))
    if delivered is not NO_OUTPUT:
        _slot("delivered", delivered)
    _slot("config", _canonical_config(effective_config))
    _warn_if_inputs_differ(state, name, refs)
    fields: dict[str, JSONValue] = {"input_refs": refs}
    if problems:
        fields["inputs_unrecordable"] = problems
    return fields


def _warn_if_inputs_differ(state: WorkflowState, name: str, refs: Mapping[str, JSONValue]) -> None:
    """Warn when a re-executed task's live inputs differ from its recorded ones."""
    expected = state.expected_inputs.get(name)
    if not expected:
        return
    differ = [
        slot
        for slot in ("upstream", "root", "delivered", "config")
        if slot in expected and expected.get(slot) != refs.get(slot)
    ]
    if differ:
        logger.warning(
            f"task {name!r} re-executes with inputs that differ from its predecessor "
            f"record in {differ}; the record shows {dict(expected)}, this attempt "
            f"uses {dict(refs)}"
        )


__all__ = ["input_fields", "output_fields"]
