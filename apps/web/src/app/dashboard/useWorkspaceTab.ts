import {
  hasMeasurableExecutions,
  isInventoryBlocked,
  showWorkspaceTab,
} from "@/app/dashboard/dashboardModel";
import { useWorkspaceRuns } from "@/app/runs/useWorkspaceRuns";
import type { WorkspaceSnapshot } from "@/app/types";

/** Whether the Workspace rail section (the dashboard) should be on the rail. */
export const useWorkspaceTabVisible = (snapshot: WorkspaceSnapshot): boolean => {
  // Navigation reads the existing inventory. Dashboard/Runs own polling;
  // showing a rail item must not scan an entire remote workspace.
  const { rows, error, unreachable, lastSyncedAt } = useWorkspaceRuns({ enabled: false });
  return showWorkspaceTab({
    synced: lastSyncedAt !== null,
    blocked: isInventoryBlocked(snapshot, {
      runsError: error,
      unreachableKeys: unreachable,
    }),
    measurable: hasMeasurableExecutions(rows),
  });
};
