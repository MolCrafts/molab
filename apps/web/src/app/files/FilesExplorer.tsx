import {
  Archive,
  Blocks,
  Copy,
  ExternalLink,
  FilePlus,
  FileText,
  FlaskConical,
  Folder,
  FolderOpen,
  FolderPlus,
  PlayCircle,
  RefreshCw,
} from "lucide-react";
import type { ComponentType } from "react";
import { ApiError } from "@/api/generated";
import { usePermissions, withWriteGate } from "@/app/auth";
import { EMPTY_COPY } from "@/app/components/entity";
import type { NavigationExplorerProps } from "@/app/navigation/sections";
import { type TreeNode, type TreeNodeAction, TreeView } from "@/app/panels/TreeView";
import { prefetchRenderer } from "@/app/renderers/lazyRenderers";
import type { FileKind, Selection, WorkspaceSnapshot, WorkspaceTreeNode } from "@/app/types";
import { useAlert, useConfirm } from "@/components/ConfirmDialog";
import { LeftExplorer } from "@/components/layout/ExplorerShell";
import { usePrompt } from "@/components/PromptDialog";
import { WorkbenchIconAction } from "@/components/workbench";
import { getWorkspaceFs } from "@/lib/workspace-fs";
import {
  formatQualifiedPath,
  join as joinWorkspacePath,
  type PathDisplayContext,
} from "@/lib/workspace-path";

const fileKindByExtension: Record<string, FileKind> = {
  ".yml": "yaml",
  ".yaml": "yaml",
  ".json": "json",
  ".py": "python",
  ".md": "markdown",
  ".txt": "text",
  ".png": "image",
  ".jpg": "image",
  ".jpeg": "image",
};

export const detectFileKind = (path: string | undefined): FileKind => {
  if (!path) return "unknown";
  const parts = path.split(".");
  const last = parts[parts.length - 1];
  const extension = parts.length > 1 && last ? `.${last.toLowerCase()}` : "";
  return fileKindByExtension[extension] ?? "unknown";
};

const errorDetail = (error: unknown): string => {
  if (error instanceof ApiError) {
    const detail = (error.body as { detail?: unknown } | null)?.detail;
    if (typeof detail === "string" && detail) return detail;
    return error.message;
  }
  return error instanceof Error ? error.message : String(error);
};

const copyText = async (text: string): Promise<void> => {
  try {
    await navigator.clipboard.writeText(text);
  } catch (error) {
    console.warn("Failed to copy workspace path:", error);
  }
};

interface WorkspaceSemantic {
  type: "project" | "experiment" | "run" | "asset";
  id: string;
  icon: ComponentType<{ className?: string }>;
  iconClass: string;
}

interface WorkspaceTreeActions {
  onSelect: (selection: Selection) => void;
  onIntentEntity?: (type: WorkspaceSemantic["type"], id: string) => void;
  onIntentDirectory?: (dirPath: string) => void;
  onCreateDirectory: (path: string) => void;
  onCreateFile: (path: string) => void;
  pathContext: PathDisplayContext;
  onRefresh: () => void;
  writeDeniedReason: string | null;
}

/**
 * Which entity, if any, owns this directory on disk.
 *
 * Matched on the path each entity reports, not on its id: a directory is
 * named for a person — a project's slug, an experiment's slug, a run's
 * parameters — while the id is a UUIDv7 that appears nowhere in the tree.
 * Comparing against ids silently matched only the entities whose slug
 * happened to equal their id.
 */
const detectWorkspaceSemantic = (
  path: string,
  snapshot: WorkspaceSnapshot,
): WorkspaceSemantic | null => {
  const owns = (entityPath: string): boolean =>
    Boolean(entityPath) && (path === entityPath || path.endsWith(`/${entityPath}`));

  const project = snapshot.projects.find((item) => owns(item.path));
  if (project) {
    return { type: "project", id: project.id, icon: Blocks, iconClass: "text-muted-foreground" };
  }
  const experiment = snapshot.experiments.find((item) => owns(item.path));
  if (experiment) {
    return {
      type: "experiment",
      id: experiment.id,
      icon: FlaskConical,
      iconClass: "text-muted-foreground",
    };
  }
  const run = snapshot.runs.find((item) => owns(item.path));
  if (run) {
    return { type: "run", id: run.id, icon: PlayCircle, iconClass: "text-muted-foreground" };
  }

  const parts = path.split("/");
  const folderName = parts[parts.length - 1];
  const parentName = parts.length > 1 ? parts[parts.length - 2] : null;
  if (parentName === "assets") {
    const asset = snapshot.assets.find((item) => item.id === folderName);
    if (asset) {
      return { type: "asset", id: asset.id, icon: Archive, iconClass: "text-muted-foreground" };
    }
  }
  return null;
};

export const buildFilesExplorerNodes = (
  snapshot: WorkspaceSnapshot,
  actions: WorkspaceTreeActions,
): TreeNode[] => {
  const root = snapshot.workspaceRoot;
  if (!root) return [];

  const walk = (node: WorkspaceTreeNode): TreeNode => {
    const isFile = node.kind === "file";
    const semantic = isFile ? null : detectWorkspaceSemantic(node.path, snapshot);
    const icon = semantic?.icon ?? (isFile ? FileText : Folder);
    const iconClass = semantic?.iconClass ?? (isFile ? "text-muted-foreground" : "text-foreground");
    const fileSelection: Selection = {
      objectType: "workspace-file",
      objectId: node.path,
      filePath: node.path,
      fileKind: detectFileKind(node.path),
      assetId: node.assetId ?? undefined,
      hasPreviewSidecar: node.hasPreviewSidecar ?? undefined,
    };

    return {
      id: node.id,
      label: node.name,
      icon,
      iconClassName: iconClass,
      meta: semantic ? (
        <span className="uppercase tracking-tighter opacity-50 group-hover:opacity-100">
          {semantic.type.substring(0, 3)}
        </span>
      ) : undefined,
      onPrefetch: () => {
        if (isFile) {
          void import("@/plugins/editor/TextEditor");
          void import("@monaco-editor/react");
          if (fileSelection.fileKind === "image") {
            void import("@/app/renderers/ImageViewer");
          }
          if (fileSelection.hasPreviewSidecar) {
            void import("@/plugins/molvis/MolvisDatasetPreview");
          }
          return;
        }
        if (semantic) {
          prefetchRenderer(semantic.type);
          actions.onIntentEntity?.(semantic.type, semantic.id);
          return;
        }
        actions.onIntentDirectory?.(node.path);
      },
      onSelect: () => {
        if (isFile) actions.onSelect(fileSelection);
        else if (semantic) actions.onSelect({ objectType: semantic.type, objectId: semantic.id });
      },
      actions: isFile
        ? [
            {
              id: "open",
              label: "Open file",
              icon: ExternalLink,
              onSelect: () => actions.onSelect(fileSelection),
            },
            {
              id: "copy-path",
              label: "Copy path",
              icon: Copy,
              onSelect: () => void copyText(formatQualifiedPath(node.path, actions.pathContext)),
            },
          ]
        : [
            ...(semantic
              ? [
                  {
                    id: "open",
                    label: `Open ${semantic.type}`,
                    icon: ExternalLink,
                    onSelect: () =>
                      actions.onSelect({ objectType: semantic.type, objectId: semantic.id }),
                  } satisfies TreeNodeAction,
                ]
              : []),
            withWriteGate<TreeNodeAction>(
              {
                id: "new-file",
                label: "New file here",
                icon: FilePlus,
                onSelect: () => actions.onCreateFile(node.path),
              },
              actions.writeDeniedReason,
            ),
            withWriteGate<TreeNodeAction>(
              {
                id: "new-folder",
                label: "New folder here",
                icon: FolderPlus,
                onSelect: () => actions.onCreateDirectory(node.path),
              },
              actions.writeDeniedReason,
            ),
            {
              id: "copy-path",
              label: "Copy path",
              icon: Copy,
              onSelect: () => void copyText(formatQualifiedPath(node.path, actions.pathContext)),
            },
            {
              id: "refresh",
              label: "Refresh",
              icon: RefreshCw,
              separatorBefore: true,
              onSelect: actions.onRefresh,
            },
          ],
      children: isFile ? undefined : node.children.map(walk),
      emptyChildLabel: !isFile
        ? node.childrenLoaded === false
          ? "…"
          : EMPTY_COPY.emptyFolder.title
        : undefined,
    };
  };

  return [walk(root)];
};

/** Complete raw Files workspace, including file commands and lazy tree expansion. */
type FilesExplorerProps = Pick<
  NavigationExplorerProps,
  "snapshot" | "selection" | "onSelect" | "onRefresh" | "fileSystem"
>;

export const FilesExplorer = (props: FilesExplorerProps): JSX.Element => {
  const { fileSystem } = props;
  const { writeDeniedReason } = usePermissions();
  const { prompt, dialog: promptDialog } = usePrompt();
  const { confirm, dialog: confirmDialog } = useConfirm();
  const { alert, dialog: alertDialog } = useAlert();
  const hasWorkspace = Boolean(props.snapshot.workspaceRoot);
  const activeWorkspace =
    props.snapshot.workspaces.find((workspace) => workspace.active) ??
    props.snapshot.workspaces[0] ??
    null;
  const pathContext: PathDisplayContext = {
    root: getWorkspaceFs().root,
    workspace: activeWorkspace
      ? {
          label: activeWorkspace.label,
          isRemote: activeWorkspace.isRemote,
          path: activeWorkspace.path,
        }
      : null,
  };

  const createFile = async (directoryPath?: string): Promise<void> => {
    const name = await prompt({
      title: "New file",
      label: directoryPath ? "File name" : "File path",
      description: directoryPath || "Relative to the workspace root.",
      placeholder: directoryPath ? undefined : "notebooks/example.md",
      confirmLabel: "Create",
    });
    if (!name) return;
    fileSystem.onCreateFile(directoryPath ? joinWorkspacePath(directoryPath, name) : name);
  };
  const createDirectory = async (directoryPath?: string): Promise<void> => {
    const name = await prompt({
      title: "New folder",
      label: directoryPath ? "Folder name" : "Folder path",
      description: directoryPath || "Relative to the workspace root.",
      placeholder: directoryPath ? undefined : "experiments/new",
      confirmLabel: "Create",
    });
    if (!name) return;
    fileSystem.onCreateDirectory(directoryPath ? joinWorkspacePath(directoryPath, name) : name);
  };
  const openWorkspace = async (): Promise<void> => {
    const path = await prompt({
      title: "Open workspace",
      label: "Workspace path",
      placeholder: "/path/to/workspace",
      confirmLabel: "Open",
    });
    if (!path) return;
    try {
      await fileSystem.onOpenWorkspace(path);
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        const create = await confirm({
          title: "Create workspace?",
          description: `${path} does not exist.`,
          confirmLabel: "Create",
        });
        if (!create) return;
        try {
          await fileSystem.onOpenWorkspace(path, { createIfMissing: true });
        } catch (retryError) {
          await alert({ title: "Open failed", description: errorDetail(retryError) });
        }
        return;
      }
      await alert({ title: "Open failed", description: errorDetail(error) });
    }
  };

  const nodes = buildFilesExplorerNodes(props.snapshot, {
    onSelect: props.onSelect,
    onIntentDirectory: fileSystem.onExpandDirectory,
    onCreateDirectory: (path) => void createDirectory(path),
    onCreateFile: (path) => void createFile(path),
    pathContext,
    onRefresh: props.onRefresh,
    writeDeniedReason,
  });
  const actions = !hasWorkspace ? (
    <WorkbenchIconAction
      label="Open workspace"
      kind="ghost"
      deniedReason={writeDeniedReason}
      onClick={() => void openWorkspace()}
    >
      <FolderOpen className="size-icon" />
    </WorkbenchIconAction>
  ) : (
    <>
      <WorkbenchIconAction
        label="New file"
        kind="ghost"
        deniedReason={writeDeniedReason}
        onClick={() => void createFile()}
      >
        <FilePlus className="size-icon" />
      </WorkbenchIconAction>
      <WorkbenchIconAction
        label="New folder"
        kind="ghost"
        deniedReason={writeDeniedReason}
        onClick={() => void createDirectory()}
      >
        <FolderPlus className="size-icon" />
      </WorkbenchIconAction>
      <WorkbenchIconAction label="Refresh files" kind="ghost" onClick={props.onRefresh}>
        <RefreshCw className="size-4" />
      </WorkbenchIconAction>
    </>
  );

  return (
    <>
      <LeftExplorer title="Files" actions={actions}>
        <TreeView
          nodes={nodes}
          activeId={props.selection?.objectId}
          expandPath={props.snapshot.workspaceRoot ? [props.snapshot.workspaceRoot.id] : []}
          dataEpoch={fileSystem.dataEpoch}
          emptyTitle={EMPTY_COPY.workspace.title}
          onExpand={fileSystem.onExpandDirectory}
        />
      </LeftExplorer>
      {promptDialog}
      {confirmDialog}
      {alertDialog}
    </>
  );
};
