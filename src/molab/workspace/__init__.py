"""Workspace module — file-system-backed storage primitive.

Hierarchy: Workspace -> Project -> Experiment -> Run

Workspace is the bottom of the molab dependency DAG: it knows about
filesystem layout, atomic JSON I/O, content-addressed assets, and
typed system folders — and nothing about workflows. The workflow layer
uses workspace for caching and persistence.
Cross-layer payloads are stored as opaque JSON dicts here; the
upstream layers own the typed shape and own the typed parsing on
read-back.

Each scope exposes:

- ``workspace.fs``         — the disk (local / remote / cached ``FileSystem``)
- ``{folder}.files``       — ``FileStore`` rooted at that folder (user byte-exit)
- ``{scope}.assets``       — ``AssetRepository`` (one id, one content, one ref)

Upstream layers extend the workspace tree by importing the public
``Folder`` base class and mounting their own subclasses via the
generic five-verb CRUD.
"""

from molab.param import GridSpace, Params, ParamSpace, UniformSpace

from .base import atomic_write_json, atomic_write_text
from .context import Context
from .domain import (
    Asset,
    AssetScope,
    ContentRef,
    Execution,
    ExecutionOrigin,
    ExecutionStatus,
    ImportOrigin,
)
from .errors import (
    AmbiguousRefError,
    ExperimentExistsError,
    ExperimentNotFoundError,
    FolderMoveCollisionError,
    ProjectExistsError,
    ProjectNotFoundError,
    RefNotFoundError,
    RunExistsError,
    RunNotFoundError,
    UnmigratedAssetError,
    UnmigratedLayoutError,
)
from .experiment import Experiment
from .file_store import FileStore
from .folder import (
    WORKSPACE_EXPERIMENT_KIND,
    WORKSPACE_PROJECT_KIND,
    WORKSPACE_ROOT_KIND,
    WORKSPACE_RUN_KIND,
    Folder,
)
from .history import AgentRef, EntityRef, GitHistory
from .models import ComputeTarget, WorkflowKind
from .project import Project
from .prune import ExecutionPruneEntry, ExecutionPrunePlan, LivePruneRefusedError
from .refs import InvalidRefError
from .run import RETRYABLE_STATUSES, TERMINAL_STATUSES, Run, RunContext, RunStatus
from .runset import RunRecord, RunSet, RunSetResult
from .target import LocalTarget, RemoteTarget, Target, TargetNotFound
from .targets import LOCAL_TARGET_NAME
from .validate import ValidationReport, Violation
from .workspace import Workspace
from .workspace_context import (
    ContextAsset,
    ContextFocus,
    ExperimentRef,
    HealthFlag,
    ProjectRef,
    RunRef,
    WorkflowRef,
    WorkspaceContext,
    WorkspaceRef,
)
from .wp import WorkspacePaths

__all__ = [
    "LOCAL_TARGET_NAME",
    "RETRYABLE_STATUSES",
    "TERMINAL_STATUSES",
    "WORKSPACE_EXPERIMENT_KIND",
    "WORKSPACE_PROJECT_KIND",
    "WORKSPACE_ROOT_KIND",
    "WORKSPACE_RUN_KIND",
    "AgentRef",
    "AmbiguousRefError",
    "Asset",
    "AssetScope",
    "ComputeTarget",
    "ContentRef",
    "Context",
    "ContextAsset",
    "ContextFocus",
    "EntityRef",
    "Execution",
    "ExecutionOrigin",
    "ExecutionPruneEntry",
    "ExecutionPrunePlan",
    "ExecutionStatus",
    "Experiment",
    "ExperimentExistsError",
    "ExperimentNotFoundError",
    "ExperimentRef",
    "FileStore",
    "Folder",
    "FolderMoveCollisionError",
    "GitHistory",
    "GridSpace",
    "HealthFlag",
    "ImportOrigin",
    "InvalidRefError",
    "LivePruneRefusedError",
    "LocalTarget",
    "ParamSpace",
    "Params",
    "Project",
    "ProjectExistsError",
    "ProjectNotFoundError",
    "ProjectRef",
    "RefNotFoundError",
    "RemoteTarget",
    "Run",
    "RunContext",
    "RunExistsError",
    "RunNotFoundError",
    "RunRecord",
    "RunRef",
    "RunSet",
    "RunSetResult",
    "RunStatus",
    "Target",
    "TargetNotFound",
    "UniformSpace",
    "UnmigratedAssetError",
    "UnmigratedLayoutError",
    "ValidationReport",
    "Violation",
    "WorkflowKind",
    "WorkflowRef",
    "Workspace",
    "WorkspaceContext",
    "WorkspacePaths",
    "WorkspaceRef",
    "atomic_write_json",
    "atomic_write_text",
]
