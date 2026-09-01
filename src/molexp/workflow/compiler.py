"""Workflow authoring and compilation — two types, never mixed.

:class:`Workflow` is the mutable authored graph (decorator + OOP).
:class:`WorkflowCompiler` lowers a :class:`Workflow` to a frozen
:class:`CompiledWorkflow`. There is no builder constructor on the compiler
and no ``compile`` method on the graph::

    wf = Workflow(name="pipeline")
    compiled = WorkflowCompiler().compile(wf)
"""

from __future__ import annotations

import warnings
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING

from ._engine.compiler import WorkflowGraphCompiler
from ._graph_decl import (
    DependentParamsFn,
    LoopDecl,
    ParallelDecl,
    TaskRegistration,
    WorkflowTopology,
)
from ._helpers import _callable_name, _stable_workflow_id, _to_snake_case
from .binding import default_binding_registry
from .compiled import CompiledWorkflow
from .protocols import Streamable, TaskBody, TaskOutput, UserDeps
from .snapshot import TaskSnapshot
from .version import TaskTopologyEntry, WorkflowVersion

if TYPE_CHECKING:
    from .binding import WorkflowBindingRegistry
    from .compiled import _ExperimentLike

_lowering = WorkflowGraphCompiler()


def compile_registrations(
    *,
    name: str,
    version_label: str,
    tasks: list[TaskRegistration],
    mode: str = "batch",
    entries: tuple[str, ...] = (),
    control_edges: tuple[tuple[str, str], ...] = (),
    branch_edges: tuple[tuple[str, str, str], ...] = (),
    loops: tuple[LoopDecl, ...] = (),
    parallels: tuple[ParallelDecl, ...] = (),
    reducer: tuple[str, Callable[..., TaskOutput]] | None = None,
    experiment: _ExperimentLike | None = None,
    registry: WorkflowBindingRegistry | None = None,
) -> CompiledWorkflow:
    """Lower registrations once and assemble the :class:`CompiledWorkflow`.

    Shared by :meth:`WorkflowCompiler.compile` and
    :meth:`CompiledWorkflow.subgraph`. The ``workflow_id`` is computed
    before lowering (so it reflects the authored topology), then the CFG
    lowering runs once (it may inject parallel-join data deps), and the
    per-task snapshots + version are computed from the lowered tasks — the
    version reuses each snapshot's ``code_hash`` so the two code-hashers
    collapse to one.
    """
    # Resolve each task's serialization slug from the type registry. The slug
    # lives with the task *type* (registered via ``@default_registry.register``),
    # not at the ``add()`` call site. Tasks that already carry a slug — the
    # deserialize path (``ir_to_spec`` sets it from the incoming JSON) — keep it.
    from .registry import default_registry

    for t in tasks:
        if t.task_type is None:
            t.task_type = default_registry.slug_for(t.fn_or_class)

    workflow_id = _stable_workflow_id(name, tasks)
    topology = WorkflowTopology(
        name=name,
        tasks=tasks,
        entries=entries,
        control_edges=control_edges,
        branch_edges=branch_edges,
        loops=loops,
        parallels=parallels,
    )
    graph = _lowering.compile(topology)

    snapshots: dict[str, TaskSnapshot] = {
        t.name: TaskSnapshot.from_task_body(t.name, t.fn_or_class) for t in tasks
    }
    version = WorkflowVersion(
        workflow_id=workflow_id,
        version=version_label,
        name=name,
        topology=tuple(
            TaskTopologyEntry(
                name=t.name,
                qualname=type(t.fn_or_class).__qualname__,
                depends_on=tuple(t.depends_on),
                code_hash=snapshots[t.name].code_hash,
            )
            for t in tasks
        ),
    )

    compiled = CompiledWorkflow(
        name=name,
        workflow_id=workflow_id,
        version_label=version_label,
        tasks=tasks,
        graph=graph,
        snapshots=snapshots,
        version=version,
        mode=mode,
        entries=entries,
        control_edges=control_edges,
        branch_edges=branch_edges,
        loops=loops,
        parallels=parallels,
        reducer=reducer,
    )
    if experiment is not None:
        reg = registry if registry is not None else default_binding_registry
        compiled.binding = reg.bind(experiment, compiled)
    return compiled


class Workflow:
    """Mutable authored graph (decorator + OOP).

    Compile with :class:`WorkflowCompiler`::

        wf = Workflow(name="pipeline")
        compiled = WorkflowCompiler().compile(wf)
    """

    def __init__(
        self,
        name: str = "",
        mode: str = "batch",
        version: str = "0",
        *,
        entry: str | list[str] | tuple[str, ...] | None = None,
    ) -> None:
        self._name = name
        self._mode = mode
        self._version = version
        self._tasks: list[TaskRegistration] = []
        self._entries: list[str] = []
        self._control_edges: list[tuple[str, str]] = []
        self._branch_edges: list[tuple[str, str, str]] = []
        self._loops: list[LoopDecl] = []
        self._parallels: list[ParallelDecl] = []
        self._reducer: tuple[str, Callable[..., TaskOutput]] | None = None
        if entry is not None:
            if isinstance(entry, str):
                self.entry(entry)
            else:
                for name_ in entry:
                    self.entry(name_)

    @property
    def name(self) -> str:
        return self._name

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def version_label(self) -> str:
        return self._version

    # ── Decorator: function-as-task ───────────────────────────────────────

    def _append_registration(self, registration: TaskRegistration) -> None:
        """Append a registration, refusing a duplicate task name loudly.

        A silent overwrite (copy-pasted decorator, forgotten ``name=``) would
        drop a task from the graph with no signal; the graph is declared once.
        """
        if any(existing.name == registration.name for existing in self._tasks):
            raise ValueError(
                f"workflow {self._name!r} already has a task named "
                f"{registration.name!r} — task names are unique; pass "
                f"name='…' to register a second task from the same callable."
            )
        self._tasks.append(registration)

    def task(
        self,
        fn: Callable | None = None,
        *,
        depends_on: list[str] | None = None,
        name: str | None = None,
        remote: UserDeps = None,
        routes: Mapping[str, str] | None = None,
        next_: str | None = None,
        dependent_params: DependentParamsFn | None = None,
    ) -> Callable:
        """Register a function as a batch workflow task.

        The task's inputs are its function parameters, **bound by name**: a
        parameter named after an upstream task receives that task's output,
        and any other parameter is filled from the run's ``params`` (sweep
        cell / ``add_run(params=…)``). Task bodies may be plain ``def`` or
        ``async def`` (sync bodies run via ``asyncio.to_thread``).

        Args:
            fn: The function (when used as a bare ``@wf.task``).
            depends_on: Upstream task names this task waits for. Optional
                when the name-binding rule already implies the edge — a
                parameter named exactly after an upstream task creates the
                dependency; declare ``depends_on`` for ordering-only edges.
            name: Task name (defaults to the function name). Must be unique
                within the workflow.
            remote: Optional execution deps forwarded to the runtime
                (e.g. a molq scheduler spec) — execution location is not
                task identity.
            routes: ``{label: target}`` branch routing — the task returns
                ``(value, Next(label))`` and control (with ``value``) flows
                to that target. Mutually exclusive with ``next_``.
            next_: Single unconditional control edge to ``target``.
                Mutually exclusive with ``routes``.
            dependent_params: Optional callable deriving extra params from
                upstream outputs before the body runs.

        Example::

            wf = Workflow(name="pipeline")


            @wf.task
            def prepare(x: int) -> int:  # x ← run params
                return x + 1


            @wf.task(depends_on=["prepare"])
            def analyze(prepare: int) -> int:  # prepare ← upstream output
                return prepare * 10
        """
        if routes is not None and next_ is not None:
            raise TypeError("Workflow.task: routes= and next_= are mutually exclusive")

        def decorator(f: Callable) -> Callable:
            task_name = name or _callable_name(f)
            self._append_registration(
                TaskRegistration(
                    name=task_name,
                    fn_or_class=f,
                    depends_on=depends_on or [],
                    is_actor=False,
                    remote=remote,
                    dependent_params=dependent_params,
                )
            )
            self._record_decorator_edges(task_name, routes=routes, next_=next_)
            return f

        if fn is not None:
            return decorator(fn)
        return decorator

    def actor(
        self,
        fn: Callable | None = None,
        *,
        depends_on: list[str] | None = None,
        name: str | None = None,
        routes: Mapping[str, str] | None = None,
        next_: str | None = None,
    ) -> Callable:
        """Register an async generator as a streaming actor.

        Same ``routes=`` / ``next_=`` semantics as :meth:`task`.
        """
        if routes is not None and next_ is not None:
            raise TypeError("Workflow.actor: routes= and next_= are mutually exclusive.")

        def decorator(f: Callable) -> Callable:
            actor_name = name or _callable_name(f)
            self._append_registration(
                TaskRegistration(
                    name=actor_name,
                    fn_or_class=f,
                    depends_on=depends_on or [],
                    is_actor=True,
                )
            )
            self._record_decorator_edges(actor_name, routes=routes, next_=next_)
            return f

        if fn is not None:
            return decorator(fn)
        return decorator

    # ── OOP: register a Task/Actor instance ───────────────────────────────

    def add(
        self,
        task: TaskBody,
        *,
        depends_on: list[str] | None = None,
        name: str | None = None,
        remote: UserDeps = None,
        routes: Mapping[str, str] | None = None,
        next_: str | None = None,
        dependent_params: DependentParamsFn | None = None,
    ) -> Workflow:
        """Register a Task / Actor instance (or any Runnable/Streamable).

        The serialization slug is **not** an argument here: it is a property of
        the task *type*, declared once via
        :meth:`TaskTypeRegistry.register` / ``@default_registry.register("slug")``
        and resolved automatically at compile time. A task's build-time
        config is **not** declared here either — it is the task instance's own
        ``__init__`` arguments (captured automatically; see
        :func:`~molexp.workflow.snapshot.task_config_of`), which the cache and IR
        both key on. Returns ``self`` to support chaining.
        """
        if routes is not None and next_ is not None:
            raise TypeError("Workflow.add: routes= and next_= are mutually exclusive.")

        task_name = name or _to_snake_case(type(task).__name__)
        for suffix in ("_task", "_actor"):
            if task_name.endswith(suffix):
                task_name = task_name[: -len(suffix)]
                break

        self._append_registration(
            TaskRegistration(
                name=task_name,
                fn_or_class=task,
                depends_on=depends_on or [],
                is_actor=isinstance(task, Streamable),
                remote=remote,
                dependent_params=dependent_params,
            )
        )
        self._record_decorator_edges(task_name, routes=routes, next_=next_)
        return self

    # ── Control-flow declarations ─────────────────────────────────────────

    def entry(self, name: str) -> Workflow:
        """Declare *name* as a workflow entry point. Multiple calls = multi-entry."""
        if name in self._entries:
            raise ValueError(f"Workflow {self._name!r}: entry {name!r} declared multiple times")
        self._entries.append(name)
        return self

    def control(self, src: str, to: str) -> Workflow:
        """Declare an unconditional control edge ``src -> to``."""
        self._control_edges.append((src, to))
        return self

    def branch(
        self,
        src: str,
        label: str | None = None,
        to: str | None = None,
        *,
        routes: Mapping[str, str] | None = None,
    ) -> Workflow:
        """Declare branch (label-routed) control edges on *src*.

        Two forms: ``wf.branch("src", "label", "target")`` or
        ``wf.branch("src", routes={"l1": "t1", "l2": "t2"})``.
        """
        if routes is not None:
            if label is not None or to is not None:
                raise TypeError(
                    "Workflow.branch: pass either positional (src, label, to) "
                    "or keyword routes={...}, not both."
                )
            for lbl, target in routes.items():
                self._branch_edges.append((src, lbl, target))
            return self
        if label is None or to is None:
            raise TypeError(
                "Workflow.branch: pass (src, label, to) or routes={...}; "
                "received a partial single-edge form."
            )
        self._branch_edges.append((src, label, to))
        return self

    def loop(
        self,
        *,
        body: list[str] | tuple[str, ...],
        until: str,
        max_iters: int,
        on_exit: str = "_end",
    ) -> Workflow:
        """Declare a loop: ``body`` runs repeatedly until ``until`` exits.

        ``until`` returns ``Next("continue")`` to loop or ``Next("exit")`` to
        proceed to ``on_exit`` (default: terminate).
        """
        if not body:
            raise ValueError(
                f"Workflow.loop: body must contain at least one task name; got {body!r}"
            )
        if max_iters < 1:
            raise ValueError(f"Workflow.loop: max_iters must be >= 1; got {max_iters!r}")
        self._loops.append(
            LoopDecl(body=tuple(body), until=until, max_iters=max_iters, on_exit=on_exit)
        )
        return self

    def parallel(
        self,
        *,
        map_over: str,
        body: str,
        join: str,
        max_concurrency: int = 1,
    ) -> Workflow:
        """Declare parallel fan-out: run *body* once per element of *map_over* output."""
        if max_concurrency < 1:
            raise ValueError(
                f"Workflow.parallel: max_concurrency must be >= 1; got {max_concurrency!r}"
            )
        self._parallels.append(
            ParallelDecl(map_over=map_over, body=body, join=join, max_concurrency=max_concurrency)
        )
        return self

    # ── Cross-replicate reducer ───────────────────────────────────────────

    def reduce(
        self,
        *,
        over: str = "replicate",
    ) -> Callable[[Callable[..., TaskOutput]], Callable[..., TaskOutput]]:
        """Register a cross-replicate reducer (not part of the DAG)."""

        def decorator(fn: Callable[..., TaskOutput]) -> Callable[..., TaskOutput]:
            if self._reducer is not None:
                raise ValueError(
                    f"Workflow {self._name!r}: reducer already registered "
                    f"({_callable_name(self._reducer[1])!r})"
                )
            self._reducer = (over, fn)
            return fn

        return decorator

    def _record_decorator_edges(
        self,
        task_name: str,
        *,
        routes: Mapping[str, str] | None,
        next_: str | None,
    ) -> None:
        if next_ is not None:
            self._control_edges.append((task_name, next_))
        if routes is not None:
            for lbl, target in routes.items():
                self._branch_edges.append((task_name, lbl, target))


class WorkflowCompiler:
    """Lowers a :class:`Workflow` to a :class:`CompiledWorkflow`.

    The compiler is not a graph and is not a builder. Author tasks on
    :class:`Workflow`, then::

        compiled = WorkflowCompiler().compile(workflow)
    """

    def compile(
        self,
        workflow: Workflow,
        *,
        experiment: _ExperimentLike | None = None,
        registry: WorkflowBindingRegistry | None = None,
    ) -> CompiledWorkflow:
        """Lower *workflow* to a :class:`CompiledWorkflow`.

        When ``experiment`` is given, the artifact is bound into ``registry``
        (or :data:`~molexp.workflow.binding.default_binding_registry`).
        """
        if not isinstance(workflow, Workflow):
            raise TypeError(
                f"WorkflowCompiler.compile requires a Workflow, got {type(workflow).__name__}"
            )
        if not workflow._tasks:
            warnings.warn(
                f"workflow {workflow._name!r} compiles with zero tasks — it will "
                f"execute and report succeeded without doing anything. "
                f"Register tasks with @wf.task / wf.add(...) first.",
                stacklevel=2,
            )
        return compile_registrations(
            name=workflow._name,
            version_label=workflow._version,
            tasks=list(workflow._tasks),
            mode=workflow._mode,
            entries=tuple(workflow._entries),
            control_edges=tuple(workflow._control_edges),
            branch_edges=tuple(workflow._branch_edges),
            loops=tuple(workflow._loops),
            parallels=tuple(workflow._parallels),
            reducer=workflow._reducer,
            experiment=experiment,
            registry=registry,
        )


__all__ = ["Workflow", "WorkflowCompiler", "compile_registrations"]
