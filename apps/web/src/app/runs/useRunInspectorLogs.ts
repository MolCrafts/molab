import { useEffect, useState } from "react";
import { runsApi } from "@/api";
import type { RunLogsResponse } from "@/api/generated";
import type { WorkspaceRunRow } from "./types";
import { POLL_INTERVAL_MS } from "./useWorkspaceRuns";
export type RunLogsPayload = {
  stdout: string | null;
  stderr: string | null;
  executionId: string | null;
};

interface UseRunInspectorLogsResult {
  logs: RunLogsPayload | null;
  error: string | null;
  loading: boolean;
  refresh: () => void;
}

const toPayload = (response: RunLogsResponse): RunLogsPayload => ({
  stdout: response.stdout ?? null,
  stderr: response.stderr ?? null,
  executionId: response.executionId ?? null,
});

/**
 * Fetch stdout/stderr for the inspector Logs tab.
 * Polls while the run (or selected attempt) is still running; one-shot otherwise.
 */
export const useRunInspectorLogs = (
  run: WorkspaceRunRow | null,
  selectedExecutionId: string | null,
  enabled: boolean,
): UseRunInspectorLogsResult => {
  const [logs, setLogs] = useState<RunLogsPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [tick, setTick] = useState(0);

  const runId = run?.id ?? null;
  const projectId = run?.projectId ?? null;
  const experimentId = run?.experimentId ?? null;
  const selectedExec = run?.executions.find((e) => e.executionId === selectedExecutionId);
  const shouldPoll =
    enabled &&
    !!run &&
    !!selectedExecutionId &&
    (selectedExec?.status === "running" || selectedExec?.status === "finalizing");

  // `tick` is a manual refresh counter bumped by `refresh()` — required dep.
  // biome-ignore lint/correctness/useExhaustiveDependencies: tick forces re-fetch
  useEffect(() => {
    if (!enabled || !runId || !projectId || !experimentId || !selectedExecutionId) {
      setLogs(null);
      setError(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    const load = (): void => {
      const fetcher = runsApi.getRunExecutionLogs(
        projectId, experimentId, runId, selectedExecutionId,
      );

      fetcher
        .then((response) => {
          if (cancelled) return;
          setLogs(toPayload(response));
          setError(null);
        })
        .catch((err) => {
          if (cancelled) return;
          setError(err instanceof Error ? err.message : "Failed to load logs");
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    };

    load();

    let interval: ReturnType<typeof setInterval> | null = null;
    if (shouldPoll) {
      interval = setInterval(load, POLL_INTERVAL_MS);
    }

    return () => {
      cancelled = true;
      if (interval) clearInterval(interval);
    };
  }, [enabled, runId, projectId, experimentId, selectedExecutionId, shouldPoll, tick]);

  return {
    logs,
    error,
    loading,
    refresh: () => setTick((n) => n + 1),
  };
};
