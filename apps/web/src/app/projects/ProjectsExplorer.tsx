import { useQueryClient } from "@tanstack/react-query";
import {
  Blocks,
  CloudOff,
  Copy,
  ExternalLink,
  FlaskConical,
  Folder,
  FolderOpen,
  FolderPlus,
  PlayCircle,
  Plus,
  RefreshCw,
  Trash2,
  Workflow,
} from "lucide-react";
import type { ReactNode } from "react";
import { useMemo, useState } from "react";
import { experimentsApi, projectsApi, workspaceApi, workspacesApi } from "@/api";
import { ApiError } from "@/api/generated";
import { usePermissions } from "@/app/auth";
import {
  itemFromExperiment,
  itemFromProject,
  itemFromRunSummary,
  useCompareSet,
} from "@/app/compare";
import { isSubtreeLoaded, siblingRunItems } from "@/app/compare/expandToRuns";
import { itemKey, parseItemKey } from "@/app/compare/types";
import { AddWorkspaceDialog } from "@/app/components/AddWorkspaceDialog";
import { CreateExperimentDialog } from "@/app/components/CreateExperimentDialog";
import { CreateProjectDialog } from "@/app/components/CreateProjectDialog";
import { CreateRunDialog } from "@/app/components/CreateRunDialog";
import { EMPTY_COPY } from "@/app/components/entity";
import type { NavigationExplorerProps } from "@/app/navigation/sections";
import { TreeMenuItems, type TreeNode, type TreeNodeAction, TreeView } from "@/app/panels/TreeView";
import { prefetchRenderer } from "@/app/renderers/lazyRenderers";
import { defaultExecutionId } from "@/app/renderers/useRunViewer";
import { buildRunListActions } from "@/app/runs/runListActions";
import { executionOutputsQueryOptions, projectAssetsQueryOptions } from "@/app/state/entityQueries";
import type {
  ExperimentSummary,
  ObjectView,
  ProjectSummary,
  RunSummary,
  Selection,
  SemanticStatus,
  ServedWorkspaceSummary,
  WorkspaceSnapshot,
} from "@/app/types";
import { useAlert, useConfirm } from "@/components/ConfirmDialog";
import { LeftExplorer } from "@/components/layout/ExplorerShell";
import { Code as InlineCode } from "@/components/ui/code";
import { WorkbenchIconAction } from "@/components/workbench";
import { countLabel } from "@/lib/count-label";
import { getWorkspaceFs } from "@/lib/workspace-fs";
import {
  formatQualifiedPath,
  type PathDisplayContext,
  runWorkspaceRelativePath,
  shortWorkspaceLabel,
} from "@/lib/workspace-path";

const errorDetail = (error: unknown): string => {
  if (error instanceof ApiError) {
    const detail = (error.body as { detail?: unknown } | null)?.detail;
    if (typeof detail === "string" && detail) return detail;
    return error.message;
  }
  return error instanceof Error ? error.message : String(error);
};

const statusTextClass = (status: SemanticStatus): string => {
  switch (status) {
    case "active":
    case "approved":
    case "succeeded":
      return "font-medium text-success";
    case "failed":
    case "rejected":
      return "font-medium text-destructive";
    case "running":
      return "font-medium text-info";
    case "draft":
    case "expired":
    case "waiting_for_review":
      return "font-medium text-warning";
    case "archived":
    case "cancelled":
    case "skipped":
      return "text-muted-foreground";
    case "pending":
      return "text-muted-foreground";
  }
};

const copyText = async (text: string): Promise<void> => {
  try {
    await navigator.clipboard.writeText(text);
  } catch (error) {
    console.warn("Failed to copy to clipboard:", error);
  }
};

const itemFromSelectionKey = (
  snapshot: WorkspaceSnapshot,
  key: string,
  fallbackKey: string,
  fallbackLabel: string,
) => {
  const ref = parseItemKey(key);
  if (!ref) return null;
  const workspace =
    snapshot.workspaces.find((ws) => ws.key === ref.workspaceKey) ??
    snapshot.workspaces.find((ws) => ws.active) ??
    snapshot.workspaces[0];
  const workspaceLabel = workspace?.label ?? fallbackLabel;
  const workspaceKey = ref.workspaceKey || fallbackKey;
  if (ref.kind === "project") {
    const project = snapshot.projects.find((row) => row.id === ref.projectId);
    if (!project) return null;
    return itemFromProject(project, { key: workspaceKey, label: workspaceLabel });
  }
  if (ref.kind === "experiment") {
    const experiment = snapshot.experiments.find((row) => row.id === ref.experimentId);
    const project = snapshot.projects.find((row) => row.id === ref.projectId);
    if (!experiment || !project) return null;
    return itemFromExperiment(
      experiment,
      { key: workspaceKey, label: workspaceLabel },
      project.name,
    );
  }
  const run = snapshot.runs.find((row) => row.id === ref.runId);
  const experiment = snapshot.experiments.find((row) => row.id === ref.experimentId);
  const project = snapshot.projects.find((row) => row.id === ref.projectId);
  if (!run || !experiment || !project) return null;
  return itemFromRunSummary(run, {
    workspaceKey,
    workspaceLabel,
    projectName: project.name,
    experimentName: experiment.name,
  });
};

export interface ProjectTreeActions {
  onSelect: (selection: Selection) => void;
  onCreateExperiment: (projectId: string) => void;
  onCreateRun: (experimentId: string) => void;
  onDeleteProject: (projectId: string) => void;
  onDeleteExperiment: (experiment: ExperimentSummary) => void;
  onOpenRunView: (run: RunSummary, view?: ObjectView) => void;
  onCopyText: (text: string) => void;
  /** Qualify absolute / host-remote paths for Copy path. */
  pathContext: PathDisplayContext;
  onRefresh: () => void;
  /** Open create-project dialog (workspace root context menu). */
  onCreateProject?: () => void;
  /** VS Code "Add Folder to Workspace" (blank-area / root menu). */
  onAddWorkspace?: () => void;
  /** Lazy-load experiments when a project row expands. */
  onExpandProject?: (projectId: string) => void;
  /** Lazy-load runs when an experiment row expands. */
  onExpandExperiment?: (projectId: string, experimentId: string) => void;
  /** Hover/focus: warm the viewer chunk and any extra queries. */
  onIntentProject?: (projectId: string) => void;
  onIntentExperiment?: (projectId: string, experimentId: string) => void;
  onIntentRun?: (run: RunSummary) => void;
  isProjectExpanded?: (projectId: string) => boolean;
  isExperimentExpanded?: (projectId: string, experimentId: string) => boolean;
  /** Role denial tip for mutating tree actions (null = allowed). */
  writeDeniedReason?: string | null;
  /** Served-workspace key stamped onto bag identities. */
  workspaceKey: string;
  workspaceLabel: string;
}

const gateTreeWrite = (
  action: TreeNodeAction,
  writeDeniedReason: string | null | undefined,
): TreeNodeAction => {
  if (!writeDeniedReason) return action;
  return { ...action, disabled: true, title: writeDeniedReason };
};

const buildRunActions = (run: RunSummary, actions: ProjectTreeActions): TreeNodeAction[] =>
  buildRunListActions(run, {
    copyId: (r) => actions.onCopyText(r.id),
    copyPath: (r) =>
      actions.onCopyText(formatQualifiedPath(runWorkspaceRelativePath(r), actions.pathContext)),
  }).map((action) => ({
    id: action.id,
    label: action.label,
    icon: action.icon,
    disabled: action.disabled,
    destructive: action.destructive,
    separatorBefore: action.separatorBefore,
    title: action.title,
    onSelect: action.onSelect,
  }));

const CompactCount = ({ children }: { children: ReactNode }): JSX.Element => (
  <span className="font-mono text-micro text-muted-foreground">{children}</span>
);

export const buildProjectNodes = (
  snapshot: WorkspaceSnapshot,
  actions: ProjectTreeActions,
  searchQuery: string,
  projectsOverride?: ProjectSummary[],
): TreeNode[] => {
  const lowerQuery = searchQuery.toLowerCase().trim();

  const hierarchy = (projectsOverride ?? snapshot.projects).map((project) => ({
    ...project,
    experiments: snapshot.experiments
      .filter((experiment) => experiment.projectId === project.id)
      .map((experiment) => ({
        ...experiment,
        runs: snapshot.runs.filter((run) => run.experimentId === experiment.id),
      })),
  }));

  const filtered = hierarchy.filter((project) => {
    if (!lowerQuery) return true;
    return (
      project.name.toLowerCase().includes(lowerQuery) ||
      project.summary.toLowerCase().includes(lowerQuery) ||
      project.experiments.some(
        (experiment) =>
          experiment.name.toLowerCase().includes(lowerQuery) ||
          experiment.summary.toLowerCase().includes(lowerQuery) ||
          experiment.runs.some(
            (run) =>
              run.name.toLowerCase().includes(lowerQuery) ||
              run.id.toLowerCase().includes(lowerQuery) ||
              run.summary.toLowerCase().includes(lowerQuery),
          ),
      )
    );
  });

  return filtered.map((project) => {
    const projectExpanded =
      actions.isProjectExpanded?.(project.id) ?? project.experiments.length > 0;
    const expCount = projectExpanded
      ? project.experiments.length
      : (project.experimentCount ?? project.experiments.length);
    const workspaceKey = project.workspaceKey ?? actions.workspaceKey;
    return {
      id: project.id,
      selectionKey: itemKey({ kind: "project", workspaceKey, projectId: project.id }),
      label: project.name,
      labelClassName: statusTextClass(project.status),
      icon: Blocks,
      iconClassName: "text-muted-foreground",
      right: (
        <CompactCount>
          {projectExpanded || project.experimentCount != null ? countLabel(expCount, "exp") : "…"}
        </CompactCount>
      ),
      onPrefetch: () => {
        actions.onExpandProject?.(project.id);
        actions.onIntentProject?.(project.id);
      },
      onSelect: () => {
        actions.onExpandProject?.(project.id);
        actions.onSelect({ objectType: "project", objectId: project.id });
      },
      actions: [
        {
          id: "open",
          label: "Open",
          icon: ExternalLink,
          onSelect: () => {
            actions.onExpandProject?.(project.id);
            actions.onSelect({ objectType: "project", objectId: project.id });
          },
        },
        gateTreeWrite(
          {
            id: "new-experiment",
            label: "New Experiment…",
            icon: FlaskConical,
            onSelect: () => actions.onCreateExperiment(project.id),
          },
          actions.writeDeniedReason,
        ),
        {
          id: "copy-path",
          label: "Copy Path",
          icon: Copy,
          onSelect: () =>
            // The server reports where a project lives; composing it from ids
            // yields a directory that was never created.
            actions.onCopyText(formatQualifiedPath(project.path, actions.pathContext)),
        },
        {
          id: "refresh",
          label: "Refresh",
          icon: RefreshCw,
          separatorBefore: true,
          onSelect: actions.onRefresh,
        },
        gateTreeWrite(
          {
            id: "delete",
            label: "Delete",
            icon: Trash2,
            destructive: true,
            separatorBefore: true,
            onSelect: () => actions.onDeleteProject(project.id),
          },
          actions.writeDeniedReason,
        ),
      ],
      // Always an array so the chevron shows; empty until expand loads experiments.
      emptyChildLabel: projectExpanded ? EMPTY_COPY.entries.title : "Loading…",
      children: project.experiments.map((experiment) => {
        const dataLoaded =
          actions.isExperimentExpanded?.(project.id, experiment.id) ?? experiment.runs.length > 0;
        const runCount = dataLoaded
          ? experiment.runs.length
          : (experiment.runCount ?? experiment.runs.length);
        const hasRunCount = dataLoaded || experiment.runCount != null;
        return {
          id: experiment.id,
          selectionKey: itemKey({
            kind: "experiment",
            workspaceKey,
            projectId: project.id,
            experimentId: experiment.id,
          }),
          label: experiment.name,
          labelClassName: statusTextClass(experiment.status),
          icon: FlaskConical,
          iconClassName: "text-muted-foreground",
          right: <CompactCount>{hasRunCount ? countLabel(runCount, "run") : "…"}</CompactCount>,
          onPrefetch: () => {
            actions.onExpandProject?.(project.id);
            actions.onExpandExperiment?.(project.id, experiment.id);
            actions.onIntentExperiment?.(project.id, experiment.id);
          },
          onSelect: () => {
            actions.onExpandProject?.(project.id);
            actions.onExpandExperiment?.(project.id, experiment.id);
            actions.onSelect({ objectType: "experiment", objectId: experiment.id });
          },
          actions: [
            {
              id: "open",
              label: "Open",
              icon: ExternalLink,
              onSelect: () => {
                actions.onExpandExperiment?.(project.id, experiment.id);
                actions.onSelect({ objectType: "experiment", objectId: experiment.id });
              },
            },
            gateTreeWrite(
              {
                id: "new-run",
                label: "New Run…",
                icon: PlayCircle,
                onSelect: () => actions.onCreateRun(experiment.id),
              },
              actions.writeDeniedReason,
            ),
            {
              id: "open-workflow",
              label: "Open Workflow",
              icon: Workflow,
              onSelect: () => {
                const workflow = snapshot.workflows.find(
                  (item) => item.experimentId === experiment.id,
                );
                if (workflow) {
                  actions.onSelect({
                    objectType: "workflow",
                    objectId: workflow.id,
                    workflowId: workflow.id,
                  });
                }
              },
              disabled: !snapshot.workflows.some((item) => item.experimentId === experiment.id),
            },
            {
              id: "copy-path",
              label: "Copy Path",
              icon: Copy,
              onSelect: () =>
                actions.onCopyText(formatQualifiedPath(experiment.path, actions.pathContext)),
            },
            gateTreeWrite(
              {
                id: "delete",
                label: "Delete",
                icon: Trash2,
                destructive: true,
                separatorBefore: true,
                onSelect: () => actions.onDeleteExperiment(experiment),
              },
              actions.writeDeniedReason,
            ),
          ],
          // Tree open + data not loaded yet → "Loading…"; loaded empty → "No runs".
          emptyChildLabel: dataLoaded ? EMPTY_COPY.runs.title : "Loading…",
          children: experiment.runs.map((run) => ({
            id: run.id,
            selectionKey: itemKey({
              kind: "run",
              workspaceKey,
              projectId: project.id,
              experimentId: experiment.id,
              runId: run.id,
            }),
            label: run.name || run.id,
            labelClassName: statusTextClass(run.status),
            icon: PlayCircle,
            iconClassName: "text-muted-foreground",
            onPrefetch: () => actions.onIntentRun?.(run),
            onSelect: () => actions.onOpenRunView(run),
            actions: buildRunActions(run, actions),
          })),
        };
      }),
    };
  });
};

// A small chip describing a served workspace's kind/state in the nav header.
const workspaceBadge = (ws: ServedWorkspaceSummary): ReactNode => {
  const tone = ws.unreachable
    ? "bg-status-failed-soft text-status-failed-foreground"
    : ws.isRemote
      ? "bg-status-warning-soft text-status-warning-foreground"
      : "bg-muted text-muted-foreground";
  const text = ws.unreachable ? "unreachable" : ws.isRemote ? "remote" : "local";
  return <span className={`rounded-control px-2 py-1 text-micro font-medium ${tone}`}>{text}</span>;
};

// Shallow project leaves for a NON-active workspace — clicking one activates
// that workspace so its full tree loads on the next poll. Kept id-prefixed by
// workspace key so expansion/keys never collide with the active group, whose
// project ids are the real (unprefixed) ones.
const buildShallowProjectNodes = (
  projects: ProjectSummary[],
  searchQuery: string,
  workspaceKey: string,
  onActivate: () => void,
): TreeNode[] => {
  const lowerQuery = searchQuery.toLowerCase().trim();
  return projects
    .filter((project) => !lowerQuery || project.name.toLowerCase().includes(lowerQuery))
    .map((project) => ({
      id: `${workspaceKey}/${project.id}`,
      label: project.name,
      labelClassName: statusTextClass(project.status),
      icon: Blocks,
      iconClassName: "text-muted-foreground/50",
      onSelect: onActivate,
      actions: [
        {
          id: "open",
          label: "Open Workspace",
          icon: FolderOpen,
          onSelect: onActivate,
        },
      ],
    }));
};

// VS Code multi-root explorer: one collapsible folder per served workspace.
// Active root expands to Project → Experiment → Run; inactive roots list
// shallow projects that switch active on click. Always used when serve has
// ≥1 workspace (including a single root — same chrome as multi-root).
const buildWorkspaceGroupedNodes = (
  snapshot: WorkspaceSnapshot,
  actions: ProjectTreeActions,
  searchQuery: string,
  onActivateWorkspace: (ws: ServedWorkspaceSummary) => void,
  onRemoveWorkspace?: (ws: ServedWorkspaceSummary) => void,
): TreeNode[] => {
  const canRemoveRoot = snapshot.workspaces.length > 1 && Boolean(onRemoveWorkspace);
  return snapshot.workspaces.map((ws) => {
    // Projects without a workspaceKey (legacy/single-ws payloads) belong to
    // the active workspace — never drop them as "no projects".
    const wsProjects = snapshot.projects.filter(
      (project) => project.workspaceKey === ws.key || (project.workspaceKey == null && ws.active),
    );

    const workspaceActions: TreeNodeAction[] = [
      ...(ws.active
        ? [
            gateTreeWrite(
              {
                id: "new-project",
                label: "New Project…",
                icon: Plus,
                onSelect: () => actions.onCreateProject?.(),
              },
              actions.writeDeniedReason,
            ),
          ]
        : [
            {
              id: "open-workspace",
              label: "Open Workspace",
              icon: FolderOpen,
              onSelect: () => onActivateWorkspace(ws),
            },
          ]),
      {
        id: "copy-path",
        label: "Copy Path",
        icon: Copy,
        onSelect: () =>
          actions.onCopyText(
            ws.isRemote || !ws.path
              ? ws.label
              : formatQualifiedPath("", {
                  root: ws.path,
                  workspace: { label: ws.label, isRemote: ws.isRemote, path: ws.path },
                }),
          ),
      },
      gateTreeWrite(
        {
          id: "add-folder",
          label: "Add Folder to Workspace…",
          icon: FolderPlus,
          separatorBefore: true,
          onSelect: () => actions.onAddWorkspace?.(),
        },
        actions.writeDeniedReason,
      ),
      {
        id: "refresh",
        label: "Refresh Explorer",
        icon: RefreshCw,
        onSelect: actions.onRefresh,
      },
      ...(canRemoveRoot
        ? [
            gateTreeWrite(
              {
                id: "remove-folder",
                label: "Remove Folder from Workspace",
                icon: Trash2,
                destructive: true,
                separatorBefore: true,
                onSelect: () => onRemoveWorkspace?.(ws),
              },
              actions.writeDeniedReason,
            ),
          ]
        : []),
    ];

    const header: TreeNode = {
      id: `ws:${ws.key}`,
      // Short chrome label (Host · leaf); full serve identity stays in title.
      label: shortWorkspaceLabel(ws.label),
      icon: ws.unreachable ? CloudOff : ws.active ? FolderOpen : Folder,
      iconClassName: ws.unreachable
        ? "text-status-failed-foreground"
        : ws.active
          ? "text-accent"
          : "text-muted-foreground",
      right: workspaceBadge(ws),
      emptyChildLabel: ws.unreachable ? "Unreachable" : "No projects",
      hoverTitle: ws.label,
      actions: workspaceActions,
      onSelect: ws.active ? undefined : () => onActivateWorkspace(ws),
    };

    if (ws.unreachable) {
      return { ...header, children: [] };
    }
    if (ws.active) {
      const scopedActions: ProjectTreeActions = {
        ...actions,
        workspaceKey: ws.key,
        workspaceLabel: ws.label,
        pathContext: {
          root: ws.path ?? actions.pathContext.root,
          workspace: { label: ws.label, isRemote: ws.isRemote, path: ws.path },
        },
      };
      return {
        ...header,
        children: buildProjectNodes(snapshot, scopedActions, searchQuery, wsProjects),
      };
    }
    return {
      ...header,
      children: buildShallowProjectNodes(wsProjects, searchQuery, ws.key, () =>
        onActivateWorkspace(ws),
      ),
    };
  });
};

export const buildProjectExpandPath = (
  snapshot: WorkspaceSnapshot,
  activeId: string | undefined,
  searchQuery: string,
): string[] => {
  // Always expand active served workspace roots (VS Code multi-root defaults open).
  const ids: string[] = snapshot.workspaces
    .filter((ws) => ws.active || searchQuery)
    .map((ws) => `ws:${ws.key}`);

  if (searchQuery) {
    for (const project of snapshot.projects) {
      ids.push(project.id);
      for (const experiment of snapshot.experiments.filter((e) => e.projectId === project.id)) {
        ids.push(experiment.id);
      }
    }
    return ids;
  }

  if (!activeId) return ids;

  if (snapshot.projects.some((p) => p.id === activeId)) {
    ids.push(activeId);
  }
  const experiment = snapshot.experiments.find((e) => e.id === activeId);
  if (experiment) {
    ids.push(experiment.projectId, experiment.id);
  }
  const run = snapshot.runs.find((r) => r.id === activeId);
  if (run) {
    ids.push(run.projectId, run.experimentId);
  }
  return ids;
};

/** Complete Projects explorer: hierarchy, multi-root workspace chrome, and CRUD dialogs. */
export const ProjectsExplorer = ({
  snapshot,
  selection,
  searchQuery,
  onSelect,
  onRefresh,
  projectTree: {
    onExpandProject,
    onExpandExperiment,
    isProjectExpanded,
    isExperimentExpanded,
    dataEpoch,
  },
}: Pick<
  NavigationExplorerProps,
  "snapshot" | "selection" | "searchQuery" | "onSelect" | "onRefresh" | "projectTree"
>): JSX.Element => {
  const [createProjectOpen, setCreateProjectOpen] = useState(false);
  const [addWorkspaceOpen, setAddWorkspaceOpen] = useState(false);
  const [createExperimentProjectId, setCreateExperimentProjectId] = useState<string | null>(null);
  const [createRunExperimentId, setCreateRunExperimentId] = useState<string | null>(null);
  const { confirm, dialog: confirmDialog } = useConfirm();
  const { alert, dialog: alertDialog } = useAlert();
  const { writeDeniedReason } = usePermissions();
  const queryClient = useQueryClient();
  const compare = useCompareSet();
  const activeId = selection?.objectId;
  const fallbackWorkspace = snapshot.workspaces.find((ws) => ws.active) ?? snapshot.workspaces[0];
  const fallbackWorkspaceKey = fallbackWorkspace?.key ?? "local";
  const fallbackWorkspaceLabel = fallbackWorkspace?.label ?? fallbackWorkspaceKey;

  const pathContext: PathDisplayContext = useMemo(() => {
    const active =
      snapshot.workspaces.find((workspace) => workspace.active) ?? snapshot.workspaces[0] ?? null;
    return {
      root: getWorkspaceFs().root,
      workspace: active
        ? { label: active.label, isRemote: active.isRemote, path: active.path }
        : null,
    };
  }, [snapshot.workspaces]);

  const deleteProject = async (projectId: string): Promise<void> => {
    const confirmed = await confirm({
      title: "Delete project?",
      description: (
        <>
          Project{" "}
          <InlineCode className="rounded-control bg-muted px-1 py-1 text-label">
            {projectId}
          </InlineCode>{" "}
          and its experiments will be removed from the workspace.
        </>
      ),
      confirmLabel: "Delete",
      destructive: true,
    });
    if (!confirmed) return;
    try {
      await projectsApi.deleteProject(projectId);
      onRefresh();
    } catch (error) {
      console.error("Failed to delete project:", error);
      void alert({
        title: "Failed to delete project",
        description: error instanceof Error ? error.message : String(error),
      });
    }
  };

  const deleteExperiment = async (experiment: ExperimentSummary): Promise<void> => {
    const confirmed = await confirm({
      title: "Delete experiment?",
      description: (
        <>
          Experiment{" "}
          <InlineCode className="rounded-control bg-muted px-1 py-1 text-label">
            {experiment.id}
          </InlineCode>{" "}
          and its runs will be removed.
        </>
      ),
      confirmLabel: "Delete",
      destructive: true,
    });
    if (!confirmed) return;
    try {
      await experimentsApi.deleteExperiment(experiment.projectId, experiment.id);
      onRefresh();
    } catch (error) {
      console.error("Failed to delete experiment:", error);
      void alert({
        title: "Failed to delete experiment",
        description: error instanceof Error ? error.message : String(error),
      });
    }
  };

  const actions: ProjectTreeActions = {
    onSelect,
    onCreateExperiment: setCreateExperimentProjectId,
    onCreateRun: setCreateRunExperimentId,
    onDeleteProject: (projectId) => void deleteProject(projectId),
    onDeleteExperiment: (experiment) => void deleteExperiment(experiment),
    onOpenRunView: (run, objectView) =>
      onSelect({ objectType: "run", objectId: run.id, objectView }),
    onCopyText: (value) => void copyText(value),
    pathContext,
    onRefresh,
    onCreateProject: () => setCreateProjectOpen(true),
    onAddWorkspace: () => setAddWorkspaceOpen(true),
    onExpandProject,
    onExpandExperiment,
    onIntentProject: (projectId) => {
      prefetchRenderer("project");
      void queryClient.prefetchQuery(projectAssetsQueryOptions(projectId));
    },
    onIntentExperiment: () => {
      prefetchRenderer("experiment");
    },
    onIntentRun: (run) => {
      prefetchRenderer("run");
      const executionId = defaultExecutionId(run.executionHistory);
      if (!executionId) return;
      void queryClient.prefetchQuery(
        executionOutputsQueryOptions(run.projectId, run.experimentId, run.id, executionId),
      );
    },
    isProjectExpanded,
    isExperimentExpanded,
    writeDeniedReason,
    workspaceKey: fallbackWorkspaceKey,
    workspaceLabel: fallbackWorkspaceLabel,
  };

  const activateWorkspace = (workspace: ServedWorkspaceSummary): void => {
    void workspaceApi
      .activate(workspace)
      .then(() => onRefresh())
      .catch((error) => console.warn(`Failed to switch to workspace ${workspace.key}:`, error));
  };
  const removeWorkspace = async (workspace: ServedWorkspaceSummary): Promise<void> => {
    if (snapshot.workspaces.length <= 1) return;
    const confirmed = await confirm({
      title: "Remove Folder from Workspace?",
      description: (
        <>
          <InlineCode className="rounded-control bg-muted px-1 py-1 text-label">
            {shortWorkspaceLabel(workspace.label)}
          </InlineCode>{" "}
          will leave the explorer. Files on disk are not deleted.
        </>
      ),
      confirmLabel: "Remove",
      destructive: true,
    });
    if (!confirmed) return;
    try {
      await workspacesApi.removeWorkspace(workspace.key);
      onRefresh();
    } catch (error) {
      await alert({ title: "Remove failed", description: errorDetail(error) });
    }
  };

  const nodes =
    snapshot.workspaces.length >= 1
      ? buildWorkspaceGroupedNodes(
          snapshot,
          actions,
          searchQuery,
          activateWorkspace,
          (workspace) => void removeWorkspace(workspace),
        )
      : buildProjectNodes(snapshot, actions, searchQuery);

  const backgroundActions: TreeNodeAction[] = [
    gateTreeWrite(
      {
        id: "add-folder",
        label: "Add Folder to Workspace…",
        icon: FolderPlus,
        onSelect: () => setAddWorkspaceOpen(true),
      },
      writeDeniedReason,
    ),
    gateTreeWrite(
      {
        id: "new-project",
        label: "New Project…",
        icon: Plus,
        onSelect: () => setCreateProjectOpen(true),
      },
      writeDeniedReason,
    ),
    {
      id: "refresh",
      label: "Refresh Explorer",
      icon: RefreshCw,
      separatorBefore: true,
      onSelect: onRefresh,
    },
  ];
  const headerActions = (
    <>
      <WorkbenchIconAction
        label="Add Folder to Workspace"
        kind="ghost"
        deniedReason={writeDeniedReason}
        onClick={() => setAddWorkspaceOpen(true)}
        title="Add Folder to Workspace"
      >
        <FolderPlus className="size-icon" />
      </WorkbenchIconAction>
      <WorkbenchIconAction label="Refresh projects" kind="ghost" onClick={onRefresh}>
        <RefreshCw className="size-4" />
      </WorkbenchIconAction>
      <CreateProjectDialog
        onProjectCreated={onRefresh}
        writeDeniedReason={writeDeniedReason}
        open={createProjectOpen}
        onOpenChange={setCreateProjectOpen}
        showTrigger
      />
    </>
  );
  const expandPath = useMemo(
    () => buildProjectExpandPath(snapshot, activeId, searchQuery),
    [snapshot, activeId, searchQuery],
  );
  const createRunExperiment = createRunExperimentId
    ? snapshot.experiments.find((experiment) => experiment.id === createRunExperimentId)
    : null;

  return (
    <>
      <LeftExplorer
        title="Projects"
        actions={headerActions}
        blankMenu={<TreeMenuItems actions={backgroundActions} />}
      >
        <TreeView
          nodes={nodes}
          activeId={activeId}
          expandPath={expandPath}
          dataEpoch={dataEpoch}
          selectedIds={compare.keys}
          onModifierSelect={(ids, modifiers) => {
            const items = ids
              .map((key) =>
                itemFromSelectionKey(snapshot, key, fallbackWorkspaceKey, fallbackWorkspaceLabel),
              )
              .filter((item): item is NonNullable<typeof item> => item !== null);
            if (items.length === 0) return;
            const ctx = {
              isSubtreeLoaded: (ref: Parameters<typeof isSubtreeLoaded>[1]) =>
                isSubtreeLoaded(snapshot, ref),
              siblingRuns: siblingRunItems.bind(null, snapshot),
            };
            if (modifiers.meta && ids.length === 1) {
              const key = ids[0];
              if (key && compare.has(key)) {
                compare.remove(key);
                return;
              }
            }
            try {
              compare.addMany(items, ctx);
            } catch {
              // Subtree not loaded: leave the bag unchanged (mergeIntoBag throws).
            }
          }}
          emptyTitle={searchQuery ? EMPTY_COPY.projectsFilter.title : EMPTY_COPY.entries.title}
          emptyDescription={
            searchQuery ? undefined : "Right-click empty space to add a folder to the workspace."
          }
          onExpand={(nodeId) => {
            if (snapshot.projects.some((project) => project.id === nodeId)) {
              onExpandProject?.(nodeId);
              return;
            }
            const experiment = snapshot.experiments.find((item) => item.id === nodeId);
            if (experiment) onExpandExperiment?.(experiment.projectId, experiment.id);
          }}
        />
      </LeftExplorer>

      <AddWorkspaceDialog
        open={addWorkspaceOpen}
        onOpenChange={setAddWorkspaceOpen}
        onAdded={onRefresh}
      />
      {createExperimentProjectId ? (
        <CreateExperimentDialog
          projectId={createExperimentProjectId}
          open
          trigger={null}
          onOpenChange={(open) => {
            if (!open) setCreateExperimentProjectId(null);
          }}
          onExperimentCreated={onRefresh}
        />
      ) : null}
      {createRunExperiment ? (
        <CreateRunDialog
          projectId={createRunExperiment.projectId}
          experimentId={createRunExperiment.id}
          workflowFile={createRunExperiment.workflowFile || ""}
          open
          trigger={null}
          onOpenChange={(open) => {
            if (!open) setCreateRunExperimentId(null);
          }}
          onRunCreated={(runId) => {
            onRefresh();
            setCreateRunExperimentId(null);
            onSelect({ objectType: "run", objectId: runId });
          }}
        />
      ) : null}
      {confirmDialog}
      {alertDialog}
    </>
  );
};
