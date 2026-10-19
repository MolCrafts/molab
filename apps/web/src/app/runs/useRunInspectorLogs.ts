import { useQuery } from "@tanstack/react-query";
import { runsApi } from "@/api";
import type { RunLogsResponse } from "@/api/generated";
import { journalRefetchInterval } from "@/app/state/entityQueries";
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
  const execution = run?.executions.find((item) => item.executionId === selectedExecutionId);
  const query = useQuery({
    queryKey: [
      "run-inspector-logs",
      run?.workspaceKey,
      run?.projectId,
      run?.experimentId,
      run?.id,
      selectedExecutionId,
    ],
    enabled: enabled && Boolean(run && selectedExecutionId),
    queryFn: async () => {
      if (!run || !selectedExecutionId) throw new Error("Select an execution");
      return toPayload(
        await (run.workspaceKey
          ? runsApi.getRunExecutionLogsWs(
              run.workspaceKey,
              run.projectId,
              run.experimentId,
              run.id,
              selectedExecutionId,
            )
          : runsApi.getRunExecutionLogs(
              run.projectId,
              run.experimentId,
              run.id,
              selectedExecutionId,
            )),
      );
    },
    refetchInterval: journalRefetchInterval(execution?.status),
    refetchIntervalInBackground: false,
  });
  return {
    logs: query.data ?? null,
    error: query.error?.message ?? null,
    loading: query.isFetching,
    refresh: () => {
      void query.refetch();
    },
  };
};
