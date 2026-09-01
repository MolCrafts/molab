import { apiErrorMessage } from "@/api/errors";
import { ApiError } from "@/api/generated/core/ApiError";
import type { ServedWorkspaceResponse } from "@/api/generated/models/ServedWorkspaceResponse";
import { WorkspaceAddRequest } from "@/api/generated/models/WorkspaceAddRequest";
import { WorkspacesService } from "@/api/generated/services/WorkspacesService";
import type { ServedWorkspaceSummary } from "@/app/types";

const toSummary = (row: ServedWorkspaceResponse): ServedWorkspaceSummary => ({
  key: row.key,
  label: row.label,
  isRemote: row.isRemote,
  path: row.path ?? null,
  active: row.active ?? false,
  unreachable: row.unreachable ?? false,
  needsAuth: row.needsAuth ?? row.unreachable ?? false,
});

const connectFailure = (err: unknown): Error => {
  if (err instanceof ApiError) {
    const status = err.status;
    if (status === 401 || status === 403) return new Error("auth");
    if (status === 408 || status === 504) return new Error("timeout");
    if (status === 502 || status === 503) return new Error("unreachable");
  }
  return new Error("failed");
};

/** The served-workspace set (`/api/workspaces`), not the active-workspace tree. */
export const workspacesApi = {
  listWorkspaces: async (): Promise<ServedWorkspaceSummary[]> => {
    const rows = await WorkspacesService.listWorkspaces();
    return rows.map(toSummary);
  },
  addWorkspace: async (input: {
    kind: "local" | "remote";
    path?: string;
    name?: string;
    createIfMissing?: boolean;
    activate?: boolean;
  }): Promise<ServedWorkspaceSummary> => {
    try {
      const row = await WorkspacesService.addWorkspace({
        kind:
          input.kind === "remote"
            ? WorkspaceAddRequest.kind.REMOTE
            : WorkspaceAddRequest.kind.LOCAL,
        path: input.path,
        name: input.name,
        create_if_missing: input.createIfMissing ?? false,
        activate: input.activate ?? true,
      });
      return toSummary(row);
    } catch (err) {
      throw new Error(apiErrorMessage(err, "Failed to add workspace"));
    }
  },
  removeWorkspace: async (key: string): Promise<void> => {
    await WorkspacesService.removeWorkspace(key);
  },
  connectWorkspace: async (
    key: string,
    code: string,
    options?: { force?: boolean },
  ): Promise<{ ok: boolean; masterAlive: boolean; host: string }> => {
    try {
      const body = await WorkspacesService.connectWorkspace(key, {
        code,
        force: options?.force ?? false,
      });
      return {
        ok: body.ok,
        masterAlive: body.masterAlive,
        host: body.host,
      };
    } catch (err) {
      throw connectFailure(err);
    }
  },
};
