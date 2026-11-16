"""Molab workflow layer — public OOP API.

Define a workflow by instantiating :class:`Workflow` and registering
tasks. :meth:`Workflow.run` runs it in memory. :meth:`Workflow.compile`
freezes it when you need the digest or a diagram. A workspace run takes
the :class:`Workflow` itself (``exp.define(wf)``, ``run.execute(wf)``).

1. **Decorator** (functions as tasks)::

       wf = Workflow(name="pipeline")


       @wf.task
       async def fetch(ctx: TaskContext) -> FetchResult: ...


       result = wf.run()

2. **OOP** (subclass ``Task`` and ``.add()``)::

       class FetchTask(Task):
           async def execute(self, ctx: TaskContext) -> FetchResult: ...


       result = Workflow(name="pipeline").add(FetchTask()).run()

3. **Protocol** (any object with ``async execute(ctx)``)::

       class ExternalProcessor:
           async def execute(self, ctx) -> dict: ...


       result = Workflow(name="pipeline").add(ExternalProcessor()).run()

Control flow beyond the DAG shape is declared on the workflow:
``wf.parallel`` (runtime-sized fan-out), ``wf.branch`` (label-routed
edges) and ``wf.loop`` (repeat-until). A branch or loop-``until`` task
returns ``(value, Next("label"))``; the routed target receives ``value``
bound to its named parameters (values-on-edges delivery — see
``docs/en/guide/control-flow.md``).

``wf.compile(experiment=exp)`` binds the frozen graph.
:data:`default_binding_registry` is what the CLI and the server read back.
"""

from ._engine.persistence import AttemptSeeds, read_attempt_seeds, read_journal, read_outputs
from ._engine.runtime import WorkflowRuntime
from .binding import WorkflowBinding, WorkflowBindingRegistry, default_binding_registry
from .cache import Caching
from .cache_store import CacheStore, FileCacheStore
from .codec import WorkflowCodec, default_codec
from .command_task import CommandTask
from .compiled import CompiledWorkflow
from .compiler import Workflow
from .context import TaskContext
from .contract import (
    DeclaredFile,
    Severity,
    TaskInputSpec,
    TaskIO,
    TaskOutputSpec,
    ValidationCheck,
    ValidationCheckId,
    ValidationIssue,
    ValidationReport,
    WorkflowContract,
)
from .digest import compute_workflow_hash
from .execute import RunFailedError, RunNotExecutableError
from .ir import (
    EdgeKind,
    GraphEdgeIR,
    GraphLoopIR,
    GraphNodePosition,
    GraphParallelIR,
    GraphTaskIR,
    WorkflowGraphIR,
)
from .loader import load_workflow_from_entrypoint
from .outputs import RegisterAsset, RegisterMetric
from .protocols import Runnable, Streamable
from .recovery import (
    WorkflowRecoveryError,
    can_recover_workflow,
    compiled_workflow_for_experiment,
    compiled_workflow_for_run,
)
from .registry import TaskTypeRegistry, default_registry
from .snapshot import TaskSnapshot
from .subworkflow import SubWorkflow
from .task import Actor, Task
from .types import (
    BranchEdges,
    CommandError,
    CycleError,
    EdgeShapeError,
    End,
    EntryAmbiguousError,
    LoopMaxItersExceeded,
    MissingRouteError,
    MissingUpstreamResultError,
    Next,
    OutEdges,
    ParallelExecutionError,
    UnconditionalEdges,
    UnknownRouteError,
    UnknownTaskError,
    UnreachableTaskError,
    WorkflowDeadlockError,
    WorkflowError,
    WorkflowExecution,
    WorkflowResult,
)

__all__ = [
    "Actor",
    "AttemptSeeds",
    "BranchEdges",
    "CacheStore",
    "Caching",
    "CommandError",
    "CommandTask",
    "CompiledWorkflow",
    "CycleError",
    "DeclaredFile",
    "EdgeKind",
    "EdgeShapeError",
    "End",
    "EntryAmbiguousError",
    "FileCacheStore",
    "GraphEdgeIR",
    "GraphLoopIR",
    "GraphNodePosition",
    "GraphParallelIR",
    "GraphTaskIR",
    "LoopMaxItersExceeded",
    "MissingRouteError",
    "MissingUpstreamResultError",
    "Next",
    "OutEdges",
    "ParallelExecutionError",
    "RegisterAsset",
    "RegisterMetric",
    "RunFailedError",
    "RunNotExecutableError",
    "Runnable",
    "Severity",
    "Streamable",
    "SubWorkflow",
    "Task",
    "TaskContext",
    "TaskIO",
    "TaskInputSpec",
    "TaskOutputSpec",
    "TaskSnapshot",
    "TaskTypeRegistry",
    "UnconditionalEdges",
    "UnknownRouteError",
    "UnknownTaskError",
    "UnreachableTaskError",
    "ValidationCheck",
    "ValidationCheckId",
    "ValidationIssue",
    "ValidationReport",
    "Workflow",
    "WorkflowBinding",
    "WorkflowBindingRegistry",
    "WorkflowCodec",
    "WorkflowContract",
    "WorkflowDeadlockError",
    "WorkflowError",
    "WorkflowExecution",
    "WorkflowGraphIR",
    "WorkflowRecoveryError",
    "WorkflowResult",
    "WorkflowRuntime",
    "can_recover_workflow",
    "compiled_workflow_for_experiment",
    "compiled_workflow_for_run",
    "compute_workflow_hash",
    "default_binding_registry",
    "default_codec",
    "default_registry",
    "load_workflow_from_entrypoint",
    "read_attempt_seeds",
    "read_journal",
    "read_outputs",
]
