import { useQuery } from "@tanstack/react-query";
import {
  Archive,
  Blocks,
  FilePlus,
  FileText,
  FlaskConical,
  Folder,
  FolderOpen,
  FolderPlus,
  PlayCircle,
  RefreshCw,
  Upload,
} from "lucide-react";
import type { ComponentType } from "react";
import { useRef, useState } from "react";
import { ApiError } from "@/api/generated";
import { workspaceApi } from "@/api/workspace";
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
  toApiPath,
} from "@/lib/workspace-path";
import { SyncMark, SyncRuleForm } from "./SyncRuleForm";
import { listSyncRules, type SyncRule, syncRuleKeys } from "./syncRules";

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

export interface SyncTarget {
  id: string;
  name: string;
  path: string;
  kind: "file" | "directory";
}

interface WorkspaceTreeActions {
  onOpenProjectPlugins?: (projectId: string) => void;
  onDownload?: (path: string) => void;
  onSelect: (selection: Selection) => void;
  onIntentEntity?: (type: WorkspaceSemantic["type"], id: string) => void;
  onIntentDirectory?: (dirPath: string) => void;
  onCreateDirectory: (path: string) => void;
  onCreateFile: (path: string) => void;
  /** Upload into this folder (workspace-relative; "" is the root). */
  onUpload?: (folder: string) => void;
  pathContext: PathDisplayContext;
  onRefresh: () => void;
  writeDeniedReason: string | null;
  /** Remote file trees only. Opens the sync form for this node. */
  onSync?: (target: SyncTarget) => void;
  rules?: readonly SyncRule[];
  workspaceRoot?: string;
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
    const rootPath = actions.workspaceRoot ?? snapshot.workspaceRoot?.path ?? "";
    const relative = toApiPath(node.path, rootPath);
    const rule = actions.rules?.find((item) => item.path === relative);
    const syncAction: TreeNodeAction[] = actions.onSync
      ? [
          {
            id: "sync",
            label: "Sync…",
            separatorBefore: true,
            onSelect: () =>
              actions.onSync?.({
                id: node.id,
                name: node.name,
                path: node.path,
                kind: node.kind,
              }),
          },
        ]
      : [];
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
      preview: isFile
        ? { kind: "file", filePath: node.path, fileKind: fileSelection.fileKind }
        : undefined,
      icon,
      iconClassName: iconClass,
      right: rule ? (
        <SyncMark when={rule.when} intervalMinutes={rule.intervalMinutes} />
      ) : undefined,
      onPrefetch: () => {
        if (isFile) {
          void import("@/plugins/editor/TextEditor");
          void import("@/plugins/editor/MonacoEditor").then((mod) => {
            mod.MonacoEditor.prefetch();
          });
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
      // A plain directory has nothing to open, so its row click toggles it.
      onSelect:
        isFile || semantic
          ? () => {
              if (isFile) actions.onSelect(fileSelection);
              else if (semantic?.type === "project" && actions.onOpenProjectPlugins)
                actions.onOpenProjectPlugins(semantic.id);
              else if (semantic)
                actions.onSelect({ objectType: semantic.type, objectId: semantic.id });
            }
          : undefined,
      actions: isFile
        ? [
            {
              id: "open",
              label: "Open",
              shortcut: "↵",
              onSelect: () => actions.onSelect(fileSelection),
            },
            ...(actions.onDownload
              ? [
                  {
                    id: "download",
                    label: "Download",
                    onSelect: () => actions.onDownload?.(node.path),
                  },
                ]
              : []),
            {
              id: "copy-path",
              label: "Copy path",
              onSelect: () => void copyText(formatQualifiedPath(node.path, actions.pathContext)),
            },
            ...syncAction,
          ]
        : [
            ...(semantic?.type === "project" && actions.onOpenProjectPlugins
              ? [
                  {
                    id: "project-plugins",
                    label: "Open Relations",
                    onSelect: () => actions.onOpenProjectPlugins?.(semantic.id),
                  },
                ]
              : []),
            ...(semantic
              ? [
                  {
                    id: "open",
                    label: `Open ${semantic.type}`,
                    onSelect: () =>
                      actions.onSelect({ objectType: semantic.type, objectId: semantic.id }),
                  } satisfies TreeNodeAction,
                ]
              : []),
            withWriteGate<TreeNodeAction>(
              {
                id: "new-file",
                label: "New file…",
                onSelect: () => actions.onCreateFile(node.path),
              },
              actions.writeDeniedReason,
            ),
            withWriteGate<TreeNodeAction>(
              {
                id: "new-folder",
                label: "New folder…",
                onSelect: () => actions.onCreateDirectory(node.path),
              },
              actions.writeDeniedReason,
            ),
            ...(actions.onUpload
              ? [
                  withWriteGate<TreeNodeAction>(
                    {
                      id: "upload",
                      label: "Upload…",
                      onSelect: () => actions.onUpload?.(relative),
                    },
                    actions.writeDeniedReason,
                  ),
                ]
              : []),
            {
              id: "copy-path",
              label: "Copy path",
              onSelect: () => void copyText(formatQualifiedPath(node.path, actions.pathContext)),
            },
            {
              id: "refresh",
              label: "Refresh",
              separatorBefore: true,
              onSelect: actions.onRefresh,
            },
            ...syncAction,
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
  const uploadInput = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  // The folder an upload goes into: a folder's “Upload…” sets it; the header icon uses the root.
  const uploadFolder = useRef("");
  const { writeDeniedReason } = usePermissions();
  const { prompt, dialog: promptDialog } = usePrompt();
  const { confirm, dialog: confirmDialog } = useConfirm();
  const { alert, dialog: alertDialog } = useAlert();
  const hasWorkspace = Boolean(props.snapshot.workspaceRoot);
  const activeWorkspace =
    props.snapshot.workspaces.find((workspace) => workspace.active) ??
    props.snapshot.workspaces[0] ??
    null;
  const remoteSync = Boolean(
    activeWorkspace?.isRemote && !activeWorkspace.unreachable && !activeWorkspace.needsAuth,
  );
  const rulesQuery = useQuery({
    queryKey: syncRuleKeys.list(activeWorkspace?.key ?? "active"),
    queryFn: listSyncRules,
    enabled: remoteSync,
  });
  const workspaceKey = activeWorkspace?.key ?? "";
  const [syncTarget, setSyncTarget] = useState<SyncTarget | null>(null);
  const [syncWorkspace, setSyncWorkspace] = useState(workspaceKey);
  if (syncWorkspace !== workspaceKey) {
    setSyncWorkspace(workspaceKey);
    setSyncTarget(null);
  }
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
    onOpenProjectPlugins: (projectId) =>
      props.onSelect({
        objectType: "project",
        objectId: projectId,
        pluginView: "relations",
        pluginExplorer: "files",
      }),
    onSelect: props.onSelect,
    onDownload: (path) =>
      window.location.assign(workspaceApi.downloadUrl(path, activeWorkspace?.key)),
    onIntentDirectory: fileSystem.onExpandDirectory,
    onCreateDirectory: (path) => void createDirectory(path),
    onCreateFile: (path) => void createFile(path),
    onUpload: (folder) => {
      uploadFolder.current = folder;
      uploadInput.current?.click();
    },
    pathContext,
    onRefresh: props.onRefresh,
    writeDeniedReason,
    onSync: remoteSync ? setSyncTarget : undefined,
    rules: rulesQuery.data ?? [],
    workspaceRoot: props.snapshot.workspaceRoot?.path ?? "",
  });
  const syncRelative = syncTarget
    ? toApiPath(syncTarget.path, props.snapshot.workspaceRoot?.path ?? "")
    : "";
  const syncRule = (rulesQuery.data ?? []).find((item) => item.path === syncRelative) ?? null;
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
      <WorkbenchIconAction
        label="Upload file"
        kind="ghost"
        disabled={uploading}
        deniedReason={writeDeniedReason}
        onClick={() => {
          uploadFolder.current = "";
          uploadInput.current?.click();
        }}
      >
        <Upload className="size-icon" />
      </WorkbenchIconAction>
      <WorkbenchIconAction label="Refresh files" kind="ghost" onClick={props.onRefresh}>
        <RefreshCw className="size-4" />
      </WorkbenchIconAction>
    </>
  );

  return (
    <>
      <input
        type="file"
        ref={uploadInput}
        hidden
        aria-label="Choose a file to upload"
        onChange={async (event) => {
          const file = event.currentTarget.files?.[0];
          event.currentTarget.value = "";
          if (!file) return;
          const path = await prompt({
            title: "Upload file",
            label: "Destination path",
            defaultValue: uploadFolder.current ? `${uploadFolder.current}/${file.name}` : file.name,
            confirmLabel: "Upload",
          });
          if (!path) return;
          setUploading(true);
          try {
            await workspaceApi.uploadFile(path, file, activeWorkspace?.key);
            props.onRefresh();
          } catch (error) {
            await alert({ title: "Upload failed", description: errorDetail(error) });
          } finally {
            setUploading(false);
          }
        }}
      />
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
      {syncTarget && remoteSync ? (
        <SyncRuleForm
          key={syncTarget.path}
          nodeId={syncTarget.id}
          name={syncTarget.name}
          relativePath={syncRelative}
          kind={syncTarget.kind}
          rule={syncRule}
          rulesLoading={rulesQuery.isLoading}
          onClose={() => setSyncTarget(null)}
          onSynced={props.onRefresh}
        />
      ) : null}
      {promptDialog}
      {confirmDialog}
      {alertDialog}
    </>
  );
};
