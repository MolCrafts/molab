import { ApiError } from "@/api/generated/core/ApiError";
import { WorkspaceService } from "@/api/generated/services/WorkspaceService";
import { emitWorkspaceSwitching } from "@/app/state/workspaceSwitchEvents";
import type { ServedWorkspaceSummary, ServeScope } from "@/app/types";

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
  getServeScope: async (): Promise<ServeScope> => {
    const response = await fetch("/api/workspace/scope");
    if (!response.ok) {
      throw new Error(`Request failed: ${response.status} ${response.statusText}`);
    }
    return (await response.json()) as ServeScope;
  },
  openWorkspace: async (path: string, createIfMissing = false) => {
    const info = await WorkspaceService.openWorkspace({ kind: "local", path, createIfMissing });
    emitWorkspaceSwitching({ activeDescriptor: path });
    return info;
  },
  activate: async (workspace: ServedWorkspaceSummary) => {
    const info = await WorkspaceService.openWorkspace(
      workspace.isRemote
        ? { kind: "remote", name: workspace.key }
        : { kind: "local", path: workspace.path ?? "" },
    );
    emitWorkspaceSwitching({ activeDescriptor: workspace.key });
    return info;
  },
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
  uploadFile: async (path: string, file: File, workspace?: string): Promise<void> => {
    const query = new URLSearchParams({ path });
    if (workspace) query.set("ws", workspace);
    const url = `/api/workspace/file/upload?${query}`;
    const uncertain =
      "Upload result could not be confirmed. Check the destination before uploading again.";
    let response: Response;
    try {
      response = await fetch(url, { method: "POST", body: file });
    } catch {
      throw new Error(uncertain);
    }
    if (!response.ok) {
      const body = await response.json().catch(() => null);
      const error = body?.error;
      const message =
        error?.outcome === "unknown" ||
        (response.status >= 500 &&
          error?.outcome !== "not_applied" &&
          error?.details?.reason !== "needs_auth")
          ? uncertain
          : error?.message || body?.detail || `Upload rejected (${response.status})`;
      throw new ApiError(
        { method: "POST", url },
        { url, ok: false, status: response.status, statusText: response.statusText, body },
        message,
      );
    }
  },
  downloadUrl: (path: string, workspace?: string): string => {
    const query = new URLSearchParams({ path, download: "true" });
    if (workspace) query.set("ws", workspace);
    return `/api/workspace/file/blob?${query}`;
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
