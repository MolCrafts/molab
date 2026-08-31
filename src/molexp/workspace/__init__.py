"""Workspace module — file-system-backed storage primitive.

Hierarchy: Workspace -> Project -> Experiment -> Run

Workspace is the bottom of the molexp dependency DAG: it knows about
filesystem layout, atomic JSON I/O, content-addressed assets, and
typed system folders — and nothing about workflows, sessions, agents,
or LLMs. The workflow layer uses workspace for caching and
persistence; the agent layer uses workspace for session storage.
Cross-layer payloads are stored as opaque JSON dicts here; the
upstream layers own the typed shape and own the typed parsing on
read-back.

Notes + literature are owned by the OKF Concepts (``Note`` /
``ReferenceConcept`` + its typed ``ReferenceMeta``), reached via the
``Bundle`` façade / ``concept_from_dir`` — directories whose path is
their identity. ``ZoteroItem`` / ``read_zotero_items`` are the
read-only Zotero importer that produces ``ReferenceConcept`` records
(PDFs pointed at, never copied).

Each scope exposes:

- ``workspace.fs``         — the disk (local / remote / cached ``FileSystem``)
- ``{folder}.files``       — ``FileStore`` rooted at that folder (user byte-exit)
- ``{scope}.assets``       — read-only asset view (typed Asset queries over the manifests)
- ``{scope}.data_assets``  — ``DataAssetLibrary`` for importing user inputs
- ``workspace.cache``      — opt-in ``CacheFolder`` (``as_cache_store()``); execute writes ``run_dir/cache`` instead

Upstream layers extend the workspace tree by importing the public
``Folder`` base class and mounting their own subclasses via the
generic five-verb CRUD — see ``molexp.agent.folders`` for the
``Agent`` / ``AgentSession`` pair.
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
from .bundle import Backlink, Bundle
from .bundle_index import BundleIndex, ConceptIndexEntry, SearchHit, SearchResult
from .cache import WORKSPACE_CACHE_KIND, CacheFolder
from .concepts import Note, ReferenceConcept
from .context import Context
from .doc_embed import EntitySummary, summarize_entity
from .edges import DEFAULT_EDGE_ROLE, Edge, EdgeRole
from .errors import (
    ConceptNotFoundError,
    ExperimentExistsError,
    ExperimentNotFoundError,
    FolderMoveCollisionError,
    KnowledgeExistsError,
    KnowledgeNotFoundError,
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
from .harvest import harvest_run
from .knowledge import (
    PLAN_BOOK_NAME,
    Assumption,
    Constraint,
    Decision,
    FailureAnalysis,
    Finding,
    Knowledge,
    KnowledgeMetadata,
    Observation,
    OpenQuestion,
    ParameterRationale,
    Plan,
    ProtocolNote,
    SourceKind,
    SourceRef,
    parse_knowledge_class,
)
from .knowledge_write import write_knowledge
from .lifecycle_ops import cancel_run
from .models import (
    ComputeTarget,
    ErrorInfo,
    ExecutionRecord,
    ExperimentMetadata,
    FolderMetadata,
    ProjectMetadata,
    RunMetadata,
    WorkspaceMetadata,
)
from .note_meta import NoteMeta
from .param import GridSpace, Params, ParamSpace, UniformSpace  # Params is the sweep-cell model
from .project import Project
from .prune import (
    ExecutionPruneEntry,
    ExecutionPrunePlan,
    LivePruneRefusedError,
    apply_execution_prune,
    plan_execution_prune,
)
from .reference_meta import ReferenceMeta
from .run import RETRYABLE_STATUSES, TERMINAL_STATUSES, Run, RunContext, RunStatus
from .run_reaper import pid_alive, reap_zombie_run
from .runset import RunRecord, RunSet, RunSetResult
from .target import (
    LocalTarget,
    RemoteTarget,
    SessionManager,
    SSHSession,
    Target,
    TargetNotFound,
    parse_target,
    resolve_target,
    target_to_transport,
)
from .targets import (
    LOCAL_TARGET_NAME,
    add_target,
    builtin_local_target,
    effective_targets,
    get_target,
    has_target,
    list_targets,
    remove_target,
    resolve_compute_target,
    target_run_dir,
    to_transport,
)
from .validate import ValidationReport, Violation, validate_workspace
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
    assemble_workspace_context,
)
from .wp import WorkspacePaths, cp, ls, mkdir, mv, rm
from .zotero_concepts import ZoteroItem, read_zotero_items

__all__ = [
    "DEFAULT_EDGE_ROLE",
    "LOCAL_TARGET_NAME",
    "PLAN_BOOK_NAME",
    "RETRYABLE_STATUSES",
    "TERMINAL_STATUSES",
    "WORKSPACE_CACHE_KIND",
    "WORKSPACE_EXPERIMENT_KIND",
    "WORKSPACE_PROJECT_KIND",
    "WORKSPACE_ROOT_KIND",
    "WORKSPACE_RUN_KIND",
    "ArtifactAsset",
    "ArtifactRef",
    "Asset",
    "AssetManifest",
    "AssetScope",
    "AssetsView",
    "Assumption",
    "Backlink",
    "Bundle",
    "BundleIndex",
    "CacheFolder",
    "CheckpointAsset",
    "ComputeTarget",
    "ConceptIndexEntry",
    "ConceptNotFoundError",
    "Constraint",
    "Context",
    "ContextFocus",
    "DataAsset",
    "DataAssetLibrary",
    "Decision",
    "Edge",
    "EdgeRole",
    "EntitySummary",
    "ErrorInfo",
    "ErrorTraceAsset",
    "ExecutionPruneEntry",
    "ExecutionPrunePlan",
    "ExecutionRecord",
    "Experiment",
    "ExperimentExistsError",
    "ExperimentMetadata",
    "ExperimentNotFoundError",
    "ExperimentRef",
    "FailureAnalysis",
    "FileStore",
    "Finding",
    "Folder",
    "FolderMetadata",
    "FolderMoveCollisionError",
    "GridSpace",
    "HealthFlag",
    "Knowledge",
    "KnowledgeExistsError",
    "KnowledgeMetadata",
    "KnowledgeNotFoundError",
    "KnowledgeRef",
    "LivePruneRefusedError",
    "LocalTarget",
    "LogAsset",
    "Note",
    "NoteMeta",
    "Observation",
    "OpenQuestion",
    "ParamSpace",
    "ParameterRationale",
    "Params",
    "Plan",
    "Producer",
    "Project",
    "ProjectExistsError",
    "ProjectMetadata",
    "ProjectNotFoundError",
    "ProjectRef",
    "ProtocolNote",
    "ReferenceConcept",
    "ReferenceMeta",
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
    "SearchHit",
    "SearchResult",
    "SessionManager",
    "SourceKind",
    "SourceRef",
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
    "ZoteroItem",
    "add_target",
    "apply_execution_prune",
    "assemble_workspace_context",
    "atomic_write_json",
    "atomic_write_text",
    "builtin_local_target",
    "cancel_run",
    "cp",
    "effective_targets",
    "get_target",
    "harvest_run",
    "has_target",
    "list_targets",
    "ls",
    "mkdir",
    "mv",
    "parse_knowledge_class",
    "parse_target",
    "pid_alive",
    "plan_execution_prune",
    "read_zotero_items",
    "reap_zombie_run",
    "remove_target",
    "resolve_compute_target",
    "resolve_target",
    "rm",
    "summarize_entity",
    "target_run_dir",
    "target_to_transport",
    "to_transport",
    "validate_workspace",
    "write_knowledge",
]
