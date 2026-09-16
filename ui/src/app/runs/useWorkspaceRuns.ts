/**
 * The workspace runs index, as the navigator and dashboard consume it.
 *
 * This is now a thin adapter over {@link useRunsIndexQuery}: the query cache
 * owns deduplication, freshness and polling, so the module-level singleton
 * (one `setInterval`, a `JSON.stringify` diff to keep array identities stable,
 * a manual subscriber count) is gone. Two consumers mounting this hook still
 * share exactly one request — that is now a property of the shared query key
 * rather than hand-written bookkeeping.
 *
 * The 3 s poll is gone with it. Freshness comes from SSE invalidation, with a
 * 30 s fallback poll only while that stream is down, and no polling at all on
 * a hidden tab.
 */

import { useMemo } from "react";

import { EMPTY_RUN_STATS, useRunsIndexQuery } from "@/app/state/queries/runs";

import type { WorkspaceRunRow, WorkspaceRunsStats } from "./types";

interface UseWorkspaceRunsResult {
  rows: WorkspaceRunRow[];
  stats: WorkspaceRunsStats;
  total: number;
  truncated: boolean;
  loading: boolean;
  error: string | null;
  lastSyncedAt: Date | null;
  refresh: () => void;
}

/**
 * Retained for the consumers that still import it as their own cadence
 * (`useRunInspectorLogs`, `WorkspaceActivityFeed`). The runs index itself no
 * longer polls on this interval.
 */
export const POLL_INTERVAL_MS = 3_000;

const EMPTY_ROWS: WorkspaceRunRow[] = [];

export interface UseWorkspaceRunsOptions {
  /** When false the hook reads cache only and issues no request. */
  enabled?: boolean;
}

export const useWorkspaceRuns = (options: UseWorkspaceRunsOptions = {}): UseWorkspaceRunsResult => {
  const { enabled = true } = options;
  const query = useRunsIndexQuery(undefined, { enabled });

  const lastSyncedAt = useMemo(
    () => (query.dataUpdatedAt > 0 ? new Date(query.dataUpdatedAt) : null),
    [query.dataUpdatedAt],
  );

  return {
    rows: query.data?.rows ?? EMPTY_ROWS,
    stats: query.data?.stats ?? EMPTY_RUN_STATS,
    total: query.data?.total ?? 0,
    truncated: query.data?.truncated ?? false,
    loading: query.isFetching,
    error: query.error instanceof Error ? query.error.message : null,
    lastSyncedAt,
    refresh: () => {
      void query.refetch();
    },
  };
};
