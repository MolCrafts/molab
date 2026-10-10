/**
 * TypeScript mirrors of the backend `WorkspaceRunsResponse` shape.
 *
 * Kept hand-written rather than pulled from the generated OpenAPI client so
 * the runs feature module compiles before `npm run generate:api` is re-run.
 */

export interface WorkspaceExecutionRow {
  executionId: string;
  runId: string;
  mode: string;
  status: string;
  createdAt: string;
  startedAt: string | null;
  finishedAt: string | null;
  durationSeconds: number | null;
  basedOnExecutionId: string | null;
  checkpointArtifactId: string | null;
  schedulerJobId: string | null;
  backend: string | null;
  backendMetadata: Record<string, string>;
}

export interface RunStatusSummary {
  total: number;
  active: number;
  notStarted: boolean;
  byStatus: Record<string, number>;
}

export interface WorkspaceRunRow {
  id: string;
  name: string;
  /**
   * Served-workspace key this row was fetched from.
   *
   * Stamped by the client, not the server: `/api/workspace/runs` answers for
   * whichever workspace the request selected, so only the caller knows which
   * one it asked. Without it a run id is ambiguous the moment two workspaces
   * are served — `run-001` exists in most of them.
   */
  workspaceKey: string;
  /**
   * Workspace-relative directory, as the server reported it.
   *
   * Never rebuilt from ids: every segment is a name — a project slug, an
   * experiment slug, a run's parameters — and an experiment whose id is a
   * UUIDv7 lives in a directory named after itself, so a composed path points
   * nowhere.
   */
  path: string;
  projectId: string;
  projectName: string;
  experimentId: string;
  experimentName: string;
  definitionHash: string;
  experimentRevisionId: string;
  inputAssetIds: string[];
  targetHint: string | null;
  statusSummary: RunStatusSummary;
  parameters: Record<string, unknown>;
  createdAt: string;
  executions: WorkspaceExecutionRow[];
}

export interface WorkspaceRunsStats {
  totalRuns: number;
  totalExecutions: number;
  activeExecutions: number;
  byStatus: Record<string, number>;
}

export interface WorkspaceRunsResponse {
  runs: WorkspaceRunRow[];
  stats: WorkspaceRunsStats;
  total: number;
  truncated: boolean;
}

export type RunsQuickView = "active" | "failed24h" | "longRunning";

export interface WorkspaceRunsFilters {
  projectId?: string[];
  experimentId?: string[];
  backend?: string[];
  cluster?: string[];
  target?: string[];
  status?: string[];
  quickView?: RunsQuickView[];
  limit?: number;
}
