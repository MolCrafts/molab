/**
 * Workspace query definitions — the bootstrap parallelism and caching claims
 * of plan P2 §2b, asserted headlessly against the msw mock server.
 */

import { afterAll, afterEach, beforeAll, describe, expect, test } from "@rstest/core";
import { QueryObserver } from "@tanstack/react-query";
import { HttpWorkspaceFs, setDefaultWorkspaceFs } from "@/lib/workspace-fs";
import { flushMicrotasks, makeMswServer, makeTestQueryClient } from "@/test/queryTestUtils";
import {
  agentSessionsQuery,
  experimentRunsQuery,
  experimentsQuery,
  projectsQuery,
  treeQuery,
  workspaceInfoQuery,
  workspacesQuery,
} from "../workspace";

const harness = makeMswServer();

// The app fetches same-origin relative URLs; node's `fetch` needs absolute
// ones. Resolve against a fixed origin so msw can match the handlers.
const ORIGIN = "http://localhost";
Reflect.set(globalThis, "location", new URL(`${ORIGIN}/`));
let originalFetch: typeof fetch;

beforeAll(() => {
  // `listen()` installs msw's interceptor on `globalThis.fetch`; wrap *that*
  // one, so relative URLs still reach the mock handlers.
  harness.server.listen({ onUnhandledRequest: "error" });
  const intercepted = globalThis.fetch;
  originalFetch = intercepted;
  const absoluteFetch: typeof fetch = (input, init) =>
    typeof input === "string" && input.startsWith("/")
      ? intercepted(`${ORIGIN}${input}`, init)
      : intercepted(input, init);
  globalThis.fetch = absoluteFetch;
  // The default fs captured `fetch` at module load, before the swap.
  setDefaultWorkspaceFs(new HttpWorkspaceFs({ fetchImpl: absoluteFetch }));
});
afterEach(() => harness.reset());
afterAll(() => {
  globalThis.fetch = originalFetch;
  harness.server.close();
});

/** Resolve a query through an observer, mirroring what a mounted hook does. */
const fetchOnce = async <T>(
  client: ReturnType<typeof makeTestQueryClient>,
  options: {
    queryKey: readonly unknown[];
  },
): Promise<T> => {
  const observer = new QueryObserver(client, options as never);
  const result = await observer.refetch();
  return result.data as T;
};

describe("TestWorkspaceBootstrapQueries", () => {
  test("the four bootstrap queries are independent and run concurrently", async () => {
    const client = makeTestQueryClient();

    // Mounting all four at once must not serialize: every request starts
    // before any of them has resolved (the old loop awaited them one by one).
    const inFlight = [
      client.fetchQuery(workspacesQuery()),
      client.fetchQuery(projectsQuery()),
      client.fetchQuery(agentSessionsQuery()),
      client.fetchQuery(treeQuery("", 2)),
    ];
    // One microtask flush is enough for all four to be dispatched; the old
    // serial loop would have issued exactly one by this point.
    await flushMicrotasks();
    const startedBeforeAnyResolved = harness.requests.length;
    await Promise.all(inFlight);

    expect(startedBeforeAnyResolved).toBe(4);
  });

  test("the workspace tree does not wait on workspace info", async () => {
    const client = makeTestQueryClient();
    // `toApiPath("")` needs no root, so the listing is independent of info —
    // the old bootstrap awaited info first, a pure waterfall.
    await Promise.all([
      client.fetchQuery(treeQuery("", 2)),
      client.fetchQuery(workspaceInfoQuery()),
    ]);

    const listing = harness.requestsTo("/api/workspace/files");
    const info = harness.requestsTo("/api/workspace/info");
    expect(listing.length).toBe(1);
    expect(info.length).toBe(1);
  });
});

describe("TestWorkspaceQueryCaching", () => {
  test("re-reading an expanded project within staleTime issues no request", async () => {
    const client = makeTestQueryClient({ gcTime: Number.POSITIVE_INFINITY });
    const options = { ...experimentsQuery("protein-folding"), staleTime: 30_000 };

    await client.fetchQuery(options);
    const afterFirst = harness.requestsTo("/experiments").length;
    await client.fetchQuery(options);

    expect(afterFirst).toBe(1);
    expect(harness.requestsTo("/experiments").length).toBe(1);
  });

  test("experiments and runs map onto the snapshot shapes", async () => {
    const client = makeTestQueryClient();

    const experiments = await fetchOnce<{ experiments: unknown[]; workflows: unknown[] }>(
      client,
      experimentsQuery("protein-folding"),
    );
    expect(Array.isArray(experiments.experiments)).toBe(true);
    expect(Array.isArray(experiments.workflows)).toBe(true);

    const runs = await fetchOnce<unknown[]>(
      client,
      experimentRunsQuery("protein-folding", "exp-001"),
    );
    expect(Array.isArray(runs)).toBe(true);
  });

  test("each experiment's runs are a separate cache entry", async () => {
    const client = makeTestQueryClient();
    await client.fetchQuery(experimentRunsQuery("protein-folding", "exp-001"));

    // A different experiment must not read the first one's rows.
    expect(client.getQueryData(experimentRunsQuery("protein-folding", "exp-002").queryKey)).toBe(
      undefined,
    );
    expect(
      client.getQueryData(experimentRunsQuery("protein-folding", "exp-001").queryKey),
    ).not.toBe(undefined);
  });
});
