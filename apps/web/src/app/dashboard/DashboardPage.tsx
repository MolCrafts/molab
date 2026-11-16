/**
 * The workspace Dashboard (Figma L01): the Overview view, at `/`. New project
 * and ⋯ sit at the right of the editor tab row. The runs that need a person, the ones going and
 * the ones just finished are the side bar's lists (`DashboardExplorer`), so the
 * page itself holds instruments only. Workspace problems are one band above it.
 */

import { Activity, LayoutDashboard, TriangleAlert } from "lucide-react";
import { type JSX, useCallback, useMemo, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
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
import type { NavigationLandingProps } from "@/app/navigation/sections";
import { usePreview } from "@/app/preview/PreviewContext";
import { runsHref } from "@/app/renderers/scopeStory";
import { runPresentationStatus } from "@/app/runs/projections";
import { useWorkspaceRuns } from "@/app/runs/useWorkspaceRuns";
import { isActiveStatus } from "@/app/status/vocabulary";
import { WorkbenchOperationState } from "@/components/workbench";

export const DashboardPage = ({ snapshot, onRefresh }: NavigationLandingProps): JSX.Element => {
  const { rows, loading, error, refresh, truncated, unreachable, lastSyncedAt } =
    useWorkspaceRuns();
  const navigate = useNavigate();
  const preview = usePreview();
  const [newProjectOpen, setNewProjectOpen] = useState(false);
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
          activeTab="overview"
          onActiveTabChange={() => void navigate("/")}
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
