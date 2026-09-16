/**
 * Agent / plan / approvals / curate queries.
 *
 * These replace the hand-rolled `setInterval` + `setState` loops that used to
 * live in `AgentViewer`, `ApprovalsBell`, `ApprovalsInbox`, `CurateComposer`
 * and `WorkspaceActivityFeed`. Three properties matter here:
 *
 * 1. **Intervals are functions of data, not constants.** A session polls at
 *    1.5 s only while it is live and stops the moment it reaches a terminal
 *    status — no chain of `setTimeout`s that outlives the component.
 * 2. **One key per fact.** The bell and the inbox both read
 *    {@link useApprovalsQuery}, so the two of them issue one request, not two.
 * 3. **Hidden tabs are quiet.** The shared client sets
 *    `refetchIntervalInBackground: false`, so every interval below pauses when
 *    the tab is hidden and catches up on focus.
 *
 * Approvals keep their own `EventSource` as a fallback. The server does now
 * republish approval changes on the workspace bus (`notify_approvals_changed`
 * receives a root at every call site, so `kind: "approval"` reaches the change
 * stream), but that path is covered only at the bus and route level — the test
 * transports serialize the app, so a push arriving *during* an open stream is
 * unobservable in-process. {@link useApprovalsStream} keeps one ref-counted
 * connection until the live path is confirmed in a browser; once it is,
 * deleting the stream is the only change, since the change stream's
 * `kind: "approval"` invalidation already lands on the same key.
 */

import { type UseQueryResult, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useSyncExternalStore } from "react";
import type { PendingApprovalItem } from "@/api/generated/models/PendingApprovalItem";
import { ApprovalsService } from "@/api/generated/services/ApprovalsService";
import { CurateTasksService } from "@/api/generated/services/CurateTasksService";
import { WorkspaceService } from "@/api/generated/services/WorkspaceService";
import { agentApi, workspaceApi } from "@/app/state/api";
import { qk } from "./keys";

/** Statuses that mean "the server is still working on this task". */
export const LIVE_AGENT_STATUSES: ReadonlySet<string> = new Set([
  "running",
  "waiting_approval",
  "awaiting_user",
]);

export const AGENT_SESSION_POLL_MS = 1_500;
export const PLAN_POLL_MS = 2_000;
export const CURATE_POLL_MS = 2_000;
export const APPROVALS_STALE_MS = 30_000;
export const AGENT_HEALTH_STALE_MS = 5 * 60_000;
/** How long after a plan decision we keep polling even if status looks calm. */
export const PLAN_DECISION_GRACE_MS = 60_000;

export const isLiveAgentStatus = (status: string | null | undefined): boolean =>
  status != null && LIVE_AGENT_STATUSES.has(status);

// ── pure interval decisions (unit-tested; see the note on fake timers) ─────

/**
 * `refetchInterval` for a session query.
 *
 * Returns `false` for a terminal session so the poll stops by itself — the
 * behaviour the old 12-tick `setTimeout` chain could not express.
 */
export function agentSessionRefetchInterval(
  session: { status?: string | null } | undefined,
  enabled = true,
): number | false {
  if (!enabled) return false;
  return isLiveAgentStatus(session?.status) ? AGENT_SESSION_POLL_MS : false;
}

/**
 * `refetchInterval` for the plan-artifacts query.
 *
 * Live while the session is live, plus a bounded grace window after a decision
 * (realization keeps writing artifacts for a moment after Approve). The window
 * is bounded on purpose: the previous `planRefreshKey > 0` predicate, once
 * bumped, kept the 2 s poll running for the rest of the session's life.
 */
export function planRefetchInterval(
  sessionStatus: string | null | undefined,
  decidedAt: number | null,
  now: number = Date.now(),
): number | false {
  if (isLiveAgentStatus(sessionStatus)) return PLAN_POLL_MS;
  if (decidedAt !== null && now - decidedAt < PLAN_DECISION_GRACE_MS) return PLAN_POLL_MS;
  return false;
}

export function curateRefetchInterval(
  task: { status?: string | null } | undefined,
): number | false {
  const status = task?.status;
  if (status === "running" || status === "waiting_approval" || status == null)
    return CURATE_POLL_MS;
  return false;
}

// ── agent health ──────────────────────────────────────────────────────────

/**
 * Agent readiness banner data.
 *
 * `retry: false` on purpose: an unconfigured or older server answers 503 and
 * that is a normal answer here, not a transient fault worth retrying.
 */
export function useAgentHealthQuery(): UseQueryResult<Awaited<
  ReturnType<typeof agentApi.getHealth>
> | null> {
  return useQuery({
    queryKey: qk.agentHealth(),
    queryFn: async () => {
      try {
        return await agentApi.getHealth();
      } catch {
        // Health is advisory — a missing endpoint must not surface an error
        // state, it just means "no banner".
        return null;
      }
    },
    staleTime: AGENT_HEALTH_STALE_MS,
    retry: false,
  });
}

// ── agent session ─────────────────────────────────────────────────────────

export interface AgentSessionQueryOptions {
  /** Poll while the session is live (the viewer disables it while loading). */
  enabled?: boolean;
}

/**
 * One agent session, polled only while live.
 *
 * The viewer still owns the *merge* (transcript coalescing, preserving array
 * identity so CSS spinners do not restart); this query owns the fetching,
 * deduping and interval.
 */
export function useAgentSessionQuery(
  sessionId: string | null,
  options: AgentSessionQueryOptions = {},
): UseQueryResult<Awaited<ReturnType<typeof agentApi.getSession>>> {
  const { enabled = true } = options;
  return useQuery({
    queryKey: qk.agentSession(sessionId ?? ""),
    queryFn: () => agentApi.getSession(sessionId as string),
    enabled: enabled && sessionId !== null,
    refetchInterval: (query) => agentSessionRefetchInterval(query.state.data, enabled),
    staleTime: 0,
  });
}

// ── plan artifacts ────────────────────────────────────────────────────────

export interface PlanRefLike {
  projectId?: string | null;
  experimentId?: string | null;
  runId?: string | null;
}

export function usePlanQuery(
  planRef: PlanRefLike | null,
  options: { sessionStatus?: string | null; decidedAt?: number | null; enabled?: boolean } = {},
): UseQueryResult<Awaited<ReturnType<typeof workspaceApi.getPlan>>> {
  const { sessionStatus = null, decidedAt = null, enabled = true } = options;
  const pid = planRef?.projectId ?? null;
  const eid = planRef?.experimentId ?? null;
  const rid = planRef?.runId ?? null;
  const ready = enabled && pid !== null && eid !== null && rid !== null;
  return useQuery({
    queryKey: qk.plan(pid ?? "", eid ?? "", rid ?? ""),
    queryFn: () => workspaceApi.getPlan(pid as string, eid as string, rid as string),
    enabled: ready,
    refetchInterval: () => (ready ? planRefetchInterval(sessionStatus, decidedAt) : false),
    // A plan that is not readable yet is an expected transient, not an error
    // worth retrying hard.
    retry: false,
    staleTime: 0,
  });
}

// ── approvals ─────────────────────────────────────────────────────────────

/**
 * Pending approvals — one key, so the bell and the inbox share one request.
 */
export function useApprovalsQuery(): UseQueryResult<PendingApprovalItem[]> {
  return useQuery({
    queryKey: qk.approvals(),
    queryFn: async () => {
      const response = await ApprovalsService.listPendingApprovalsApiApprovalsGet();
      return response.items ?? [];
    },
    staleTime: APPROVALS_STALE_MS,
  });
}

// One ref-counted `EventSource` for approvals, shared by every consumer.
// Previously ApprovalsBell and ApprovalsInbox each opened their own.
const APPROVALS_STREAM_URL = "/api/approvals/events";

interface ApprovalsStreamState {
  source: EventSource | null;
  refs: number;
  errored: boolean;
}

const approvalsStream: ApprovalsStreamState = { source: null, refs: 0, errored: false };
const approvalsListeners = new Set<() => void>();

const emitApprovalsState = (): void => {
  for (const fn of approvalsListeners) fn();
};

export const getApprovalsStreamErrored = (): boolean => approvalsStream.errored;

const subscribeApprovalsState = (fn: () => void): (() => void) => {
  approvalsListeners.add(fn);
  return () => {
    approvalsListeners.delete(fn);
  };
};

/** Test hook: drop the shared connection between cases. */
export const resetApprovalsStream = (): void => {
  approvalsStream.source?.close();
  approvalsStream.source = null;
  approvalsStream.refs = 0;
  approvalsStream.errored = false;
  emitApprovalsState();
};

/**
 * Subscribe to approval changes; invalidates {@link useApprovalsQuery}'s key.
 *
 * Ref-counted, so mounting the bell and the inbox at once still opens exactly
 * one connection and a change triggers one refetch.
 */
export function useApprovalsStream(): { streamError: boolean } {
  const client = useQueryClient();
  const streamError = useSyncExternalStore(
    subscribeApprovalsState,
    getApprovalsStreamErrored,
    getApprovalsStreamErrored,
  );

  useEffect(() => {
    approvalsStream.refs += 1;
    if (approvalsStream.source === null && typeof EventSource !== "undefined") {
      try {
        const source = new EventSource(APPROVALS_STREAM_URL);
        const onChanged = (): void => {
          approvalsStream.errored = false;
          emitApprovalsState();
          void client.invalidateQueries({ queryKey: qk.approvals(), exact: true });
        };
        source.addEventListener("changed", onChanged);
        source.onmessage = onChanged;
        source.onopen = () => {
          approvalsStream.errored = false;
          emitApprovalsState();
        };
        source.onerror = () => {
          approvalsStream.errored = true;
          emitApprovalsState();
        };
        approvalsStream.source = source;
      } catch {
        // No EventSource (SSR / tests): the query's staleTime still applies.
      }
    }
    return () => {
      approvalsStream.refs -= 1;
      if (approvalsStream.refs <= 0) {
        approvalsStream.source?.close();
        approvalsStream.source = null;
        approvalsStream.errored = false;
        emitApprovalsState();
      }
    };
  }, [client]);

  return { streamError };
}

// ── curate ────────────────────────────────────────────────────────────────

export function useCurateTaskQuery(
  ids: { projectId: string; experimentId: string; taskId: string } | null,
  options: { enabled?: boolean } = {},
): UseQueryResult<Awaited<
  ReturnType<
    typeof CurateTasksService.getCurateTaskApiProjectsProjectIdExperimentsExperimentIdCurateTasksTaskIdGet
  >
> | null> {
  const { enabled = true } = options;
  const ready = enabled && ids !== null;
  return useQuery({
    queryKey: qk.curateTask(ids?.projectId ?? "", ids?.experimentId ?? "", ids?.taskId ?? ""),
    queryFn: () =>
      CurateTasksService.getCurateTaskApiProjectsProjectIdExperimentsExperimentIdCurateTasksTaskIdGet(
        (ids as { projectId: string }).projectId,
        (ids as { experimentId: string }).experimentId,
        (ids as { taskId: string }).taskId,
      ),
    enabled: ready,
    refetchInterval: (query) =>
      ready ? curateRefetchInterval(query.state.data ?? undefined) : false,
    retry: false,
    staleTime: 0,
  });
}

// ── workspace activity feed ───────────────────────────────────────────────

export const ACTIVITY_FALLBACK_POLL_MS = 30_000;

/**
 * The global event-spine feed.
 *
 * Invalidated by the change stream (every spine append publishes a change), so
 * the interval here is a fallback for when the stream is down — the caller
 * passes {@link useFallbackInterval}'s value.
 */
export function useWorkspaceEventsQuery(
  max: number,
  options: { refetchInterval?: number | false } = {},
): UseQueryResult<unknown[]> {
  const { refetchInterval = false } = options;
  return useQuery({
    queryKey: qk.events({ max }),
    queryFn: async () =>
      (await WorkspaceService.getWorkspaceEventsApiEventsGet(
        undefined,
        undefined,
        max,
      )) as unknown[],
    refetchInterval,
    staleTime: 5_000,
  });
}
