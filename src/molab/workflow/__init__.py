"""Molab workflow layer — public OOP API.

Define a workflow by instantiating :class:`Workflow`, registering
tasks via its methods, then calling :meth:`WorkflowCompiler.compile` to
produce the frozen, content-addressed :class:`CompiledWorkflow` (graph +
per-task snapshots + version + optional experiment binding). Three
equivalent styles share the :class:`Workflow` builder:

1. **Decorator** (functions as tasks)::

       wf = Workflow(name="pipeline")


       @wf.task
       async def fetch(ctx: TaskContext) -> FetchResult: ...


       compiled = WorkflowCompiler().compile(wf)
       result = await WorkflowRuntime().execute(compiled)

2. **OOP** (subclass ``Task`` and ``.add()``)::

       class FetchTask(Task):
           async def execute(self, ctx: TaskContext) -> FetchResult: ...


       compiled = WorkflowCompiler().compile(Workflow(name="pipeline").add(FetchTask()))

3. **Protocol** (any object with ``async execute(ctx)``)::

       class ExternalProcessor:
           async def execute(self, ctx) -> dict: ...


       compiled = WorkflowCompiler().compile(Workflow(name="pipeline").add(ExternalProcessor()))

Control flow beyond the DAG shape is declared on the workflow:
``wf.parallel`` (runtime-sized fan-out), ``wf.branch`` (label-routed
edges) and ``wf.loop`` (repeat-until). A branch or loop-``until`` task
returns ``(value, Next("label"))``; the routed target receives ``value``
bound to its named parameters (values-on-edges delivery — see
``docs/en/guide/control-flow.md``).

Execution lives on :class:`WorkflowRuntime`
(``runtime.execute(compiled)`` / ``.start`` / ``.run_on``), not on the
artifact. Bind a compiled workflow to an experiment via
``WorkflowCompiler().compile(wf, experiment=exp)`` or
:data:`default_binding_registry`.bind(exp, compiled)`` so that downstream
code (CLI / server / cluster workers) can recover it via
``default_binding_registry.for_experiment(experiment)``.
"""

from ._engine.persistence import read_journal, read_outputs, read_resume_seeds
from ._engine.runtime import WorkflowRuntime
from .binding import WorkflowBinding, WorkflowBindingRegistry, default_binding_registry
from .cache import Caching
from .cache_store import CacheStore, FileCacheStore
from .codec import WorkflowCodec, default_codec
from .command_task import CommandTask
from .compiled import CompiledWorkflow
from .compiler import Workflow, WorkflowCompiler
from .context import TaskContext
from .contract import (
    ArtifactDecl,
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
from .digest import compute_workflow_digest
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
from .outputs import RegisterArtifact, RegisterMetric
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
    "ArtifactDecl",
    "BranchEdges",
    "CacheStore",
    "Caching",
    "CommandError",
    "CommandTask",
    "CompiledWorkflow",
    "CycleError",
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
    "RegisterArtifact",
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
    "WorkflowCompiler",
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
    "compute_workflow_digest",
    "default_binding_registry",
    "default_codec",
    "default_registry",
    "load_workflow_from_entrypoint",
    "read_journal",
    "read_outputs",
    "read_resume_seeds",
]
