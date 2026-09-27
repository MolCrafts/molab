"""Workspace module — file-system-backed storage primitive.

Hierarchy: Workspace -> Project -> Experiment -> Run

Workspace is the bottom of the molab dependency DAG: it knows about
filesystem layout, atomic JSON I/O, content-addressed assets, and
typed system folders — and nothing about workflows. The workflow layer
uses workspace for caching and persistence.
Cross-layer payloads are stored as opaque JSON dicts here; the
upstream layers own the typed shape and own the typed parsing on
read-back.

Notes + literature are owned by ``molab.knowledge`` (``Note`` /
``Literature`` + its typed ``ReferenceMeta``) — directories whose path is
their identity — and are **not** re-exported here: import them from
``molab.knowledge``. The read-only Zotero importer (``ZoteroItem`` /
``read_zotero_items``) lives there too.

Each scope exposes:

- ``workspace.fs``         — the disk (local / remote / cached ``FileSystem``)
- ``{folder}.files``       — ``FileStore`` rooted at that folder (user byte-exit)
- ``{scope}.assets``       — read-only asset view (typed Asset queries over the manifests)
- ``{scope}.data_assets``  — ``DataAssetLibrary`` for importing user inputs

Upstream layers extend the workspace tree by importing the public
``Folder`` base class and mounting their own subclasses via the
generic five-verb CRUD.
"""

from .assets import (
    ArtifactAsset,
    Asset,
    AssetManifest,
    AssetScope,
    AssetsView,
    CheckpointAsset,
    DataAsset,
    DataAssetLibrary,
    ErrorTraceAsset,
    LogAsset,
    Producer,
)
from .base import atomic_write_json, atomic_write_text
from .context import Context

# ``Asset`` is the manifest-family name imported above; the Project *data*
# identity of the same spelling is ``molab.workspace.domain.Asset``. Both
# ``Asset`` and ``AssetVersion`` are advertised in ``__all__``, so both are
# bound here — an ``__all__`` entry that does not resolve breaks ``import *``.
from .domain import Artifact, AssetVersion, ContentRef, Execution, ExecutionStatus
from .errors import (
    ExperimentExistsError,
    ExperimentNotFoundError,
    FolderMoveCollisionError,
    ProjectExistsError,
    ProjectNotFoundError,
    RunExistsError,
    RunNotFoundError,
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
from .models import (
    ComputeTarget,
    ErrorInfo,
    ExperimentMetadata,
    FolderMetadata,
    ProjectMetadata,
    RunMetadata,
    WorkspaceMetadata,
)
from .param import GridSpace, Params, ParamSpace, UniformSpace  # Params is the sweep-cell model
from .project import Project
from .prune import ExecutionPruneEntry, ExecutionPrunePlan, LivePruneRefusedError
from .run import RETRYABLE_STATUSES, TERMINAL_STATUSES, Run, RunContext, RunStatus
from .runset import RunRecord, RunSet, RunSetResult
from .target import LocalTarget, RemoteTarget, SessionManager, SSHSession, Target, TargetNotFound
from .targets import LOCAL_TARGET_NAME
from .validate import ValidationReport, Violation
from .workspace import Workspace
from .workspace_context import (
    ArtifactRef,
    ContextFocus,
    ExperimentRef,
    HealthFlag,
    KnowledgeRef,
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
    "Artifact",
    "ArtifactAsset",
    "ArtifactRef",
    "Asset",
    "AssetManifest",
    "AssetScope",
    "AssetVersion",
    "AssetsView",
    "CheckpointAsset",
    "ComputeTarget",
    "ContentRef",
    "Context",
    "ContextFocus",
    "DataAsset",
    "DataAssetLibrary",
    "EntityRef",
    "ErrorInfo",
    "ErrorTraceAsset",
    "Execution",
    "ExecutionPruneEntry",
    "ExecutionPrunePlan",
    "ExecutionStatus",
    "Experiment",
    "ExperimentExistsError",
    "ExperimentMetadata",
    "ExperimentNotFoundError",
    "ExperimentRef",
    "FileStore",
    "Folder",
    "FolderMetadata",
    "FolderMoveCollisionError",
    "GitHistory",
    "GridSpace",
    "HealthFlag",
    "KnowledgeRef",
    "LivePruneRefusedError",
    "LocalTarget",
    "LogAsset",
    "ParamSpace",
    "Params",
    "Producer",
    "Project",
    "ProjectExistsError",
    "ProjectMetadata",
    "ProjectNotFoundError",
    "ProjectRef",
    "RemoteTarget",
    "Run",
    "RunContext",
    "RunExistsError",
    "RunMetadata",
    "RunNotFoundError",
    "RunRecord",
    "RunRef",
    "RunSet",
    "RunSetResult",
    "RunStatus",
    "SSHSession",
    "SessionManager",
    "Target",
    "TargetNotFound",
    "UniformSpace",
    "ValidationReport",
    "Violation",
    "WorkflowRef",
    "Workspace",
    "WorkspaceContext",
    "WorkspaceMetadata",
    "WorkspacePaths",
    "WorkspaceRef",
    "atomic_write_json",
    "atomic_write_text",
]
