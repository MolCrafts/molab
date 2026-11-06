import { queryOptions, useQuery } from "@tanstack/react-query";
import { workspacesApi } from "@/api/workspaces";
import { pulseSync } from "@/app/state/syncPulse";
import { getWorkspaceQueryScope } from "@/app/state/workspaceSwitchEvents";

import { workspaceRunsApi } from "./api";
import type { WorkspaceRunRow, WorkspaceRunsResponse, WorkspaceRunsStats } from "./types";

interface UseWorkspaceRunsResult {
  rows: WorkspaceRunRow[];
  /** Served workspaces whose page failed this poll; the rest still loaded. */
  unreachable: string[];
  stats: WorkspaceRunsStats;
  total: number;
  truncated: boolean;
  loading: boolean;
  error: string | null;
  lastSyncedAt: Date | null;
  refresh: () => void;
}

export const POLL_INTERVAL_MS = 3_000;
const FETCH_LIMIT = 1000;

/** Stand-in key when the server serves no named set (single-workspace mode). */
const ACTIVE_WORKSPACE_KEY = "";

const EMPTY_STATS: WorkspaceRunsStats = {
  totalRuns: 0,
  totalExecutions: 0,
  activeExecutions: 0,
  byStatus: {},
};

const EMPTY_ROWS: WorkspaceRunRow[] = [];

/**
 * Merge one page of runs per served workspace into a single response.
 *
 * Failures are isolated per workspace: one unreachable remote must not empty
 * the table for the local roots beside it. A workspace that fails contributes
 * nothing and is named in `unreachable`, which the caller surfaces instead of
 * treating the whole poll as an error.
 */
export const mergeWorkspaceRuns = (
  results: readonly { key: string; response: WorkspaceRunsResponse | null }[],
): WorkspaceRunsResponse & { unreachable: string[] } => {
  const rows: WorkspaceRunRow[] = [];
  const unreachable: string[] = [];
  const byStatus: Record<string, number> = {};
  let totalExecutions = 0;
  let activeExecutions = 0;
  let total = 0;
  let truncated = false;

  for (const { key, response } of results) {
    if (!response) {
      unreachable.push(key);
      continue;
    }
    // Stamp the workspace here: this is the only point that knows which one
    // was asked, and every consumer downstream needs it to address the run.
    // A partial payload must not throw: Object.entries(undefined) is the
    // "Cannot convert undefined or null to object" that blanks the dashboard.
    const incoming = Array.isArray(response.runs) ? response.runs : [];
    for (const run of incoming) rows.push({ ...run, workspaceKey: key });
    const stats = response.stats;
    totalExecutions += stats?.totalExecutions ?? 0;
    activeExecutions += stats?.activeExecutions ?? 0;
    const statusCounts = stats?.byStatus;
    if (statusCounts != null && typeof statusCounts === "object") {
      for (const [status, count] of Object.entries(statusCounts)) {
        if (typeof count !== "number") continue;
        byStatus[status] = (byStatus[status] ?? 0) + count;
      }
    }
    total += response.total ?? 0;
    truncated = truncated || Boolean(response.truncated);
  }

  rows.sort((a, b) => (b.createdAt ?? "").localeCompare(a.createdAt ?? ""));

  return {
    runs: rows,
    stats: { totalRuns: rows.length, totalExecutions, activeExecutions, byStatus },
    total,
    truncated,
    unreachable,
  };
};

/**
 * One page of runs from every served workspace.
 *
 * `/api/workspace/runs` is mounted flat only — there is no
 * `/api/workspaces/{ws}/workspace/runs` — so each workspace is addressed with
 * `?ws=`, which `get_workspace` resolves the same way the `{ws}` segment does.
 * The served set is re-read each poll so adding or removing a workspace shows
 * up without a reload.
 */
const fetchAllWorkspaces = async (): Promise<WorkspaceRunsResponse & { unreachable: string[] }> => {
  const served = await workspacesApi.listWorkspaces();

  if (served.length === 0) {
    const response = await workspaceRunsApi.listRuns({ limit: FETCH_LIMIT });
    return mergeWorkspaceRuns([{ key: ACTIVE_WORKSPACE_KEY, response }]);
  }

  const results = await Promise.all(
    served.map(async (ws) => {
      if (ws.unreachable) return { key: ws.key, response: null };
      try {
        return {
          key: ws.key,
          response: await workspaceRunsApi.listRuns({ ws: ws.key, limit: FETCH_LIMIT }),
        };
      } catch {
        return { key: ws.key, response: null };
      }
    }),
  );
  return mergeWorkspaceRuns(results);
};

export const workspaceRunsQueryOptions = () =>
  queryOptions({
    queryKey: ["workspace-runs", getWorkspaceQueryScope()],
    queryFn: async () => {
      const response = await fetchAllWorkspaces();
      pulseSync();
      return response;
    },
    refetchInterval: POLL_INTERVAL_MS,
    refetchIntervalInBackground: false,
  });

export interface UseWorkspaceRunsOptions {
  enabled?: boolean;
}

export const useWorkspaceRuns = (options: UseWorkspaceRunsOptions = {}): UseWorkspaceRunsResult => {
  const query = useQuery({ ...workspaceRunsQueryOptions(), enabled: options.enabled ?? true });
  const response = query.data;
  return {
    rows: response?.runs ?? EMPTY_ROWS,
    unreachable: response?.unreachable ?? [],
    stats: response?.stats ?? EMPTY_STATS,
    total: response?.total ?? 0,
    truncated: response?.truncated ?? false,
    loading: query.isFetching,
    error: query.error?.message ?? null,
    lastSyncedAt: query.dataUpdatedAt ? new Date(query.dataUpdatedAt) : null,
    refresh: () => {
      void query.refetch();
    },
  };
};
