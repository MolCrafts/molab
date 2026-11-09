import type { ManagedAssetResponse } from "@/api/generated/models/ManagedAssetResponse";
import type { WorkspaceFileNode, WorkspaceFilesResponse } from "@/api/workspace";
import { withRunTitles } from "@/app/runs/runTitle";
import { EXECUTION_STATUSES, isActiveStatus, latestStatus } from "@/app/status/vocabulary";
import type {
  ApiAssetResponse,
  ApiExperimentResponse,
  ApiProjectResponse,
  ApiRunResponse,
  AssetOrigin,
  AssetSummary,
  ExperimentSummary,
  ProjectSummary,
  RunSummary,
  WorkflowSummary,
  WorkspaceSnapshot,
  WorkspaceTreeNode,
} from "@/app/types";
import { parseTaskGraphIr } from "@/plugins/workflow/flowgram-document";
import type { TaskGraphJson } from "@/plugins/workflow/task-graph-ir";

export type { EmbedRole, EmbedTargetKind, EntityCard } from "@/api/knowledge";
export type { RunFilesResponse, RunFileTextResponse } from "@/api/runs";
export { workflowApi } from "@/api/workflow";
export type { WorkspaceFilesResponse } from "@/api/workspace";

export const buildEmptySnapshot = (): WorkspaceSnapshot => {
  return {
    workspaces: [],
    serveScope: null,
    projects: [],
    experiments: [],
    runs: [],
    assets: [],
    workflows: [],
    workspaceRoot: null,
    consoleEntries: [],
  };
};

export const mapProjects = (
  projects: ApiProjectResponse[],
  workspaceKey?: string,
): ProjectSummary[] => {
  return projects.map((project) => ({
    id: project.id,
    name: project.name,
    path: project.path,
    status: "active",
    summary: project.description?.trim() ?? "",
    updatedAt: project.created,
    experimentCount: project.experimentCount ?? null,
    ref: project.ref,
    ...(workspaceKey ? { workspaceKey } : {}),
  }));
};

/** True when ``workflow`` carries inline IR JSON rather than a path/filename. */
const isInlineWorkflowPayload = (value: string): boolean => {
  const trimmed = value.trim();
  return trimmed.startsWith("{") || trimmed.startsWith("[");
};

/**
 * Split API ``experiment.workflow`` into a short display path/name and optional
 * source body. Mock/feature-showcase data often ships the full IR as the
 * ``workflow`` string — never surface that blob as a UI label.
 */
export const splitExperimentWorkflowField = (
  workflow: string | null | undefined,
): { workflowFile: string; workflowSource: string | null } => {
  if (workflow == null || workflow === "") {
    return { workflowFile: "", workflowSource: null };
  }
  if (!isInlineWorkflowPayload(workflow)) {
    return { workflowFile: workflow, workflowSource: workflow };
  }
  let displayName = "";
  try {
    const parsed = JSON.parse(workflow) as { name?: unknown };
    if (typeof parsed.name === "string" && parsed.name.trim()) {
      displayName = parsed.name.trim();
    }
  } catch {
    // keep empty display name
  }
  return { workflowFile: displayName, workflowSource: workflow };
};

export const mapExperiments = (
  projectId: string,
  experiments: ApiExperimentResponse[],
  workspaceKey?: string,
): ExperimentSummary[] => {
  return experiments.map((experiment) => {
    const { workflowFile, workflowSource } = splitExperimentWorkflowField(
      experiment.workflow ?? null,
    );
    return {
      id: experiment.id,
      name: experiment.name,
      path: experiment.path,
      status: "active",
      summary: experiment.description || "",
      workflowFile,
      updatedAt: experiment.created,
      projectId: experiment.projectId || projectId,
      parameterSpace: (experiment.parameterSpace ?? {}) as Record<string, unknown>,
      workflowSource,
      workflowKind: experiment.workflowKind,
      workflowEntrypoint: experiment.workflowEntrypoint ?? null,
      ref: experiment.ref,
      runCount: experiment.runCount ?? null,
      ...(workspaceKey ? { workspaceKey } : {}),
    };
  });
};

/** One label for a workflow: a document name, else a code locator, else empty. */
export const experimentWorkflowLabel = (
  experiment: Pick<ExperimentSummary, "workflowFile" | "workflowEntrypoint">,
): string => experiment.workflowFile || experiment.workflowEntrypoint || "";

export const mapRuns = (
  projectId: string,
  experimentId: string,
  runs: ApiRunResponse[],
  workspaceKey?: string,
): RunSummary[] => {
  // A run reads as its latest attempt (the server's `status_label`): a later
  // failure is not hidden by an earlier success, and no attempt is "pending".
  const mapStatus = (attempts: readonly { status: string }[]): RunSummary["status"] => {
    const key = latestStatus(attempts);
    return (EXECUTION_STATUSES as readonly string[]).includes(key) && key !== "cached"
      ? (key as RunSummary["status"])
      : "pending";
  };

  const mapped = runs.map((run): RunSummary => {
    const executions =
      run.executions ??
      (run.executionHistory ?? []).map((item) => ({
        id: item.executionId,
        runId: run.id,
        mode: "initial",
        status: item.status,
        createdAt: item.startedAt,
        startedAt: item.startedAt,
        finishedAt: item.finishedAt,
        basedOnExecutionId: null,
        executor: item.schedulerJobId ? { scheduler_job_id: item.schedulerJobId } : {},
        environment: {},
        error: null,
      }));
    const status = mapStatus(executions);
    const firstStarted = executions.find((item) => item.startedAt)?.startedAt ?? null;
    const terminalErrors = executions.filter((item) => item.error);
    const lastError = terminalErrors[terminalErrors.length - 1]?.error;
    return {
      id: run.id,
      // What the run is called is its parameters, and where it lives is a path
      // of names — both come from the server, neither is derivable from ids.
      name: run.name,
      path: run.path,
      status,
      summary: run.statusSummary?.notStarted
        ? "Not executed"
        : `${run.statusSummary?.total ?? executions.length} execution${(run.statusSummary?.total ?? executions.length) === 1 ? "" : "s"}`,
      updatedAt: run.finished ?? run.created,
      projectId: run.projectId || projectId,
      experimentId: run.experimentId || experimentId,
      definitionHash: run.definitionHash ?? "",
      experimentRevisionId: run.experimentRevisionId ?? "",
      inputs: run.inputs ?? [],
      statusSummary: run.statusSummary ?? {
        total: executions.length,
        active: executions.filter((item) => isActiveStatus(item.status)).length,
        notStarted: executions.length === 0,
        byStatus: Object.fromEntries(
          [...new Set(executions.map((item) => item.status))].map((value) => [
            value,
            executions.filter((item) => item.status === value).length,
          ]),
        ),
      },
      parameters: (run.parameters ?? {}) as Record<string, unknown>,
      workflowSource: run.workflowSource ?? run.workflow?.source ?? null,
      workflowSnapshot: run.workflow ?? null,
      startedAt: firstStarted,
      finishedAt: run.finished ?? null,
      executionHistory: executions.map((rec) => ({
        executionId: rec.id,
        mode: rec.mode,
        createdAt: rec.createdAt,
        startedAt: rec.startedAt ?? null,
        finishedAt: rec.finishedAt ?? null,
        status: rec.status,
        basedOnExecutionId: rec.basedOnExecutionId ?? null,
        executor: rec.executor ?? {},
        environment: rec.environment ?? {},
        error: rec.error ?? null,
      })),
      errorMessage:
        lastError && typeof lastError.message === "string"
          ? lastError.message
          : (run.error?.message ?? null),
      ...(run.ref ? { ref: run.ref } : {}),
      ...(workspaceKey ? { workspaceKey } : {}),
    };
  });
  return withRunTitles(mapped);
};

const assetSize = (asset: ApiAssetResponse): number | null => {
  const extraSize = (asset.extra as Record<string, unknown> | undefined)?.size;
  return typeof extraSize === "number" ? extraSize : null;
};

const assetSummary = (asset: ApiAssetResponse): string => {
  const scope = asset.scopeKind ? `${asset.scopeKind} scope` : "unscoped";
  return `${asset.kind} · ${scope}`;
};

const extraString = (extra: Record<string, unknown> | undefined, key: string): string | null => {
  const value = extra?.[key];
  return typeof value === "string" && value ? value : null;
};

/** The origin `projectAssetView` folds into `extra` (absent: not recorded). */
const originFromExtra = (extra: Record<string, unknown> | undefined): AssetOrigin | undefined => {
  const kind = extraString(extra, "originKind");
  if (!kind) return undefined;
  return {
    kind,
    runId: extraString(extra, "runId"),
    executionId: extraString(extra, "executionId"),
    task: extraString(extra, "task"),
    uri: extraString(extra, "uri"),
  };
};

export const mapAssets = (
  assets: (ApiAssetResponse | ManagedAssetResponse)[],
  projectId?: string,
): AssetSummary[] => {
  return assets.map((asset) => {
    if (!("scopeIds" in asset)) {
      return {
        id: asset.id,
        name: asset.title,
        kind: "asset",
        status: "active",
        summary: asset.originKind,
        updatedAt: asset.createdAt,
        sizeBytes: asset.size,
        scopeKind: "project",
        projectId: asset.projectId || projectId,
        ref: asset.ref,
        file: asset.file || undefined,
        mediaType: asset.mediaType ?? null,
        origin: {
          kind: asset.originKind,
          runId: asset.runId ?? null,
          executionId: asset.executionId ?? null,
          task: asset.task ?? null,
          uri: asset.uri ?? null,
        },
      };
    }
    // ``scopeIds`` is the parent chain ending at the leaf scope: a run-scoped
    // asset is ``[projectId, experimentId, runId]``, an experiment-scoped one
    // ``[projectId, experimentId]``, etc. This drives the Assets nav grouping.
    const ids = asset.scopeIds ?? [];
    return {
      id: asset.id,
      name: asset.name,
      kind: asset.kind,
      status: "active",
      summary: assetSummary(asset),
      updatedAt: asset.updatedAt,
      sizeBytes: assetSize(asset),
      scopeKind: asset.scopeKind,
      projectId: ids[0] ?? projectId,
      experimentId: ids[1],
      runId: ids[2],
      ref: asset.ref ?? undefined,
      file: asset.path || undefined,
      mediaType: extraString(asset.extra, "mediaType"),
      origin: originFromExtra(asset.extra),
    };
  });
};

export const mapWorkflows = (
  experiments: ExperimentSummary[],
  rawExperiments: ApiExperimentResponse[],
): WorkflowSummary[] => {
  const experimentById = new Map(rawExperiments.map((experiment) => [experiment.id, experiment]));
  return experiments.map((experiment) => {
    const raw = experimentById.get(experiment.id);
    const source = raw?.workflow ?? null;
    const graph: TaskGraphJson | undefined = parseTaskGraphIr(source) ?? undefined;
    return {
      id: `workflow:${experiment.id}`,
      name: `${experiment.name} workflow`,
      status: "active",
      summary: graph
        ? `${graph.task_configs.length} tasks · ${graph.links.length} dependencies`
        : (source ?? "workflow"),
      updatedAt: experiment.updatedAt,
      projectId: experiment.projectId,
      experimentId: experiment.id,
      graph,
    };
  });
};

const mapWorkspaceNode = (node: WorkspaceFileNode): WorkspaceTreeNode => {
  const isFile = node.type === "file";
  const updatedAt =
    typeof node.modified === "number"
      ? new Date(node.modified * 1000).toISOString()
      : (node.modified ?? "");
  return {
    id: node.id ?? node.path,
    name: node.name,
    path: node.path,
    kind: isFile ? "file" : "directory",
    children: (node.children ?? []).map(mapWorkspaceNode),
    sizeBytes: node.size ?? 0,
    updatedAt,
    assetId: node.assetId ?? undefined,
    hasPreviewSidecar: node.hasPreviewSidecar ?? undefined,
  };
};

export const mapWorkspaceTree = (
  rootPath: string,
  response: WorkspaceFilesResponse,
): WorkspaceTreeNode => {
  return {
    id: "workspace-root",
    name: response.path ?? rootPath,
    path: response.path ?? rootPath,
    kind: "directory",
    children: (response.children ?? []).map(mapWorkspaceNode),
    sizeBytes: 0,
    updatedAt: "",
  };
};
