import { ListTodo, PanelsTopLeft, TriangleAlert } from "lucide-react";
import { type JSX, useEffect, useMemo, useState } from "react";
import { Link, Navigate } from "react-router-dom";

import { DashboardCanvas, StatusLedger } from "@/app/components/entity";
import { DashboardAttention } from "@/app/dashboard/DashboardAttention";
import { DashboardGrid, DashboardToolbar } from "@/app/dashboard/DashboardGrid";
import {
  buildDashboardModel,
  hasMeasurableExecutions,
  isInventoryBlocked,
  showDashboardGrid,
  showDashboardSkeleton,
  showTruncationStrip,
} from "@/app/dashboard/dashboardModel";
import { DashboardWidgetBody, rollupExecutions } from "@/app/dashboard/dashboardWidgets";
import {
  DASHBOARD_LAYOUT_KEY,
  type DashboardWidget,
  defaultWidgets,
  parseLayout,
  serializeLayout,
} from "@/app/dashboard/layout";
import { useWorkspaceTabVisible } from "@/app/dashboard/useWorkspaceTab";
import type { NavigationLandingProps } from "@/app/navigation/sections";
import { useWorkspaceRuns } from "@/app/runs/useWorkspaceRuns";
import { WorkbenchIconAction, WorkbenchOperationState } from "@/components/workbench";

const useWideDashboard = (): boolean => {
  const query = "(min-width: 1024px)";
  const [wide, setWide] = useState(() =>
    typeof window === "undefined" ? true : window.matchMedia(query).matches,
  );
  useEffect(() => {
    const media = window.matchMedia(query);
    const apply = (): void => setWide(media.matches);
    apply();
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, []);
  return wide;
};

const readLayout = (): DashboardWidget[] => {
  if (typeof window === "undefined") return defaultWidgets();
  return parseLayout(window.localStorage.getItem(DASHBOARD_LAYOUT_KEY));
};

export const DashboardPage = ({ snapshot }: NavigationLandingProps): JSX.Element => {
  const { rows, loading, error, refresh, truncated, unreachable, lastSyncedAt } =
    useWorkspaceRuns();
  const [widgets, setWidgets] = useState<DashboardWidget[]>(readLayout);
  const [arranging, setArranging] = useState(false);
  const wide = useWideDashboard();
  const blocked = isInventoryBlocked(snapshot, {
    runsError: error,
    unreachableKeys: unreachable,
  });
  const model = useMemo(
    () =>
      buildDashboardModel(snapshot, rows, {
        runsError: error,
        truncated,
        unreachableKeys: unreachable,
      }),
    [snapshot, rows, error, truncated, unreachable],
  );
  const skeleton = showDashboardSkeleton({
    loading,
    rowCount: rows.length,
    synced: lastSyncedAt !== null,
    blocked,
  });
  const workspaceTab = useWorkspaceTabVisible(snapshot);
  const instruments = showDashboardGrid(blocked, rows.length) && hasMeasurableExecutions(rows);

  useEffect(() => {
    window.localStorage.setItem(DASHBOARD_LAYOUT_KEY, serializeLayout(widgets));
  }, [widgets]);

  useEffect(() => {
    if (!wide || !instruments) setArranging(false);
  }, [wide, instruments]);

  if (!workspaceTab) {
    return <Navigate to="/projects" replace />;
  }

  const quiet = !skeleton && !instruments && !blocked;
  const counts = rollupExecutions(rows);

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-background">
      <div className="min-h-0 flex-1 overflow-y-auto">
        {skeleton ? (
          <WorkbenchOperationState
            kind="loading"
            title="Loading workspace status"
            skeletonRows={5}
          />
        ) : (
          <>
            <DashboardAttention
              items={model.operational}
              overflow={model.operationalOverflow}
              retrying={loading}
              onRetry={refresh}
            />
            {showTruncationStrip(truncated, error) ? (
              <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-2 border-b border-status-warning/30 bg-status-warning-soft px-6 py-2 text-label text-status-warning-foreground">
                <TriangleAlert className="size-icon-sm shrink-0" aria-hidden />
                <p className="min-w-0 flex-1 basis-48 break-words">
                  Partial results. Filter runs to see more.
                </p>
                <WorkbenchIconAction label="Open runs" asChild>
                  <Link to="/runs">
                    <ListTodo aria-hidden />
                  </Link>
                </WorkbenchIconAction>
              </div>
            ) : null}
            <header className="sticky top-0 z-10 flex flex-wrap items-center justify-between min-h-8 gap-x-3 gap-y-1 border-b border-border bg-background px-4 py-1">
              <h1 className="min-w-0 text-body font-medium text-foreground">Dashboard</h1>
              {instruments ? (
                <DashboardToolbar
                  arranging={arranging}
                  wide={wide}
                  widgets={widgets}
                  onArranging={setArranging}
                  onWidgets={setWidgets}
                />
              ) : null}
            </header>
            {quiet ? (
              <div className="px-6 py-8">
                <p className="max-w-[65ch] text-body text-foreground">No executions yet.</p>
                <div className="mt-4 flex flex-wrap gap-2">
                  <WorkbenchIconAction label="Open projects" asChild>
                    <Link to="/projects">
                      <PanelsTopLeft aria-hidden />
                    </Link>
                  </WorkbenchIconAction>
                  <WorkbenchIconAction label="Open runs" asChild>
                    <Link to="/runs">
                      <ListTodo aria-hidden />
                    </Link>
                  </WorkbenchIconAction>
                </div>
              </div>
            ) : null}
            {instruments ? (
              <div id="dashboard-charts">
                <DashboardCanvas className="max-w-none space-y-4 px-4 py-3">
                  <StatusLedger counts={counts} unit={["execution", "executions"]} />
                  <DashboardGrid
                    widgets={widgets}
                    arranging={arranging}
                    wide={wide}
                    onWidgets={setWidgets}
                    renderWidget={(widget) => (
                      <DashboardWidgetBody widget={widget} rows={rows} inventoryBlocked={blocked} />
                    )}
                  />
                </DashboardCanvas>
              </div>
            ) : null}
          </>
        )}
      </div>
    </div>
  );
};
