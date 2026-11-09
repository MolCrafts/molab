/**
 * The one server read the Molq run view makes: the attempt's execution record
 * (`GET …/executions/{id}`), whose executor metadata and times the view shows.
 * Keyed under `runKeys.all`, so invalidating the runs invalidates it too, and
 * polled only while the attempt is active.
 */

import type { RunAttempt } from "@molcrafts/molab-plugin";
import { queryOptions } from "@tanstack/react-query";
import { runsApi } from "@/api";
import { journalRefetchInterval, runKeys } from "@/app/state/entityQueries";
import { getWorkspaceQueryScope } from "@/app/state/workspaceSwitchEvents";

type AttemptCoords = Pick<RunAttempt, "projectId" | "experimentId" | "runId" | "executionId">;

export const molqExecutionKey = ({ projectId, experimentId, runId, executionId }: AttemptCoords) =>
  [
    ...runKeys.all,
    getWorkspaceQueryScope(),
    projectId,
    experimentId,
    runId,
    executionId,
    "record",
  ] as const;

export const molqExecutionQueryOptions = (attempt: AttemptCoords) =>
  queryOptions({
    queryKey: molqExecutionKey(attempt),
    queryFn: () =>
      runsApi.getExecution(
        attempt.projectId,
        attempt.experimentId,
        attempt.runId,
        attempt.executionId,
      ),
    staleTime: 10_000,
    refetchInterval: (query) => journalRefetchInterval(query.state.data?.status),
  });
