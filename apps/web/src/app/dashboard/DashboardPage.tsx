import { ArrowUpRight, LayoutDashboard, TriangleAlert } from "lucide-react";
import { type JSX, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { DashboardCanvas, EntityPage } from "@/app/components/entity";
import { DashboardGrid, DashboardToolbar } from "@/app/dashboard/DashboardGrid";
import { DashboardWidgetBody } from "@/app/dashboard/dashboardWidgets";
import {
  DASHBOARD_LAYOUT_KEY,
  type DashboardWidget,
  defaultWidgets,
  parseLayout,
  serializeLayout,
} from "@/app/dashboard/layout";
import { useWorkspaceRuns } from "@/app/runs/useWorkspaceRuns";
import type { WorkspaceSnapshot } from "@/app/types";
import {
  WorkbenchIconAction,
  WorkbenchOperationState,
  WorkbenchRetryAction,
} from "@/components/workbench";
import { formatRelative } from "@/lib/format-time";

interface DashboardPageProps {
  snapshot: WorkspaceSnapshot;
}

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

export const DashboardPage = ({ snapshot }: DashboardPageProps): JSX.Element => {
  const { rows, loading, error, lastSyncedAt, refresh, truncated } = useWorkspaceRuns();
  const activeWorkspace =
    snapshot.workspaces.find((workspace) => workspace.active) ?? snapshot.workspaces[0];
  const [widgets, setWidgets] = useState<DashboardWidget[]>(readLayout);
  const [arranging, setArranging] = useState(false);
  const wide = useWideDashboard();
  const executions = rows.reduce((sum, run) => sum + run.executions.length, 0);

  useEffect(() => {
    window.localStorage.setItem(DASHBOARD_LAYOUT_KEY, serializeLayout(widgets));
  }, [widgets]);

  return (
    <EntityPage
      icon={LayoutDashboard}
      title="Dashboard"
      meta={
        <>
          <span>{rows.length} runs</span>
          <span>{executions} executions</span>
          {activeWorkspace ? <span>{activeWorkspace.label}</span> : null}
          {lastSyncedAt ? <span>synced {formatRelative(lastSyncedAt.toISOString())}</span> : null}
        </>
      }
      actions={
        <>
          <DashboardToolbar
            arranging={arranging}
            widgets={widgets}
            onArranging={setArranging}
            onWidgets={setWidgets}
          />
          <WorkbenchIconAction label="Open runs" kind="primary" size="default" asChild>
            <Link to="/runs">
              <ArrowUpRight className="size-3.5" />
            </Link>
          </WorkbenchIconAction>
        </>
      }
    >
      <div className="min-h-0 flex-1 overflow-y-auto">
        {loading && rows.length === 0 ? (
          <WorkbenchOperationState
            kind="loading"
            title="Loading workspace status"
            skeletonRows={5}
          />
        ) : (
          <>
            {error ? (
              <WorkbenchOperationState
                kind="error"
                density="compact"
                title="Could not load dashboard runs"
                detail={error}
                action={<WorkbenchRetryAction onClick={refresh} />}
              />
            ) : null}
            {truncated ? (
              <div className="flex items-center gap-2 border-b border-status-warning/30 bg-status-warning-soft px-4 py-2 text-micro text-status-warning-foreground">
                <TriangleAlert className="size-icon-sm" />
                <span>Run inventory is truncated; open Runs to narrow the dataset.</span>
              </div>
            ) : null}
            <DashboardCanvas>
              <DashboardGrid
                widgets={widgets}
                arranging={arranging}
                wide={wide}
                onWidgets={setWidgets}
                renderWidget={(widget) => <DashboardWidgetBody widget={widget} rows={rows} />}
              />
            </DashboardCanvas>
          </>
        )}
      </div>
    </EntityPage>
  );
};
