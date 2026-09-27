"""WorkflowRuntime: the workflow execution facade over the structural engine.

The single concrete runtime; molab does not abstract over runtime
backends because there is only one.  Execution modes:

- ``execute()`` — run to completion, return :class:`WorkflowResult`.
- ``start()`` — launch in background, return :class:`WorkflowExecution`.

No per-frame snapshots are written; ``workflow.json`` is opened via
:func:`.persistence.open_execution_document` for observability (per-node
:func:`.persistence.mark_task_status` updates are coalesced in memory and
flushed at bounded staleness; terminal states flush synchronously, and a
``finally``-path :func:`.persistence.close_execution_document` guarantees
the last write even when the engine raises). Resume is caller-driven via
``WorkflowResult.outputs`` + ``execute(seed_outputs=…)``.

Each ``CompiledWorkflow`` carries a frozen
:class:`~molab.workflow._engine.plan.ExecutionPlan` (see
:mod:`.compiler`). The runtime builds fresh state + deps per execution and
drives :func:`.engine.run_plan` — the values-on-edges scheduler; final
outputs are read from the shared, mutated ``state.results``.
"""

from __future__ import annotations

import asyncio
import contextlib
import traceback
import warnings
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import anyio
from mollog import get_logger

from ..protocols import JSONMapping, JSONValue, RunContextLike, TaskOutput, UserDeps
from ..types import WorkflowError, WorkflowExecution, WorkflowResult
from .engine import run_plan
from .node import _workdir_for
from .state import WorkflowDeps, WorkflowState

if TYPE_CHECKING:
    from ..cache import Caching
    from ..compiled import CompiledWorkflow, _ExperimentLike
    from .plan import ExecutionPlan


# Sentinel for ``execute(root_input=…)``: distinguishes "no forwarding" from a
# legitimately-``None`` forwarded value (a fan-out element may itself be ``None``).
_NO_ROOT_INPUT: Any = object()


def _resolve_single_root(compiled: CompiledWorkflow) -> str:
    """Return the inner spec's single entry task (the one fed a forwarded input).

    Used when a :class:`~molab.workflow.SubWorkflow` forwards its node input into
    the inner workflow: that value becomes the entry task's ``ctx.inputs``. Prefers
    an explicit single ``entries`` declaration; otherwise computes the single
    dependency-root (a task with no upstream deps that is not a ``wf.parallel``
    body). Raises :class:`ValueError` when the entry is ambiguous, mirroring
    :meth:`SubWorkflow._resolve_output_name`.
    """
    entries = tuple(compiled._entries)
    if len(entries) == 1:
        return entries[0]
    body_names = {par.body for par in compiled._parallels}
    roots = sorted(
        reg.name for reg in compiled._tasks if not reg.depends_on and reg.name not in body_names
    )
    if len(roots) == 1:
        return roots[0]
    raise ValueError(
        f"SubWorkflow forwards an input into inner workflow {compiled.name!r}, "
        f"but it has {len(roots)} entry task(s) {roots!r}; give the inner spec a "
        f"single entry (one root task, or Workflow(entry='<task>')) so the "
        f"forwarded input has an unambiguous destination."
    )


def _resolve_cache(
    explicit: Caching | None,
    instance_cache: Caching | None,
    run_context: RunContextLike | None,
) -> Caching | None:
    """Pick the effective :class:`Caching` for one execution.

    Resolution order (spec workflow-refactor-04 §Plumbing):

    1. an explicit ``cache=`` kwarg passed to ``execute`` / ``start`` / …;
    2. the runtime's flat ``self.cache`` instance attribute;
    3. auto-derived from a workspace ``run_context`` that exposes
       ``run_dir`` — a :class:`FileCacheStore` under ``<workspace>/.molab/cache/``
       (never the workspace-root ``cache/``);
    4. ``None`` (caching off — identical behaviour to before this spec).
    """
    if explicit is not None:
        return explicit
    if instance_cache is not None:
        return instance_cache
    return _auto_cache_from_run_context(run_context)


def _cache_dir(run_dir: Path) -> Path:
    """Cache location for *run_dir* — machine state, so it lives in ``.molab/``.

    Walks up to the workspace root (the directory holding ``workspace.json``)
    and keys the cache by the run's path below it, so two runs never share a
    cache and no scientific directory gains a machine-only subdirectory.
    """
    from molab.workspace.naming import workspace_root

    root = workspace_root(run_dir)
    if root is None:
        return run_dir / ".cache"
    rel = run_dir.relative_to(root).as_posix().replace("/", "%")
    return root / ".molab" / "cache" / rel


def _auto_cache_from_run_context(run_context: RunContextLike | None) -> Caching | None:
    """Best-effort: build a run-local ``Caching`` from a run_context.

    Cache lives under ``<workspace>/.molab/cache/``. Returns ``None`` when the duck-typed
    surface does not expose a ``run_dir``. Never raises. Never creates a
    workspace-root ``cache/``.
    """
    if run_context is None:
        return None
    run_dir = getattr(run_context, "run_dir", None)
    if run_dir is None:
        run = getattr(run_context, "run", None)
        run_dir = getattr(run, "run_dir", None)
    if run_dir is None:
        return None
    try:
        store_dir = _cache_dir(Path(run_dir))
    except TypeError:
        return None
    from ..cache import Caching
    from ..cache_store import FileCacheStore

    return Caching(store=FileCacheStore(store_dir))


logger = get_logger(__name__)


async def _run_compiled(
    plan: ExecutionPlan,
    state: WorkflowState,
    deps: WorkflowDeps,
) -> WorkflowState:
    """Drive a compiled :class:`ExecutionPlan` to completion and return the final state.

    The engine mutates *state* in place (each completed node records into
    ``state.results``), so the returned object is the same *state* instance
    carrying the final outputs.
    """
    await run_plan(plan, state, deps)
    return state


def _resolve_run_dir(
    run_context: RunContextLike | None, explicit_run_dir: str | Path | None
) -> Path | None:
    """Pick the run directory: explicit ``run_dir=`` wins, else duck-type
    ``run_context.run_dir``."""
    if explicit_run_dir is not None:
        return Path(explicit_run_dir)
    if run_context is None:
        return None
    run_dir = getattr(run_context, "run_dir", None)
    if run_dir is not None:
        return Path(run_dir)
    return None


def _get_run_id(run_context: RunContextLike | None) -> str | None:
    """Extract a stable run identifier from a duck-typed run_context."""
    if run_context is None:
        return None
    run = getattr(run_context, "run", None)
    if run is None:
        return None
    return getattr(run, "id", getattr(run, "run_id", None))


#: Message for the ``ValueError`` raised when a persisting execution resolves
#: a ``run_dir`` but no execution id.
_MISSING_EXECUTION_ID = (
    "execution_id is required to persist under a run_dir: the workspace allocates "
    "Execution ids — open one with Run.create_execution() or run.start() and pass "
    "execution_id= (or run_context=)"
)


def _get_active_execution_id(run_context: RunContextLike | None) -> str | None:
    """Read the open attempt's id from *run_context*'s public surface.

    A workspace ``ExecutionContext`` names its attempt through ``.id``, which
    raises ``RuntimeError`` until the context is entered — that reads as "no
    id yet". A duck-typed context without ``.id`` may carry a public
    ``execution_id`` attribute instead.
    """
    if run_context is None:
        return None
    try:
        value = getattr(run_context, "id", None)
    except RuntimeError:
        value = None
    if isinstance(value, str) and value:
        return value
    value = getattr(run_context, "execution_id", None)
    return value if isinstance(value, str) and value else None


def _record_run_failure(
    run_context: RunContextLike | None,
    error: str | None,
    traceback_text: str | None = None,
) -> None:
    """Mark task-failure on a duck-typed run_context via its typed
    :meth:`RunContextLike.mark_failed`.

    A task body can fail without the exception propagating out of ``execute()``
    (e.g. a ``wf.parallel`` element capturing its error). The workspace's
    ``RunContext`` resolves an exception-free ``with ctx:`` exit to a failed
    run-status by consulting what ``mark_failed`` records, so the CLI surfaces
    the failure even though no exception reached it.

    ``traceback_text`` forwards the formatted stack of the swallowed task
    exception so the workspace can land a REAL traceback in
    ``executions/<exec_id>/error.txt`` (not a placeholder note).
    """
    mark_failed = getattr(run_context, "mark_failed", None)
    if callable(mark_failed):
        mark_failed(error, traceback_text)


def _record_run_success(run_context: RunContextLike | None) -> None:
    """Mark workflow success on a duck-typed run_context (``mark_succeeded``).

    The positive counterpart of :func:`_record_run_failure`: the workspace's
    ``RunContext`` never defaults a previously-failed run back to succeeded on
    a signal-less exit (run-recovery bug 1), so a workflow that genuinely ran
    to completion must say so explicitly. Probed via ``getattr`` so duck-typed
    stub contexts without the method are unaffected.
    """
    mark_succeeded = getattr(run_context, "mark_succeeded", None)
    if callable(mark_succeeded):
        mark_succeeded()


class WorkflowRuntime:
    """Workflow runtime over the structural values-on-edges engine.

    Takes a pre-compiled :class:`~molab.workflow.compiled.CompiledWorkflow`
    (lowered once by :meth:`WorkflowCompiler.compile`) and executes its
    ``.graph`` (an :class:`ExecutionPlan`) via :func:`.engine.run_plan`; no
    recompilation happens here. This class owns the execution facade —
    ``execute`` / ``start`` / ``run_on`` — that used to live on the
    ``Workflow`` spec object.

    ``self.cache`` is a flat, settable :class:`~molab.workflow.cache.Caching`
    instance attribute (default ``None`` — caching off). It is the lowest
    priority cache source; an explicit ``cache=`` kwarg on any execution
    method wins, and a run-local cache under ``<workspace>/.molab/cache/`` is auto-derived
    from a ``run_context`` when neither is set (see :func:`_resolve_cache`).
    """

    def __init__(self) -> None:
        self.cache: Caching | None = None

    @staticmethod
    def _build_initial_state(
        compiled: CompiledWorkflow,
        seed_outputs: Mapping[str, TaskOutput] | None,
    ) -> WorkflowState:
        """Construct the initial :class:`WorkflowState`, optionally seeded.

        When ``seed_outputs`` is non-empty:

        * Every key is validated against the spec's registered task names
          so unknown names fail fast (the ``planmode-review-repair-loop``
          ``ac-006`` contract).
        * Seeded names land in ``state.results`` + ``state.completed`` (so
          downstream tasks find their values) and ``state.seeded`` (so the
          seeded task's own Step skips invoking the body while still
          routing normally through the lowered graph).
        """
        if not seed_outputs:
            return WorkflowState()
        registered = {t.name for t in compiled._tasks}
        unknown = sorted(set(seed_outputs) - registered)
        if unknown:
            raise ValueError(
                f"execute(seed_outputs=...): unknown task name(s) "
                f"{unknown!r}; registered tasks: {sorted(registered)}"
            )
        return WorkflowState.from_seed(seed_outputs)

    @staticmethod
    def _build_deps(
        compiled: CompiledWorkflow,
        *,
        run_context: RunContextLike | None,
        run_dir: Path | None,
        execution_id: str | None,
        config: JSONMapping | None,
        deps: UserDeps,
        cache: Caching | None = None,
        bypass_cache: bool = False,
        scratch_root: Path | None = None,
    ) -> WorkflowDeps:
        """Build a fresh :class:`WorkflowDeps` for one execution.

        Topology fields (registration_by_name / parallel_decls /
        loop_max_iters) are derived from the compiled artifact; one fresh
        :class:`anyio.CapacityLimiter` is built per ``wf.parallel`` body,
        sized to its ``max_concurrency``. When *run_context* is provided
        its attached ``.config`` takes precedence over the *config* kwarg.

        ``cache`` (the resolved effective :class:`Caching`, or ``None``) and
        the compiled artifact's per-task ``snapshots`` are threaded onto the
        deps so the per-task Step cache hook can derive a cache key and
        get / put results.
        """
        if run_context is not None:
            ctx_config = getattr(run_context, "config", None)
            effective_config = ctx_config if ctx_config is not None else config
        else:
            effective_config = config

        run_for_deps = getattr(run_context, "run", None) if run_context is not None else None

        # Static topology maps are derived once and cached on the (frozen)
        # compiled artifact — reused across every execution. Only the capacity
        # limiters must be fresh per run (live anyio objects).
        registration_by_name = compiled.registration_by_name
        parallel_decls = compiled.parallel_decls_by_body
        loop_max_iters = compiled.loop_max_iters
        parallel_limiters = {
            par.body: anyio.CapacityLimiter(par.max_concurrency) for par in compiled._parallels
        }

        return WorkflowDeps(
            run=run_for_deps,
            run_context=run_context,
            config=effective_config,
            user_deps=deps,
            remote_executor=None,
            run_dir=run_dir,
            execution_id=execution_id,
            registration_by_name=registration_by_name,
            parallel_decls=parallel_decls,
            loop_max_iters=loop_max_iters,
            parallel_limiters=parallel_limiters,
            cache=cache,
            bypass_cache=bypass_cache,
            snapshots=compiled.snapshots,
            scratch_root=scratch_root,
        )

    @staticmethod
    def _populate_root_inputs(
        compiled: CompiledWorkflow,
        state: WorkflowState,
        deps: WorkflowDeps,
        run_context: RunContextLike | None,
        root_input: Any = _NO_ROOT_INPUT,  # noqa: ANN401
    ) -> None:
        """Inject root-task inputs (capabilities-as-inputs + SubWorkflow forwarding).

        For each ROOT task (no upstream deps, not a ``wf.parallel`` body, not
        seeded) of a *workspace* run the engine pre-sets ``ctx.inputs = {"params":
        <run params>, "workdir": <task scratch Path>}``. The workdir is a bare
        ``pathlib.Path`` (NEVER a navigable handle) under the execution slot;
        this half is a no-op without a ``run_context`` so non-workspace runs are
        unaffected.

        When ``root_input`` is provided (a :class:`SubWorkflow` forwarding its node
        input — the fan-out element, upstream output, or root params — into this
        inner spec), it is delivered to the single entry task as its ``ctx.inputs``.
        When BOTH the engine-injected ``{params, workdir}`` and the forwarded value
        are dicts, they are MERGED (forwarded keys win) so the inner entry sees the
        element AND keeps ``params`` / ``workdir``; otherwise the forwarded value
        replaces the entry input. Applies whether or not a ``run_context`` is
        present, so the inner entry sees the element even on a plain run.
        """
        body_names = {par.body for par in compiled._parallels}
        if run_context is not None:
            params = getattr(run_context, "params", None) or {}
            for reg in compiled._tasks:
                name = reg.name
                if reg.depends_on or name in body_names or name in state.seeded:
                    continue
                workdir = _workdir_for(deps, name)
                state.root_inputs[name] = {"params": dict(params), "workdir": workdir}
        if root_input is not _NO_ROOT_INPUT:
            entry = _resolve_single_root(compiled)
            existing = state.root_inputs.get(entry)
            if isinstance(existing, dict) and isinstance(root_input, dict):
                # Merge: keep engine-injected params/workdir, forwarded keys win.
                state.root_inputs[entry] = {**existing, **root_input}
            else:
                state.root_inputs[entry] = root_input

    # ── execute ──────────────────────────────────────────────────────────────

    async def execute(
        self,
        compiled: CompiledWorkflow,
        *,
        run_context: RunContextLike | None = None,
        run_dir: str | Path | None = None,
        config: JSONMapping | None = None,
        deps: UserDeps = None,
        execution_id: str | None = None,
        seed_outputs: Mapping[str, TaskOutput] | None = None,
        cache: Caching | None = None,
        bypass_cache: bool = False,
        root_input: Any = _NO_ROOT_INPUT,  # noqa: ANN401
        persist: bool = True,
        scratch_root: str | Path | None = None,
    ) -> WorkflowResult:
        """Run the workflow to completion and return a WorkflowResult.

        ``scratch_root`` (optional) gives task bodies a ``ctx.workdir`` for a
        BARE execution (no tracked Run). Ignored when a ``run_context`` is
        attached (the execution ``out/<task>/`` slot wins). Without either,
        ``ctx.workdir`` stays ``None`` — never silently defaulted to cwd.

        ``seed_outputs`` (optional) pre-populates the initial state with
        already-known task outputs; see :meth:`Workflow.execute` for the
        full contract. ``cache`` (optional) opts the run into content-
        addressed task-result caching; see :func:`_resolve_cache` for the
        precedence rules when it is omitted. ``root_input``
        (optional) forwards a value into the spec's single entry task as its
        ``ctx.inputs`` — the channel a :class:`~molab.workflow.SubWorkflow`
        uses to pass its node input (fan-out element / upstream output) into
        the inner workflow. ``persist=False`` (engine-internal — set by the
        ``sub_runner`` capability for SubWorkflow inner runs) disables ALL
        ``workflow.json`` persistence for this execution, so a nested run
        inheriting the outer ``run_context`` never rewrites the parent
        execution's document: after a run containing SubWorkflows,
        ``executions/<exec_id>/workflow.json`` describes the OUTER graph only.

        Args:
            compiled: The frozen workflow to run.
            execution_id: The workspace-allocated Execution id (``eNN``). It
                comes from the caller or from the open ``run_context``
                only — the runtime never mints one. Allocate it with
                ``Run.create_execution()`` or open it with ``run.start()``.
                A bare run (no ``run_dir`` / ``run_context``) has none.
            bypass_cache: Skip cache READS for this execution (the
                ``--fresh`` escape hatch) — every task body runs, results
                are still written back to the cache. Effective when this
                kwarg is true OR the Execution record requests it
                (``run_context.bypass_cache``).

        Returns:
            The terminal :class:`WorkflowResult`; ``execution_id`` is
            ``None`` for a bare run.

        Raises:
            ValueError: ``persist`` is on, a ``run_dir`` resolves (explicitly
                or from ``run_context``) and no ``execution_id`` is known.
                Raised before any IO, so nothing is written. Also raised for
                ``seed_outputs`` naming unknown tasks.
        """

        # Validate seed_outputs FAIL-FAST before any IO / scheduling work.
        state = self._build_initial_state(compiled, seed_outputs)

        resolved_run_dir = _resolve_run_dir(run_context, run_dir)
        run_id = _get_run_id(run_context)

        # The workspace allocates Execution ids; the runtime only reads one.
        execution_id = execution_id or _get_active_execution_id(run_context)
        # The Execution record carries the cache-bypass request; an explicit
        # kwarg still ORs in.
        if run_context is not None:
            bypass_cache = bypass_cache or run_context.bypass_cache

        # Ownership guard — a journal under ``run_dir`` needs a workspace-
        # allocated id. Raised before any IO so nothing lands on disk.
        journal: tuple[Path, str] | None = None
        if persist and resolved_run_dir is not None:
            if execution_id is None:
                raise ValueError(_MISSING_EXECUTION_ID)
            journal = (resolved_run_dir, execution_id)

        # Resume-seed integrity gate — runs BEFORE the prior workflow.json is
        # rewritten below. Seeds whose persisted snapshot key no longer matches
        # the live task code, whose persisted output is lossy, or that cannot
        # be verified (pre-upgrade document) are dropped with a warning and
        # recomputed; see ``filter_resume_seeds``. Unknown names already
        # failed fast in ``_build_initial_state`` above.
        if seed_outputs and journal is not None:
            from .persistence import filter_resume_seeds

            verified = filter_resume_seeds(*journal, seed_outputs, compiled.snapshots)
            if set(verified) != set(seed_outputs):
                seed_outputs = verified
                state = self._build_initial_state(compiled, seed_outputs)

        # Observability — open the execution document (initial workflow.json is
        # written synchronously under ``<run_dir>/executions/<execution_id>/``
        # so the execution-id directory always exists post-execution for
        # tooling) and register the coalescing in-memory writer: per-node
        # ``mark_task_status`` updates buffer in memory and flush at bounded
        # staleness instead of rewriting the document per transition. The
        # graph runner persists no per-frame snapshots (resume is caller-driven
        # via seed_outputs).
        if journal is not None:
            from .persistence import open_execution_document

            open_execution_document(*journal, compiled=compiled)

        try:
            workflow_deps = self._build_deps(
                compiled,
                run_context=run_context,
                run_dir=resolved_run_dir,
                # ``deps.execution_id`` gates per-task workflow.json status
                # writes (``mark_task_status``); a persistence-off (nested)
                # run must not touch the parent's document.
                execution_id=execution_id if persist else None,
                config=config,
                deps=deps,
                cache=_resolve_cache(cache, self.cache, run_context),
                bypass_cache=bypass_cache,
                scratch_root=Path(scratch_root) if scratch_root is not None else None,
            )

            self._populate_root_inputs(compiled, state, workflow_deps, run_context, root_input)

            result_state: WorkflowState = await _run_compiled(compiled.graph, state, workflow_deps)

            # Propagate the terminal signal to the workspace's RunContext so it
            # resolves the final run.status when the caller's
            # ``with run.start() as ctx: workflow.execute(run_context=ctx)``
            # block exits cleanly. Failure: without this back-channel the
            # failure only surfaces in WorkflowResult.status — which the CLI
            # does not consult. Success: the lifecycle never *defaults* a
            # previously-failed run back to succeeded (run-recovery bug 1), so
            # a genuinely completed workflow must say so. Only the OUTER run
            # signals success (``persist`` is False for SubWorkflow inner runs).
            if result_state.failed and run_context is not None:
                _record_run_failure(run_context, result_state.error)
            elif not result_state.failed and persist and run_context is not None:
                _record_run_success(run_context)
            if journal is not None:
                from .persistence import mark_workflow_finished

                mark_workflow_finished(
                    *journal,
                    status="failed" if result_state.failed else "succeeded",
                    outputs=result_state.results,
                    error=result_state.error,
                )

            return WorkflowResult(
                status="failed" if result_state.failed else "succeeded",
                outputs=result_state.results,
                run_id=run_id,
                execution_id=execution_id,
            )
        except WorkflowError as exc:
            # Programming errors in the workflow definition / task body
            # (CycleError, UnknownRouteError, MissingRouteError, …)
            # propagate to the caller.
            if journal is not None:
                from .persistence import mark_workflow_finished

                mark_workflow_finished(
                    *journal,
                    status="failed",
                    outputs=dict(state.results),
                    error=str(exc),
                )
            raise
        except Exception as exc:
            logger.exception(f"Workflow {compiled.name!r} execution failed")
            # Carry the exception TYPE alongside the message ("ZeroDivisionError:
            # division by zero"), matching the task-level record engine.py writes,
            # so the workspace can persist a typed ErrorInfo instead of a bare
            # message with no type. The FULL formatted traceback rides along so
            # the run's error.txt holds the real stack (the exception itself is
            # swallowed here — this is its last chance to be captured).
            error_text = f"{type(exc).__name__}: {exc}"
            tb_text = "".join(traceback.format_exception(exc))
            if run_context is not None:
                _record_run_failure(run_context, error_text, traceback_text=tb_text)
            if journal is not None:
                from .persistence import mark_workflow_finished

                mark_workflow_finished(
                    *journal,
                    status="failed",
                    outputs=dict(state.results),
                    error=error_text,
                )
            # ``state`` is mutated in place by the graph runner, so it still
            # holds every task result recorded before the raise. Preserve them
            # so the caller can resume via ``seed_outputs=`` instead of
            # recomputing completed (often expensive) tasks.
            return WorkflowResult(
                status="failed",
                outputs=dict(state.results),
                run_id=run_id,
                execution_id=execution_id,
            )
        finally:
            # Guarantee the last in-memory document state lands on disk even
            # when the engine raises something the arms above never see
            # (BaseException / cancellation): flush coalesced-but-unwritten
            # node records and end the writer lifecycle. No-op on the normal
            # paths (mark_workflow_finished already flushed + closed) and for
            # persistence-off (SubWorkflow inner) executions.
            if journal is not None:
                from .persistence import close_execution_document

                close_execution_document(*journal)

    # ── start ────────────────────────────────────────────────────────────────

    async def start(
        self,
        compiled: CompiledWorkflow,
        *,
        run_context: RunContextLike | None = None,
        run_dir: str | Path | None = None,
        config: JSONMapping | None = None,
        deps: UserDeps = None,
        execution_id: str | None = None,
        seed_outputs: Mapping[str, TaskOutput] | None = None,
        cache: Caching | None = None,
        bypass_cache: bool = False,
    ) -> WorkflowExecution:
        """Launch workflow as background asyncio task.

        See :meth:`execute` for ``seed_outputs`` semantics; the same
        fail-fast validation applies before scheduling the background task.

        Args:
            compiled: The frozen workflow to run.
            execution_id: The workspace-allocated Execution id (``eNN``),
                from the caller or the open ``run_context`` only — the
                runtime never mints one. A bare run has none.
            bypass_cache: Skip cache READS (results are still written back).
                Effective when this kwarg is true OR the Execution record
                requests it (``run_context.bypass_cache``).

        Returns:
            A :class:`WorkflowExecution` handle; its ``execution_id`` is
            ``None`` for a bare run.

        Raises:
            ValueError: A ``run_dir`` resolves and no ``execution_id`` is
                known — raised synchronously, before any IO and before the
                background task is created. Also raised for ``seed_outputs``
                naming unknown tasks.
        """
        # Fail-fast on bad seeds so the caller observes the ValueError
        # synchronously, not via an awaited handle.
        seed_state = self._build_initial_state(compiled, seed_outputs)
        resolved_run_dir = _resolve_run_dir(run_context, run_dir)
        run_id = _get_run_id(run_context)
        execution_id = execution_id or _get_active_execution_id(run_context)
        if run_context is not None:
            bypass_cache = bypass_cache or run_context.bypass_cache

        # Ownership guard — see ``execute()``; ``start`` always persists when a
        # run_dir resolves, so it raises here, before any task is scheduled.
        journal: tuple[Path, str] | None = None
        if resolved_run_dir is not None:
            if execution_id is None:
                raise ValueError(_MISSING_EXECUTION_ID)
            journal = (resolved_run_dir, execution_id)

        # Observability — see ``execute()`` for the rationale (initial write +
        # coalescing in-memory writer; closed in ``_bg``'s ``finally``).
        if journal is not None:
            from .persistence import open_execution_document

            open_execution_document(*journal, compiled=compiled)

        handle = _GraphWorkflowExecution(
            execution_id=execution_id,
            workflow_id=compiled.workflow_id,
            run_id=run_id,
        )

        resolved_cache = _resolve_cache(cache, self.cache, run_context)

        async def _bg() -> None:
            try:
                workflow_deps = self._build_deps(
                    compiled,
                    run_context=run_context,
                    run_dir=resolved_run_dir,
                    execution_id=execution_id,
                    config=config,
                    deps=deps,
                    cache=resolved_cache,
                    bypass_cache=bypass_cache,
                )
                result_state: WorkflowState = await _run_compiled(
                    compiled.graph, seed_state, workflow_deps
                )
                if result_state.failed:
                    _record_run_failure(run_context, result_state.error)
                else:
                    _record_run_success(run_context)
                handle._result = WorkflowResult(
                    status="failed" if result_state.failed else "succeeded",
                    outputs=result_state.results,
                    run_id=run_id,
                    execution_id=execution_id,
                )
                if journal is not None:
                    from .persistence import mark_workflow_finished

                    mark_workflow_finished(
                        *journal,
                        status="failed" if result_state.failed else "succeeded",
                        outputs=result_state.results,
                        error=result_state.error,
                    )
            except Exception as exc:
                # ``seed_state`` is mutated in place by the graph runner — it
                # carries the results of every task that completed before the
                # raise. Preserve them for ``seed_outputs=`` resume.
                handle._result = WorkflowResult(
                    status="failed",
                    outputs=dict(seed_state.results),
                    run_id=handle.run_id,
                    execution_id=execution_id,
                )
                if journal is not None:
                    from .persistence import mark_workflow_finished

                    mark_workflow_finished(
                        *journal,
                        status="failed",
                        outputs=dict(seed_state.results),
                        error=str(exc),
                    )
                logger.exception(f"Background workflow {compiled.name!r} failed")
            finally:
                # Terminal-flush guarantee for paths the except-arm never sees
                # (cancellation): land the last document state, end the writer
                # lifecycle. No-op when mark_workflow_finished already closed.
                if journal is not None:
                    from .persistence import close_execution_document

                    close_execution_document(*journal)
                handle._done_event.set()

        handle._task = asyncio.create_task(_bg())
        return handle

    # ── run_on ─────────────────────────────────────────────────────────────────

    async def run_on(
        self,
        compiled: CompiledWorkflow,
        experiment: _ExperimentLike,
        *,
        params: Mapping[str, JSONValue] | None = None,
        parameters: Mapping[str, JSONValue] | None = None,
        deps: UserDeps = None,
        profile_config: object | None = None,
        config: JSONMapping | None = None,
        cache: Caching | None = None,
    ) -> WorkflowResult:
        """Build a fresh Run on *experiment*, execute *compiled*, return the result.

        Relocated from the old ``Workflow.run_on``. Does NOT bind the
        workflow to the experiment; register it explicitly via a
        :class:`~molab.workflow.binding.WorkflowBindingRegistry` (or pass
        ``experiment=`` to :meth:`WorkflowCompiler.compile`) if you need it
        recoverable after process restart.

        ``parameters=`` is a deprecated alias; passing both raises ``TypeError``.
        """
        if parameters is not None:
            if params is not None:
                raise TypeError(
                    "run_on() got both 'params' and its deprecated alias "
                    "'parameters'; pass only 'params'"
                )
            warnings.warn(
                "WorkflowRuntime.run_on(parameters=...) is deprecated; use params=...",
                DeprecationWarning,
                stacklevel=2,
            )
            params = parameters
        params_dict = dict(params) if params is not None else None
        run = cast("Any", experiment).add_run(params=params_dict)
        with run.start(profile_config=profile_config) as run_ctx:
            result = await self.execute(
                compiled, run_context=run_ctx, config=config, deps=deps, cache=cache
            )
        if result.status != "succeeded":
            err = run.metadata.error
            err_msg = (
                f"workflow {compiled.name!r} ended with status {result.status!r}: "
                f"{err.type}: {err.message}"
                if err is not None
                else f"workflow {compiled.name!r} ended with status {result.status!r}"
            )
            raise RuntimeError(err_msg)
        return result


class _GraphWorkflowExecution(WorkflowExecution):
    """Concrete WorkflowExecution returned by start()."""

    def __init__(self, execution_id: str | None, workflow_id: str, run_id: str | None) -> None:
        super().__init__(
            execution_id=execution_id,
            workflow_id=workflow_id,
            run_id=run_id,
        )
        self._result: WorkflowResult | None = None
        self._done_event: asyncio.Event = asyncio.Event()
        self._task: asyncio.Task | None = None

    async def wait(self) -> WorkflowResult:
        """Block until the workflow finishes and return the result."""
        await self._done_event.wait()
        assert self._result is not None
        return self._result

    async def cancel(self) -> None:
        """Cancel the background task."""
        if self._task is not None and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        self._done_event.set()
