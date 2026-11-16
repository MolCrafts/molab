"""Content-addressed result caching for per-task node bodies.

Wraps :func:`molab.workflow._engine.node.run_task_body` with the
cache get/put dance: collect + JSON-safe the inputs, look up by
``(snapshot, inputs)``, replay the task's metric records on a hit, and store
the result plus metric records on a miss. A hit's result is the value the
body recorded, including any ``molab:asset/<id>`` ref. The bytes already
live with the asset, so a hit does not copy files again. Kept apart from
the dispatch core in :mod:`.node`.

The cache ``inputs`` payload covers every runtime input of a task: upstream
outputs, engine-injected root inputs (run params), a trigger-delivered value
and the task's **effective config** — the profile data with any
``dependent_params`` overlay *value* applied. Two terms are deliberately out:
the profile *name* (only its data is config) and the execution location (the
task output directory; the effective config carries no ``run_dir``), so
attempts of one run executed in different places share their entries.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from mollog import get_logger

from ..protocols import JSONMapping, JSONValue, TaskInput, TaskOutput
from ..types import UnknownTaskError
from .node import (
    _UNRESOLVED_CONFIG,
    NO_OUTPUT,
    _collect_upstream_outputs,
    run_task_body,
    take_task_metrics,
)
from .node_params import _resolve_dependent_params
from .state import WorkflowDeps, WorkflowState

logger = get_logger(__name__)

# Once-per-(execution, task) dedup for promoted cache-put failure warnings.
# Graceful degradation stays (the run continues uncached), but a permanently
# failing cache backend (permissions, full disk) must surface at WARNING
# instead of vanishing at debug level. Keyed on ``(id(deps), task_name)`` —
# ``WorkflowDeps`` is built fresh per execution, so each run warns at most
# once per task. Bounded so a long-lived process never grows it unboundedly.
_PUT_FAILURE_WARNED: set[tuple[int, str]] = set()
_PUT_FAILURE_WARNED_MAX = 4096


def _is_json_safe(value: object) -> bool:
    """Return True iff *value* round-trips through ``json.dumps`` cleanly."""
    import json

    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return False
    return True


def _canonical_root_inputs(value: TaskOutput) -> TaskOutput:
    """Canonicalize one engine-injected root-inputs value for cache identity.

    The content-addressed ``workdir`` Path is excluded: it varies per
    workspace / execution but never changes task semantics (the body's
    behavior is a function of params + upstream data, not of *where* it
    scratches). Run params — and any SubWorkflow-forwarded keys merged into
    the root entry — MUST stay in, so a parameter sweep never collides on
    one cache entry.
    """
    if isinstance(value, dict):
        return {k: v for k, v in value.items() if k != "workdir"}
    return value


def _canonical_config(config: object) -> JSONValue:
    """Canonicalize a task's effective config for cache identity.

    ``None`` becomes ``{}`` (one key shape for "no config"). A ``Mapping`` —
    including a :class:`~molab.profile.ProfileConfig` — becomes a plain dict
    of its entries; a profile's *name* is not an entry, so it is excluded,
    matching ``ProfileConfig.content_hash`` (data, never name). Anything else
    is returned as-is for the JSON-safety check to judge. Key order is
    normalized downstream by ``Caching._compute_input_hash`` (``sort_keys``).
    """
    if config is None:
        return {}
    if isinstance(config, Mapping):
        return cast("JSONValue", {str(k): v for k, v in config.items()})
    return cast("JSONValue", config)


def _cache_inputs(
    name: str,
    state: WorkflowState,
    upstream: TaskInput,
    delivered: TaskInput = NO_OUTPUT,
    *,
    config: JSONMapping | None = None,
) -> dict[str, JSONValue]:
    """Build the cache ``inputs`` mapping — the task's FULL runtime-input identity.

    ``{"inputs": <upstream>, "config": <effective config>}`` is the key shape
    for plain tasks. The effective config (profile data plus any
    ``dependent_params`` overlay value, see :func:`_canonical_config`) is
    always present — ``None`` and ``{}`` give the same key — and the profile
    name is not part of it. It rides the cache's own ``inputs`` term, never
    the ``TaskSnapshot``. When the engine
    injected root inputs for *name* (sweep params + workdir for a workspace
    run, possibly merged with a SubWorkflow-forwarded value), they are folded
    in under a separate ``"root_inputs"`` key — because the body binds its
    named parameters from ``state.root_inputs[name]``, those values are part
    of the task's cache identity. The workdir Path is canonicalized OUT (see
    :func:`_canonical_root_inputs`). A trigger-*delivered* value (branch-routed
    / loop-back input for a dep-less task) likewise joins the identity under a
    ``"delivered"`` key — two different routed values must never share a cache
    entry. The execution location is not part of the identity: the workdir is
    stripped and the effective config carries no ``run_dir``. Determinism: the
    downstream ``Caching._compute_input_hash`` serializes with
    ``sort_keys=True``, so key insertion order never moves the hash.
    """
    payload: dict[str, JSONValue] = {
        "inputs": cast("JSONValue", upstream),
        "config": _canonical_config(config),
    }
    if name in state.root_inputs:
        root = _canonical_root_inputs(state.root_inputs[name])
        payload["root_inputs"] = cast("JSONValue", root)
    if delivered is not NO_OUTPUT:
        payload["delivered"] = cast("JSONValue", delivered)
    return payload


def _replay_cached_metrics(deps: WorkflowDeps, name: str, payload: Mapping[str, object]) -> None:
    """Append a cache entry's metric records to the current attempt (D93).

    Each record keeps its ``w`` / ``s`` / tags and gains
    ``tags.replayed_from`` (the attempt that produced the entry). An entry
    without ``metrics`` (written before D93, or by a task past the capture
    cap) replays nothing. A failure is logged and never fails the hit.
    """
    records = payload.get("metrics")
    producer = payload.get("producer_execution")
    if not isinstance(records, list) or not records or not isinstance(producer, str):
        return
    try:
        metrics = getattr(deps.run_context, "metrics", None)
        replay = getattr(metrics, "replay", None)
        if callable(replay):
            replay(records, replayed_from=producer)
    except Exception:
        logger.warning(f"cache: metric replay for task {name!r} skipped", exc_info=True)


async def run_task_body_cached(
    name: str,
    deps: WorkflowDeps,
    state: WorkflowState,
    *,
    delivered: TaskInput = NO_OUTPUT,
    effective_config: JSONMapping | None = _UNRESOLVED_CONFIG,
) -> TaskOutput:
    """Run task *name*'s body with content-addressed result caching.

    Gating (caller pre-checks ``deps.cache is not None``, non-actor task,
    ``name in deps.snapshots``):

    * collect the upstream inputs once and resolve the task's effective
      config once (profile data plus the ``dependent_params`` overlay value —
      the user's function runs exactly once per execution, on a hit too, since
      the key needs its value; the engine passes it in as *effective_config*
      when it already resolved it); wrap them — together with any engine-injected
      root inputs for this task (sweep params; the workdir Path is
      canonicalized out) — as the cache ``inputs`` payload. The profile name
      and the execution location are not part of the key;
    * ``cache.get`` → on HIT, replay the cached metric records (tagged
      ``replayed_from``) and return the recorded ``result`` WITHOUT running
      the body (the per-task body counter must not increment). The result
      may be an asset ref; the bytes stay with the asset.
    * on MISS, run the body and ``cache.put({"result": raw})``, plus
      ``"metrics"`` and ``"producer_execution"`` when the task wrote metric
      records under the capture cap. Non-JSON-safe inputs / results degrade
      gracefully — the body still runs and the put is skipped.

    The returned raw value is routed by the caller through the SAME
    ``_classify_return`` path as a plain return, so branch / End semantics
    hold identically on hits and misses.
    """
    registration = deps.registration_by_name.get(name)
    if registration is None:
        raise UnknownTaskError(f"run_task_body_cached: unknown task {name!r}")

    cache = deps.cache
    snapshot = deps.snapshots.get(name)
    assert cache is not None and snapshot is not None  # caller-gated

    inputs = _collect_upstream_outputs(registration, state)
    if effective_config is _UNRESOLVED_CONFIG:
        effective_config = _resolve_dependent_params(
            registration=registration,
            state=state,
            base_config=deps.config,
        )
    cache_inputs = _cache_inputs(name, state, inputs, delivered, config=effective_config)
    cacheable = _is_json_safe(cache_inputs)

    # ``bypass_cache`` (the --fresh escape hatch) skips the READ only: the
    # body always runs, and the fresh result still lands in the cache below.
    if cacheable and not deps.bypass_cache:
        try:
            payload = cache.get(snapshot, cache_inputs)
        except Exception as exc:
            logger.warning(
                f"cache: get for task {name!r} failed ({type(exc).__name__}: {exc}); "
                "the body will run"
            )
            payload = None
        if payload is not None:
            _replay_cached_metrics(deps, name, payload)
            return payload.get("result")

    try:
        raw = await run_task_body(
            name,
            deps,
            state,
            delivered=delivered,
            effective_config=effective_config,
            keep_metrics=True,
        )
    finally:
        # Always popped, so a failed body leaves nothing behind.
        records = take_task_metrics(deps.run_context, name)

    if cacheable and _is_json_safe(raw):
        result_payload = cast("dict[str, JSONValue]", {"result": raw})
        if records and deps.execution_id is not None:
            result_payload["metrics"] = cast("JSONValue", records)
            result_payload["producer_execution"] = deps.execution_id
        # Published only after the journal records completion. A crash between
        # the body and that flush must not leave a cache hit the journal
        # cannot seed.
        deps.pending_cache[name] = (snapshot, cache_inputs, result_payload)
    return raw


def flush_pending_cache(deps: WorkflowDeps, name: str) -> None:
    """Write the cache entry staged for *name*, after its journal record is durable."""
    pending = deps.pending_cache.pop(name, None)
    cache = deps.cache
    if pending is None or cache is None:
        return
    snapshot, cache_inputs, result_payload = pending
    try:
        cache.put(snapshot, cache_inputs, result_payload)
    except Exception as exc:
        warn_key = (id(deps), name)
        if warn_key not in _PUT_FAILURE_WARNED:
            if len(_PUT_FAILURE_WARNED) >= _PUT_FAILURE_WARNED_MAX:
                _PUT_FAILURE_WARNED.clear()
            _PUT_FAILURE_WARNED.add(warn_key)
            logger.warning(
                f"cache: put for task {name!r} failed "
                f"({type(exc).__name__}: {exc}); result caching is degraded "
                f"for this task — the workflow continues uncached"
            )
        else:
            logger.debug(f"cache: put for task {name!r} failed again (suppressed)")
