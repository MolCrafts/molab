import type { ManagedAssetResponse } from "@/api/generated/models/ManagedAssetResponse";
import type { WorkspaceFileNode, WorkspaceFilesResponse } from "@/api/workspace";
import type {
  ApiAssetResponse,
  ApiExperimentResponse,
  ApiProjectResponse,
  ApiRunResponse,
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
export type {
  TensorboardScalarSeries,
  TensorboardScalarsResponse,
} from "@/api/tensorboard";
export { TensorboardScalarsError } from "@/api/tensorboard";
export { workflowApi } from "@/api/workflow";
export type { WorkspaceFilesResponse } from "@/api/workspace";

export const buildEmptySnapshot = (): WorkspaceSnapshot => {
  return {
    workspaces: [],
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
    summary: project.description || "No description",
    updatedAt: project.created,
    experimentCount: project.experimentCount ?? null,
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
      projectId,
      parameterSpace: (experiment.parameterSpace ?? {}) as Record<string, unknown>,
      workflowSource,
      runCount: experiment.runCount ?? null,
      ...(workspaceKey ? { workspaceKey } : {}),
    };
  });
};

export const mapRuns = (
  projectId: string,
  experimentId: string,
  runs: ApiRunResponse[],
  workspaceKey?: string,
): RunSummary[] => {
  const mapStatus = (run: ApiRunResponse): RunSummary["status"] => {
    if (!run.statusSummary) {
      const legacy = run.status ?? "pending";
      return legacy === "running" ||
        legacy === "succeeded" ||
        legacy === "failed" ||
        legacy === "cancelled"
        ? legacy
        : "pending";
    }
    const counts = run.statusSummary.byStatus ?? {};
    if (run.statusSummary.active > 0) return "running";
    if ((counts.succeeded ?? 0) > 0) return "succeeded";
    if ((counts.failed ?? 0) > 0 || (counts.interrupted ?? 0) > 0) return "failed";
    if ((counts.cancelled ?? 0) > 0) return "cancelled";
    return "pending";
  };

  return runs.map((run) => {
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
        checkpointArtifactId: null,
        executor: item.schedulerJobId ? { scheduler_job_id: item.schedulerJobId } : {},
        environment: {},
        artifactIds: [],
        error: null,
      }));
    const status = mapStatus(run);
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
      projectId,
      experimentId,
      definitionHash: run.definitionHash ?? "",
      experimentRevisionId: run.experimentRevisionId ?? "",
      statusSummary: run.statusSummary ?? {
        total: executions.length,
        active: executions.filter((item) =>
          ["queued", "running", "finalizing"].includes(item.status),
        ).length,
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
        checkpointArtifactId: rec.checkpointArtifactId ?? null,
        executor: rec.executor ?? {},
        environment: rec.environment ?? {},
        artifactIds: rec.artifactIds ?? [],
        error: rec.error ?? null,
      })),
      errorMessage:
        lastError && typeof lastError.message === "string"
          ? lastError.message
          : (run.error?.message ?? null),
      ...(workspaceKey ? { workspaceKey } : {}),
    };
  });
};

const assetSize = (asset: ApiAssetResponse): number | null => {
  const extraSize = (asset.extra as Record<string, unknown> | undefined)?.size;
  return typeof extraSize === "number" ? extraSize : null;
};

const assetSummary = (asset: ApiAssetResponse): string => {
  const scope = asset.scopeKind ? `${asset.scopeKind} scope` : "unscoped";
  return `${asset.kind} · ${scope}`;
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
        summary: `${asset.versionCount ?? 0} version${asset.versionCount === 1 ? "" : "s"}`,
        updatedAt: asset.createdAt,
        sizeBytes: null,
        scopeKind: "project",
        projectId: asset.projectId || projectId,
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
