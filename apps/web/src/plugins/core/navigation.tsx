import type { PluginAPI } from "@molcrafts/molexp-plugin";
import {
  Activity,
  Archive,
  Blocks,
  Bot,
  FolderTree,
  LayoutDashboard,
  PlayCircle,
  Settings,
  Workflow,
} from "lucide-react";
import { lazy } from "react";
import type { NavigationContribution } from "@/app/navigation/sections";

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

export const CORE_NAVIGATION: readonly NavigationContribution[] = [
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
];

export const registerCoreNavigation = (api: PluginAPI): void => {
  for (const spec of CORE_NAVIGATION) {
    api.views.registerContainer({
      id: spec.id,
      title: spec.label,
      icon: spec.icon,
      placement: spec.placement,
      order: spec.order,
    });
    api.views.register({
      id: spec.id,
      container: spec.id,
      title: spec.explorerTitle,
      breadcrumbLabel: spec.breadcrumbLabel,
      route: spec.route,
      shellMode: spec.shellMode,
      order: spec.order,
      explorer: spec.explorer,
      landing: spec.landing,
      emptySelection: spec.emptySelection,
      retainSelectionFor: spec.retainSelectionFor,
      matches: spec.matches,
    });
  }
};
