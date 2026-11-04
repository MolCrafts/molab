"""Workflow authoring.

:class:`Workflow` is the graph a person writes. :meth:`Workflow.compile`
freezes it. :meth:`Workflow.run` runs that frozen graph in memory.
"""

from __future__ import annotations

import inspect
import warnings
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING

from ._engine.compiler import WorkflowGraphCompiler
from ._engine.executors import check_executor
from ._graph_decl import (
    DependentParamsFn,
    LoopDecl,
    ParallelDecl,
    TaskRegistration,
    WorkflowTopology,
)
from ._helpers import _callable_name, _to_snake_case
from .binding import default_binding_registry
from .compiled import CompiledWorkflow
from .protocols import Streamable, TaskBody
from .snapshot import TaskSnapshot
from .types import WorkflowResult

if TYPE_CHECKING:
    from .binding import WorkflowBindingRegistry
    from .compiled import _ExperimentLike

_lowering = WorkflowGraphCompiler()

_NOT_A_DEPENDENCY = frozenset({"self", "ctx"})


def _copy_registration(task: TaskRegistration) -> TaskRegistration:
    """A registration the compiler may edit without touching the author's."""
    return TaskRegistration(
        name=task.name,
        fn_or_class=task.fn_or_class,
        depends_on=list(task.depends_on),
        is_actor=task.is_actor,
        task_type=task.task_type,
        dependent_params=task.dependent_params,
        position=task.position,
        executor=task.executor,
    )


def _body_callable(body: object) -> Callable | None:
    if inspect.isfunction(body) or inspect.ismethod(body):
        return body
    for attr in ("execute", "run"):
        candidate = getattr(body, attr, None)
        if callable(candidate):
            return candidate
    return body if callable(body) else None


def _infer_depends_on(tasks: list[TaskRegistration]) -> None:
    """A parameter whose name is a task is a dependency. One place, at compile."""
    known = {task.name for task in tasks}
    for task in tasks:
        fn = _body_callable(task.fn_or_class)
        if fn is None:
            continue
        try:
            signature = inspect.signature(fn)
        except (TypeError, ValueError):
            continue
        for param in signature.parameters.values():
            if param.kind in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            ):
                continue
            if param.name in _NOT_A_DEPENDENCY or param.name == task.name:
                continue
            if param.name in known and param.name not in task.depends_on:
                task.depends_on.append(param.name)


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
    experiment: _ExperimentLike | None = None,
    registry: WorkflowBindingRegistry | None = None,
    executor: str | None = None,
) -> CompiledWorkflow:
    """Lower registrations once and assemble the :class:`CompiledWorkflow`.

    Shared by :meth:`Workflow.compile` and
    :meth:`CompiledWorkflow.subgraph`. The CFG lowering runs once (it may
    inject parallel-join data deps). Identity is ``workflow_hash``, derived
    from the lowered tasks.
    """
    # Resolve each task's serialization slug from the type registry. The slug
    # lives with the task *type* (registered via ``@default_registry.register``),
    # not at the ``add()`` call site. Tasks that already carry a slug — the
    # deserialize path (``ir_to_spec`` sets it from the incoming JSON) — keep it.
    from .registry import default_registry

    tasks = [_copy_registration(task) for task in tasks]
    _infer_depends_on(tasks)
    for t in tasks:
        if t.task_type is None:
            t.task_type = default_registry.slug_for(t.fn_or_class)

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

    compiled = CompiledWorkflow(
        name=name,
        version_label=version_label,
        tasks=tasks,
        graph=graph,
        snapshots=snapshots,
        mode=mode,
        entries=entries,
        control_edges=control_edges,
        branch_edges=branch_edges,
        loops=loops,
        parallels=parallels,
        executor=executor,
    )
    if experiment is not None:
        reg = registry if registry is not None else default_binding_registry
        compiled.binding = reg.bind(experiment, compiled)
    return compiled


class Workflow:
    """Mutable authored graph (decorator + OOP).

    Freeze it with :meth:`compile` when you need the digest or a diagram.
    Run it in memory with :meth:`run`. A workspace run does not use either:
    pass this object to ``exp.define(wf)`` or ``run.execute(wf)``.

        wf = Workflow(name="pipeline")
        result = wf.run()

    ``executor`` (``"thread"`` — the default —, ``"process"`` or
    ``"inline"``) is how its task bodies run unless a task or the run chooses
    otherwise (see :mod:`molab.workflow._engine.executors`). The
    ``process`` executor imports the module that defines the workflow in each
    worker and finds the task by name, so define the workflow at module level
    (or bind it with a locator).
    """

    def __init__(
        self,
        name: str = "",
        mode: str = "batch",
        version: str = "0",
        *,
        entry: str | list[str] | tuple[str, ...] | None = None,
        executor: str | None = None,
    ) -> None:
        self._name = name
        self._executor = check_executor(executor, where="Workflow(executor=...)")
        self._mode = mode
        self._version = version
        self._tasks: list[TaskRegistration] = []
        self._entries: list[str] = []
        self._control_edges: list[tuple[str, str]] = []
        self._branch_edges: list[tuple[str, str, str]] = []
        self._loops: list[LoopDecl] = []
        self._parallels: list[ParallelDecl] = []
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

    @property
    def executor(self) -> str | None:
        """The workflow's default task executor (``None``: ``thread``)."""
        return self._executor

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
        routes: Mapping[str, str] | None = None,
        next_: str | None = None,
        dependent_params: DependentParamsFn | None = None,
        executor: str | None = None,
    ) -> Callable:
        """Register a function as a batch workflow task.

        The task's inputs are its function parameters, **bound by name**: a
        parameter named after an upstream task receives that task's output,
        and any other parameter is filled from the run's ``params`` (sweep
        cell / ``add_run(params=…)``). Task bodies may be plain ``def`` or
        ``async def``; how a sync body runs is its executor (worker thread by
        default, see *executor*).

        Args:
            fn: The function (when used as a bare ``@wf.task``).
            depends_on: Upstream task names this task waits for. A parameter
                whose name is another task is added at compile
                (:func:`_infer_depends_on`); pass ``depends_on`` for an
                ordering-only edge whose name the body does not take.
            name: Task name (defaults to the function name). Must be unique
                within the workflow.
            routes: ``{label: target}`` branch routing — the task returns
                ``(value, Next(label))`` and control (with ``value``) flows
                to that target. Mutually exclusive with ``next_``.
            next_: Single unconditional control edge to ``target``.
                Mutually exclusive with ``routes``.
            dependent_params: Optional callable deriving extra params from
                upstream outputs before the body runs.
            executor: How this task's body runs (``"thread"`` / ``"process"``
                / ``"inline"``), overriding the workflow's; a run's executor
                overrides both.

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
        check_executor(executor, where="Workflow.task(executor=...)")

        def decorator(f: Callable) -> Callable:
            task_name = name or _callable_name(f)
            self._append_registration(
                TaskRegistration(
                    name=task_name,
                    fn_or_class=f,
                    depends_on=depends_on or [],
                    is_actor=False,
                    dependent_params=dependent_params,
                    executor=executor,
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
        executor: str | None = None,
    ) -> Callable:
        """Register an async generator as a streaming actor.

        Same ``routes=`` / ``next_=`` / ``executor=`` semantics as :meth:`task`.
        """
        if routes is not None and next_ is not None:
            raise TypeError("Workflow.actor: routes= and next_= are mutually exclusive.")
        check_executor(executor, where="Workflow.actor(executor=...)")

        def decorator(f: Callable) -> Callable:
            actor_name = name or _callable_name(f)
            self._append_registration(
                TaskRegistration(
                    name=actor_name,
                    fn_or_class=f,
                    depends_on=depends_on or [],
                    is_actor=True,
                    executor=executor,
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
        routes: Mapping[str, str] | None = None,
        next_: str | None = None,
        dependent_params: DependentParamsFn | None = None,
        executor: str | None = None,
    ) -> Workflow:
        """Register a Task / Actor instance (or any Runnable/Streamable).

        The serialization slug is **not** an argument here: it is a property of
        the task *type*, declared once via
        :meth:`TaskTypeRegistry.register` / ``@default_registry.register("slug")``
        and resolved automatically at compile time. A task's build-time
        config is **not** declared here either — it is the task instance's own
        ``__init__`` arguments (captured automatically; see
        :func:`~molab.workflow.snapshot.task_config_of`), which the cache and IR
        both key on. ``executor`` is as for :meth:`task`. Returns ``self`` to
        support chaining.
        """
        if routes is not None and next_ is not None:
            raise TypeError("Workflow.add: routes= and next_= are mutually exclusive.")
        check_executor(executor, where="Workflow.add(executor=...)")

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
                dependent_params=dependent_params,
                executor=executor,
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

    def compile(
        self,
        *,
        experiment: _ExperimentLike | None = None,
        registry: WorkflowBindingRegistry | None = None,
    ) -> CompiledWorkflow:
        """Freeze this graph.

        The result carries the task code, the edges, and ``workflow_hash``.
        ``experiment`` records the binding. A tracked run does not need this
        call: ``exp.define(wf)`` and ``run.execute(wf)`` freeze the graph.
        """
        if not self._tasks:
            warnings.warn(
                f"workflow {self._name!r} compiles with zero tasks — it will "
                "execute and report succeeded without doing anything. "
                "Register tasks with @wf.task / wf.add(...) first.",
                stacklevel=2,
            )
        return compile_registrations(
            name=self._name,
            version_label=self._version,
            tasks=list(self._tasks),
            mode=self._mode,
            entries=tuple(self._entries),
            control_edges=tuple(self._control_edges),
            branch_edges=tuple(self._branch_edges),
            loops=tuple(self._loops),
            parallels=tuple(self._parallels),
            experiment=experiment,
            registry=registry,
            executor=self._executor,
        )

    async def arun(self) -> WorkflowResult:
        """Run this graph in memory. No workspace and no new attempt.

        A tracked run is ``run.execute(self)``, not this method.
        """
        from ._engine.runtime import WorkflowRuntime

        return await WorkflowRuntime().execute(self.compile())

    def run(self) -> WorkflowResult:
        """Run this graph in memory and return its outputs.

        Synchronous. Inside a running event loop, await :meth:`arun`.
        A tracked run is ``run.execute(self)``.
        """
        import asyncio

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise RuntimeError(
                "wf.run() was called from inside a running event loop; await wf.arun() instead."
            )
        return asyncio.run(self.arun())


__all__ = ["Workflow", "compile_registrations"]
