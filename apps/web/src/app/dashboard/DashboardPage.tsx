import { ListTodo, PanelsTopLeft, TriangleAlert } from "lucide-react";
import { type JSX, useCallback, useMemo, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { activeNeedsAuth } from "@/api/errors";
import {
  DashboardCanvas,
  EntityTabBar,
  EntityTabContent,
  EntityTabs,
  OverviewSurface,
} from "@/app/components/entity";
import { DashboardAttention } from "@/app/dashboard/DashboardAttention";
import {
  buildDashboardModel,
  hasMeasurableExecutions,
  isInventoryBlocked,
  showDashboardGrid,
  showDashboardSkeleton,
  showTruncationStrip,
} from "@/app/dashboard/dashboardModel";
import { attentionRuns, NeedsAttention, RunTimeline } from "@/app/dashboard/dashboardWidgets";
import { ExecutionOverview } from "@/app/dashboard/ExecutionOverview";
import { useWorkspaceTabVisible } from "@/app/dashboard/useWorkspaceTab";
import { experimentPath, projectPath } from "@/app/entities/paths";
import type { NavigationLandingProps } from "@/app/navigation/sections";
import { useWorkspaceRuns } from "@/app/runs/useWorkspaceRuns";
import { useNavigationState } from "@/app/state/useNavigationState";
import { WorkbenchIconAction, WorkbenchOperationState } from "@/components/workbench";
import { PlanProgress } from "@/plugins/knowledge/PlanProgress";

type DashboardTab = "overview" | "attention" | "timeline";

const isDashboardTab = (value: string): value is DashboardTab =>
  value === "overview" || value === "attention" || value === "timeline";

export const DashboardPage = ({ snapshot }: NavigationLandingProps): JSX.Element => {
  const { rows, loading, error, refresh, truncated, unreachable, lastSyncedAt } =
    useWorkspaceRuns();
  const [tab, setTab] = useState<DashboardTab>("overview");
  const navigate = useNavigate();
  const { setSelection } = useNavigationState(snapshot);
  const openPlanExperiment = useCallback(
    (name: string) => {
      const experiment = snapshot.experiments.find((item) => item.name === name);
      if (experiment) navigate(experimentPath(experiment.projectId, experiment.id));
    },
    [navigate, snapshot.experiments],
  );
  const openPlanDoc = useCallback(
    (path: string) => setSelection({ objectType: "knowledge", objectId: path }),
    [setSelection],
  );
  const waitingForCode = activeNeedsAuth(snapshot.workspaces);
  const reportRunsError = loading || waitingForCode ? null : error;
  const blocked = isInventoryBlocked(snapshot, {
    runsError: reportRunsError,
    unreachableKeys: unreachable,
  });
  const model = useMemo(
    () =>
      buildDashboardModel(snapshot, rows, {
        runsError: reportRunsError,
        truncated,
        unreachableKeys: unreachable,
      }),
    [snapshot, rows, reportRunsError, truncated, unreachable],
  );
  const flaggedCount = useMemo(() => attentionRuns(rows).length, [rows]);
  const openProject = useCallback((id: string) => navigate(projectPath(id)), [navigate]);
  const skeleton =
    (waitingForCode && rows.length === 0) ||
    showDashboardSkeleton({
      loading,
      rowCount: rows.length,
      synced: lastSyncedAt !== null,
      blocked,
    });
  const workspaceTab = useWorkspaceTabVisible(snapshot);
  const instruments = showDashboardGrid(blocked, rows.length) && hasMeasurableExecutions(rows);

  if (!workspaceTab) {
    return <Navigate to="/projects" replace />;
  }

  const quiet = !skeleton && !instruments && !blocked;

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-background">
      <header className="flex min-h-8 shrink-0 items-center gap-x-3 border-b border-border/60 bg-background px-4 py-1">
        <h1 className="min-w-0 text-body font-medium text-foreground">Dashboard</h1>
      </header>
      <DashboardAttention
        items={model.operational}
        overflow={model.operationalOverflow}
        retrying={loading}
        onRetry={refresh}
      />
      {showTruncationStrip(truncated, error) ? (
        <div className="flex min-w-0 shrink-0 flex-wrap items-center gap-x-3 gap-y-2 border-b border-status-warning/30 bg-status-warning-soft px-4 py-2 text-label text-status-warning-foreground">
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
      {skeleton ? (
        <div className="min-h-0 flex-1 overflow-y-auto">
          <WorkbenchOperationState
            kind="loading"
            title="Loading workspace status"
            skeletonRows={5}
          />
        </div>
      ) : quiet ? (
        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-8">
          <PlanProgress onOpenExperiment={openPlanExperiment} onOpenDoc={openPlanDoc} />
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
      ) : instruments ? (
        <EntityTabs
          value={tab}
          onValueChange={(next) => {
            if (isDashboardTab(next)) setTab(next);
          }}
        >
          <EntityTabBar
            tabs={[
              { value: "overview", label: "Overview" },
              {
                value: "attention",
                label: flaggedCount > 0 ? `Attention (${flaggedCount})` : "Attention",
              },
              { value: "timeline", label: "Timeline" },
            ]}
          />
          <EntityTabContent value="overview">
            <OverviewSurface>
              <DashboardCanvas className="px-4 py-6 sm:px-8 sm:py-8">
                <PlanProgress onOpenExperiment={openPlanExperiment} onOpenDoc={openPlanDoc} />
                <ExecutionOverview
                  rows={rows}
                  partial={truncated}
                  inventoryBlocked={blocked}
                  groupBy="project"
                  onGroupSelect={openProject}
                  onOpenAttention={() => setTab("attention")}
                  onOpenTimeline={() => setTab("timeline")}
                />
              </DashboardCanvas>
            </OverviewSurface>
          </EntityTabContent>
          <EntityTabContent value="attention">
            <OverviewSurface>
              <DashboardCanvas className="px-4 py-6 sm:px-8 sm:py-8">
                <div className="mx-auto w-full max-w-6xl">
                  <NeedsAttention rows={rows} inventoryBlocked={blocked} />
                </div>
              </DashboardCanvas>
            </OverviewSurface>
          </EntityTabContent>
          <EntityTabContent value="timeline">
            <OverviewSurface>
              <DashboardCanvas className="px-4 py-6 sm:px-8 sm:py-8">
                <div className="mx-auto w-full max-w-6xl">
                  <RunTimeline rows={rows} inventoryBlocked={blocked} />
                </div>
              </DashboardCanvas>
            </OverviewSurface>
          </EntityTabContent>
        </EntityTabs>
      ) : null}
    </div>
  );
};
