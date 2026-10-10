import { useSyncExternalStore } from "react";
import { workspacesApi } from "@/api/workspaces";
import { pulseSync } from "@/app/state/syncPulse";

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

interface StoreSnapshot {
  rows: WorkspaceRunRow[];
  unreachable: string[];
  stats: WorkspaceRunsStats;
  total: number;
  truncated: boolean;
  loading: boolean;
  error: string | null;
  lastSyncedAt: Date | null;
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

const EMPTY_SNAPSHOT: StoreSnapshot = {
  rows: [],
  unreachable: [],
  stats: EMPTY_STATS,
  total: 0,
  truncated: false,
  loading: false,
  error: null,
  lastSyncedAt: null,
};

// Module-level singleton: one fetch loop shared across all hook consumers
// (LeftPanel facet counts + RunsPage dashboard) so the API is hit once per
// poll instead of once per mounted component.
let snapshot: StoreSnapshot = EMPTY_SNAPSHOT;
let lastResponseSignature: string | null = null;
const subscribers = new Set<() => void>();
let intervalId: ReturnType<typeof setInterval> | null = null;
let inflight: Promise<void> | null = null;

const notify = (): void => {
  for (const fn of subscribers) fn();
};

const sameResponse = (response: WorkspaceRunsResponse): boolean => {
  const next = JSON.stringify(response);
  if (next === lastResponseSignature) return true;
  lastResponseSignature = next;
  return false;
};

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
    for (const run of response.runs) rows.push({ ...run, workspaceKey: key });
    totalExecutions += response.stats.totalExecutions;
    activeExecutions += response.stats.activeExecutions;
    for (const [status, count] of Object.entries(response.stats.byStatus)) {
      byStatus[status] = (byStatus[status] ?? 0) + count;
    }
    total += response.total;
    truncated = truncated || response.truncated;
  }

  rows.sort((a, b) => b.createdAt.localeCompare(a.createdAt));

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
  let served: Awaited<ReturnType<typeof workspacesApi.listWorkspaces>>;
  try {
    served = await workspacesApi.listWorkspaces();
  } catch {
    // No served-set endpoint (older server, or it is down): fall back to the
    // active workspace, which is what this hook did before it fanned out.
    served = [];
  }

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

const fetchOnce = async (silent: boolean): Promise<void> => {
  if (!silent && !snapshot.loading) {
    snapshot = { ...snapshot, loading: true };
    notify();
  }
  try {
    const response = await fetchAllWorkspaces();
    if (sameResponse(response)) {
      // Preserve row/stats array refs so downstream useMemo deps stay stable
      // (Plotly charts won't re-render). Only loading/error need to clear.
      if (snapshot.loading || snapshot.error !== null || snapshot.lastSyncedAt === null) {
        snapshot = {
          ...snapshot,
          loading: false,
          error: null,
          lastSyncedAt: snapshot.lastSyncedAt ?? new Date(),
        };
        notify();
      }
      // Poll completed even when payload is unchanged — still breathe.
      pulseSync();
      return;
    }
    snapshot = {
      rows: response.runs,
      stats: response.stats,
      total: response.total,
      truncated: response.truncated,
      unreachable: response.unreachable,
      loading: false,
      error: null,
      lastSyncedAt: new Date(),
    };
    notify();
    pulseSync();
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    snapshot = { ...snapshot, loading: false, error: message };
    notify();
    pulseSync();
  }
};

const triggerFetch = (silent: boolean): void => {
  if (inflight) return;
  inflight = fetchOnce(silent).finally(() => {
    inflight = null;
  });
};

const subscribe = (fn: () => void): (() => void) => {
  if (subscribers.size === 0) {
    triggerFetch(false);
    intervalId = setInterval(() => triggerFetch(true), POLL_INTERVAL_MS);
  }
  subscribers.add(fn);
  return () => {
    subscribers.delete(fn);
    if (subscribers.size === 0 && intervalId !== null) {
      clearInterval(intervalId);
      intervalId = null;
    }
  };
};

const getSnapshot = (): StoreSnapshot => snapshot;

// No-op subscribe used when the caller asks us to stand down (e.g. when the
// active left-panel view isn't "runs"). Keeps the Rules of Hooks intact while
// letting subscriber count fall to zero so the poll loop stops.
const noopSubscribe = (): (() => void) => (): void => undefined;

export interface UseWorkspaceRunsOptions {
  /** When false, the hook returns the cached snapshot but does not subscribe
   *  or trigger fetches. Use to gate polling by active view. Defaults to true. */
  enabled?: boolean;
}

export const useWorkspaceRuns = (options: UseWorkspaceRunsOptions = {}): UseWorkspaceRunsResult => {
  const { enabled = true } = options;
  const data = useSyncExternalStore(enabled ? subscribe : noopSubscribe, getSnapshot, getSnapshot);
  return {
    ...data,
    refresh: () => triggerFetch(false),
  };
};
