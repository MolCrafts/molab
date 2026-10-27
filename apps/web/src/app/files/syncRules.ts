/** Per-path sync rules for the open remote workspace. */

export type SyncContent = "everything" | "records" | "code" | "skip-bulk" | "types";
export type SyncWhen = "manual" | "on-open" | "interval";
export type SyncFileType = "py" | "json" | "md" | "images" | "logs";

export interface SyncRule {
  id: string;
  path: string;
  kind: "file" | "directory";
  direction: "pull" | "push";
  content: SyncContent;
  types: SyncFileType[];
  extraFiles: "keep" | "remove";
  when: SyncWhen;
  intervalMinutes: number;
  lastRunAt: string | null;
  lastStatus: string | null;
  lastOutput: string | null;
}

export interface SyncRuleDraft {
  path: string;
  kind: "file" | "directory";
  direction: "pull" | "push";
  content: SyncContent;
  types: SyncFileType[];
  extraFiles: "keep" | "remove";
  when: SyncWhen;
  intervalMinutes: number;
}

export interface SyncRunResult {
  rule: SyncRule;
  output: string;
  dryRun: boolean;
}

export const syncRuleKeys = {
  all: ["workspace", "sync-rules"] as const,
  list: (workspaceKey: string) => ["workspace", "sync-rules", workspaceKey] as const,
};

const readError = async (response: Response): Promise<string> => {
  const body: unknown = await response.json().catch(() => null);
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string" && detail) return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((item) => {
          if (item && typeof item === "object" && "msg" in item) return String(item.msg);
          return String(item);
        })
        .join("; ");
    }
  }
  return `Sync failed (${response.status})`;
};

const request = async (path: string, init?: RequestInit): Promise<Response> => {
  const response = await fetch(path, init);
  if (!response.ok) throw new Error(await readError(response));
  return response;
};

export const listSyncRules = async (): Promise<SyncRule[]> => {
  const response = await fetch("/api/workspace/sync-rules");
  if (response.status === 409) return [];
  if (!response.ok) throw new Error(await readError(response));
  const body = (await response.json()) as { rules?: SyncRule[] };
  return body.rules ?? [];
};

export const saveSyncRule = async (draft: SyncRuleDraft): Promise<SyncRule> => {
  const response = await request("/api/workspace/sync-rules", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(draft),
  });
  return (await response.json()) as SyncRule;
};

export const deleteSyncRule = async (id: string): Promise<void> => {
  await request(`/api/workspace/sync-rules/${encodeURIComponent(id)}`, { method: "DELETE" });
};

export const runSyncRule = async (id: string): Promise<SyncRunResult> => {
  const response = await request(`/api/workspace/sync-rules/${encodeURIComponent(id)}/run`, {
    method: "POST",
  });
  return (await response.json()) as SyncRunResult;
};

export const previewSyncRule = async (id: string): Promise<SyncRunResult> => {
  const response = await request(`/api/workspace/sync-rules/${encodeURIComponent(id)}/preview`, {
    method: "POST",
  });
  return (await response.json()) as SyncRunResult;
};
