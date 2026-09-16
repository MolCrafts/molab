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
  limit?: number;
}

/**
 * The runs-index URL for `options`.
 *
 * Exported so the query layer can fetch it conditionally (`If-None-Match`)
 * while this module keeps the plain, spy-able `fetch` used elsewhere.
 */
export const runsIndexUrl = (options: ListRunsOptions = {}): string => {
  const params = new URLSearchParams();
  if (options.limit !== undefined) params.set("limit", String(options.limit));
  return params.size > 0 ? `${ENDPOINT}?${params.toString()}` : ENDPOINT;
};

export const workspaceRunsApi = {
  async listRuns(options: ListRunsOptions = {}): Promise<WorkspaceRunsResponse> {
    const response = await fetch(runsIndexUrl(options));
    return handle<WorkspaceRunsResponse>(response, "List workspace runs");
  },
};
