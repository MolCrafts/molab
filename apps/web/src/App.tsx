import { useEffect, useState, useSyncExternalStore } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { workspaceApi } from "@/api";
import { AuthGate, AuthProvider, LoginPage } from "@/app/auth";
import { useWorkspaceTabVisible } from "@/app/dashboard/useWorkspaceTab";
import { experimentPath, projectPath, runPath } from "@/app/entities/paths";
import { AppShell } from "@/app/layout/AppShell";
import { ErrorBoundary } from "@/app/layout/ErrorBoundary";
import { RouteProfiler } from "@/app/layout/RouteProfiler";
import { prefetchPrimaryNavigationOnIdle } from "@/app/navigation/prefetch";
import { navigationVisibleAtScope } from "@/app/navigation/sections";
import { prefetchRenderer } from "@/app/renderers/lazyRenderers";
import { useWorkspaceRuns } from "@/app/runs/useWorkspaceRuns";
import {
  getLeftPanelViewFromPath,
  hierarchyRouteContextFromPath,
  useNavigationState,
} from "@/app/state/useNavigationState";
import { useWorkspaceState } from "@/app/state/useWorkspaceState";
import { getWorkspaceQueryScope, onWorkspaceSwitching } from "@/app/state/workspaceSwitchEvents";
import type { InspectorTarget, Selection } from "@/app/types";
import { prefetchMarkdown } from "@/components/ui/markdown";
import { prefetchOnIdle } from "@/lib/lazy-with-prefetch";

const buildDefaultInspectorTarget = (selection: Selection | null): InspectorTarget => {
  if (!selection) {
    return { kind: "object", objectType: "project", objectId: "" };
  }

  return {
    kind: "object",
    objectType: selection.objectType,
    objectId: selection.objectId,
  };
};

// Workspace-backed app tree. Kept as a separate component so its hooks only
// mount on non-login routes.
const WorkspaceApp = ({ pathname }: { pathname: string }): JSX.Element => {
  const navigate = useNavigate();
  const activeView = getLeftPanelViewFromPath(pathname);
  const {
    snapshot,
    status,
    error,
    refresh,
    dataEpoch,
    expandDirectory,
    expandProject,
    expandExperiment,
    isProjectExpanded,
    isExperimentExpanded,
  } = useWorkspaceState(activeView);
  const workspaceTab = useWorkspaceTabVisible(snapshot);
  // Subscribe to the runs poller only when the user is on an operational runs surface; the
  // hook still gives us a refresh handle even when disabled so manual refresh
  // works regardless of polling state.
  const runs = useWorkspaceRuns({ enabled: activeView === "runs" || activeView === "dashboard" });
  const { leftPanelView, selection, setLeftPanelView, setSelection } = useNavigationState(snapshot);
  const panelView = leftPanelView === "dashboard" && !workspaceTab ? "projects" : leftPanelView;
  const hierarchyRoute = hierarchyRouteContextFromPath(pathname);
  const routeProjectId = hierarchyRoute?.projectId ?? null;
  const routeExperimentId = hierarchyRoute?.experimentId ?? null;
  const [inspectorTarget, setInspectorTarget] = useState<InspectorTarget>(
    buildDefaultInspectorTarget(selection),
  );

  useEffect(() => {
    const scope = snapshot.serveScope;
    if (!scope || navigationVisibleAtScope(leftPanelView, scope.kind)) return;
    const target =
      scope.kind === "workspace.project"
        ? projectPath(scope.id)
        : scope.kind === "workspace.experiment"
          ? experimentPath("", scope.id)
          : scope.kind === "workspace.run"
            ? runPath("", "", scope.id)
            : null;
    if (target && target !== pathname) navigate(target, { replace: true });
  }, [leftPanelView, navigate, pathname, snapshot.serveScope]);

  useEffect(() => {
    if (leftPanelView === "dashboard" && !workspaceTab && pathname !== "/projects") {
      navigate("/projects", { replace: true });
    }
  }, [leftPanelView, navigate, pathname, workspaceTab]);

  useEffect(() => {
    prefetchPrimaryNavigationOnIdle();
    prefetchOnIdle(() => {
      prefetchRenderer("project");
      prefetchRenderer("experiment");
      prefetchRenderer("run");
      prefetchMarkdown();
    });
  }, []);

  // A canonical deep link contains its parent ids even before the shallow
  // workspace catalog does. Hydrate that chain in dependency order so opening
  // an Experiment or Run URL never resolves to a misleading "not found" shell.
  useEffect(() => {
    if (!routeProjectId) return;
    let cancelled = false;
    void expandProject(routeProjectId).then(() => {
      if (!cancelled && routeExperimentId) {
        void expandExperiment(routeProjectId, routeExperimentId);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [expandExperiment, expandProject, routeExperimentId, routeProjectId]);

  useEffect(() => {
    setInspectorTarget(buildDefaultInspectorTarget(selection));
  }, [selection]);

  // Preserve old shared links without keeping Workflow as a competing top-level
  // workspace. Once its owner is available, replace `/workflows/:id` with the
  // canonical experiment-scoped Workflow tab.
  useEffect(() => {
    if (selection?.objectType !== "workflow") return;
    const workflow = snapshot.workflows.find((item) => item.id === selection.workflowId);
    const experiment = workflow
      ? snapshot.experiments.find((item) => item.id === workflow.experimentId)
      : undefined;
    if (!experiment) return;
    setSelection({
      objectType: "experiment",
      objectId: experiment.id,
      experimentView: "workflow",
    });
  }, [selection, setSelection, snapshot.experiments, snapshot.workflows]);

  const handleSelectionChange = (nextSelection: Selection): void => {
    setSelection(nextSelection);
  };

  const handleOpenWorkspace = async (
    path: string,
    options?: { createIfMissing?: boolean },
  ): Promise<void> => {
    await workspaceApi.openWorkspace(path, options?.createIfMissing ?? false);
    refresh();
  };

  const handleCreateDirectory = async (path: string): Promise<void> => {
    await workspaceApi.createDirectory(path);
    refresh();
  };

  const handleCreateFile = async (path: string): Promise<void> => {
    await workspaceApi.writeFile(path, "");
    refresh();
  };

  // The toolbar refresh button targets only the data the active view actually
  // reads — runs view pulls from the runs poller; everything else reads from
  // the workspace snapshot.
  const handleActiveRefresh = refresh;

  const isRefreshing =
    activeView === "runs" || activeView === "dashboard" ? runs.loading : status === "loading";

  // Sync / mutation tips land only in the bottom status strip (heartbeat +
  // activity region). No floating "Syncing…" cards — aligned with MolVis.
  return (
    <ErrorBoundary>
      <AppShell
        leftPanelView={panelView}
        selection={selection}
        snapshot={snapshot}
        inspectorTarget={inspectorTarget}
        isRefreshing={isRefreshing}
        loadError={error}
        onLeftPanelViewChange={setLeftPanelView}
        onSelectionChange={handleSelectionChange}
        onInspectorTargetChange={setInspectorTarget}
        onOpenWorkspace={handleOpenWorkspace}
        onCreateDirectory={handleCreateDirectory}
        onCreateFile={handleCreateFile}
        onExpandDirectory={(path) => {
          void expandDirectory(path);
        }}
        onExpandProject={(projectId) => {
          void expandProject(projectId);
        }}
        onExpandExperiment={(projectId, experimentId) => {
          void expandExperiment(projectId, experimentId);
        }}
        isProjectExpanded={isProjectExpanded}
        isExperimentExpanded={isExperimentExpanded}
        dataEpoch={dataEpoch}
        onWorkspaceRefresh={refresh}
        onActiveRefresh={handleActiveRefresh}
      />
    </ErrorBoundary>
  );
};

const App = (): JSX.Element => {
  const location = useLocation();
  const workspaceScope = useSyncExternalStore(
    onWorkspaceSwitching,
    getWorkspaceQueryScope,
    getWorkspaceQueryScope,
  );
  const content = (
    <AuthProvider>
      {location.pathname === "/login" ? (
        <LoginPage />
      ) : (
        <AuthGate>
          <WorkspaceApp key={workspaceScope} pathname={location.pathname} />
        </AuthGate>
      )}
    </AuthProvider>
  );
  return <RouteProfiler id={location.pathname}>{content}</RouteProfiler>;
};

export default App;
