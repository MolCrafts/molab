// The run inventory a project or experiment Overview reads: one workspace-wide
// page, shared across scopes through one query key, narrowed on the client.

import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { workspaceRunsApi } from "@/app/runs/api";
import type { WorkspaceRunRow } from "@/app/runs/types";
import { runKeys } from "@/app/state/entityQueries";

const INVENTORY_LIMIT = 1000;

export interface RunScope {
  projectId?: string;
  experimentId?: string;
}

export const inScope = (run: WorkspaceRunRow, scope: RunScope): boolean =>
  (scope.projectId === undefined || run.projectId === scope.projectId) &&
  (scope.experimentId === undefined || run.experimentId === scope.experimentId);

export const useScopeRuns = (scope: RunScope, enabled: boolean) => {
  const query = useQuery({
    queryKey: runKeys.inventory(),
    queryFn: () => workspaceRunsApi.listRuns({ limit: INVENTORY_LIMIT }),
    enabled,
    staleTime: 30_000,
  });
  const { projectId, experimentId } = scope;
  const rows = useMemo(
    () => (query.data?.runs ?? []).filter((run) => inScope(run, { projectId, experimentId })),
    [query.data, projectId, experimentId],
  );
  return { query, rows, truncated: Boolean(query.data?.truncated) };
};
