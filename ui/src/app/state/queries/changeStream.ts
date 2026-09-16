/**
 * Workspace change stream → targeted query invalidation.
 *
 * One `EventSource` on `GET /api/workspace/events/stream?since=<seq>` replaces
 * the per-view polling loops. The server sends:
 *
 *   event: hello   data: {"versions": {...}, "seq": N, "replayed"?: bool}
 *
 * `replayed: true` means every change after `since` was delivered; the server
 * reports `false` (and sends no change frames) when the backlog was too large
 * to replay, which is the client's cue to refresh the list-level keys.
 *   event: change  data: {"kind", "ref", "seq", "projectId"?, "experimentId"?, "runId"?}
 *   : keep-alive
 *
 * Changes are buffered for `debounceMs`, coalesced by `kind+ref` (max seq
 * wins), and mapped through {@link invalidationsFor}. A hidden tab only marks
 * queries stale (`refetchType: "none"`); `refetchOnWindowFocus` catches up on
 * return. On `error` the stream closes, `connected` flips to false (so
 * {@link useFallbackInterval} re-enables slow polling), and it reconnects with
 * exponential backoff — silently: a missing route must never spam the console.
 *
 * Mounted once by `WorkspaceApp`, so invalidation is push-driven and the
 * fallback polls only run while the stream is down.
 */

import { type QueryClient, useQueryClient } from "@tanstack/react-query";
import { useEffect, useSyncExternalStore } from "react";
import { onWorkspaceSwitching } from "@/app/state/workspaceSwitchEvents";
import {
  applyInvalidations,
  invalidationsFor,
  LIST_LEVEL_INVALIDATIONS,
  type WorkspaceChange,
  type WorkspaceChangeKind,
} from "./invalidation";

export const CHANGE_STREAM_URL = "/api/workspace/events/stream";
export const DEFAULT_DEBOUNCE_MS = 250;
export const MIN_BACKOFF_MS = 1_000;
export const MAX_BACKOFF_MS = 30_000;

const CHANGE_KINDS: ReadonlySet<string> = new Set<WorkspaceChangeKind>([
  "run",
  "asset",
  "knowledge",
  "project",
  "experiment",
  "workspace",
  "agent",
  "approval",
  "all",
]);

// ── observable connection state ───────────────────────────────────────────

export interface ChangeStreamState {
  connected: boolean;
  lastSeq: number | null;
}

let state: ChangeStreamState = { connected: false, lastSeq: null };
const listeners = new Set<() => void>();

const setState = (patch: Partial<ChangeStreamState>): void => {
  const next = { ...state, ...patch };
  if (next.connected === state.connected && next.lastSeq === state.lastSeq) return;
  state = next;
  for (const fn of listeners) fn();
};

const subscribe = (fn: () => void): (() => void) => {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
};

export const getChangeStreamState = (): ChangeStreamState => state;

/** Test hook: forget the connection state between cases. */
export const resetChangeStreamState = (): void => {
  state = { connected: false, lastSeq: null };
  for (const fn of listeners) fn();
};

export const useChangeStreamState = (): ChangeStreamState =>
  useSyncExternalStore(subscribe, getChangeStreamState, getChangeStreamState);

/** `refetchInterval` for list queries: poll only while the stream is down. */
export const useFallbackInterval = (intervalMs: number): number | false => {
  const { connected } = useChangeStreamState();
  return connected ? false : intervalMs;
};

// ── pure helpers ──────────────────────────────────────────────────────────

/** Dedupe by `kind+ref`, keeping the highest seq; preserves first-seen order. */
export function coalesce(changes: readonly WorkspaceChange[]): WorkspaceChange[] {
  const byKey = new Map<string, WorkspaceChange>();
  for (const change of changes) {
    const key = `${change.kind}|${change.ref ?? ""}`;
    const prior = byKey.get(key);
    if (!prior || (change.seq ?? -1) > (prior.seq ?? -1)) {
      byKey.set(key, prior ? { ...prior, ...change } : change);
    }
  }
  return [...byKey.values()];
}

export function parseChange(raw: unknown): WorkspaceChange | null {
  if (typeof raw !== "object" || raw === null) return null;
  const record = raw as Record<string, unknown>;
  const kind = record.kind;
  if (typeof kind !== "string" || !CHANGE_KINDS.has(kind)) return null;
  const change: WorkspaceChange = {
    kind: kind as WorkspaceChangeKind,
    ref: typeof record.ref === "string" ? record.ref : null,
    seq: typeof record.seq === "number" ? record.seq : null,
  };
  if (typeof record.projectId === "string") change.projectId = record.projectId;
  if (typeof record.experimentId === "string") change.experimentId = record.experimentId;
  if (typeof record.runId === "string") change.runId = record.runId;
  return change;
}

const parseJson = (data: unknown): unknown => {
  if (typeof data !== "string") return null;
  try {
    return JSON.parse(data) as unknown;
  } catch {
    return null;
  }
};

export const buildStreamUrl = (base: string, since: number | null): string =>
  since === null ? base : `${base}${base.includes("?") ? "&" : "?"}since=${since}`;

// ── controller ────────────────────────────────────────────────────────────

/** The subset of `EventSource` the controller uses (swappable in tests). */
export interface EventSourceLike {
  addEventListener(type: string, listener: (event: { data?: unknown }) => void): void;
  close(): void;
}

export type EventSourceFactory = (url: string) => EventSourceLike;

export interface ChangeStreamOptions {
  client: QueryClient;
  url?: string;
  debounceMs?: number;
  minBackoffMs?: number;
  maxBackoffMs?: number;
  eventSourceFactory?: EventSourceFactory;
  /** Defaults to `document.visibilityState !== "hidden"` (true off-DOM). */
  isVisible?: () => boolean;
}

export interface ChangeStreamController {
  /** Close, forget `lastSeq`, reconnect now (workspace switch). */
  restart: () => void;
  stop: () => void;
}

const defaultFactory: EventSourceFactory = (url) => {
  if (typeof EventSource === "undefined") throw new Error("EventSource unavailable");
  return new EventSource(url);
};

const defaultIsVisible = (): boolean =>
  typeof document === "undefined" || document.visibilityState !== "hidden";

export function startChangeStream(options: ChangeStreamOptions): ChangeStreamController {
  const {
    client,
    url = CHANGE_STREAM_URL,
    debounceMs = DEFAULT_DEBOUNCE_MS,
    minBackoffMs = MIN_BACKOFF_MS,
    maxBackoffMs = MAX_BACKOFF_MS,
    eventSourceFactory = defaultFactory,
    isVisible = defaultIsVisible,
  } = options;

  let source: EventSourceLike | null = null;
  let stopped = false;
  let backoff = minBackoffMs;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let flushTimer: ReturnType<typeof setTimeout> | null = null;
  let buffer: WorkspaceChange[] = [];
  let lastSeq: number | null = null;
  let hadConnection = false;

  const clearTimers = (): void => {
    if (reconnectTimer !== null) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    if (flushTimer !== null) {
      clearTimeout(flushTimer);
      flushTimer = null;
    }
  };

  const closeSource = (): void => {
    if (source) {
      try {
        source.close();
      } catch {
        // already closed
      }
      source = null;
    }
  };

  const bumpSeq = (seq: number | null): void => {
    if (seq !== null && (lastSeq === null || seq > lastSeq)) {
      lastSeq = seq;
      setState({ lastSeq });
    }
  };

  const flush = (): void => {
    flushTimer = null;
    if (buffer.length === 0) return;
    const batch = coalesce(buffer);
    buffer = [];
    const refetchType = isVisible() ? "active" : "none";
    for (const change of batch) {
      void applyInvalidations(client, invalidationsFor(change), { refetchType });
      bumpSeq(change.seq);
    }
  };

  const scheduleReconnect = (): void => {
    if (stopped || reconnectTimer !== null) return;
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null;
      connect();
    }, backoff);
    backoff = Math.min(backoff * 2, maxBackoffMs);
  };

  const onError = (): void => {
    closeSource();
    setState({ connected: false });
    scheduleReconnect();
  };

  const onHello = (event: { data?: unknown }): void => {
    const hello = parseJson(event.data) as { seq?: unknown; replayed?: unknown } | null;
    const advertised = typeof hello?.seq === "number" ? hello.seq : null;
    // `replayed` is authoritative: the server sends it only when every event
    // after `since` was delivered, and withholds the change frames entirely
    // when the backlog outran its replay cap. So this flag alone is the gap
    // test — no client-side guess at the server's limit.
    if (hadConnection && hello?.replayed !== true) {
      // Reconnected without a guaranteed replay: refresh the list-level keys
      // once so nothing missed during the outage stays stale.
      void applyInvalidations(client, LIST_LEVEL_INVALIDATIONS, {
        refetchType: isVisible() ? "active" : "none",
      });
    }
    hadConnection = true;
    if (advertised !== null) bumpSeq(advertised);
  };

  const onChange = (event: { data?: unknown }): void => {
    const change = parseChange(parseJson(event.data));
    if (!change) return;
    buffer.push(change);
    if (flushTimer === null) flushTimer = setTimeout(flush, debounceMs);
  };

  const connect = (): void => {
    if (stopped) return;
    closeSource();
    let next: EventSourceLike;
    try {
      next = eventSourceFactory(buildStreamUrl(url, lastSeq));
    } catch {
      scheduleReconnect();
      return;
    }
    source = next;
    next.addEventListener("open", () => {
      backoff = minBackoffMs;
      setState({ connected: true });
    });
    next.addEventListener("error", onError);
    next.addEventListener("hello", onHello);
    next.addEventListener("change", onChange);
  };

  const stop = (): void => {
    stopped = true;
    clearTimers();
    buffer = [];
    closeSource();
    setState({ connected: false });
  };

  const restart = (): void => {
    if (stopped) return;
    clearTimers();
    buffer = [];
    closeSource();
    lastSeq = null;
    hadConnection = false;
    backoff = minBackoffMs;
    setState({ connected: false, lastSeq: null });
    connect();
  };

  connect();
  return { restart, stop };
}

// ── shared React binding ──────────────────────────────────────────────────

let shared: { controller: ChangeStreamController; client: QueryClient; refs: number } | null = null;

/** Ref-counted shared stream: many mounts, one `EventSource`. */
export function acquireChangeStream(client: QueryClient): () => void {
  if (shared && shared.client === client) {
    shared.refs += 1;
  } else {
    shared?.controller.stop();
    shared = { controller: startChangeStream({ client }), client, refs: 1 };
  }
  const mine = shared;
  const unsubscribeSwitch = onWorkspaceSwitching(() => mine.controller.restart());
  return () => {
    unsubscribeSwitch();
    mine.refs -= 1;
    if (mine.refs <= 0 && shared === mine) {
      mine.controller.stop();
      shared = null;
    }
  };
}

/**
 * Mount once (in the workspace shell) to keep the cache fresh by push.
 * Safe to mount before the server route exists: it just stays disconnected.
 */
export function useWorkspaceChangeStream(): void {
  const client = useQueryClient();
  useEffect(() => acquireChangeStream(client), [client]);
}
