import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { GlobalCommandPalette } from "@/app/entities/GlobalCommandPalette";
import { ContextBar } from "@/app/layout/ContextBar";
import { RemoteConnectDialog } from "@/app/layout/RemoteConnectDialog";
import { getNavigationContribution } from "@/app/navigation/sections";
import { CenterPanel } from "@/app/panels/CenterPanel";
import type { InspectorSurfaceRegistration } from "@/app/panels/inspectorSurface";
import { LeftPanel } from "@/app/panels/LeftPanel";
import { RightPanel } from "@/app/panels/RightPanel";
import { resolveRenderersForSelection } from "@/app/registry";
import { type InspectedTask, InspectedTaskContext } from "@/app/state/inspectedTask";
import type { InspectorTarget, LeftPanelView, Selection, WorkspaceSnapshot } from "@/app/types";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { WorkbenchStatusStrip } from "@/components/workbench";
import { useIsMobile } from "@/hooks/use-is-mobile";
import { useContributionGeneration } from "@/lib/contribution-runtime";
import { listStatusBarItems, useWorkbenchGeneration } from "@/plugins/contributions/workbench";
import { setHostActions } from "@/plugins/host_actions";
import { usePluginPreferencesGeneration } from "@/plugins/preferences";
import { CommandKeymap, runCommand } from "@/plugins/ui/CommandKeymap";
import { PluginBottomPanelHost } from "@/plugins/ui/PluginBottomPanelHost";

interface AppShellProps {
  leftPanelView: LeftPanelView;
  selection: Selection | null;
  snapshot: WorkspaceSnapshot;
  inspectorTarget: InspectorTarget;
  isRefreshing: boolean;
  onLeftPanelViewChange: (view: LeftPanelView) => void;
  onSelectionChange: (selection: Selection) => void;
  onInspectorTargetChange: (target: InspectorTarget) => void;
  onOpenWorkspace: (path: string, options?: { createIfMissing?: boolean }) => Promise<void>;
  onCreateDirectory: (path: string) => void;
  onCreateFile: (path: string) => void;
  onExpandDirectory?: (dirPath: string) => void;
  onExpandProject?: (projectId: string) => void;
  onExpandExperiment?: (projectId: string, experimentId: string) => void;
  isProjectExpanded?: (projectId: string) => boolean;
  isExperimentExpanded?: (projectId: string, experimentId: string) => boolean;
  /** Bumps after refresh clears lazy entity caches — TreeView re-hydrates open folders. */
  dataEpoch?: number;
  onWorkspaceRefresh: () => void;
  onActiveRefresh: () => void;
}

const NAV_SIZE = { default: "272px", min: "216px", max: "384px" };
const INSPECTOR_SIZE = { default: "280px", min: "240px", max: "420px" };
const SHELL_PANEL_IDS = ["navigator", "workspace"];

export const AppShell = ({
  leftPanelView,
  selection,
  snapshot,
  inspectorTarget,
  isRefreshing,
  onLeftPanelViewChange,
  onSelectionChange,
  onInspectorTargetChange,
  onOpenWorkspace,
  onCreateDirectory,
  onCreateFile,
  onExpandDirectory,
  onExpandProject,
  onExpandExperiment,
  isProjectExpanded,
  isExperimentExpanded,
  dataEpoch = 0,
  onWorkspaceRefresh,
  onActiveRefresh,
}: AppShellProps): JSX.Element => {
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [inspectedTask, setInspectedTask] = useState<InspectedTask | null>(null);
  const [inspectorSurface, setInspectorSurface] = useState<InspectorSurfaceRegistration | null>(
    null,
  );
  const registeredInspectorId = useRef<string | null>(null);
  const registeredSelectionInspectorId = useRef<string | null>(null);
  const isMobile = useIsMobile();
  const contributionGeneration = useContributionGeneration();
  const pluginPreferencesGeneration = usePluginPreferencesGeneration();
  useWorkbenchGeneration();
  const railOnlyNavigation = getNavigationContribution(leftPanelView).shellMode === "rail-only";

  const inspectTask = useCallback((taskId: string, runId: string): void => {
    setInspectedTask({ taskId, runId });
    setInspectorOpen(true);
  }, []);

  const clearInspectedTask = useCallback((): void => {
    setInspectedTask(null);
  }, []);

  const handleInspectorSurfaceChange = useCallback(
    (registration: InspectorSurfaceRegistration | null): void => {
      const nextInspectorId = registration?.id ?? null;
      setInspectorSurface(registration);
      if (nextInspectorId && nextInspectorId !== registeredInspectorId.current) {
        setInspectorOpen(true);
      }
      registeredInspectorId.current = nextInspectorId;
    },
    [],
  );

  const inspectedTaskContext = useMemo(
    () => ({ inspectedTask, inspectTask, clearInspectedTask }),
    [inspectedTask, inspectTask, clearInspectedTask],
  );

  const pinnedTaskActive =
    inspectedTask !== null &&
    ((selection?.objectType === "run" && selection.objectId === inspectedTask.runId) ||
      selection?.objectType === "workflow" ||
      selection?.objectType === "experiment");

  const selectionInspectorId = useMemo(() => {
    void contributionGeneration;
    void pluginPreferencesGeneration;
    if (selection?.objectType !== "run") return null;
    const renderer = resolveRenderersForSelection(selection, snapshot, "right").find(
      (candidate) => candidate.pluginId && candidate.pluginId !== "core",
    );
    return renderer?.id ?? null;
  }, [contributionGeneration, pluginPreferencesGeneration, selection, snapshot]);

  useEffect(() => {
    const nextId = selectionInspectorId
      ? `${selectionInspectorId}:${selection?.objectId ?? ""}`
      : null;
    if (nextId && nextId !== registeredSelectionInspectorId.current) {
      setInspectorOpen(true);
    }
    registeredSelectionInspectorId.current = nextId;
  }, [selection?.objectId, selectionInspectorId]);

  const inspectorSelection: Selection | null =
    inspectedTask && pinnedTaskActive
      ? {
          objectType: "task",
          taskId: inspectedTask.taskId,
          runId: inspectedTask.runId,
          objectId: inspectedTask.taskId,
        }
      : selectionInspectorId
        ? selection
        : null;

  // The right side is contextual chrome, not a permanent second details page.
  // It is available only when a feature explicitly registers a task/run surface,
  // a workflow task has been pinned, or a plugin owns a contextual run inspector.
  const hasInspectorContent = Boolean(inspectorSurface || inspectorSelection);
  const inspectorVisible = inspectorOpen && hasInspectorContent;
  const inspectorPanelIds = useMemo(
    () => (inspectorVisible ? ["work-surface", "inspector"] : ["work-surface"]),
    [inspectorVisible],
  );

  const activeWorkspace = useMemo(
    () => snapshot.workspaces.find((w) => w.active) ?? snapshot.workspaces[0] ?? null,
    [snapshot.workspaces],
  );

  // Auto-open the OTP dialog when the active remote workspace is unreachable.
  const [connectOpen, setConnectOpen] = useState(false);
  useEffect(() => {
    const key = activeWorkspace?.key;
    if (
      key &&
      activeWorkspace?.isRemote &&
      (activeWorkspace.unreachable || activeWorkspace.needsAuth)
    ) {
      setConnectOpen(true);
    } else {
      setConnectOpen(false);
    }
  }, [
    activeWorkspace?.key,
    activeWorkspace?.isRemote,
    activeWorkspace?.unreachable,
    activeWorkspace?.needsAuth,
  ]);

  /** Heartbeat / palette: re-auth if remote needs it, else hard reload. */
  const handleReconnect = useCallback(() => {
    if (activeWorkspace?.isRemote) {
      setConnectOpen(true);
      return;
    }
    onWorkspaceRefresh();
  }, [activeWorkspace?.isRemote, onWorkspaceRefresh]);

  useLayoutEffect(() => {
    setHostActions({
      reloadWindow: onWorkspaceRefresh,
      reloadActiveView: onActiveRefresh,
      reconnectRemote: () => setConnectOpen(true),
      isRemote: () => Boolean(activeWorkspace?.isRemote),
    });
  }, [activeWorkspace?.isRemote, onWorkspaceRefresh, onActiveRefresh]);

  const statusBarExtras = listStatusBarItems();

  const handleNavSelect = useCallback(
    (next: Selection): void => {
      onSelectionChange(next);
      setMobileNavOpen(false);
    },
    [onSelectionChange],
  );

  const navContent = (
    <LeftPanel
      view={leftPanelView}
      selection={selection}
      snapshot={snapshot}
      onViewChange={onLeftPanelViewChange}
      onSelect={isMobile ? handleNavSelect : onSelectionChange}
      onOpenWorkspace={onOpenWorkspace}
      onCreateDirectory={onCreateDirectory}
      onCreateFile={onCreateFile}
      onExpandDirectory={onExpandDirectory}
      onExpandProject={onExpandProject}
      onExpandExperiment={onExpandExperiment}
      isProjectExpanded={isProjectExpanded}
      isExperimentExpanded={isExperimentExpanded}
      dataEpoch={dataEpoch}
      onRefresh={onWorkspaceRefresh}
    />
  );

  const centerContent = (
    <div className="flex h-full min-h-0 flex-col">
      <div className="min-h-0 flex-1 overflow-hidden bg-canvas">
        <CenterPanel
          selection={selection}
          snapshot={snapshot}
          leftPanelView={leftPanelView}
          inspectorTarget={inspectorTarget}
          onInspectorTargetChange={onInspectorTargetChange}
          onInspectorChange={handleInspectorSurfaceChange}
          onRefresh={onWorkspaceRefresh}
        />
      </div>
    </div>
  );

  const inspectorContent = inspectorSurface ? (
    inspectorSurface.render({ className: "border-l-0 bg-surface-subtle" })
  ) : (
    <RightPanel
      selection={inspectorSelection}
      snapshot={snapshot}
      inspectorTarget={inspectorTarget}
      onInspectorTargetChange={onInspectorTargetChange}
      onRefresh={onWorkspaceRefresh}
    />
  );

  const workbenchColumns = isMobile ? (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <div className="min-h-0 flex-1 overflow-hidden">{centerContent}</div>
      <Sheet open={mobileNavOpen} onOpenChange={setMobileNavOpen}>
        <SheetContent
          side="left"
          className={railOnlyNavigation ? "w-12 p-0" : "w-drawer max-w-sm p-0"}
        >
          <SheetHeader className="sr-only">
            <SheetTitle>Navigation</SheetTitle>
            <SheetDescription>Workspace tree and views</SheetDescription>
          </SheetHeader>
          <div className="h-full overflow-hidden">{navContent}</div>
        </SheetContent>
      </Sheet>
      <Sheet open={inspectorVisible} onOpenChange={setInspectorOpen}>
        <SheetContent side="right" className="w-drawer max-w-md p-0">
          <SheetHeader className="sr-only">
            <SheetTitle>Inspector</SheetTitle>
            <SheetDescription>Details for the selected object</SheetDescription>
          </SheetHeader>
          <div className="h-full overflow-hidden bg-surface-subtle">{inspectorContent}</div>
        </SheetContent>
      </Sheet>
    </div>
  ) : railOnlyNavigation ? (
    <div className="flex min-h-0 flex-1 overflow-hidden">
      <div className="h-full w-12 shrink-0 overflow-hidden border-r border-border bg-surface">
        {navContent}
      </div>
      <div className="min-w-0 flex-1 overflow-hidden">{centerContent}</div>
    </div>
  ) : (
    <ResizablePanelGroup
      id="molab-workbench-shell"
      direction="horizontal"
      autoSaveId="molab.workbench.shell"
      autoSavePanelIds={SHELL_PANEL_IDS}
      className="min-h-0 flex-1"
    >
      <ResizablePanel
        id="navigator"
        defaultSize={NAV_SIZE.default}
        minSize={NAV_SIZE.min}
        maxSize={NAV_SIZE.max}
      >
        <div className="h-full overflow-hidden border-r border-border bg-surface">{navContent}</div>
      </ResizablePanel>
      <ResizableHandle />
      <ResizablePanel id="workspace" defaultSize="calc(100% - 272px)">
        <ResizablePanelGroup
          id="molab-workbench-detail"
          direction="horizontal"
          autoSaveId="molab.workbench.detail"
          autoSavePanelIds={inspectorPanelIds}
          className="h-full"
        >
          <ResizablePanel
            id="work-surface"
            defaultSize={inspectorVisible ? "calc(100% - 280px)" : "100%"}
          >
            {centerContent}
          </ResizablePanel>
          {inspectorVisible && (
            <>
              <ResizableHandle />
              <ResizablePanel
                id="inspector"
                defaultSize={INSPECTOR_SIZE.default}
                minSize={INSPECTOR_SIZE.min}
                maxSize={INSPECTOR_SIZE.max}
              >
                <div className="mol-motion-enter-from-right h-full overflow-hidden border-l border-border bg-surface-subtle">
                  {inspectorContent}
                </div>
              </ResizablePanel>
            </>
          )}
        </ResizablePanelGroup>
      </ResizablePanel>
    </ResizablePanelGroup>
  );

  return (
    <InspectedTaskContext.Provider value={inspectedTaskContext}>
      <CommandKeymap />
      <GlobalCommandPalette snapshot={snapshot} />
      <div className="flex h-screen flex-col bg-background text-foreground">
        <ContextBar onMenuClick={isMobile ? () => setMobileNavOpen(true) : undefined} />
        {/* Work surface above a plugin bottom drawer and a 28px status bar. */}
        <main className="flex min-h-0 flex-1 flex-col overflow-hidden">
          {workbenchColumns}
          <PluginBottomPanelHost />
          <WorkbenchStatusStrip
            isRefreshing={isRefreshing}
            onRemoteIndexReady={onWorkspaceRefresh}
            activeWorkspace={activeWorkspace}
            onReconnect={handleReconnect}
            extras={statusBarExtras.map((item) => (
              <button
                key={item.id}
                type="button"
                title={item.tooltip ?? item.text}
                className="max-w-40 truncate px-1 font-mono text-micro text-statusbar-foreground/90 hover:text-statusbar-foreground"
                onClick={() => {
                  if (item.command) runCommand(item.command);
                }}
              >
                {item.text}
              </button>
            ))}
          />
        </main>
        <RemoteConnectDialog
          workspace={activeWorkspace}
          open={connectOpen}
          onOpenChange={setConnectOpen}
          onConnected={onWorkspaceRefresh}
        />
      </div>
    </InspectedTaskContext.Provider>
  );
};
