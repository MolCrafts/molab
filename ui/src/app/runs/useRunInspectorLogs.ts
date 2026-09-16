/**
 * stdout/stderr for the runs-inspector Logs tab.
 *
 * Shares its cache key with `RunViewer`'s logs query, so opening a run in the
 * inspector and then in the centre panel is one request, not two. Polling is a
 * function of the run's own state and stops when the attempt finishes.
 */

import { useCallback } from "react";

import { useRunLogsQuery } from "@/app/state/queries/runs";

import type { WorkspaceRunRow } from "./types";

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

export const useRunInspectorLogs = (
  run: WorkspaceRunRow | null,
  selectedExecutionId: string | null,
  enabled: boolean,
): UseRunInspectorLogsResult => {
  const coords = run
    ? { projectId: run.projectId, experimentId: run.experimentId, runId: run.id }
    : null;

  const selectedExec = run?.executions.find((e) => e.executionId === selectedExecutionId);
  const isRunning =
    !!run &&
    (run.status === "running" ||
      selectedExec?.status === "running" ||
      (selectedExecutionId === null &&
        run.executions.some((e) => e.status === "running" || e.finishedAt === null)));

  const query = useRunLogsQuery(coords, selectedExecutionId, { enabled, isRunning });
  const refetch = query.refetch;

  const refresh = useCallback((): void => {
    void refetch();
  }, [refetch]);

  return {
    logs: query.data
      ? {
          stdout: query.data.stdout ?? null,
          stderr: query.data.stderr ?? null,
          executionId: query.data.execution_id ?? null,
        }
      : null,
    error: query.error instanceof Error ? query.error.message : null,
    loading: query.isPending && enabled && coords !== null,
    refresh,
  };
};
