import type { TaskGraphJson } from "@/plugins/workflow/task-graph-ir";

/** Activity-bar / left-panel id. Core and plugins register these as view ids. */
export type LeftPanelView = string;

export type SemanticObjectType =
  | "project"
  | "experiment"
  | "run"
  | "asset"
  | "workflow"
  | "workspace-file"
  | "task"
  | "knowledge";

export type BaseObjectType = "project" | "experiment" | "run" | "asset";

export type PanelKind = "editor" | "viewer" | "inspector";

export type FileKind = "yaml" | "json" | "python" | "markdown" | "text" | "image" | "unknown";

export type ContentType = "workflow-graph" | "metadata" | "log" | "text" | "metrics" | "image";

export type JsonValue = string | number | boolean | null | JsonObject | JsonValue[];

export interface JsonObject {
  [key: string]: JsonValue;
}

export type SemanticStatus =
  | "active"
  | "archived"
  | "draft"
  | "pending"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled"
  | "skipped"
  | "waiting_for_review"
  | "approved"
  | "rejected"
  | "expired";

import type { ExperimentCreateRequest } from "../api/generated/models/ExperimentCreateRequest";
import type { ProjectCreateRequest } from "../api/generated/models/ProjectCreateRequest";
import type { RunCreateRequest } from "../api/generated/models/RunCreateRequest";

export type { ExperimentCreateRequest, ProjectCreateRequest, RunCreateRequest };

import type { ExecutionOutputsResponse } from "../api/generated/models/ExecutionOutputsResponse";
import type { ExperimentResponse } from "../api/generated/models/ExperimentResponse";
import type { ProjectResponse } from "../api/generated/models/ProjectResponse";
import type { RunResponse } from "../api/generated/models/RunResponse";
import type { RunStatusSummaryResponse } from "../api/generated/models/RunStatusSummaryResponse";
import type { RunSummary as ApiRunSummaryModel } from "../api/generated/models/RunSummary";
import type { WorkflowSnapshotResponse } from "../api/generated/models/WorkflowSnapshotResponse";

// Re-export as Api*Response for compatibility
export type ApiProjectResponse = ProjectResponse;
export type ApiExperimentResponse = ExperimentResponse;
// ``name`` and ``path`` are as required as ``id``: only the server knows what a
// run is called and where it lives, and there is no id-shaped substitute for
// either — a fallback would put a UUID in front of the user.
export type ApiRunResponse = Pick<
  RunResponse,
  "id" | "name" | "path" | "projectId" | "experimentId" | "created"
> &
  Partial<Omit<RunResponse, "error">> & {
    /** Mock-only v1 fields; production mapping never treats them as truth. */
    status?: string;
    results?: Record<string, unknown>;
    profile?: string | null;
    configHash?: string | null;
    executorInfo?: Record<string, unknown>;
    executionHistory?: Array<{
      executionId: string;
      startedAt: string;
      finishedAt?: string | null;
      status: string;
      schedulerJobId?: string | null;
    }>;
    error?: ({ message?: string } & Record<string, unknown>) | null;
  };
/** Transitional UI projection for Project Assets. Artifacts use their own type. */
export interface ApiAssetResponse {
  id: string;
  projectId: string;
  title: string;
  createdAt: string;
  versionCount?: number;
  name: string;
  kind: string;
  path: string;
  updatedAt: string;
  scopeKind: string;
  scopeIds: string[];
  extra?: Record<string, unknown>;
  tags?: Record<string, string>;
  hasPreviewSidecar?: boolean;
  /** Legacy mock-only metadata; production Project Assets use versions. */
  producer?: Record<string, unknown> | null;
  /** Legacy mock-only content field. */
  contentHash?: string | null;
}
export type ApiWorkflowSnapshot = WorkflowSnapshotResponse;
export type ApiRunSummary = ApiRunSummaryModel;

/**
 * Known asset kinds emitted by the unified catalog. The list is open — the
 * backend may add new kinds — but these are the ones the UI renders with
 * dedicated logic.
 */
export type AssetKind =
  | "data"
  | "artifact"
  | "log"
  | "checkpoint"
  | "error_trace"
  | "execution_state"
  | "output";

export interface ProjectSummary {
  id: string;
  name: string;
  /** Workspace-relative directory, as the server reported it — never composed. */
  path: string;
  status: SemanticStatus;
  summary: string;
  updatedAt: string;
  /**
   * Stable key of the served workspace this project belongs to. Undefined in
   * the single-workspace case (the flat `/api/projects` path), set when the
   * project list is aggregated across several served workspaces.
   */
  workspaceKey?: string;
  /** Server-reported count when list is shallow (experiments not loaded yet). */
  experimentCount?: number | null;
  /** Server-composed molab reference. */
  ref?: string;
}

export interface ExperimentSummary {
  id: string;
  name: string;
  /** Workspace-relative directory, as the server reported it — never composed. */
  path: string;
  status: SemanticStatus;
  summary: string;
  workflowFile: string;
  updatedAt: string;
  projectId: string;
  parameterSpace: Record<string, unknown>;
  workflowSource: string | null;
  /** Server-reported count when list is shallow (runs not loaded yet). */
  runCount?: number | null;
  /** Served-workspace key, stamped at expand time. */
  workspaceKey?: string;
  workflowKind?: "code" | "document" | null;
  /** Code-workflow locator. Never fetched; absent on document experiments. */
  workflowEntrypoint?: string | null;
  /** Server-composed molab reference. */
  ref?: string;
}

export interface ExecutionRecordSummary {
  executionId: string;
  mode: string;
  createdAt: string;
  startedAt: string | null;
  finishedAt: string | null;
  status: string;
  basedOnExecutionId: string | null;
  checkpointArtifactId: string | null;
  executor: Record<string, unknown>;
  environment: Record<string, unknown>;
  artifactIds: string[];
  error: Record<string, unknown> | null;
}

export interface RunSummary {
  id: string;
  name: string;
  /** Workspace-relative directory, as the server reported it — never composed. */
  path: string;
  status: SemanticStatus;
  summary: string;
  updatedAt: string;
  projectId: string;
  experimentId: string;
  definitionHash: string;
  experimentRevisionId: string;
  statusSummary: RunStatusSummaryResponse;
  parameters: Record<string, unknown>;
  workflowSource: string | null;
  workflowSnapshot: WorkflowSnapshotResponse | null;
  startedAt: string | null;
  finishedAt: string | null;
  executionHistory: ExecutionRecordSummary[];
  errorMessage: string | null;
  /** Canonical run reference from the server. Absent on a fixture that predates it. */
  ref?: string;
  /** Served-workspace key, stamped at expand time. */
  workspaceKey?: string;
}

export interface AssetSummary {
  id: string;
  name: string;
  kind: AssetKind | string;
  status: SemanticStatus;
  summary: string;
  updatedAt: string;
  sizeBytes: number | null;
  /** Scope owner chain, derived from the asset's `scope_ids`. Drives the
   *  Project → Experiment → Run grouping in the Assets nav. */
  projectId?: string;
  experimentId?: string;
  runId?: string;
  /** Scope leaf kind: `workspace` / `project` / `experiment` / `run`. */
  scopeKind?: string;
}

export interface WorkflowSummary {
  id: string;
  name: string;
  status: SemanticStatus;
  summary: string;
  updatedAt: string;
  projectId: string;
  experimentId: string;
  /** The workflow's task-graph IR (the sole client IR type), when available. */
  graph?: TaskGraphJson;
}

export interface WorkspaceTreeNode {
  id: string;
  name: string;
  path: string;
  kind: "file" | "directory";
  children: WorkspaceTreeNode[];
  sizeBytes: number;
  updatedAt: string;
  // Populated when the file tree is fetched with `?include=catalog`: the
  // registered asset id and the server's existence-only sidecar flag.
  assetId?: string;
  hasPreviewSidecar?: boolean;
  /**
   * Directory children were fetched via WorkspaceFs.listdir.
   * ``false`` ⇒ UI should re-listdir on expand (shallow / remote trees).
   * Files are always treated as loaded.
   */
  childrenLoaded?: boolean;
}

export interface ConsoleEntry {
  id: string;
  level: "info" | "warning" | "error";
  message: string;
  timestamp: string;
}

/** One workspace `molab serve` is hosting (mirrors GET /api/workspaces). */
export interface ServedWorkspaceSummary {
  key: string;
  label: string;
  isRemote: boolean;
  path: string | null;
  /** True for the workspace whose deep tree (experiments/runs) is loaded. */
  active: boolean;
  unreachable: boolean;
  /**
   * Remote host needs a verification code (2FA/OTP). When true the shell
   * shows the connect dialog so the user can enter the code in-browser.
   */
  needsAuth?: boolean;
}

export interface WorkspaceSnapshot {
  /**
   * The set of served workspaces (empty or single in the unchanged
   * single-workspace case). When length > 1 the left nav groups projects under
   * a per-workspace header.
   */
  workspaces: ServedWorkspaceSummary[];
  projects: ProjectSummary[];
  experiments: ExperimentSummary[];
  runs: RunSummary[];
  assets: AssetSummary[];
  workflows: WorkflowSummary[];
  workspaceRoot: WorkspaceTreeNode | null;
  consoleEntries: ConsoleEntry[];
}

export type CoreObjectView = "overview" | "executions" | "logs" | "metrics" | "scheduler";
/** Core views plus stable tab values contributed by independently loaded plugins. */
export type ObjectView = CoreObjectView | (string & {});

export type ExperimentView = "overview" | "workflow" | "runs";
export type ProjectView = "overview" | "experiments" | "assets" | "settings";

export interface ObjectSelection {
  objectType: BaseObjectType;
  objectId: string;
  objectView?: ObjectView;
  /** Route-backed view within an experiment. Only meaningful for experiment selections. */
  experimentView?: ExperimentView;
  /** Route-backed view within a project. Only meaningful for project selections. */
  projectView?: ProjectView;
}

export interface WorkflowSelection {
  objectType: "workflow";
  workflowId: string;
  objectId: string;
}

export interface WorkspaceFileSelection {
  objectType: "workspace-file";
  filePath: string;
  fileKind: FileKind;
  objectId: string;
  assetId?: string;
  hasPreviewSidecar?: boolean;
}

export interface TaskSelection {
  objectType: "task";
  taskId: string; // workflow-graph node id
  runId: string; // owning run — used to resolve the task's produced assets
  objectId: string; // === taskId, for RendererProps compatibility
}

export interface KnowledgeSelection {
  objectType: "knowledge";
  objectId: string; // the concept's bundle-relative path, or "" for the browse overview
}

export type Selection =
  | ObjectSelection
  | WorkflowSelection
  | WorkspaceFileSelection
  | TaskSelection
  | KnowledgeSelection;

export type InspectorTarget =
  | {
      kind: "object";
      objectType: SemanticObjectType;
      objectId: string;
    }
  | {
      kind: "workflow-node";
      workflowId: string;
      nodeId: string;
    };

export interface RendererKey {
  objectType: SemanticObjectType;
  fileKind: FileKind;
  contentType: ContentType;
  panelKind: PanelKind;
}

/**
 * Entity catalog available to renderer contributions. Filesystem trees,
 * console history, and other shell-owned state deliberately stay outside the
 * renderer contract.
 */
export type RendererSnapshot = Pick<
  WorkspaceSnapshot,
  "projects" | "experiments" | "runs" | "assets" | "workflows" | "workspaces"
>;

export interface RendererProps {
  selection: Selection;
  snapshot: RendererSnapshot;
  inspectorTarget: InspectorTarget;

  onInspectorTargetChange: (target: InspectorTarget) => void;
  onRefresh: () => void;
  /** Explicit physical attempt selected by the host. Never inferred as "latest". */
  executionId?: string | null;
  /** Host-fetched output inventory for that execution. */
  executionOutputs?: ExecutionOutputsResponse | null;
  /**
   * The attempt's workspace-relative directory, as the server reported it.
   *
   * File paths a renderer receives are relative to *this*, not to the run —
   * anything resolving them against the run root misses the
   * ``executions/<id>/`` segment and reads a directory that is not there.
   */
  executionDir?: string | null;
}

/** Compile-time field scope for feature renderers with smaller catalog needs. */
export type ScopedRendererProps<K extends keyof RendererSnapshot> = Omit<
  RendererProps,
  "snapshot"
> & {
  snapshot: Pick<RendererSnapshot, K>;
};

export interface BreadcrumbItem {
  label: string;
  to?: string;
}
