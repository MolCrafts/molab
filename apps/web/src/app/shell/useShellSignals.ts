/**
 * What the status bar reports about the workspace (L00): how many runs need
 * attention, and when the workspace was last read. Shares the Runs table's
 * query (one cache entry); the status bar only asks every 30 s, and the Runs
 * page's faster poll serves it while that page is open.
 */

import { useQuery } from "@tanstack/react-query";
import { applyFilters } from "@/app/runs/aggregates";
import type { WorkspaceRunRow } from "@/app/runs/types";
import { workspaceRunsQueryOptions } from "@/app/runs/useWorkspaceRuns";
import { ATTENTION_GROUPS } from "@/app/status/vocabulary";

const STATUS_BAR_POLL_MS = 30_000;

/** Run states the failures indicator counts and the filtered Runs table shows. */
export const ATTENTION_STATUSES = ATTENTION_GROUPS;

/**
 * Runs, not attempts: the same predicate the Runs table applies to
 * `?status=failed,interrupted`, so the number is the number of rows it opens.
 */
export const attentionCount = (runs: readonly WorkspaceRunRow[] | undefined): number =>
  runs ? applyFilters([...runs], { status: [...ATTENTION_STATUSES] }).length : 0;

export interface ShellSignals {
  attention: number;
  lastSyncedAt: Date | null;
}

export const useShellSignals = (): ShellSignals => {
  const query = useQuery({ ...workspaceRunsQueryOptions(), refetchInterval: STATUS_BAR_POLL_MS });
  return {
    attention: attentionCount(query.data?.runs),
    lastSyncedAt: query.dataUpdatedAt > 0 ? new Date(query.dataUpdatedAt) : null,
  };
};
