/**
 * VS Code-style verification-code prompt.
 *
 * A remote that needs a one-time code asks once, on its own. Probe traffic
 * (workspace list, 503 needs_auth) opens the dialog. After Esc, further probes
 * stay quiet until the host is healthy again or the user asks to reconnect.
 * A gesture (Add Folder, Reconnect) always opens it.
 */
import type { ServedWorkspaceSummary } from "@/app/types";

export type RemoteAuthSource = "probe" | "gesture";

type Listener = (workspace: ServedWorkspaceSummary) => void;

const listeners = new Set<Listener>();
const dismissed = new Set<string>();
let fallback: ServedWorkspaceSummary | null = null;
let fetchInstalled = false;

export const remoteNeedsCode = (workspace: ServedWorkspaceSummary | null | undefined): boolean =>
  Boolean(workspace?.isRemote && workspace.needsAuth);

export const subscribeRemoteAuth = (listener: Listener): (() => void) => {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};

export const setRemoteAuthFallback = (workspace: ServedWorkspaceSummary | null): void => {
  fallback = workspace?.isRemote ? workspace : null;
};

const emit = (workspace: ServedWorkspaceSummary): void => {
  for (const listener of listeners) listener(workspace);
};

/** Ask the shell to show the verification-code dialog for `workspace`. */
export const requestRemoteAuth = (
  workspace: ServedWorkspaceSummary,
  source: RemoteAuthSource,
): void => {
  if (!workspace.isRemote) return;
  if (source === "gesture") dismissed.delete(workspace.key);
  if (source === "probe" && dismissed.has(workspace.key)) return;
  emit(workspace);
};

/**
 * Drive the prompt from a served-workspace row.
 * A healthy remote clears a previous Esc so the next code request pops again.
 */
export const noteRemoteAuthState = (workspace: ServedWorkspaceSummary): void => {
  if (!workspace.isRemote) return;
  if (!remoteNeedsCode(workspace)) {
    if (!workspace.unreachable) dismissed.delete(workspace.key);
    return;
  }
  requestRemoteAuth(workspace, "probe");
};

export const dismissRemoteAuth = (key: string): void => {
  dismissed.add(key);
};

const asRecord = (value: unknown): Record<string, unknown> | null =>
  value !== null && typeof value === "object" ? (value as Record<string, unknown>) : null;

/** Workspace key from a 503 body, or "" when the body is needs_auth without a key. */
export const parseNeedsAuthKey = (body: unknown): string | null => {
  const root = asRecord(body);
  const error = asRecord(root?.error) ?? root;
  if (!error) return null;
  const message = typeof error.message === "string" ? error.message : "";
  const details = asRecord(error.details);
  const reason = typeof details?.reason === "string" ? details.reason : "";
  if (message !== "needs_auth" && reason !== "needs_auth") return null;
  const workspace = details?.workspace;
  return typeof workspace === "string" && workspace ? workspace : "";
};

const workspaceForKey = (key: string): ServedWorkspaceSummary | null => {
  if (fallback && (key === "" || fallback.key === key)) return fallback;
  if (!key) return null;
  return {
    key,
    label: key,
    isRemote: true,
    path: null,
    active: false,
    unreachable: true,
    needsAuth: true,
  };
};

/** Inspect one HTTP response. Callers pass a clone so the original body stays readable. */
export const noteRemoteAuthResponse = async (
  response: Pick<Response, "status" | "json">,
): Promise<void> => {
  if (response.status !== 503) return;
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    return;
  }
  const key = parseNeedsAuthKey(body);
  if (key === null) return;
  const workspace = workspaceForKey(key);
  if (workspace) requestRemoteAuth(workspace, "probe");
};

/** Patch `window.fetch` so any API 503 needs_auth opens the code dialog. */
export const installRemoteAuthFetch = (): void => {
  if (fetchInstalled || typeof window === "undefined") return;
  fetchInstalled = true;
  const orig = window.fetch.bind(window);
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const response = await orig(input, init);
    if (response.status === 503) {
      void noteRemoteAuthResponse(response.clone());
    }
    return response;
  };
};

/** Test-only. Production never resets this. */
export const resetRemoteAuthForTests = (): void => {
  listeners.clear();
  dismissed.clear();
  fallback = null;
  fetchInstalled = false;
};
