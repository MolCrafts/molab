import { useIsFetching } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { AppShell } from "@/app/layout/AppShell";
import { ErrorBoundary } from "@/app/layout/ErrorBoundary";
import { OAuthCallbackPage } from "@/app/oauth/OAuthCallbackPage";
import { workspaceApi } from "@/app/state/api";
import { useInvalidate, useWorkspaceChangeStream, viewInvalidations } from "@/app/state/queries";
import { getLeftPanelViewFromPath, useNavigationState } from "@/app/state/useNavigationState";
import { useWorkspaceState } from "@/app/state/useWorkspaceState";
import type { InspectorTarget, LeftPanelView, Selection } from "@/app/types";

/** True while any query the active view reads is in flight (status-strip only). */
const useViewIsFetching = (view: LeftPanelView): boolean => {
  const specs = viewInvalidations(view);
  const count = useIsFetching({
    predicate: (query) =>
      specs.some((spec) =>
        spec.predicate
          ? spec.predicate(query)
          : (spec.queryKey?.every((segment, index) => Object.is(segment, query.queryKey[index])) ??
            false),
      ),
  });
  return count > 0;
};

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
// mount on non-OAuth routes — App's early return for /oauth-callback must not
// skip hooks within the same component (Rules of Hooks).
const WorkspaceApp = ({ pathname }: { pathname: string }): JSX.Element => {
  const activeView = getLeftPanelViewFromPath(pathname);
  // One `EventSource` for the whole app: the server pushes `{kind, ref, seq}`
  // and the cache invalidates exactly the affected keys. While it is connected
  // every list query's fallback interval collapses to `false` (see
  // `useFallbackInterval`), so a quiet workspace issues no periodic requests
  // at all. A disconnect flips the fallbacks back on automatically.
  useWorkspaceChangeStream();
  const {
    snapshot,
    status,
    error,
    refresh,
    sliceErrors,
    expandDirectory,
    expandProject,
    expandExperiment,
    isProjectExpanded,
    isExperimentExpanded,
  } = useWorkspaceState(activeView);
  const { afterFsWrite, afterWorkspaceSwitch, invalidateView } = useInvalidate();
  const { leftPanelView, selection, setLeftPanelView, setSelection } = useNavigationState(snapshot);
  const [inspectorTarget, setInspectorTarget] = useState<InspectorTarget>(
    buildDefaultInspectorTarget(selection),
  );

  useEffect(() => {
    setInspectorTarget(buildDefaultInspectorTarget(selection));
  }, [selection]);

  if (error) {
    throw error;
  }

  const handleSelectionChange = (nextSelection: Selection): void => {
    setSelection(nextSelection);
  };

  const handleOpenWorkspace = async (
    path: string,
    options?: { createIfMissing?: boolean },
  ): Promise<void> => {
    await workspaceApi.openWorkspace(path, options?.createIfMissing ?? false);
    // A different workspace invalidates everything workspace-bound; the
    // bootstrap queries refetch themselves.
    await afterWorkspaceSwitch();
  };

  // A new file or directory changes exactly one listing — its parent's.
  const handleCreateDirectory = async (path: string): Promise<void> => {
    await workspaceApi.createDirectory(path);
    await afterFsWrite(path);
  };

  const handleCreateFile = async (path: string): Promise<void> => {
    await workspaceApi.writeFile(path, "");
    await afterFsWrite(path);
  };

  // The toolbar refresh button targets only the data the active view actually
  // reads — the runs view reads the runs index, everything else the workspace
  // snapshot — so it never refetches the whole workspace to update one list.
  const handleActiveRefresh = useCallback((): void => {
    if (activeView === "runs") {
      void invalidateView("runs");
      return;
    }
    refresh();
  }, [activeView, refresh, invalidateView]);

  // Background revalidation shows in the heartbeat, not as a blocked shell:
  // the first load is `status === "loading"`, everything after is a fetch count
  // scoped to the queries this view actually reads.
  const viewFetching = useViewIsFetching(activeView);
  const isRefreshing = status === "loading" || viewFetching;

  // Sync / mutation tips land only in the bottom status strip (heartbeat +
  // activity region). No floating "Syncing…" cards — aligned with MolVis.
  return (
    <ErrorBoundary>
      <AppShell
        leftPanelView={leftPanelView}
        selection={selection}
        snapshot={snapshot}
        sliceErrors={sliceErrors}
        inspectorTarget={inspectorTarget}
        isRefreshing={isRefreshing}
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
        onWorkspaceRefresh={refresh}
        onActiveRefresh={handleActiveRefresh}
      />
    </ErrorBoundary>
  );
};

const App = (): JSX.Element => {
  const location = useLocation();
  // OAuth popup target — bypass workspace boot so the page can postMessage
  // its code/state back to the opener without spinning up the whole app.
  if (location.pathname === "/oauth-callback") {
    return <OAuthCallbackPage />;
  }
  return <WorkspaceApp pathname={location.pathname} />;
};

export default App;
