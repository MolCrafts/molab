"""molab: Scientific-workflow platform for FAIR research.

Core packages:
    - ``molab.workspace``: File-system-backed experiment management
    - ``molab.workflow``: DAG-based workflow definition and execution
    - ``molab.plugins``: Optional capabilities (remote HPC, metrics ingest, ...)

Workflow-layer conveniences are re-exported lazily at the top level —
``molab.WorkflowCompiler``, ``molab.TaskContext`` and
``molab.WorkflowRuntime`` resolve on first attribute access (loading
the ``molab.workflow`` engine machinery only at that point; plain
``import molab`` stays light).

``import molab`` also wires the workspace run-executor seam
(``molab.workspace.run.set_run_executor``) with a lazy proxy, so
``Run.execute`` / ``Run.get_result`` / ``RunSet`` work in any process that
imported molab without loading the workflow layer until first use.
"""

from __future__ import annotations

__version__ = "0.1.0"

from collections.abc import Callable
from typing import TYPE_CHECKING

import molcfg
from mollog import Logger, get_logger

# Wire the plugin-owned run metrics writer onto the workspace seam
# (molab.workspace.metrics_seam). The plugin is stdlib-only, so this keeps
# ``import molab`` light while ``RunContext.register_metric`` stays usable
# in any process that imported molab.
import molab.plugins.metrics as _plugins_metrics
from molab.entry import entry

# User-facing hierarchy (all from workspace — single source of truth)
from molab.param import GridSpace, ParamSpace, UniformSpace
from molab.path import Path
from molab.workspace.experiment import Experiment
from molab.workspace.project import Project
from molab.workspace.run import Run, RunContext, RunWorkflowExecutor, set_run_executor
from molab.workspace.workspace import Workspace

if TYPE_CHECKING:
    from molab._typing import TaskOutput


def _load_workflow_run_executor() -> RunWorkflowExecutor:
    """Import the workflow layer's seam implementation through its public factory."""
    from molab.workflow.execute import workspace_run_executor

    return workspace_run_executor()


class _LazyRunExecutor:
    """Run-executor seam proxy that loads the workflow layer on first call.

    Mirrors ``molab.workspace.run.RunWorkflowExecutor``; keep in lockstep.
    The delegate is stateless, so there is no lock: concurrent first calls at
    worst build two equivalent instances.
    """

    def __init__(
        self, load: Callable[[], RunWorkflowExecutor] = _load_workflow_run_executor
    ) -> None:
        self._load = load
        self._delegate: RunWorkflowExecutor | None = None

    def _target(self) -> RunWorkflowExecutor:
        if self._delegate is None:
            self._delegate = self._load()
        return self._delegate

    def execute(
        self,
        run: Run,
        workflow: object | None,
        *,
        resume: bool = False,
        rerun: bool = False,
        fresh: bool = False,
        checkpoint: str | None = None,
        execution_id: str | None = None,
    ) -> object:
        return self._target().execute(
            run,
            workflow,
            resume=resume,
            rerun=rerun,
            fresh=fresh,
            checkpoint=checkpoint,
            execution_id=execution_id,
        )

    async def aexecute(
        self,
        run: Run,
        workflow: object | None,
        *,
        resume: bool = False,
        rerun: bool = False,
        fresh: bool = False,
        checkpoint: str | None = None,
        execution_id: str | None = None,
    ) -> object:
        return await self._target().aexecute(
            run,
            workflow,
            resume=resume,
            rerun=rerun,
            fresh=fresh,
            checkpoint=checkpoint,
            execution_id=execution_id,
        )

    def read_outputs(self, run: Run, execution_id: str) -> dict[str, TaskOutput]:
        return self._target().read_outputs(run, execution_id)


# Wire the workspace run-executor seam; ``molab.workflow`` loads on first use.
# The annotation makes ``ty check`` verify the proxy against the Protocol.
_RUN_EXECUTOR: RunWorkflowExecutor = _LazyRunExecutor()
set_run_executor(_RUN_EXECUTOR)

#: Process-global, in-code molab config — a live ``molcfg.Config``. The
#: sanctioned place to register runtime values in code, never from environment
#: variables. Mutate with molcfg-native syntax::
#:
#:     import molab
#:     molab.config["section.key"] = "value"
#:     molab.config.get("section.key")
#:
#: Distinct from :mod:`molab.profile` — the file-based, per-run profile config.
config: molcfg.Config = molcfg.Config({})

__all__ = [
    "Experiment",
    "GridSpace",
    "Logger",
    "ParamSpace",
    "Project",
    "Run",
    "RunContext",
    "TaskContext",
    "UniformSpace",
    "Workflow",
    "WorkflowCompiler",
    "WorkflowRuntime",
    "Workspace",
    "config",
    "entry",
    "get_logger",
    "wp",
]

#: Workflow-layer attributes re-exported lazily at the top level. Resolving
#: any of them imports ``molab.workflow`` (the engine machinery) on
#: first access only — ``import molab`` must stay light
#: (tests/test_workspace/test_import_guard.py enforces this).
_LAZY_WORKFLOW_ATTRS = (
    "Workflow",
    "WorkflowCompiler",
    "TaskContext",
    "WorkflowRuntime",
)


# Lazy imports — heavy sub-packages are only loaded on first access.
# NOTE: must use importlib, not ``from molab import …`` — the latter re-enters
# this ``__getattr__`` via ``_handle_fromlist`` and recurses infinitely for
# ``from molab import workflow``-style user imports.
def __getattr__(name: str):  # noqa: ANN202
    if name in ("workspace", "workflow", "plugins"):
        import importlib

        return importlib.import_module(f"molab.{name}")
    if name == "wp":
        # Path toolkit: me.wp.mv(ws, src, dst) / me.wp.ls(ws, …)
        import importlib

        return importlib.import_module("molab.workspace.wp")
    if name in _LAZY_WORKFLOW_ATTRS:
        import importlib

        workflow = importlib.import_module("molab.workflow")
        return getattr(workflow, name)
    raise AttributeError(f"module 'molab' has no attribute {name!r}")
