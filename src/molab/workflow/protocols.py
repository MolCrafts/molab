"""Structural protocols for workflow nodes.

Any object matching these protocols can participate in a molab workflow
**without importing molab**. This enables zero-dependency integration
with third-party libraries.

Three ways to define a task — all equivalent at runtime:

1. Function registered via :meth:`Workflow.task` decorator::

       wf = Workflow(name="pipeline")


       @wf.task
       async def fetch(ctx): ...

2. Subclass ``Task`` (convenience base, optional)::

       class Fetch(Task):
           async def execute(self, ctx: TaskContext) -> dict: ...

3. Any object with a matching method (third-party, zero import)::

       # In another package — no molab dependency needed
       class ExternalFetch:
           async def execute(self, ctx) -> dict: ...
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

# Re-exported from the cross-layer typing root so workflow code can use these
# without reaching into ``molab._typing`` directly. The aliases live in one
# place to keep the layering DAG cycle-free.
from .._typing import (
    JSONMapping,
    JSONValue,
    TaskInput,
    TaskOutput,
    UserDeps,
)

__all__ = [
    "AssetsViewLike",
    "JSONMapping",
    "JSONValue",
    "RunContextLike",
    "RunLike",
    "Runnable",
    "Streamable",
    "TaskBody",
    "TaskInput",
    "TaskOutput",
    "UpstreamViewLike",
    "UserDeps",
]

if TYPE_CHECKING:
    # Imported under TYPE_CHECKING only — ``task.py`` imports back into this
    # module for ``TaskInput`` / ``TaskOutput``, so a runtime import would
    # create a cycle. The PEP 695 ``type`` alias below is evaluated lazily,
    # so the names need only be resolvable to a type-checker.
    from .task import Actor, Task

# Anything that may be the body of a registered task. The runtime dispatches
# bodies via isinstance / Protocol checks (see ``_invoke_body_with_ctx``):
# OOP ``Task`` / ``Actor`` instances, third-party objects matching
# :class:`Runnable` / :class:`Streamable`, or a bare async callable.
type TaskBody = "Task | Actor | Runnable | Streamable | Callable[..., Awaitable[TaskOutput]]"


@runtime_checkable
class RunLike(Protocol):
    """Duck-typed shape of ``molab.workspace.run.Run`` used by the workflow runtime.

    Defining the contract here as a Protocol — instead of importing the
    workspace ``Run`` class — is what lets the workflow layer remain
    independent of the workspace layer (CLAUDE.md § *Workflow ↔ pydantic-graph
    boundary*). Members are read-only properties so the concrete ``Run`` (whose
    ``id`` is a property) structurally satisfies the protocol.
    """

    @property
    def id(self) -> str: ...

    def execution(self, execution_id: str) -> object:
        """Read one attempt's record (``KeyError`` when there is none)."""
        ...

    def execution_dir(self, execution_id: str) -> Path:
        """The directory of one attempt; the workspace owns the layout."""
        ...

    def machine_dir(self) -> Path:
        """The run-level machine-state directory the workspace hands out.

        ``<workspace>/.molab/runs/<run-id>/``: machine state a person never
        opens, keyed by run identity. The workflow node cache lives in its
        ``cache/`` subdirectory.

        Returns:
            The directory as a :class:`pathlib.Path`. It is not created by
            this call; only content-addressed state may live under it.
        """
        ...


@runtime_checkable
class UpstreamViewLike(Protocol):
    """View handed to a ``dependent_params`` callback per upstream task.

    Exposes the upstream task's recorded output and (when a workspace
    ``RunContext`` is attached) a producer-task-filtered asset query handle.
    """

    output: TaskOutput
    assets: AssetsViewLike | None


@runtime_checkable
class AssetsViewLike(Protocol):
    """Duck-typed shape of ``workspace.assets.AssetsView`` used by the workflow runtime.

    Only the ``.query(**filters)`` method is reached by workflow code; this
    protocol covers it without importing the workspace's ``Asset`` /
    ``AssetList`` types into the workflow layer.
    """

    def query(
        self,
        *,
        kind: str | type | None = ...,
        producer_run: str | None = ...,
        producer_task: str | None = ...,
        tag: tuple[str, str] | None = ...,
        limit: int | None = ...,
        recursive: bool = ...,
    ) -> TaskOutput: ...


@runtime_checkable
class RunContextLike(Protocol):
    """Duck-typed shape of ``workspace.run.RunContext`` used by the workflow runtime.

    Captures only the surface the workflow scheduler reaches into: the run
    reference, the run directory, the attempt it names (``id`` /
    ``execution_dir`` / ``based_on_execution_id``), the attempt's cache-bypass
    flag, and the register verbs. Members are read-only properties so the
    concrete ``ExecutionContext`` structurally satisfies the protocol.
    Anything else on a real context is out of scope for the workflow layer.

    ``id``, ``execution_dir`` and ``based_on_execution_id`` are required: the
    runtime writes the node journal into ``execution_dir`` (it composes no
    path itself) and verifies resume seeds against the
    ``based_on_execution_id`` attempt; a context lacking them is a
    ``TypeError``. ``bypass_cache`` is read directly whenever a context is
    given.
    """

    @property
    def id(self) -> str:
        """The attempt id (``eNN``) this context has open."""
        ...

    @property
    def execution_dir(self) -> Path:
        """The attempt's directory, supplied by the workspace."""
        ...

    @property
    def based_on_execution_id(self) -> str | None:
        """The predecessor attempt this one resumes / reruns, if any."""
        ...

    @property
    def run_dir(self) -> Path: ...

    @property
    def run(self) -> RunLike: ...

    @property
    def bypass_cache(self) -> bool:
        """Whether this Execution's record asks the runtime to skip cache reads.

        Fixed on ``execution.json`` when the attempt is created
        (``Run.create_execution(bypass_cache=...)`` / ``run.start(bypass_cache=...)``).
        The runtime ORs it with its own ``bypass_cache`` kwarg.
        """
        ...

    def emit_artifact(self, data: object, *, name: str | None = ...) -> object: ...

    def task_workdir(self, task_name: str) -> Path: ...

    def mark_failed(self, error: str | None = None, traceback_text: str | None = None) -> None: ...

    def mark_succeeded(self) -> None: ...


@runtime_checkable
class Runnable(Protocol):
    """Protocol for batch task nodes.

    Any object with ``async execute(ctx) -> output`` qualifies.
    The ``ctx`` argument will be a :class:`~molab.workflow.context.TaskContext`
    at runtime, but the protocol deliberately types it as ``Any`` so that
    third-party implementations need not import molab.

    Example (no molab import needed)::

        class MyProcessor:
            async def execute(self, ctx, data) -> dict:
                # ``data`` binds an upstream output by name; ``ctx`` is optional.
                return {"processed": data}
    """

    async def execute(self, ctx: TaskInput) -> TaskOutput: ...


@runtime_checkable
class Streamable(Protocol):
    """Protocol for streaming actor nodes.

    Any object with ``async run(ctx, ...) -> AsyncIterator`` qualifies. The
    engine drives the generator to exhaustion and records the last yielded
    value as the task's output; streaming bodies are never cached.

    Actor bodies bind their non-``ctx`` parameters by name — from {build-time
    config} | {upstream outputs | run params} — exactly like a batch task; the
    only streaming-specific behaviour is that the LAST value they yield becomes
    the task output. A body whose sole parameter is ``ctx`` is the minimal case.

    Example::

        class MyStreamer:
            async def run(self, ctx, data):
                for item in data:  # ``data`` binds an upstream output
                    yield transform(item)
    """

    # Async-generator functions return their iterator on call (no
    # ``await``), so the Protocol method is declared ``def`` not
    # ``async def`` to match how ``async for`` consumes the result.
    def run(self, ctx: TaskInput) -> AsyncIterator[TaskOutput]: ...
