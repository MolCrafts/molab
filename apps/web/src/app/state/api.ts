import type { WorkspaceFileNode, WorkspaceFilesResponse } from "@/api/workspace";
import type { ManagedAssetResponse } from "@/api/generated/models/ManagedAssetResponse";
import { AgentUnavailableError, probeOnce, resetAgentProbes } from "@/app/state/agentProbe";
import type {
  AgentSessionSummary,
  ApiAgentSession,
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
export type {
  LammpsLogResponse,
  LammpsThermoStage,
  MetricRecord,
  RunFilesResponse,
  RunFileTextResponse,
  RunMetricsQuery,
  RunMetricsResponse,
} from "@/api/runs";
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
    agentSessions: [],
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
): ExperimentSummary[] => {
  return experiments.map((experiment) => {
    const { workflowFile, workflowSource } = splitExperimentWorkflowField(
      experiment.workflow ?? null,
    );
    return {
      id: experiment.id,
      name: experiment.name,
      status: "active",
      summary: experiment.description || "",
      workflowFile,
      updatedAt: experiment.created,
      projectId,
      parameterSpace: (experiment.parameterSpace ?? {}) as Record<string, unknown>,
      workflowSource,
      planRunId: experiment.planRunId ?? null,
      runCount: experiment.runCount ?? null,
    };
  });
};

export const mapRuns = (
  projectId: string,
  experimentId: string,
  runs: ApiRunResponse[],
): RunSummary[] => {
  const mapStatus = (run: ApiRunResponse): RunSummary["status"] => {
    if (!run.statusSummary) {
      const legacy = run.status ?? "pending";
      return legacy === "running" || legacy === "succeeded" || legacy === "failed" || legacy === "cancelled"
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
      name: run.id,
      status,
      summary: run.statusSummary?.notStarted
        ? "Not executed"
        : `${run.statusSummary?.total ?? executions.length} execution${(run.statusSummary?.total ?? executions.length) === 1 ? "" : "s"}`,
      updatedAt: run.finished ?? run.created,
      projectId,
      experimentId,
      definitionHash: run.definitionHash ?? "",
      experimentRevisionId: run.experimentRevisionId ?? "",
      statusSummary:
        run.statusSummary ??
        ({
          total: executions.length,
          active: executions.filter((item) => ["queued", "running", "finalizing"].includes(item.status)).length,
          notStarted: executions.length === 0,
          byStatus: Object.fromEntries(
            [...new Set(executions.map((item) => item.status))].map((value) => [
              value,
              executions.filter((item) => item.status === value).length,
            ]),
          ),
        }),
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

export const mapAgentSessions = (sessions: ApiAgentSession[]): AgentSessionSummary[] => {
  return sessions.map((s) => ({
    id: s.taskId ?? s.sessionId,
    sessionId: s.sessionId,
    title: s.title ?? "",
    goal: s.goal,
    status: s.status as AgentSessionSummary["status"],
    createdAt: s.createdAt,
    eventCount: s.events?.length ?? 0,
  }));
};

export interface ApiAgentHealth {
  ready: boolean;
  provider: string;
  model: string;
  source: "stored" | "env" | "none";
  reason: string;
  envVar: string;
}

/**
 * Thrown by createSession when the backend rejects with code
 * "agent_not_configured" (HTTP 400). Carries the structured fields so
 * the UI can route the user to the Provider settings tab.
 */
export class AgentNotConfiguredError extends Error {
  readonly code = "agent_not_configured";
  readonly provider: string;
  readonly model: string;
  readonly envVar: string;

  constructor(message: string, provider: string, model: string, envVar: string) {
    super(message);
    this.name = "AgentNotConfiguredError";
    this.provider = provider;
    this.model = model;
    this.envVar = envVar;
  }
}

/**
 * Optional overrides accepted by ``POST /api/agent/sessions``. Keep aligned
 * with :class:`molexp.server.schemas.requests.GoalCreateRequest`.
 */
export interface SessionLaunchOptions {
  /** Canonical agent for the first turn — only ``mode``, never plan_mode. */
  mode?: "chat" | "plan";
  instructionsOverride?: string;
  skillId?: string;
  /** Mount scope (vision-loop-11): the entity whose state seeds the session. */
  projectId?: string;
  experimentId?: string;
  runId?: string;
}

interface ApiAgentTask {
  taskId: string;
  title: string;
  goal: string;
  status: string;
  createdAt: string;
  updatedAt?: string | null;
  sessionId?: string;
  events?: ApiAgentSession["events"];
  stats?: ApiAgentSession["stats"];
  planMode?: boolean;
  activeMode?: "chat" | "plan";
  activeTurnId?: string | null;
  activePlanTaskId?: string | null;
  skillId?: string | null;
  projectId?: string | null;
  experimentId?: string | null;
  runId?: string | null;
}

const normalizeAgentTask = (task: ApiAgentTask): ApiAgentSession => ({
  taskId: task.taskId,
  title: task.title,
  sessionId: task.sessionId ?? task.taskId,
  status: task.status,
  goal: task.goal,
  createdAt: task.createdAt,
  updatedAt: task.updatedAt,
  events: task.events ?? [],
  stats: task.stats,
  planMode: task.planMode ?? false,
  activeMode: (task.activeMode ??
    (task.planMode ? "plan" : "chat")) as ApiAgentSession["activeMode"],
  activeTurnId: task.activeTurnId ?? null,
  activePlanTaskId: task.activePlanTaskId ?? null,
  skillId: task.skillId ?? null,
  projectId: task.projectId ?? null,
  experimentId: task.experimentId ?? null,
  runId: task.runId ?? null,
});

export const agentApi = {
  listSessions: async (): Promise<ApiAgentSession[]> => {
    const response = await fetch("/api/agent-tasks");
    if (!response.ok) throw new Error(`Failed to fetch agent tasks: ${response.statusText}`);
    const data = await response.json();
    return (data.tasks ?? []).map(normalizeAgentTask);
  },

  // Probe endpoint: routed through probeOnce so an unconfigured agent stack
  // (503) is detected once and never re-requested (see agentProbe.ts).
  getHealth: (): Promise<ApiAgentHealth> =>
    probeOnce("agent-health", async () => {
      const response = await fetch("/api/agent/health");
      if (response.status === 503) throw new AgentUnavailableError("/api/agent/health");
      if (!response.ok) throw new Error(`Failed to fetch agent health: ${response.statusText}`);
      return response.json();
    }),

  createSession: async (
    description: string,
    successCriteria: string[] = [],
    options: SessionLaunchOptions = {},
  ): Promise<ApiAgentSession> => {
    const body: Record<string, unknown> = {
      description,
      success_criteria: successCriteria,
    };
    // Canonical field only — never dual-write plan_mode.
    if (options.mode !== undefined) body.mode = options.mode;
    if (options.instructionsOverride !== undefined)
      body.instructions_override = options.instructionsOverride;
    if (options.skillId !== undefined) body.skill_id = options.skillId;
    if (options.projectId !== undefined) body.projectId = options.projectId;
    if (options.experimentId !== undefined) body.experimentId = options.experimentId;
    if (options.runId !== undefined) body.runId = options.runId;
    const response = await fetch("/api/agent-tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (response.status === 400) {
      // FastAPI nests structured errors under {"detail": {...}}
      const body = await response.json().catch(() => null);
      const detail = body?.detail;
      if (detail && typeof detail === "object" && detail.code === "agent_not_configured") {
        throw new AgentNotConfiguredError(
          String(detail.message ?? "Agent provider is not configured."),
          String(detail.provider ?? ""),
          String(detail.model ?? ""),
          String(detail.envVar ?? ""),
        );
      }
    }
    if (!response.ok) throw new Error(`Failed to create agent task: ${response.statusText}`);
    return normalizeAgentTask(await response.json());
  },

  getSession: async (sessionId: string): Promise<ApiAgentSession> => {
    const response = await fetch(`/api/agent-tasks/${sessionId}`);
    if (!response.ok) throw new Error(`Failed to fetch agent task: ${response.statusText}`);
    return normalizeAgentTask(await response.json());
  },

  streamEvents: (sessionId: string): EventSource => {
    return new EventSource(`/api/agent-tasks/${sessionId}/events`);
  },

  postMessage: async (
    sessionId: string,
    content: string,
    requestId: string | null = null,
    mode: "chat" | "plan" = "chat",
  ): Promise<void> => {
    const response = await fetch(`/api/agent-tasks/${sessionId}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content, request_id: requestId, mode }),
    });
    if (!response.ok) {
      // Surface FastAPI `detail` (e.g. missing model) — statusText alone is useless.
      let detail = "";
      try {
        const body = (await response.json()) as { detail?: unknown };
        if (typeof body.detail === "string") detail = body.detail;
        else if (Array.isArray(body.detail))
          detail = body.detail
            .map((d) => (typeof d === "object" && d && "msg" in d ? String(d.msg) : String(d)))
            .join("; ");
        else if (body.detail != null) detail = JSON.stringify(body.detail);
      } catch {
        /* ignore non-JSON error bodies */
      }
      throw new Error(
        detail || `Failed to post message: ${response.status} ${response.statusText}`,
      );
    }
  },

  /** Stop the in-flight turn for a task (idempotent when already idle). */
  cancelSession: async (sessionId: string): Promise<void> => {
    const response = await fetch(`/api/agent-tasks/${encodeURIComponent(sessionId)}/cancel`, {
      method: "POST",
    });
    if (!response.ok) throw new Error(`Failed to cancel agent task: ${response.statusText}`);
  },

  /** Drop a task (cancels live turn + removes on-disk metadata). */
  deleteSession: async (sessionId: string): Promise<void> => {
    const response = await fetch(`/api/agent-tasks/${encodeURIComponent(sessionId)}`, {
      method: "DELETE",
    });
    if (!response.ok) throw new Error(`Failed to delete agent task: ${response.statusText}`);
  },
};

// ── Agent admin (MCP / tools / skills) ────────────────────────────────────

export type ApiMcpScope = "user" | "workspace";
export type ApiMcpTransport = "stdio" | "http" | "sse";

export interface ApiMcpAuthSummary {
  type: "oauth2";
  scopes: string[];
  clientId: string | null;
  connected: boolean;
}

export interface ApiMcpServer {
  name: string;
  scope: ApiMcpScope;
  transport: string;
  command: string | null;
  args: string[];
  url: string | null;
  envKeys: string[];
  /** Non-secret env literals (e.g. MOLMCP_SOURCES) for the editor. */
  env?: Record<string, string>;
  headerKeys: string[];
  secretRefs: string[];
  unresolvedSecrets: string[];
  shadowed: boolean;
  valid: boolean;
  invalidReason: string;
  auth: ApiMcpAuthSummary | null;
  /** Parsed MOLMCP_SOURCES when this is a molmcp server. */
  knowledgeSources?: string[];
}

export interface ApiMcpOAuthStatus {
  name: string;
  scope: ApiMcpScope;
  hasTokens: boolean;
  scopes: string[];
}

export interface ApiMcpOAuthStart {
  name: string;
  scope: ApiMcpScope;
  authorizeUrl: string;
}

export interface ApiMcpServerList {
  workspacePath: string;
  userPath: string;
  servers: ApiMcpServer[];
}

export interface ApiMcpServerTestResult {
  ok: boolean;
  name: string;
  scope: ApiMcpScope;
  transport: string;
  latencyMs: number;
  toolCount: number;
  error: string | null;
}

export interface ApiMcpSecretRow {
  key: string;
  isSet: boolean;
  referencedBy: string[];
}

export interface ApiMcpSecretList {
  scope: ApiMcpScope;
  path: string;
  secrets: ApiMcpSecretRow[];
}

export interface McpOAuth2AuthInput {
  type: "oauth2";
  scopes: string[];
  clientId: string | null;
}

export type McpServerSpecInput =
  | { type: "stdio"; command: string; args: string[]; env: Record<string, string> }
  | {
      type: "http" | "sse";
      url: string;
      headers: Record<string, string>;
      auth?: McpOAuth2AuthInput | null;
    };

export interface McpServerUpsertInput {
  name: string;
  scope: ApiMcpScope;
  spec: McpServerSpecInput;
}

export interface ApiToolParameter {
  name: string;
  annotation: string;
  required: boolean;
}

export interface ApiAgentTool {
  name: string;
  description: string;
  parameters: ApiToolParameter[];
  requiresApproval: boolean;
  source: string;
}

export interface ApiMcpToolGroup {
  server: string;
  scope: ApiMcpScope;
  ok: boolean;
  toolCount: number;
  error: string | null;
}

export interface ApiAgentToolList {
  tools: ApiAgentTool[];
  mcpGroups: ApiMcpToolGroup[];
}

// Every tool belongs to an MCP server. Keep its wire-format source prefix
// centralized so the MCP list can attach tools to their owning server.
export const mcpSource = (server: string): string => `mcp:${server}`;

export interface ApiSkill {
  id: string;
  name: string;
  description: string;
  goalTemplate: string;
  slashName: string;
  instructions: string;
  defaultPlanMode: boolean;
  constraints: string[];
  successCriteria: string[];
  tags: string[];
  createdAt: string;
  updatedAt: string;
}

export interface SkillUpsertInput {
  name: string;
  goalTemplate: string;
  description?: string;
  slashName?: string;
  instructions?: string;
  defaultPlanMode?: boolean;
  constraints?: string[];
  successCriteria?: string[];
  tags?: string[];
}

const _toSkillBody = (input: SkillUpsertInput) => ({
  name: input.name,
  goal_template: input.goalTemplate,
  description: input.description ?? "",
  slash_name: input.slashName ?? "",
  instructions: input.instructions ?? "",
  default_plan_mode: input.defaultPlanMode ?? false,
  constraints: input.constraints ?? [],
  success_criteria: input.successCriteria ?? [],
  tags: input.tags ?? [],
});

// ── Slash commands + system prompt ────────────────────────────────────────

export interface ApiCommandParameter {
  name: string;
  required: boolean;
}

export interface ApiCommand {
  slashName: string;
  name: string;
  description: string;
  parameters: ApiCommandParameter[];
  defaultPlanMode: boolean;
  isBuiltin: boolean;
  skillId: string | null;
}

export interface ApiCommandParse {
  kind: "skill" | "builtin" | "error";
  name: string;
  skillId: string;
  parameters: Record<string, string>;
  planMode: boolean;
  error: string;
}

export interface ApiAgentSystemPrompt {
  base: string;
  workspaceInstructions: string;
  skillInstructions: string;
  sessionOverride: string | null;
  planMode: boolean;
  effective: string;
}

/** RESERVED_SLASH_NAMES mirrors the backend whitelist for client-side validation. */
export const RESERVED_SLASH_NAMES = ["plan", "clear", "model", "help"] as const;
export const SLASH_NAME_PATTERN = /^[a-z0-9][a-z0-9-]{0,31}$/;

// Provider config — read/write the workspace's LLM provider settings.
export type ApiProviderName = "anthropic" | "openai" | "google" | "deepseek" | "openai-compatible";

export type ApiModelTier = "cheap" | "default" | "heavy";
export type ApiTierModels = Record<ApiModelTier, string>;

export interface ApiAgentProvider {
  provider: ApiProviderName;
  model: string;
  baseUrl: string;
  apiKeyPreview: string;
  apiKeySet: boolean;
  instructions: string;
  supportedProviders: ApiProviderName[];
  /** Global cheap/default/heavy table — full ``provider:model`` ids; may cross providers. */
  models: ApiTierModels;
  configurations: ApiProviderConfiguration[];
}

export interface ApiProviderConfiguration {
  provider: ApiProviderName;
  /** Legacy per-provider tier map; prefer top-level ``models``. */
  models: ApiTierModels;
  baseUrl: string;
  apiKeyPreview: string;
  apiKeySet: boolean;
}

export interface ProviderUpdateInput {
  provider?: ApiProviderName;
  model?: string;
  models?: ApiTierModels;
  apiKey?: string;
  baseUrl?: string;
  instructions?: string;
}

export interface ApiAgentProviderTestResult {
  ok: boolean;
  provider: string;
  model: string;
  latencyMs: number;
  reply: string;
  error: string | null;
}

const _toProviderBody = (input: ProviderUpdateInput): Record<string, unknown> => {
  const body: Record<string, unknown> = {};
  if (input.provider !== undefined) body.provider = input.provider;
  if (input.model !== undefined) body.model = input.model;
  if (input.models !== undefined) body.models = input.models;
  if (input.apiKey !== undefined) body.api_key = input.apiKey;
  if (input.baseUrl !== undefined) body.base_url = input.baseUrl;
  if (input.instructions !== undefined) body.instructions = input.instructions;
  return body;
};

export type ApiKnowledgeSources = {
  sources: string[];
  knownPackages: string[];
  unrestricted: boolean;
  serverName: string;
  scope: string;
  configured: boolean;
};

export const agentAdminApi = {
  // Probe endpoint: routed through probeOnce so an unconfigured agent stack
  // (503) is detected once and never re-requested (see agentProbe.ts).
  getProvider: (): Promise<ApiAgentProvider> =>
    probeOnce("agent-provider", async () => {
      const response = await fetch("/api/agent/provider");
      if (response.status === 503) throw new AgentUnavailableError("/api/agent/provider");
      if (!response.ok) throw new Error(`Failed to fetch provider: ${response.statusText}`);
      return response.json();
    }),

  getKnowledgeSources: (): Promise<ApiKnowledgeSources> =>
    probeOnce("agent-knowledge-sources", async () => {
      const response = await fetch("/api/agent/knowledge-sources");
      if (response.status === 503) {
        throw new AgentUnavailableError("/api/agent/knowledge-sources");
      }
      if (!response.ok) {
        throw new Error(`Failed to fetch knowledge sources: ${response.statusText}`);
      }
      return response.json();
    }),

  updateKnowledgeSources: async (sources: string[]): Promise<ApiKnowledgeSources> => {
    const response = await fetch("/api/agent/knowledge-sources", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sources }),
    });
    if (!response.ok) {
      const detail = await response.text().catch(() => "");
      throw new Error(`Failed to update knowledge sources: ${response.statusText} ${detail}`);
    }
    resetAgentProbes();
    return response.json();
  },

  updateProvider: async (input: ProviderUpdateInput): Promise<ApiAgentProvider> => {
    const response = await fetch("/api/agent/provider", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(_toProviderBody(input)),
    });
    if (!response.ok) {
      const detail = await response.text().catch(() => "");
      throw new Error(`Failed to update provider: ${response.statusText} ${detail}`);
    }
    // A saved provider can turn an unconfigured stack into a live one —
    // drop any cached "unavailable" probe outcomes so the UI re-probes.
    resetAgentProbes();
    return response.json();
  },

  testProvider: async (input: ProviderUpdateInput): Promise<ApiAgentProviderTestResult> => {
    const response = await fetch("/api/agent/provider/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(_toProviderBody(input)),
    });
    if (!response.ok) {
      const detail = await response.text().catch(() => "");
      throw new Error(`Failed to test provider: ${response.statusText} ${detail}`);
    }
    return response.json();
  },

  listMcpServers: (): Promise<ApiMcpServerList> =>
    probeOnce("agent-mcp-servers", async () => {
      const response = await fetch("/api/agent/mcp/servers");
      if (response.status === 503) throw new AgentUnavailableError("/api/agent/mcp/servers");
      if (!response.ok) throw new Error(`Failed to fetch MCP servers: ${response.statusText}`);
      return response.json();
    }),

  createMcpServer: async (input: McpServerUpsertInput): Promise<ApiMcpServer> => {
    const response = await fetch("/api/agent/mcp/servers", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    });
    if (!response.ok) {
      const detail = await response.text().catch(() => "");
      throw new Error(`Failed to create MCP server: ${response.statusText} ${detail}`);
    }
    return response.json();
  },

  replaceMcpServer: async (name: string, input: McpServerUpsertInput): Promise<ApiMcpServer> => {
    const response = await fetch(`/api/agent/mcp/servers/${encodeURIComponent(name)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    });
    if (!response.ok) {
      const detail = await response.text().catch(() => "");
      throw new Error(`Failed to update MCP server: ${response.statusText} ${detail}`);
    }
    return response.json();
  },

  deleteMcpServer: async (name: string, scope: ApiMcpScope): Promise<void> => {
    const response = await fetch(
      `/api/agent/mcp/servers/${encodeURIComponent(name)}?scope=${scope}`,
      { method: "DELETE" },
    );
    if (!response.ok) {
      const detail = await response.text().catch(() => "");
      throw new Error(`Failed to delete MCP server: ${response.statusText} ${detail}`);
    }
  },

  testMcpServer: async (name: string, scope: ApiMcpScope): Promise<ApiMcpServerTestResult> => {
    const response = await fetch(
      `/api/agent/mcp/servers/${encodeURIComponent(name)}/test?scope=${scope}`,
      { method: "POST" },
    );
    if (!response.ok) {
      const detail = await response.text().catch(() => "");
      throw new Error(`Failed to test MCP server: ${response.statusText} ${detail}`);
    }
    return response.json();
  },

  startMcpOauth: async (name: string, scope: ApiMcpScope): Promise<ApiMcpOAuthStart> => {
    const response = await fetch(
      `/api/agent/mcp/servers/${encodeURIComponent(name)}/oauth/start?scope=${scope}`,
      { method: "POST" },
    );
    if (!response.ok) {
      const detail = await response.text().catch(() => "");
      throw new Error(`Failed to start OAuth: ${response.statusText} ${detail}`);
    }
    return response.json();
  },

  callbackMcpOauth: async (
    name: string,
    scope: ApiMcpScope,
    code: string,
    state: string | null,
  ): Promise<ApiMcpOAuthStatus> => {
    const response = await fetch(
      `/api/agent/mcp/servers/${encodeURIComponent(name)}/oauth/callback?scope=${scope}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code, state }),
      },
    );
    if (!response.ok) {
      const detail = await response.text().catch(() => "");
      throw new Error(`OAuth callback failed: ${response.statusText} ${detail}`);
    }
    return response.json();
  },

  getMcpOauthStatus: async (name: string, scope: ApiMcpScope): Promise<ApiMcpOAuthStatus> => {
    const response = await fetch(
      `/api/agent/mcp/servers/${encodeURIComponent(name)}/oauth?scope=${scope}`,
    );
    if (!response.ok) {
      throw new Error(`Failed to get OAuth status: ${response.statusText}`);
    }
    return response.json();
  },

  disconnectMcpOauth: async (name: string, scope: ApiMcpScope): Promise<void> => {
    const response = await fetch(
      `/api/agent/mcp/servers/${encodeURIComponent(name)}/oauth?scope=${scope}`,
      { method: "DELETE" },
    );
    if (!response.ok) {
      const detail = await response.text().catch(() => "");
      throw new Error(`Failed to disconnect OAuth: ${response.statusText} ${detail}`);
    }
  },

  listMcpSecrets: async (scope: ApiMcpScope): Promise<ApiMcpSecretList> => {
    const response = await fetch(`/api/agent/mcp/secrets?scope=${scope}`);
    if (!response.ok) {
      throw new Error(`Failed to list MCP secrets: ${response.statusText}`);
    }
    return response.json();
  },

  setMcpSecret: async (key: string, value: string, scope: ApiMcpScope): Promise<void> => {
    const response = await fetch(`/api/agent/mcp/secrets/${encodeURIComponent(key)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ value, scope }),
    });
    if (!response.ok) {
      const detail = await response.text().catch(() => "");
      throw new Error(`Failed to set MCP secret: ${response.statusText} ${detail}`);
    }
  },

  listTools: (): Promise<ApiAgentTool[]> =>
    probeOnce("agent-tools-list", async () => {
      const response = await fetch("/api/agent/tools");
      if (response.status === 503) throw new AgentUnavailableError("/api/agent/tools");
      if (!response.ok) throw new Error(`Failed to fetch tools: ${response.statusText}`);
      const data = await response.json();
      return data.tools ?? [];
    }).catch((error: unknown) => {
      if (error instanceof AgentUnavailableError) return [];
      throw error;
    }),

  listToolsAndGroups: (): Promise<ApiAgentToolList> =>
    probeOnce("agent-tools-groups", async () => {
      const response = await fetch("/api/agent/tools");
      if (response.status === 503) throw new AgentUnavailableError("/api/agent/tools");
      if (!response.ok) throw new Error(`Failed to fetch tools: ${response.statusText}`);
      const data = await response.json();
      return { tools: data.tools ?? [], mcpGroups: data.mcpGroups ?? [] };
    }).catch((error: unknown) => {
      if (error instanceof AgentUnavailableError) return { tools: [], mcpGroups: [] };
      throw error;
    }),

  listSkills: (): Promise<ApiSkill[]> =>
    probeOnce("agent-skills", async () => {
      const response = await fetch("/api/agent/skills");
      if (response.status === 503) throw new AgentUnavailableError("/api/agent/skills");
      if (!response.ok) throw new Error(`Failed to fetch skills: ${response.statusText}`);
      const data = await response.json();
      return data.skills ?? [];
    }).catch((error: unknown) => {
      if (error instanceof AgentUnavailableError) return [];
      throw error;
    }),

  createSkill: async (input: SkillUpsertInput): Promise<ApiSkill> => {
    const response = await fetch("/api/agent/skills", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(_toSkillBody(input)),
    });
    if (!response.ok) {
      const detail = await response.text().catch(() => "");
      throw new Error(`Failed to create skill: ${response.statusText} ${detail}`);
    }
    return response.json();
  },

  updateSkill: async (skillId: string, input: Partial<SkillUpsertInput>): Promise<ApiSkill> => {
    const body: Record<string, unknown> = {};
    if (input.name !== undefined) body.name = input.name;
    if (input.goalTemplate !== undefined) body.goal_template = input.goalTemplate;
    if (input.description !== undefined) body.description = input.description;
    if (input.slashName !== undefined) body.slash_name = input.slashName;
    if (input.instructions !== undefined) body.instructions = input.instructions;
    if (input.defaultPlanMode !== undefined) body.default_plan_mode = input.defaultPlanMode;
    if (input.constraints !== undefined) body.constraints = input.constraints;
    if (input.successCriteria !== undefined) body.success_criteria = input.successCriteria;
    if (input.tags !== undefined) body.tags = input.tags;
    const response = await fetch(`/api/agent/skills/${skillId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      const detail = await response.text().catch(() => "");
      throw new Error(`Failed to update skill: ${response.statusText} ${detail}`);
    }
    return response.json();
  },

  deleteSkill: async (skillId: string): Promise<void> => {
    const response = await fetch(`/api/agent/skills/${skillId}`, { method: "DELETE" });
    if (!response.ok) throw new Error(`Failed to delete skill: ${response.statusText}`);
  },

  launchSkill: async (
    skillId: string,
    parameters: Record<string, unknown> = {},
    options: { mode?: "chat" | "plan" } = {},
  ): Promise<ApiAgentSession> => {
    const body: Record<string, unknown> = { parameters };
    if (options.mode !== undefined) body.mode = options.mode;
    const response = await fetch(`/api/agent/skills/${skillId}/launch`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) throw new Error(`Failed to launch skill: ${response.statusText}`);
    return response.json();
  },
};

// ── Slash commands ────────────────────────────────────────────────────────

export const commandsApi = {
  // Probe endpoint: routed through probeOnce so an unconfigured agent stack
  // (503) is detected once and never re-requested (see agentProbe.ts).
  list: (): Promise<ApiCommand[]> =>
    probeOnce("agent-commands", async () => {
      const response = await fetch("/api/agent/commands");
      if (response.status === 503) throw new AgentUnavailableError("/api/agent/commands");
      if (!response.ok) throw new Error(`Failed to fetch commands: ${response.statusText}`);
      const data = await response.json();
      return data.commands ?? [];
    }),

  parse: async (raw: string): Promise<ApiCommandParse> => {
    const response = await fetch("/api/agent/commands/parse", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ raw }),
    });
    if (!response.ok) throw new Error(`Failed to parse command: ${response.statusText}`);
    return response.json();
  },
};

// ── Per-session prompt inspection ─────────────────────────────────────────

export const planApi = {
  /**
   * System-prompt breakdown for the task inspector.
   *
   * Live surface is `/api/agent-tasks/{id}/system-prompt` (accepts task id or
   * runtime session id). The legacy `/api/agent/sessions/.../system-prompt`
   * path is retired and always 503s.
   */
  getSystemPrompt: async (taskOrSessionId: string): Promise<ApiAgentSystemPrompt> => {
    const response = await fetch(`/api/agent-tasks/${taskOrSessionId}/system-prompt`);
    if (!response.ok) {
      const detail = await response.text().catch(() => "");
      const suffix = detail ? ` — ${detail.slice(0, 200)}` : "";
      throw new Error(`Failed to fetch system prompt: ${response.statusText}${suffix}`);
    }
    return response.json();
  },
};
