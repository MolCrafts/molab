import { WorkspaceService } from "@/api/generated/services/WorkspaceService";
import type { ServedWorkspaceSummary } from "@/app/types";

/** Wire node for `mapWorkspaceTree` (HTTP listing adapted via WorkspaceFs). */
export interface WorkspaceFileNode {
  id?: string;
  name: string;
  path: string;
  type?: string;
  children?: WorkspaceFileNode[];
  size?: number | null;
  modified?: string | number;
  assetId?: string | null;
  assetKind?: string | null;
  producerRunId?: string | null;
  producerTaskId?: string | null;
  hasPreviewSidecar?: boolean | null;
}

export interface WorkspaceFilesResponse {
  path?: string;
  children?: WorkspaceFileNode[];
}

/** Active workspace (`/api/workspace/*`): info, open, files, cache. */
export const workspaceApi = {
  getWorkspaceInfo: () => WorkspaceService.getWorkspaceInfo(),
  openWorkspace: (path: string, createIfMissing = false) =>
    WorkspaceService.openWorkspace({
      kind: "local",
      path,
      createIfMissing,
    }),
  activate: (workspace: ServedWorkspaceSummary) =>
    WorkspaceService.openWorkspace(
      workspace.isRemote
        ? { kind: "remote", name: workspace.key }
        : { kind: "local", path: workspace.path ?? "" },
    ),
  createDirectory: async (path: string): Promise<void> => {
    await WorkspaceService.createDirectory({ folder_id: "workspace", path });
  },
  writeFile: async (path: string, content = ""): Promise<void> => {
    await WorkspaceService.writeFile({ folder_id: "workspace", path, content });
  },
  getWorkspaceFileText: async (path: string): Promise<string> => {
    const response = await WorkspaceService.readWorkspaceFile(path);
    return response.content;
  },
  getWorkspaceFileBlob: async (path: string): Promise<Blob> => {
    // Generated client JSON-decodes this binary route.
    const response = await fetch(`/api/workspace/file/blob?path=${encodeURIComponent(path)}`);
    if (!response.ok) {
      throw new Error(`Request failed: ${response.status} ${response.statusText}`);
    }
    return response.blob();
  },
  getWorkspaceTree: async (
    options: { path?: string; maxDepth?: number; includeCatalog?: boolean } = {},
  ): Promise<WorkspaceFilesResponse> => {
    const { getWorkspaceFs } = await import("@/lib/workspace-fs");
    const fs = getWorkspaceFs();
    const dirents = await fs.listdir(options.path ?? "", {
      maxDepth: options.maxDepth ?? 2,
      includeCatalog: options.includeCatalog,
    });
    const toRaw = (d: (typeof dirents)[number]): WorkspaceFileNode => ({
      name: d.name,
      path: d.path,
      type: d.kind === "file" ? "file" : "folder",
      size: d.sizeBytes,
      modified: d.mtime ?? undefined,
      children: d.children.map(toRaw),
      assetId: d.assetId,
      hasPreviewSidecar: d.hasPreviewSidecar,
    });
    return {
      path: options.path || fs.root || "/",
      children: dirents.map(toRaw),
    };
  },
};
