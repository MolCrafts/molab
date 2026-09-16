/**
 * Test utilities for the query layer — headless (node environment).
 *
 * rstest 0.10 has no per-file DOM environment, so query tests drive
 * `QueryClient` / `QueryObserver` directly and stub the network with msw's
 * node server (`ui/mocks/handlers` + per-test `server.use(...)`).
 */

import { QueryClient } from "@tanstack/react-query";
import type { RequestHandler } from "msw";
import { setupServer } from "msw/node";
import type { EventSourceLike } from "@/app/state/queries/changeStream";
import { handlers as mockHandlers } from "../../mocks/handlers";

/**
 * A client with retries off so tests are deterministic.
 *
 * `gcTime` defaults to `Infinity`: with `0`, an observer-less query seeded via
 * `setQueryData` is collected on the next timer tick, so any test that
 * advances fake timers would find its seeded keys gone. Pass `gcTime` to
 * exercise collection explicitly.
 */
export function makeTestQueryClient(options: { gcTime?: number } = {}): QueryClient {
  const gcTime = options.gcTime ?? Number.POSITIVE_INFINITY;
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime, staleTime: 0, networkMode: "always" },
      mutations: { retry: false, networkMode: "always" },
    },
  });
}

export interface RecordedRequest {
  method: string;
  url: string;
  headers: Record<string, string>;
}

export interface MswHarness {
  server: ReturnType<typeof setupServer>;
  requests: RecordedRequest[];
  /** Requests whose URL contains `fragment`. */
  requestsTo: (fragment: string) => RecordedRequest[];
  reset: () => void;
}

/**
 * An msw node server that records every request it sees. Unhandled requests
 * are errors, so a test that issues an unexpected call fails loudly.
 */
export function makeMswServer(extra: RequestHandler[] = []): MswHarness {
  const server = setupServer(...extra, ...mockHandlers);
  const requests: RecordedRequest[] = [];
  server.events.on("request:start", ({ request }) => {
    const headers: Record<string, string> = {};
    request.headers.forEach((value, key) => {
      headers[key.toLowerCase()] = value;
    });
    requests.push({ method: request.method, url: request.url, headers });
  });
  return {
    server,
    requests,
    requestsTo: (fragment) => requests.filter((r) => r.url.includes(fragment)),
    reset: () => {
      requests.length = 0;
      server.resetHandlers();
    },
  };
}

type Listener = (event: { data?: unknown }) => void;

/** A scriptable stand-in for the browser `EventSource`. */
export class FakeEventSource implements EventSourceLike {
  static instances: FakeEventSource[] = [];
  readonly url: string;
  closed = false;
  private readonly listeners = new Map<string, Set<Listener>>();

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  static reset(): void {
    FakeEventSource.instances = [];
  }

  static get latest(): FakeEventSource {
    const last = FakeEventSource.instances.at(-1);
    if (!last) throw new Error("no FakeEventSource has been created");
    return last;
  }

  addEventListener(type: string, listener: Listener): void {
    let set = this.listeners.get(type);
    if (!set) {
      set = new Set();
      this.listeners.set(type, set);
    }
    set.add(listener);
  }

  close(): void {
    this.closed = true;
  }

  private dispatch(type: string, event: { data?: unknown }): void {
    for (const listener of this.listeners.get(type) ?? []) listener(event);
  }

  /** Simulate the connection opening. */
  open(): void {
    this.dispatch("open", {});
  }

  /** Simulate a named server-sent event with a JSON payload. */
  emit(type: string, data: unknown): void {
    this.dispatch(type, { data: JSON.stringify(data) });
  }

  /** Simulate a transport failure. */
  fail(): void {
    this.dispatch("error", {});
  }
}

export const fakeEventSourceFactory = (url: string): EventSourceLike => new FakeEventSource(url);

/** Let pending promise callbacks run (useful between fake-timer ticks). */
export const flushMicrotasks = async (): Promise<void> => {
  for (let i = 0; i < 4; i += 1) await Promise.resolve();
};
