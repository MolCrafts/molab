"""molab: Workflow and agent platform for research experiment management.

Core packages:
    - ``molab.workspace``: File-system-backed experiment management
    - ``molab.workflow``: DAG-based workflow definition and execution
    - ``molab.plugins``: Optional capabilities (remote HPC, AI agent, ...)

Workflow-layer conveniences are re-exported lazily at the top level —
``molab.WorkflowCompiler``, ``molab.TaskContext`` and
``molab.WorkflowRuntime`` resolve on first attribute access (loading
the ``molab.workflow`` engine machinery only at that point; plain
``import molab`` stays light).
"""

__version__ = "0.1.0"

import molcfg

# Wire the plugin-owned run metrics writer onto the workspace seam
# (molab.workspace.metrics_seam). The plugin is stdlib-only, so this keeps
# ``import molab`` light while ``RunContext.register_metric`` stays usable
# in any process that imported molab.
import molab.plugins.metrics as _plugins_metrics
from molab._logger import Logger, get_logger
from molab.entry import entry
from molab.path import Path

# User-facing hierarchy (all from workspace — single source of truth)
from molab.workspace.experiment import Experiment
from molab.workspace.param import GridSpace, ParamSpace, UniformSpace
from molab.workspace.project import Project
from molab.workspace.run import Run, RunContext
from molab.workspace.workspace import Workspace

#: Process-global, in-code molab config — a live ``molcfg.Config``. The
#: sanctioned place to register runtime values (notably LLM API keys) in code,
#: never from environment variables. Mutate with molcfg-native syntax::
#:
#:     import molab
#:     molab.config["deepseek_api_key"] = "sk-..."
#:     molab.config.get("deepseek_api_key")
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
    # The Python one-step API documented in CLAUDE.md as
    # ``molab.execute_run(wf, run, …)`` — the third face of the same
    # Execution-mode path the CLI and the server drive.
    "execute_run",
    "aexecute_run",
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
