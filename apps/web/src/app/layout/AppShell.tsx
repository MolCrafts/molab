import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@molcrafts/ui";
import { useCallback, useEffect, useLayoutEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { activeNeedsAuth, shouldShowFailure } from "@/api/errors";
import { UserMenu } from "@/app/auth";
import { Breadcrumb } from "@/app/entities/Breadcrumb";
import { buildTrail } from "@/app/entities/breadcrumbTrail";
import { GlobalCommandPalette } from "@/app/entities/GlobalCommandPalette";
import { RemoteConnectDialog } from "@/app/layout/RemoteConnectDialog";
import {
  dismissRemoteAuth,
  noteRemoteAuthState,
  remoteNeedsCode,
  requestRemoteAuth,
  setRemoteAuthFallback,
  subscribeRemoteAuth,
} from "@/app/layout/remoteAuthPrompt";
import { NavigationRail } from "@/app/navigation/NavigationRail";
import { getNavigationContribution } from "@/app/navigation/sections";
import { CenterPanel } from "@/app/panels/CenterPanel";
import { LeftPanel } from "@/app/panels/LeftPanel";
import { PreviewBody, PreviewOverlay } from "@/app/preview/Preview";
import { PreviewProvider } from "@/app/preview/PreviewContext";
import { type PreviewTarget, previewOverlaysEditor } from "@/app/preview/target";
import { describeEditorTab } from "@/app/shell/describeEditorTab";
import { EditorTabStrip } from "@/app/shell/EditorTabStrip";
import { EditorActionsSlotProvider } from "@/app/shell/editorActions";
import { focusShellRegion } from "@/app/shell/focusRegions";
import { ConnectionBanner, MobileAppBar } from "@/app/shell/MobileChrome";
import { useShellLayout } from "@/app/shell/shellLayout";
import { TitleBar } from "@/app/shell/TitleBar";
import { useEditorTabs } from "@/app/shell/useEditorTabs";
import { ATTENTION_STATUSES, useShellSignals } from "@/app/shell/useShellSignals";
import { useTabSnapshot } from "@/app/shell/useTabSnapshot";
import { EntityExpansionProvider } from "@/app/state/entityExpansion";
import type {
  InspectorTarget,
  LeftPanelView,
  Selection,
  ServedWorkspaceSummary,
  WorkspaceSnapshot,
} from "@/app/types";
import { NotificationHost } from "@/components/notifications/NotificationHost";
import {
  WorkbenchOperationState,
  WorkbenchRetryAction,
  WorkbenchStatusStrip,
} from "@/components/workbench";
import { useIsMobile } from "@/hooks/use-is-mobile";
import { useContributionGeneration } from "@/lib/contribution-runtime";
import { buildMolabRefIndex } from "@/lib/entity-linkify";
import { MolabRefIndexContext } from "@/lib/molab-ref-context";
import { shortWorkspaceLabel } from "@/lib/workspace-path";
import { listStatusBarItems, useWorkbenchGeneration } from "@/plugins/contributions/workbench";
import { setHostActions } from "@/plugins/host_actions";
import { usePluginPreferencesGeneration } from "@/plugins/preferences";
import { CommandKeymap, runCommand } from "@/plugins/ui/CommandKeymap";
import {
  PluginBottomPanelHost,
  useBottomPanelOpenRequests,
  useHasBottomPanels,
} from "@/plugins/ui/PluginBottomPanelHost";

interface AppShellProps {
  leftPanelView: LeftPanelView;
  selection: Selection | null;
  snapshot: WorkspaceSnapshot;
  inspectorTarget: InspectorTarget;
  isRefreshing: boolean;
  loadError?: Error | null;
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

/** L00: side bar 248 (200–480); panel 220 (120–60%). Sizes persist per key. */
const SIDE_BAR_SIZE = { default: "248px", min: "200px", max: "480px" };
const PANEL_SIZE = { default: "220px", min: "120px", max: "60%" };
/** Below this width (and above phones) the side bar opens as a drawer. */
const DOCKED_SIDE_BAR_MIN = 1024;

/** A row divider out of the vertical-by-default handle. */
const HORIZONTAL_HANDLE =
  "h-px w-full after:inset-x-0 after:left-0 after:top-1/2 after:bottom-auto after:h-1 after:w-full after:translate-x-0 after:-translate-y-1/2 hover:bg-accent/60";

export const AppShell = ({
  leftPanelView,
  selection,
  snapshot,
  inspectorTarget,
  isRefreshing,
  loadError,
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
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  /** The one Preview (L12): what a single click shows, over the editor. */
  const [previewTarget, setPreviewTarget] = useState<PreviewTarget | null>(null);
  const isMobile = useIsMobile();
  const isNarrow = useIsMobile(DOCKED_SIDE_BAR_MIN);
  const layout = useShellLayout();
  const editorTabs = useEditorTabs(selection, leftPanelView, snapshot);
  const hasPanels = useHasBottomPanels();
  const signals = useShellSignals();
  const navigate = useNavigate();
  const location = useLocation();
  const [actionsSlot, setActionsSlot] = useState<HTMLDivElement | null>(null);
  const [sideBarDrawerOpen, setSideBarDrawerOpen] = useState(false);
  useContributionGeneration();
  usePluginPreferencesGeneration();
  useWorkbenchGeneration();

  // VS Code: the activity bar switches the side bar, not the editor. A section
  // with a page of its own (Dashboard, Runs, Settings) opens it as a tab; an
  // explorer-only section just shows its explorer while a tab stays open. The
  // choice holds until the next navigation, then the side bar follows the
  // active editor again.
  const currentPath = `${location.pathname}${location.search}`;
  const [sideBarChoice, setSideBarChoice] = useState<{ view: LeftPanelView; path: string } | null>(
    null,
  );
  const sideBarView =
    sideBarChoice && sideBarChoice.path === currentPath ? sideBarChoice.view : leftPanelView;
  const railOnlyNavigation = getNavigationContribution(sideBarView).shellMode === "rail-only";

  const activeWorkspace = useMemo(
    () => snapshot.workspaces.find((w) => w.active) ?? snapshot.workspaces[0] ?? null,
    [snapshot.workspaces],
  );

  // Verification-code prompt. Probes open it; Esc dismisses until the host
  // is healthy again. A reconnect gesture always opens it. Do not close it
  // just because a later snapshot has not caught up yet.
  const [connectWorkspace, setConnectWorkspace] = useState<ServedWorkspaceSummary | null>(null);
  const [connectOpen, setConnectOpen] = useState(false);
  useEffect(
    () =>
      subscribeRemoteAuth((workspace) => {
        setConnectWorkspace(workspace);
        setConnectOpen(true);
      }),
    [],
  );
  useEffect(() => {
    setRemoteAuthFallback(activeWorkspace);
    if (activeWorkspace) noteRemoteAuthState(activeWorkspace);
  }, [
    activeWorkspace,
    activeWorkspace?.key,
    activeWorkspace?.isRemote,
    activeWorkspace?.unreachable,
    activeWorkspace?.needsAuth,
  ]);
  useEffect(() => {
    if (!connectOpen || !connectWorkspace || !remoteNeedsCode(connectWorkspace)) return;
    const current = snapshot.workspaces.find((workspace) => workspace.key === connectWorkspace.key);
    if (current?.isRemote && !remoteNeedsCode(current)) {
      setConnectOpen(false);
    }
  }, [connectOpen, connectWorkspace, snapshot.workspaces]);

  const connectionTrouble = activeWorkspace?.needsAuth
    ? "Verification code needed to reach the workspace"
    : activeWorkspace?.unreachable
      ? "Live updates paused — reconnecting"
      : null;

  /** Heartbeat / palette: re-auth if remote needs it, else hard reload. */
  const handleReconnect = useCallback(() => {
    if (activeWorkspace?.isRemote) {
      requestRemoteAuth(activeWorkspace, "gesture");
      return;
    }
    onWorkspaceRefresh();
  }, [activeWorkspace, onWorkspaceRefresh]);

  const sideBarDocked = !isMobile && !isNarrow;
  const toggleSideBar = useCallback(() => {
    if (sideBarDocked) layout.toggle("sideBarVisible");
    else if (isMobile) setMobileNavOpen((open) => !open);
    else setSideBarDrawerOpen((open) => !open);
  }, [isMobile, layout, sideBarDocked]);
  const openPanel = useCallback(() => layout.set("panelVisible", true), [layout]);

  // Off the docked layout a Preview replaces the navigation sheet / drawer.
  useEffect(() => {
    if (!previewTarget || sideBarDocked) return;
    setMobileNavOpen(false);
    setSideBarDrawerOpen(false);
  }, [previewTarget, sideBarDocked]);

  // The side-bar drawer (768–1023) closes on Esc like any overlay.
  useEffect(() => {
    if (!sideBarDrawerOpen) return;
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "Escape") setSideBarDrawerOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [sideBarDrawerOpen]);
  useBottomPanelOpenRequests(openPanel);

  useLayoutEffect(() => {
    setHostActions({
      reloadWindow: onWorkspaceRefresh,
      reloadActiveView: onActiveRefresh,
      reconnectRemote: () => {
        if (activeWorkspace?.isRemote) requestRemoteAuth(activeWorkspace, "gesture");
      },
      isRemote: () => Boolean(activeWorkspace?.isRemote),
      toggleSideBar,
      togglePanel: () => {
        if (hasPanels) layout.toggle("panelVisible");
      },
      hasPanel: () => hasPanels,
      closeEditor: editorTabs.closeActive,
      cycleEditor: editorTabs.cycle,
      focusRegion: (delta) => focusShellRegion(delta),
    });
  }, [
    activeWorkspace,
    onWorkspaceRefresh,
    onActiveRefresh,
    toggleSideBar,
    hasPanels,
    layout,
    editorTabs.closeActive,
    editorTabs.cycle,
  ]);

  const statusBarExtras = listStatusBarItems();

  const handleNavSelect = useCallback(
    (next: Selection): void => {
      onSelectionChange(next);
      setMobileNavOpen(false);
      setSideBarDrawerOpen(false);
    },
    [onSelectionChange],
  );

  const handleActivitySelect = useCallback(
    (view: LeftPanelView): void => {
      const contribution = getNavigationContribution(view);
      const hasPage = Boolean(contribution.landing) || contribution.shellMode === "rail-only";
      // Pushed out by a right surface (< 1280): bring the side bar back first.
      // Clicking the active section again hides the side bar (VS Code).
      if (sideBarDocked && view === sideBarView && !hasPage && layout.sideBarVisible) {
        layout.set("sideBarVisible", false);
        return;
      }
      if (sideBarDocked) layout.set("sideBarVisible", true);
      else if (!isMobile && !hasPage) setSideBarDrawerOpen(true);
      if (hasPage || editorTabs.state.tabs.length === 0) {
        setSideBarChoice(null);
        if (hasPage) {
          setMobileNavOpen(false);
          setSideBarDrawerOpen(false);
        }
        onLeftPanelViewChange(view);
        return;
      }
      setSideBarChoice({ view, path: currentPath });
    },
    [
      currentPath,
      editorTabs.state.tabs.length,
      isMobile,
      layout,
      onLeftPanelViewChange,
      sideBarDocked,
      sideBarView,
    ],
  );

  const activityBar = (
    <NavigationRail
      activeId={sideBarView}
      scopeKind={snapshot.serveScope?.kind}
      snapshot={snapshot}
      onSelect={handleActivitySelect}
      account={<UserMenu />}
    />
  );

  const navContent = (
    <LeftPanel
      view={sideBarView}
      selection={selection}
      snapshot={snapshot}
      pinnedExpanded={layout.pinnedExpanded}
      onTogglePinned={() => layout.toggle("pinnedExpanded")}
      onSelect={sideBarDocked ? onSelectionChange : handleNavSelect}
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
    <div className="min-h-0 flex-1 overflow-hidden bg-canvas">
      {shouldShowFailure(loadError, {
        fetching: isRefreshing,
        needsAuth: activeNeedsAuth(snapshot.workspaces),
      }) && loadError ? (
        <WorkbenchOperationState
          kind="error"
          title="Could not load workspace"
          detail={loadError.message}
          action={<WorkbenchRetryAction onClick={onWorkspaceRefresh} />}
        />
      ) : (
        <CenterPanel
          selection={selection}
          snapshot={snapshot}
          leftPanelView={leftPanelView}
          inspectorTarget={inspectorTarget}
          onInspectorTargetChange={onInspectorTargetChange}
          onRefresh={onWorkspaceRefresh}
        />
      )}
    </div>
  );

  const trail = useMemo(
    () => buildTrail(selection, leftPanelView, snapshot),
    [selection, leftPanelView, snapshot],
  );
  const activeTab = editorTabs.state.tabs.find((tab) => tab.key === editorTabs.state.activeKey);
  const overlayOpen = previewOverlaysEditor(previewTarget, activeTab ?? null);
  // Pinning or leaving the italic tab retires a peek that belonged to it.
  useEffect(() => {
    if (previewTarget && !activeTab?.preview) setPreviewTarget(null);
  }, [activeTab, previewTarget]);
  const tabSnapshot = useTabSnapshot(snapshot);
  const activePresentation = activeTab ? describeEditorTab(activeTab, tabSnapshot) : null;
  const workspaceLabel = activeWorkspace ? shortWorkspaceLabel(activeWorkspace.label) : "molab";

  // Editor group: tab row (with the editor actions) · breadcrumb · the page.
  // The docked right slot stays beside the page until the Preview lands (L12).
  const editorMain = (
    <main
      className="flex h-full min-h-0 min-w-0 flex-col bg-background"
      aria-label="Editor"
      data-shell-region="editor"
    >
      {!isMobile && editorTabs.state.tabs.length > 0 ? (
        <EditorTabStrip
          state={editorTabs.state}
          snapshot={snapshot}
          onActivate={editorTabs.activate}
          onClose={editorTabs.close}
          onPin={editorTabs.pin}
          actionsRef={setActionsSlot}
        />
      ) : null}
      <Breadcrumb items={trail} />
      {isMobile ? (
        <>
          {connectionTrouble ? (
            <ConnectionBanner
              message={connectionTrouble}
              actionLabel={activeWorkspace?.needsAuth ? "Enter verification code" : "Reconnect"}
              onAction={handleReconnect}
            />
          ) : null}
          <div className="flex min-h-0 flex-1 flex-col">{centerContent}</div>
        </>
      ) : (
        // The Preview overlays the page; it never reflows it (L12).
        <div className="relative flex min-h-0 flex-1 flex-col">
          {centerContent}
          <PreviewOverlay
            snapshot={snapshot}
            narrow={isNarrow}
            open={overlayOpen}
            onRefresh={onWorkspaceRefresh}
          />
        </div>
      )}
    </main>
  );

  const panelShown = hasPanels && layout.panelVisible && !isMobile;
  const editorColumn = panelShown ? (
    <ResizablePanelGroup
      id="molab-shell-panel"
      direction="vertical"
      autoSaveId="molab.shell.v3.panel"
      autoSavePanelIds={["editor-main", "panel"]}
      className="h-full"
    >
      <ResizablePanel id="editor-main" minSize="120px">
        {editorMain}
      </ResizablePanel>
      <ResizableHandle className={HORIZONTAL_HANDLE} />
      <ResizablePanel
        id="panel"
        defaultSize={PANEL_SIZE.default}
        minSize={PANEL_SIZE.min}
        maxSize={PANEL_SIZE.max}
      >
        <PluginBottomPanelHost onClose={() => layout.set("panelVisible", false)} />
      </ResizablePanel>
    </ResizablePanelGroup>
  ) : (
    editorMain
  );

  // The Preview overlays the editor and never pushes the side bar out (L12).
  const sideBarShown = sideBarDocked && layout.sideBarVisible && !railOnlyNavigation;

  const workbench = isMobile ? (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      {editorMain}
      <Sheet open={mobileNavOpen} onOpenChange={setMobileNavOpen}>
        <SheetContent
          side="left"
          className="w-drawer max-w-sm p-0"
          // The scrim closes it; a corner ✕ would sit on the explorer's own actions.
          showCloseButton={false}
          // Land on the open item, not on the first rail cell (whose tooltip would pop).
          onOpenAutoFocus={(event) => {
            event.preventDefault();
            const target = event.currentTarget as HTMLElement;
            (
              target.querySelector<HTMLElement>('[role="treeitem"][tabindex="0"]') ?? target
            ).focus();
          }}
        >
          <SheetHeader className="sr-only">
            <SheetTitle>Navigation</SheetTitle>
            <SheetDescription>Workspace sections and explorer</SheetDescription>
          </SheetHeader>
          {/* Phones: rows and actions take the 44px touch floor (coarse pointer rule). */}
          <div className="flex h-full overflow-hidden [&_[data-tree-row]>div]:min-h-touch-target">
            {activityBar}
            {railOnlyNavigation ? null : <div className="min-w-0 flex-1">{navContent}</div>}
          </div>
        </SheetContent>
      </Sheet>
      {/* Phones: the same Preview as a bottom sheet (v6 frame 14). */}
      <Sheet open={overlayOpen} onOpenChange={(open) => !open && setPreviewTarget(null)}>
        <SheetContent
          side="bottom"
          className="h-viewport-tall max-h-[70%] p-0"
          showCloseButton={false}
          // Focus the sheet, not its first action (whose tooltip would pop).
          onOpenAutoFocus={(event) => {
            event.preventDefault();
            (event.currentTarget as HTMLElement).focus();
          }}
        >
          <SheetHeader className="sr-only">
            <SheetTitle>Preview</SheetTitle>
            <SheetDescription>The selected item</SheetDescription>
          </SheetHeader>
          {previewTarget ? (
            <PreviewBody
              target={previewTarget}
              snapshot={snapshot}
              onRefresh={onWorkspaceRefresh}
            />
          ) : null}
        </SheetContent>
      </Sheet>
    </div>
  ) : (
    <div className="relative flex min-h-0 flex-1 overflow-hidden">
      {activityBar}
      <ResizablePanelGroup
        id="molab-shell"
        direction="horizontal"
        autoSaveId="molab.shell.v3"
        autoSavePanelIds={sideBarShown ? ["sidebar", "editor"] : ["editor"]}
        className="min-h-0 min-w-0 flex-1"
      >
        {sideBarShown ? (
          <>
            <ResizablePanel
              id="sidebar"
              defaultSize={SIDE_BAR_SIZE.default}
              minSize={SIDE_BAR_SIZE.min}
              maxSize={SIDE_BAR_SIZE.max}
            >
              <div className="h-full overflow-hidden border-r border-border">{navContent}</div>
            </ResizablePanel>
            <ResizableHandle />
          </>
        ) : null}
        <ResizablePanel id="editor">{editorColumn}</ResizablePanel>
      </ResizablePanelGroup>
      {/* 768–1023: the side bar opens over the editor and closes on choice / Esc. */}
      {!sideBarDocked && sideBarDrawerOpen && !railOnlyNavigation ? (
        <>
          <button
            type="button"
            aria-label="Close side bar"
            className="absolute inset-0 left-12 z-20 bg-overlay-scrim/20"
            onClick={() => setSideBarDrawerOpen(false)}
          />
          <div className="absolute inset-y-0 left-12 z-30 w-shell-sidebar border-r border-border shadow-overlay">
            {navContent}
          </div>
        </>
      ) : null}
    </div>
  );

  const expansion = useMemo(
    () => ({
      expandProject: (projectId: string) => onExpandProject?.(projectId),
      expandExperiment: (projectId: string, experimentId: string) =>
        onExpandExperiment?.(projectId, experimentId),
      isProjectExpanded: (projectId: string) => isProjectExpanded?.(projectId) ?? true,
      isExperimentExpanded: (projectId: string, experimentId: string) =>
        isExperimentExpanded?.(projectId, experimentId) ?? true,
    }),
    [onExpandProject, onExpandExperiment, isProjectExpanded, isExperimentExpanded],
  );

  return (
    <MolabRefIndexContext.Provider value={useMemo(() => buildMolabRefIndex(snapshot), [snapshot])}>
      <PreviewProvider
        target={previewTarget}
        onTargetChange={setPreviewTarget}
        workspaces={snapshot.workspaces}
        activeEditor={activeTab ?? null}
        onOpenInBackground={editorTabs.openInBackground}
      >
        <EditorActionsSlotProvider value={actionsSlot}>
          <EntityExpansionProvider value={expansion}>
            <CommandKeymap />
            <GlobalCommandPalette snapshot={snapshot} />
            <div className="flex h-screen flex-col bg-background text-foreground">
              {isMobile ? (
                <MobileAppBar
                  title={
                    activePresentation?.label ?? getNavigationContribution(leftPanelView).label
                  }
                  context={activePresentation?.context}
                  onOpenNavigation={() => setMobileNavOpen(true)}
                  actionsRef={setActionsSlot}
                />
              ) : (
                <TitleBar
                  workspaceLabel={workspaceLabel}
                  sideBarVisible={sideBarDocked ? sideBarShown : sideBarDrawerOpen}
                  onToggleSideBar={toggleSideBar}
                  panelVisible={layout.panelVisible}
                  onTogglePanel={hasPanels ? () => layout.toggle("panelVisible") : undefined}
                />
              )}
              {workbench}
              {isMobile ? null : (
                <WorkbenchStatusStrip
                  isRefreshing={isRefreshing}
                  onRemoteIndexReady={onWorkspaceRefresh}
                  activeWorkspace={activeWorkspace}
                  onReconnect={handleReconnect}
                  lastSyncedAt={signals.lastSyncedAt}
                  attention={{
                    count: signals.attention,
                    onOpen: () => navigate(`/runs?status=${ATTENTION_STATUSES.join(",")}`),
                  }}
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
              )}
              <NotificationHost />
              <RemoteConnectDialog
                workspace={connectWorkspace ?? activeWorkspace}
                open={connectOpen}
                onOpenChange={setConnectOpen}
                onDismiss={() => {
                  if (connectWorkspace) dismissRemoteAuth(connectWorkspace.key);
                }}
                onConnected={onWorkspaceRefresh}
              />
            </div>
          </EntityExpansionProvider>
        </EditorActionsSlotProvider>
      </PreviewProvider>
    </MolabRefIndexContext.Provider>
  );
};
