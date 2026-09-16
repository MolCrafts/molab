/**
 * Run-page and runs-index queries (plan P2 §2c/2d).
 *
 * Two rules shape this module:
 *
 * 1. **One fetch, many filters.** The server has no filter pushdown yet, so a
 *    filtered runs list is the *same* request as an unfiltered one. The query
 *    key therefore describes what we ask the server for (`{limit}`), never the
 *    UI filter, and `applyFilters` runs in `select`. RunsPage and LeftPanel
 *    share one request and one memoized derivation.
 * 2. **Polling is a fallback, not a heartbeat.** Every interval here is a
 *    function of the data, so it cancels itself the moment a run reaches a
 *    terminal state. List polling comes from {@link useFallbackInterval}: it is
 *    30 s while the SSE change stream is down and `false` once it connects.
 *    Hidden tabs never poll (`refetchIntervalInBackground: false` on the
 *    client default).
 */

import { type QueryClient, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef } from "react";

import type { RunExecutionResponse, RunLogsResponse } from "@/api/generated";
import { applyFilters } from "@/app/runs/aggregates";
import { runsIndexUrl } from "@/app/runs/api";
import type {
  WorkspaceRunRow,
  WorkspaceRunsFilters,
  WorkspaceRunsResponse,
  WorkspaceRunsStats,
} from "@/app/runs/types";
import type { MetricRecord, RunFilesResponse } from "@/app/state/api";
import { workspaceApi } from "@/app/state/api";
import type { ApiAssetResponse } from "@/app/types";
import { useFallbackInterval } from "./changeStream";
import { fetchJsonConditional } from "./etagFetch";
import { qk } from "./keys";

// ── runs index ────────────────────────────────────────────────────────────

/** Row cap the runs index asks the server for. */
export const RUNS_INDEX_LIMIT = 1000;
/** A fresh runs index stays authoritative this long without a refetch. */
export const RUNS_INDEX_STALE_MS = 10_000;
/** Slow poll used only while the SSE change stream is disconnected. */
export const RUNS_FALLBACK_POLL_MS = 30_000;

const RUNS_INDEX_PARAMS = { limit: RUNS_INDEX_LIMIT } as const;

/** The one runs-index cache key. Filters never enter it — see the module doc. */
export const runsIndexKey = (): readonly unknown[] => qk.runsIndex(RUNS_INDEX_PARAMS);

export const EMPTY_RUN_STATS: WorkspaceRunsStats = {
  total: 0,
  running: 0,
  pending: 0,
  failed: 0,
  succeeded: 0,
};

const EMPTY_ROWS: readonly WorkspaceRunRow[] = [];

/** What a runs-index observer sees: the filtered view plus the raw payload. */
export interface RunsIndexView {
  /** Rows after the caller's filters (identical to `allRows` when none). */
  rows: WorkspaceRunRow[];
  /** Every row the server returned, unfiltered. */
  allRows: WorkspaceRunRow[];
  stats: WorkspaceRunsStats;
  total: number;
  truncated: boolean;
}

const hasFilters = (filters?: WorkspaceRunsFilters): boolean =>
  filters !== undefined && Object.values(filters).some((v) => v !== undefined);

export function runsIndexQueryFn(client: QueryClient) {
  return ({ signal }: { signal: AbortSignal }): Promise<WorkspaceRunsResponse> =>
    fetchJsonConditional<WorkspaceRunsResponse>(runsIndexUrl({ limit: RUNS_INDEX_LIMIT }), {
      signal,
      previous: () => client.getQueryData<WorkspaceRunsResponse>(runsIndexKey()),
    });
}

/**
 * The workspace runs index.
 *
 * `filters` narrows the returned rows in `select` only — it does not change
 * the request, so every consumer shares one in-flight fetch and one cache
 * entry regardless of how each filters it.
 */
export function useRunsIndexQuery(
  filters?: WorkspaceRunsFilters,
  options: { enabled?: boolean } = {},
) {
  const client = useQueryClient();
  const fallbackInterval = useFallbackInterval(RUNS_FALLBACK_POLL_MS);

  // `select` keeps a stable identity while `filters` does, which is what lets
  // TanStack hand back the previous derived object instead of rebuilding it.
  // Callers memoize their filters (RunsPage derives them from the URL), so an
  // unchanged filter set re-derives nothing.
  const select = useCallback(
    (data: WorkspaceRunsResponse): RunsIndexView => ({
      rows: hasFilters(filters) ? applyFilters(data.runs, filters ?? {}) : data.runs,
      allRows: data.runs,
      stats: data.stats,
      total: data.total,
      truncated: data.truncated,
    }),
    [filters],
  );

  return useQuery({
    queryKey: runsIndexKey(),
    queryFn: runsIndexQueryFn(client),
    staleTime: RUNS_INDEX_STALE_MS,
    refetchInterval: fallbackInterval,
    enabled: options.enabled ?? true,
    select,
  });
}

/** Empty view used before the first payload lands. */
export const EMPTY_RUNS_INDEX: RunsIndexView = {
  rows: EMPTY_ROWS as WorkspaceRunRow[],
  allRows: EMPTY_ROWS as WorkspaceRunRow[],
  stats: EMPTY_RUN_STATS,
  total: 0,
  truncated: false,
};

// ── run logs ──────────────────────────────────────────────────────────────

/**
 * Byte window requested for a log tail.
 *
 * `0` means "whatever the server sends" — the windowed log contract
 * (`?tail=`) arrives with plan P4; the key carries the number already so the
 * cache does not have to be reshaped then.
 */
export const DEFAULT_LOG_TAIL = 0;
/** Log refresh cadence while the attempt is still producing output. */
export const RUN_LOGS_POLL_MS = 3_000;

/** Log poll interval — only while the attempt is still producing output. */
export const runLogsRefetchInterval = (isRunning: boolean): number | false =>
  isRunning ? RUN_LOGS_POLL_MS : false;

/** Whether the logs query should run at all: only on a visible Logs tab. */
export const runLogsEnabled = (
  coords: { runId: string } | null,
  options: { enabled?: boolean } = {},
): boolean => (options.enabled ?? true) && coords !== null;

export interface RunLogsCoords {
  projectId: string;
  experimentId: string;
  runId: string;
}

/**
 * stdout/stderr for a run or one of its attempts.
 *
 * `RunViewer` and the runs-inspector Logs tab pass the same coords, so they
 * share one key and one request. Keep `enabled` false unless the Logs tab is
 * actually visible: this used to be an eager fetch on every run open.
 */
export function useRunLogsQuery(
  coords: RunLogsCoords | null,
  executionId: string | null,
  options: { enabled?: boolean; isRunning?: boolean } = {},
) {
  const { enabled = true, isRunning = false } = options;
  return useQuery({
    queryKey: qk.runLogs(coords?.runId ?? "", executionId, DEFAULT_LOG_TAIL),
    queryFn: (): Promise<RunLogsResponse> => {
      if (!coords) throw new Error("run logs requested without a run");
      return executionId
        ? workspaceApi.getRunExecutionLogs(
            coords.projectId,
            coords.experimentId,
            coords.runId,
            executionId,
          )
        : workspaceApi.getRunLogs(coords.projectId, coords.experimentId, coords.runId);
    },
    enabled: runLogsEnabled(coords, { enabled }),
    refetchInterval: runLogsRefetchInterval(isRunning),
  });
}

// ── run execution (workflow graph) ────────────────────────────────────────

/** Execution-graph refresh cadence while the attempt is running. */
export const RUN_EXECUTION_POLL_MS = 2_000;

const executionIsRunning = (data: RunExecutionResponse | undefined): boolean =>
  data?.status === "running";

/**
 * The execution poll interval for a given response — `false` once the attempt
 * is terminal. Exported so the self-cancelling property is testable without
 * driving real timers.
 */
export const runExecutionRefetchInterval = (
  data: RunExecutionResponse | undefined,
  runIsRunning: boolean,
): number | false => (runIsRunning || executionIsRunning(data) ? RUN_EXECUTION_POLL_MS : false);

/**
 * One execution's persisted workflow graph.
 *
 * The interval is a function of the response, so it stops the moment the
 * attempt reaches a terminal state — no unmount race, no stale timer.
 */
export function useRunExecutionQuery(
  coords: RunLogsCoords | null,
  executionId: string | null,
  options: { enabled?: boolean; runIsRunning?: boolean } = {},
) {
  const { enabled = true, runIsRunning = false } = options;
  return useQuery({
    queryKey: qk.runExecution(coords?.runId ?? "", executionId),
    queryFn: (): Promise<RunExecutionResponse> => {
      if (!coords) throw new Error("run execution requested without a run");
      return workspaceApi.getRunExecution(
        coords.projectId,
        coords.experimentId,
        coords.runId,
        executionId,
      );
    },
    enabled: enabled && coords !== null,
    refetchInterval: (query) => runExecutionRefetchInterval(query.state.data, runIsRunning),
  });
}

// ── run files / assets ────────────────────────────────────────────────────

/** A run's file tree — drives file-type plugin discovery. */
export function useRunFilesQuery<T = RunFilesResponse>(
  coords: RunLogsCoords | null,
  options: { enabled?: boolean; select?: (data: RunFilesResponse) => T } = {},
) {
  return useQuery({
    queryKey: qk.runFiles(coords?.runId ?? ""),
    queryFn: (): Promise<RunFilesResponse> => {
      if (!coords) throw new Error("run files requested without a run");
      return workspaceApi.getRunFiles(coords.projectId, coords.experimentId, coords.runId);
    },
    enabled: (options.enabled ?? true) && coords !== null,
    staleTime: 60_000,
    select: options.select,
  });
}

/** Assets produced by a run. */
export function useRunAssetsQuery(runId: string | null, options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: qk.runAssets(runId ?? ""),
    queryFn: (): Promise<ApiAssetResponse[]> => {
      if (!runId) throw new Error("run assets requested without a run");
      return workspaceApi.getRunAssets(runId);
    },
    enabled: (options.enabled ?? true) && runId !== null,
    staleTime: 60_000,
  });
}

// ── run metrics (incremental) ─────────────────────────────────────────────

/** Metrics refresh cadence while the run is producing records. */
export const RUN_METRICS_POLL_MS = 3_000;

export interface RunMetricsPage {
  records: MetricRecord[];
  nextLine: number;
  /** Cumulative count of unparseable lines across every page so far. */
  parseErrors: number;
}

/**
 * A run's metrics stream, appended in place.
 *
 * The query reads its own last page out of the cache and asks the server only
 * for records after `nextLine`, so a long-running sweep re-parses nothing.
 */
export function useRunMetricsQuery(
  coords: RunLogsCoords | null,
  options: { enabled?: boolean; isRunning?: boolean } = {},
) {
  const client = useQueryClient();
  const { enabled = true, isRunning = false } = options;
  const queryKey = qk.runMetrics(coords?.runId ?? "");

  return useQuery({
    queryKey,
    queryFn: async (): Promise<RunMetricsPage> => {
      if (!coords) throw new Error("run metrics requested without a run");
      const previous = client.getQueryData<RunMetricsPage>(queryKey);
      const sinceLine = previous?.nextLine ?? 0;
      const response = await workspaceApi.getRunMetrics(
        coords.projectId,
        coords.experimentId,
        coords.runId,
        { sinceLine },
      );
      const records =
        sinceLine === 0 ? response.records : [...(previous?.records ?? []), ...response.records];
      return {
        records,
        nextLine: response.nextLine,
        parseErrors: (sinceLine === 0 ? 0 : (previous?.parseErrors ?? 0)) + response.parseErrors,
      };
    },
    enabled: enabled && coords !== null,
    refetchInterval: isRunning ? RUN_METRICS_POLL_MS : false,
  });
}

// ── compute targets ───────────────────────────────────────────────────────

// ── prefetch ──────────────────────────────────────────────────────────────

/**
 * Warm a run row's detail queries so opening it paints from cache.
 *
 * Pair with {@link usePrefetchOnIntent} on a row: the fetch fires only after
 * sustained hover/focus and a warm key is a no-op.
 */
export function usePrefetchRunRow(): (coords: RunLogsCoords) => void {
  const client = useQueryClient();
  return useCallback(
    (coords: RunLogsCoords) => {
      void client.prefetchQuery({
        queryKey: qk.runFiles(coords.runId),
        queryFn: () =>
          workspaceApi.getRunFiles(coords.projectId, coords.experimentId, coords.runId),
        staleTime: 60_000,
      });
      void client.prefetchQuery({
        queryKey: qk.runAssets(coords.runId),
        queryFn: () => workspaceApi.getRunAssets(coords.runId),
        staleTime: 60_000,
      });
    },
    [client],
  );
}

/** Stable coords object for a run row (or null when there is no run). */
export function useRunCoords(
  run: { id: string; projectId: string; experimentId: string } | null | undefined,
): RunLogsCoords | null {
  const runId = run?.id;
  const projectId = run?.projectId;
  const experimentId = run?.experimentId;
  return useMemo(
    () => (runId && projectId && experimentId ? { projectId, experimentId, runId } : null),
    [runId, projectId, experimentId],
  );
}

/**
 * Hover/focus prefetch handlers for the rows of a run table.
 *
 * A table-level variant of {@link usePrefetchOnIntent}: one shared timer,
 * because only one row can be hovered at a time, so rows stay plain markup
 * inside a `.map` instead of each needing its own component to hold a hook.
 */
export function useRunRowPrefetch(delayMs = 120): (coords: RunLogsCoords) => {
  onMouseEnter: () => void;
  onFocus: () => void;
  onMouseLeave: () => void;
  onBlur: () => void;
} {
  const prefetchRow = usePrefetchRunRow();
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const disarm = useCallback((): void => {
    if (timer.current !== null) {
      clearTimeout(timer.current);
      timer.current = null;
    }
  }, []);

  useEffect(() => disarm, [disarm]);

  return useCallback(
    (coords: RunLogsCoords) => {
      const arm = (): void => {
        disarm();
        timer.current = setTimeout(() => {
          timer.current = null;
          prefetchRow(coords);
        }, delayMs);
      };
      return { onMouseEnter: arm, onFocus: arm, onMouseLeave: disarm, onBlur: disarm };
    },
    [prefetchRow, disarm, delayMs],
  );
}
