import type { ComponentType, SVGProps } from "react";
import type { InspectorSurfaceRegistration } from "@/app/panels/inspectorSurface";
import type { LeftPanelView, Selection, SemanticObjectType, WorkspaceSnapshot } from "@/app/types";
import {
  listAllViewContainers,
  listAllViews,
  listViewContainers,
  listViews,
  useWorkbenchGeneration,
} from "@/plugins/contributions/workbench";

export type NavigationPlacement = "primary" | "secondary" | "management" | "legacy";
export type NavigationShellMode = "explorer" | "rail-only";

export interface NavigationFileSystemPorts {
  onOpenWorkspace: (path: string, options?: { createIfMissing?: boolean }) => Promise<void>;
  onCreateDirectory: (path: string) => void;
  onCreateFile: (path: string) => void;
  onExpandDirectory?: (dirPath: string) => void;
  dataEpoch: number;
}

export interface NavigationProjectTreePorts {
  onExpandProject?: (projectId: string) => void;
  onExpandExperiment?: (projectId: string, experimentId: string) => void;
  isProjectExpanded?: (projectId: string) => boolean;
  isExperimentExpanded?: (projectId: string, experimentId: string) => boolean;
  dataEpoch: number;
}

export interface NavigationExplorerProps {
  snapshot: WorkspaceSnapshot;
  selection: Selection | null;
  searchQuery: string;
  onSelect: (selection: Selection) => void;
  onRefresh: () => void;
  fileSystem: NavigationFileSystemPorts;
  projectTree: NavigationProjectTreePorts;
}

export interface NavigationLandingProps {
  snapshot: WorkspaceSnapshot;
  onRefresh: () => void;
  onInspectorChange: (registration: InspectorSurfaceRegistration | null) => void;
}

export interface NavigationEmptySelection {
  title: string;
  description: string;
}

export interface NavigationContribution {
  id: LeftPanelView;
  label: string;
  explorerTitle: string;
  breadcrumbLabel: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  route: string;
  placement: NavigationPlacement;
  order: number;
  shellMode: NavigationShellMode;
  explorer?: ComponentType<NavigationExplorerProps>;
  landing?: ComponentType<NavigationLandingProps>;
  emptySelection?: NavigationEmptySelection;
  retainSelectionFor: readonly SemanticObjectType[];
  matches: (pathname: string) => boolean;
  pluginId?: string;
}

const joinNavigation = (
  views: ReturnType<typeof listAllViews>,
  containers: ReturnType<typeof listAllViewContainers>,
): NavigationContribution[] => {
  const byId = new Map(containers.map((container) => [container.id, container]));
  const joined: NavigationContribution[] = [];
  for (const view of views) {
    const container = byId.get(view.container);
    if (!container) continue;
    joined.push({
      id: view.id,
      label: container.title,
      explorerTitle: view.title,
      breadcrumbLabel: view.breadcrumbLabel ?? view.title,
      icon: container.icon,
      route: view.route,
      placement: container.placement,
      order: view.order ?? container.order ?? 0,
      shellMode: view.shellMode,
      explorer: view.explorer as NavigationContribution["explorer"],
      landing: view.landing as NavigationContribution["landing"],
      emptySelection: view.emptySelection,
      retainSelectionFor: view.retainSelectionFor as readonly SemanticObjectType[],
      matches: view.matches,
      pluginId: view.pluginId ?? container.pluginId,
    });
  }
  return joined.sort((left, right) => left.order - right.order);
};

/** Enabled contributions (rail / explorer). */
export const listNavigationContributions = (): NavigationContribution[] =>
  joinNavigation(listViews(), listViewContainers());

/** Includes disabled plugins so stale URLs still resolve. */
export const listAllNavigationContributions = (): NavigationContribution[] =>
  joinNavigation(listAllViews(), listAllViewContainers());

/** Live list — prefer `listNavigationContributions()` in new code. */
export const navigationContributions = {
  get length() {
    return listNavigationContributions().length;
  },
  map: <T,>(fn: (contribution: NavigationContribution, index: number) => T): T[] =>
    listNavigationContributions().map(fn),
  find: (
    predicate: (contribution: NavigationContribution) => boolean,
  ): NavigationContribution | undefined => listAllNavigationContributions().find(predicate),
  filter: (
    predicate: (contribution: NavigationContribution) => boolean,
  ): NavigationContribution[] => listNavigationContributions().filter(predicate),
};

export const getNavigationContribution = (id: LeftPanelView): NavigationContribution => {
  const all = listAllNavigationContributions();
  const contribution = all.find((item) => item.id === id);
  if (contribution) return contribution;
  const fallback = all.find((item) => item.id === "projects") ?? all[0];
  if (!fallback) {
    throw new Error(`Unknown navigation contribution: ${id}`);
  }
  return fallback;
};

export const railNavigationContributions = (): NavigationContribution[] =>
  listNavigationContributions()
    .filter(({ placement }) => placement === "primary" || placement === "secondary")
    .sort((left, right) => left.order - right.order);

export const managementNavigationContribution = (): NavigationContribution | undefined =>
  listNavigationContributions().find(({ placement }) => placement === "management");

/**
 * Product routes used when the live view registry is empty (unit tests, or a
 * URL hit before core/knowledge activate). Plugin-registered routes win first.
 */
const PRODUCT_ROUTE_FALLBACK: ReadonlyArray<{
  id: LeftPanelView;
  matches: (pathname: string) => boolean;
}> = [
  { id: "dashboard", matches: (pathname) => pathname === "/" || pathname.startsWith("/dashboard") },
  { id: "projects", matches: (pathname) => pathname.startsWith("/projects") },
  { id: "runs", matches: (pathname) => pathname.startsWith("/runs") },
  {
    id: "compare",
    matches: (pathname) => pathname === "/compare" || pathname.startsWith("/compare/"),
  },
  { id: "agent", matches: (pathname) => pathname.startsWith("/agent-tasks") },
  { id: "knowledge", matches: (pathname) => pathname.startsWith("/knowledge") },
  { id: "asset", matches: (pathname) => pathname.startsWith("/assets") },
  { id: "workspace", matches: (pathname) => pathname.startsWith("/workspace") },
  { id: "settings", matches: (pathname) => pathname.startsWith("/settings") },
  { id: "activity", matches: (pathname) => pathname.startsWith("/activity") },
  { id: "workflow", matches: (pathname) => pathname.startsWith("/workflows") },
];

/** Pure pathname → product section mapping, including hidden compatibility routes. */
export const leftPanelViewFromPath = (pathname: string): LeftPanelView =>
  listAllNavigationContributions().find(({ matches }) => matches(pathname))?.id ??
  PRODUCT_ROUTE_FALLBACK.find(({ matches }) => matches(pathname))?.id ??
  "projects";

export const useNavigationContributions = (): NavigationContribution[] => {
  useWorkbenchGeneration();
  return listNavigationContributions();
};
