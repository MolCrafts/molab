/**
 * The workspace Dashboard (Figma L01): views Overview · Plan (when a roadmap
 * exists), in the URL (`/` and `/dashboard/plan`). New project and ⋯ sit at the
 * right of the editor tab row. The runs that need a person, the ones going and
 * the ones just finished are the side bar's lists (`DashboardExplorer`), so the
 * page itself holds instruments only. Workspace problems are one band above it.
 */

import { Activity, LayoutDashboard, ListChecks, TriangleAlert } from "lucide-react";
import { type JSX, useCallback, useMemo, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { activeNeedsAuth } from "@/api/errors";
import { CreateProjectDialog } from "@/app/components/CreateProjectDialog";
import { EntityPage, ViewLabel } from "@/app/components/entity";
import { DashboardAttention } from "@/app/dashboard/DashboardAttention";
import { DashboardEditorActions } from "@/app/dashboard/DashboardEditorActions";
import {
  buildDashboardModel,
  isInventoryBlocked,
  showDashboardSkeleton,
  showTruncationStrip,
} from "@/app/dashboard/dashboardModel";
import { useWorkspaceTabVisible } from "@/app/dashboard/useWorkspaceTab";
import { WorkspaceOverview } from "@/app/dashboard/WorkspaceOverview";
import { experimentPath } from "@/app/entities/paths";
import type { NavigationLandingProps } from "@/app/navigation/sections";
import { usePreview } from "@/app/preview/PreviewContext";
import { runsHref } from "@/app/renderers/scopeStory";
import { runPresentationStatus } from "@/app/runs/projections";
import { useWorkspaceRuns } from "@/app/runs/useWorkspaceRuns";
import { useNavigationState } from "@/app/state/useNavigationState";
import { isActiveStatus } from "@/app/status/vocabulary";
import { WorkbenchOperationState } from "@/components/workbench";
import { PlanProgress, usePlanCampaigns } from "@/plugins/knowledge/PlanProgress";

type DashboardView = "overview" | "plan";

export const DASHBOARD_PLAN_PATH = "/dashboard/plan";

const viewOf = (pathname: string): DashboardView =>
  pathname === DASHBOARD_PLAN_PATH ? "plan" : "overview";

export const DashboardPage = ({ snapshot, onRefresh }: NavigationLandingProps): JSX.Element => {
  const { rows, loading, error, refresh, truncated, unreachable, lastSyncedAt } =
    useWorkspaceRuns();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const preview = usePreview();
  const { setSelection } = useNavigationState(snapshot);
  const [newProjectOpen, setNewProjectOpen] = useState(false);
  const { campaigns } = usePlanCampaigns();
  const requested = viewOf(pathname);
  const view: DashboardView =
    requested === "plan" && campaigns.length === 0 ? "overview" : requested;

  const openPlanExperiment = useCallback(
    (name: string) => {
      const experiment = snapshot.experiments.find(
        (item) => item.name === name || item.path.endsWith(`/${name}`),
      );
      if (experiment) void navigate(experimentPath(experiment.projectId, experiment.id));
    },
    [navigate, snapshot.experiments],
  );
  const openPlanDoc = useCallback(
    (path: string) => setSelection({ objectType: "knowledge", objectId: path }),
    [setSelection],
  );
  const openRuns = useCallback(
    (filter?: string) => {
      void navigate(runsHref(filter));
    },
    [navigate],
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
  const projects = useMemo(
    () => snapshot.projects.map((project) => ({ id: project.id, name: project.name })),
    [snapshot.projects],
  );
  const active = useMemo(
    () => rows.some((row) => isActiveStatus(runPresentationStatus(row))),
    [rows],
  );
  const skeleton =
    (waitingForCode && rows.length === 0) ||
    showDashboardSkeleton({
      loading,
      rowCount: rows.length,
      synced: lastSyncedAt !== null,
      blocked,
    });
  const workspaceTab = useWorkspaceTabVisible(snapshot);

  if (!workspaceTab) {
    return <Navigate to="/projects" replace />;
  }

  const partial = blocked || showTruncationStrip(truncated, error);
  const overview = skeleton ? (
    <WorkbenchOperationState kind="loading" title="Loading workspace status" skeletonRows={5} />
  ) : (
    <WorkspaceOverview
      rows={rows}
      projects={projects}
      known={snapshot.runs}
      partial={partial}
      inventoryBlocked={blocked}
      onOpenRuns={openRuns}
      onPreviewProject={(projectId) => preview.preview({ kind: "project", projectId })}
      onNewProject={() => setNewProjectOpen(true)}
    />
  );

  const tabs = [
    {
      value: "overview",
      label: <ViewLabel icon={Activity}>Overview</ViewLabel>,
      content: overview,
    },
    ...(campaigns.length > 0
      ? [
          {
            value: "plan",
            label: <ViewLabel icon={ListChecks}>Plan</ViewLabel>,
            content: (
              <div className="h-full min-h-0 overflow-auto bg-background px-6 py-6">
                <PlanProgress
                  campaigns={campaigns}
                  hostLabel={(path) =>
                    snapshot.projects.find((project) => path.startsWith(`${project.path}/`))
                      ?.name ?? null
                  }
                  onOpenExperiment={openPlanExperiment}
                  onOpenDoc={openPlanDoc}
                />
              </div>
            ),
          },
        ]
      : []),
  ];

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-background">
      <DashboardAttention
        items={model.operational}
        overflow={model.operationalOverflow}
        retrying={loading}
        onRetry={refresh}
      />
      {showTruncationStrip(truncated, error) ? (
        <div className="flex h-7 min-w-0 shrink-0 items-center gap-2 border-b border-status-warning/30 bg-status-warning-soft px-6 text-label text-status-warning-foreground">
          <TriangleAlert className="size-icon-sm shrink-0" aria-hidden />
          <span className="min-w-0 truncate">
            Partial results · the newest {rows.length} runs are counted
          </span>
        </div>
      ) : null}
      <div className="min-h-0 flex-1">
        <EntityPage
          icon={LayoutDashboard}
          title="Dashboard"
          actions={
            <DashboardEditorActions
              active={active}
              syncing={loading}
              onNewProject={() => setNewProjectOpen(true)}
              onOpenRuns={() => openRuns()}
              onOpenProjects={() => void navigate("/projects")}
              onSync={() => {
                refresh();
                onRefresh();
              }}
            />
          }
          activeTab={view}
          onActiveTabChange={(next) => void navigate(next === "plan" ? DASHBOARD_PLAN_PATH : "/")}
          tabs={tabs}
        />
      </div>
      <CreateProjectDialog
        open={newProjectOpen}
        onOpenChange={setNewProjectOpen}
        showTrigger={false}
        onProjectCreated={onRefresh}
      />
    </div>
  );
};
