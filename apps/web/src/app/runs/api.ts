import type { WorkspaceRunsResponse } from "./types";

const ENDPOINT = "/api/workspace/runs";

const handle = async <T>(response: Response, label: string): Promise<T> => {
  if (!response.ok) {
    const detail = await response
      .json()
      .then((body: { detail?: string } | null) => body?.detail)
      .catch(() => null);
    throw new Error(`${label} failed (${response.status}): ${detail ?? response.statusText}`);
  }
  return response.json() as Promise<T>;
};

export interface ListRunsOptions {
  offset?: number;
  limit?: number;
  /**
   * Served-workspace key. The flat route resolves it through `get_workspace`
   * (`{ws}` path segment → `?ws=` → `X-Molexp-Workspace`), so the same
   * endpoint answers for any served workspace; omitting it means "active".
   *
   * There is no `/api/workspaces/{ws}/workspace/runs` — the cross-project runs
   * route lives on the non-namespaced `workspace` router — so this is the only
   * way to address a non-active workspace here.
   */
  ws?: string;
}

export const workspaceRunsApi = {
  async listRuns(options: ListRunsOptions = {}): Promise<WorkspaceRunsResponse> {
    const params = new URLSearchParams();
    if (options.offset !== undefined) params.set("offset", String(options.offset));
    if (options.limit !== undefined) params.set("limit", String(options.limit));
    if (options.ws !== undefined) params.set("ws", options.ws);
    const url = params.size > 0 ? `${ENDPOINT}?${params.toString()}` : ENDPOINT;
    const response = await fetch(url);
    return handle<WorkspaceRunsResponse>(response, "List workspace runs");
  },
};
