/**
 * The one TanStack Query client for server state.
 *
 * Defaults (plan P2 §2a):
 *  - `staleTime` 30 s — the SSE change stream + ETag/304 make this safe; a
 *    revisit inside the window renders instantly with no request.
 *  - `gcTime` 5 min — off-screen pages stay warm, so back-navigation is instant.
 *  - `refetchOnWindowFocus` / `refetchOnReconnect` — only stale queries refetch.
 *  - `refetchIntervalInBackground: false` — hidden tabs go quiet.
 *  - `retry` twice on 5xx / network errors only; never on 4xx.
 *  - `throwOnError: false` — read failures render as `WorkbenchOperationState`
 *    in place, never the route error boundary.
 *
 * Cache-level hooks keep two existing contracts: every successful fetch
 * `pulseSync()`s the status-strip heartbeat, and a background failure on a
 * query that already has data becomes a one-line status-bar warning (no
 * floating cards — see `.claude/notes/ui-guidelines.md`).
 *
 * A workspace switch cancels and removes every query except the
 * cross-workspace ones (`workspaces`, `targets`); the bootstrap queries then
 * refetch on their own.
 */

import { QueryCache, QueryClient, type QueryClientConfig } from "@tanstack/react-query";
import { ApiError } from "@/api/generated/core/ApiError";
import { pulseSync } from "@/app/state/syncPulse";
import { onWorkspaceSwitching } from "@/app/state/workspaceSwitchEvents";
import { reportStatus } from "@/lib/status-report";
import { HttpStatusError, resetEtagCache } from "./etagFetch";
import { notCrossWorkspace } from "./invalidation";

export const STALE_TIME_MS = 30_000;
export const GC_TIME_MS = 5 * 60_000;

const statusOf = (error: unknown): number | null => {
  if (error instanceof ApiError || error instanceof HttpStatusError) return error.status;
  return null;
};

/** Retry transient failures only — a 4xx is an answer, not an outage. */
export const shouldRetry = (failureCount: number, error: unknown): boolean => {
  if (failureCount >= 2) return false;
  const status = statusOf(error);
  return status === null || status >= 500;
};

const messageOf = (error: unknown): string =>
  error instanceof Error && error.message ? error.message : "Request failed";

export function createQueryClient(overrides: QueryClientConfig = {}): QueryClient {
  return new QueryClient({
    ...overrides,
    queryCache:
      overrides.queryCache ??
      new QueryCache({
        onSuccess: () => pulseSync(),
        onError: (error, query) => {
          // Only when stale data is still on screen: an initial failure is the
          // query's own `error` state and renders as an operation state.
          if (query.state.data !== undefined) reportStatus(messageOf(error), "warning");
        },
      }),
    defaultOptions: {
      queries: {
        staleTime: STALE_TIME_MS,
        gcTime: GC_TIME_MS,
        refetchOnWindowFocus: true,
        refetchOnReconnect: true,
        refetchOnMount: true,
        refetchIntervalInBackground: false,
        structuralSharing: true,
        throwOnError: false,
        retry: shouldRetry,
        retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 8000),
        networkMode: "online",
        ...overrides.defaultOptions?.queries,
      },
      mutations: {
        retry: 0,
        networkMode: "online",
        ...overrides.defaultOptions?.mutations,
      },
    },
  });
}

/** Drop every workspace-bound query (keeps `workspaces` / `targets`). */
export async function resetForWorkspaceSwitch(client: QueryClient): Promise<void> {
  resetEtagCache();
  await client.cancelQueries({ predicate: notCrossWorkspace });
  client.removeQueries({ predicate: notCrossWorkspace });
}

/** Wire the workspace-switch reset; returns the unsubscribe. */
export function installWorkspaceSwitchReset(client: QueryClient): () => void {
  return onWorkspaceSwitching(() => {
    void resetForWorkspaceSwitch(client);
  });
}

/** The app-wide client (also used by queryFns that need `getQueryData`). */
export const queryClient: QueryClient = createQueryClient();

installWorkspaceSwitchReset(queryClient);
