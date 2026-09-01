import {
  Activity,
  Archive,
  Blocks,
  BookOpen,
  Bot,
  FolderTree,
  LayoutDashboard,
  PlayCircle,
  Settings,
  Workflow,
} from "lucide-react";
import { type ComponentType, lazy, type SVGProps } from "react";
import type { InspectorSurfaceRegistration } from "@/app/panels/inspectorSurface";
import type { LeftPanelView, Selection, SemanticObjectType, WorkspaceSnapshot } from "@/app/types";

const DashboardPage = lazy(() =>
  import("@/app/dashboard/DashboardPage").then((module) => ({ default: module.DashboardPage })),
);
const RunsPage = lazy(() =>
  import("@/app/runs/RunsPage").then((module) => ({ default: module.RunsPage })),
);
const SettingsPage = lazy(() =>
  import("@/app/settings/SettingsPage").then((module) => ({ default: module.SettingsPage })),
);
const ActivityPage = lazy(() =>
  import("@/app/runs/ActivityPage").then((module) => ({ default: module.ActivityPage })),
);
const WorkflowsPage = lazy(() =>
  import("@/app/workflows/WorkflowsPage").then((module) => ({ default: module.WorkflowsPage })),
);

const RunsExplorer = lazy(() =>
  import("@/app/runs/RunsExplorer").then((module) => ({ default: module.RunsExplorer })),
);
const DashboardExplorer = lazy(() =>
  import("@/app/dashboard/DashboardExplorer").then((module) => ({
    default: module.DashboardExplorer,
  })),
);
const KnowledgeExplorer = lazy(() =>
  import("@/plugins/knowledge/KnowledgeExplorer").then((module) => ({
    default: module.KnowledgeExplorer,
  })),
);
const AssetsExplorer = lazy(() =>
  import("@/app/assets/AssetsExplorer").then((module) => ({ default: module.AssetsExplorer })),
);
const AgentExplorer = lazy(() =>
  import("@/app/agent/AgentExplorer").then((module) => ({ default: module.AgentExplorer })),
);
const FilesExplorer = lazy(() =>
  import("@/app/files/FilesExplorer").then((module) => ({ default: module.FilesExplorer })),
);
const ProjectsExplorer = lazy(() =>
  import("@/app/projects/ProjectsExplorer").then((module) => ({
    default: module.ProjectsExplorer,
  })),
);
const WorkflowExplorer = lazy(() =>
  import("@/app/workflows/WorkflowExplorer").then((module) => ({
    default: module.WorkflowExplorer,
  })),
);
const ActivityExplorer = lazy(() =>
  import("@/app/runs/ActivityExplorer").then((module) => ({
    default: module.ActivityExplorer,
  })),
);

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
}

/**
 * Product-owned section metadata. The shared ExplorerShell renders these
 * descriptors but deliberately knows nothing about Molexp routes or domains.
 * Legacy routes stay described for compatibility without returning to the rail.
 */
export const navigationContributions = [
  {
    id: "dashboard",
    label: "Dashboard",
    explorerTitle: "Workspace",
    breadcrumbLabel: "Dashboard",
    icon: LayoutDashboard,
    route: "/",
    placement: "primary",
    order: 10,
    shellMode: "explorer",
    explorer: DashboardExplorer,
    landing: DashboardPage,
    retainSelectionFor: [],
    matches: (pathname) => pathname === "/" || pathname.startsWith("/dashboard"),
  },
  {
    id: "projects",
    label: "Projects",
    explorerTitle: "Projects",
    breadcrumbLabel: "Projects",
    icon: Blocks,
    route: "/projects",
    placement: "primary",
    order: 20,
    shellMode: "explorer",
    explorer: ProjectsExplorer,
    emptySelection: {
      title: "No project item selected",
      description: "Choose a project, experiment, or run from the explorer to open its workspace.",
    },
    retainSelectionFor: ["project", "experiment", "run"],
    matches: (pathname) => pathname.startsWith("/projects"),
  },
  {
    id: "runs",
    label: "Runs",
    explorerTitle: "Runs",
    breadcrumbLabel: "Runs",
    icon: PlayCircle,
    route: "/runs",
    placement: "primary",
    order: 30,
    shellMode: "explorer",
    explorer: RunsExplorer,
    landing: RunsPage,
    retainSelectionFor: [],
    matches: (pathname) => pathname.startsWith("/runs"),
  },
  {
    id: "agent",
    label: "Agent",
    explorerTitle: "Agent tasks",
    breadcrumbLabel: "Agent",
    icon: Bot,
    route: "/agent-tasks",
    placement: "primary",
    order: 40,
    shellMode: "explorer",
    explorer: AgentExplorer,
    emptySelection: {
      title: "No agent task selected",
      description: "Select an agent task from the explorer, or start a new one.",
    },
    retainSelectionFor: ["agent"],
    matches: (pathname) => pathname.startsWith("/agent-tasks"),
  },
  {
    id: "knowledge",
    label: "Knowledge",
    explorerTitle: "Knowledge",
    breadcrumbLabel: "Knowledge",
    icon: BookOpen,
    route: "/knowledge",
    placement: "primary",
    order: 50,
    shellMode: "explorer",
    explorer: KnowledgeExplorer,
    emptySelection: {
      title: "No document selected",
      description: "Choose a note from the explorer, or create a new one.",
    },
    retainSelectionFor: ["knowledge"],
    matches: (pathname) => pathname.startsWith("/knowledge"),
  },
  {
    id: "asset",
    label: "Assets",
    explorerTitle: "Assets",
    breadcrumbLabel: "Assets",
    icon: Archive,
    route: "/assets",
    placement: "secondary",
    order: 60,
    shellMode: "explorer",
    explorer: AssetsExplorer,
    emptySelection: {
      title: "No asset selected",
      description: "Choose an asset from the explorer to inspect its metadata and files.",
    },
    retainSelectionFor: ["asset"],
    matches: (pathname) => pathname.startsWith("/assets"),
  },
  {
    id: "workspace",
    label: "Files",
    explorerTitle: "Files",
    breadcrumbLabel: "Files",
    icon: FolderTree,
    route: "/workspace",
    placement: "secondary",
    order: 70,
    shellMode: "explorer",
    explorer: FilesExplorer,
    emptySelection: {
      title: "No file selected",
      description: "Choose a file from the explorer to open it in the workspace.",
    },
    retainSelectionFor: ["workspace-file"],
    matches: (pathname) => pathname.startsWith("/workspace"),
  },
  {
    id: "settings",
    label: "Settings",
    explorerTitle: "Settings",
    breadcrumbLabel: "Settings",
    icon: Settings,
    route: "/settings",
    placement: "management",
    order: 80,
    shellMode: "rail-only",
    landing: SettingsPage,
    retainSelectionFor: [],
    matches: (pathname) => pathname.startsWith("/settings"),
  },
  {
    id: "activity",
    label: "Activity",
    explorerTitle: "Activity",
    breadcrumbLabel: "Activity",
    icon: Activity,
    route: "/activity",
    placement: "legacy",
    order: 90,
    shellMode: "explorer",
    explorer: ActivityExplorer,
    landing: ActivityPage,
    retainSelectionFor: [],
    matches: (pathname) => pathname.startsWith("/activity"),
  },
  {
    id: "workflow",
    label: "Workflows",
    explorerTitle: "Workflows",
    breadcrumbLabel: "Workflows",
    icon: Workflow,
    route: "/workflows",
    placement: "legacy",
    order: 100,
    shellMode: "explorer",
    explorer: WorkflowExplorer,
    landing: WorkflowsPage,
    retainSelectionFor: ["workflow"],
    matches: (pathname) => pathname.startsWith("/workflows"),
  },
] satisfies readonly NavigationContribution[];

const contributionsById = new Map(
  navigationContributions.map((contribution) => [contribution.id, contribution]),
);

export const getNavigationContribution = (id: LeftPanelView): NavigationContribution => {
  const contribution = contributionsById.get(id);
  if (!contribution) throw new Error(`Unknown navigation contribution: ${id}`);
  return contribution;
};

export const railNavigationContributions = navigationContributions
  .filter(({ placement }) => placement === "primary" || placement === "secondary")
  .sort((left, right) => left.order - right.order);

export const managementNavigationContribution = navigationContributions.find(
  ({ placement }) => placement === "management",
);

/** Pure pathname → product section mapping, including hidden compatibility routes. */
export const leftPanelViewFromPath = (pathname: string): LeftPanelView =>
  navigationContributions.find(({ matches }) => matches(pathname))?.id ?? "projects";
