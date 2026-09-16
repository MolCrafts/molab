/**
 * The behaviour contract of the `useWorkspaceState` rewrite (plan P2 §2b).
 *
 * rstest 0.10 has no DOM environment, so the hook is not rendered here;
 * instead each claim is asserted against the query client the hook drives,
 * which is where all of the behaviour actually lives:
 *
 *  - expansion is idempotent (expanding twice costs one request),
 *  - a refresh is targeted and never clears the expanded tree,
 *  - each mutation invalidates only its own keys.
 */

import { afterAll, afterEach, beforeAll, describe, expect, test } from "@rstest/core";
import { HttpWorkspaceFs, setDefaultWorkspaceFs } from "@/lib/workspace-fs";
import { flushMicrotasks, makeMswServer, makeTestQueryClient } from "@/test/queryTestUtils";
import { createInvalidators } from "../queries/invalidation";
import { qk } from "../queries/keys";
import { experimentsQuery, projectsQuery, workspacesQuery } from "../queries/workspace";

const harness = makeMswServer();
const ORIGIN = "http://localhost";
Reflect.set(globalThis, "location", new URL(`${ORIGIN}/`));

let originalFetch: typeof fetch;

beforeAll(() => {
  harness.server.listen({ onUnhandledRequest: "error" });
  const intercepted = globalThis.fetch;
  originalFetch = intercepted;
  const absoluteFetch: typeof fetch = (input, init) =>
    typeof input === "string" && input.startsWith("/")
      ? intercepted(`${ORIGIN}${input}`, init)
      : intercepted(input, init);
  globalThis.fetch = absoluteFetch;
  setDefaultWorkspaceFs(new HttpWorkspaceFs({ fetchImpl: absoluteFetch }));
});
afterEach(() => harness.reset());
afterAll(() => {
  globalThis.fetch = originalFetch;
  harness.server.close();
});

describe("TestWorkspaceStateExpansion", () => {
  test("expanding the same project twice issues one request", async () => {
    const client = makeTestQueryClient();
    const options = { ...experimentsQuery("protein-folding"), staleTime: 30_000 };

    // Expansion is set membership: re-adding an id re-reads the cache.
    await Promise.all([client.fetchQuery(options), client.fetchQuery(options)]);
    await client.fetchQuery(options);

    expect(harness.requestsTo("/experiments").length).toBe(1);
  });

  test("two expanded projects are independent cache entries", async () => {
    const client = makeTestQueryClient();
    await client.fetchQuery(experimentsQuery("protein-folding"));

    expect(client.getQueryData(qk.experiments("protein-folding"))).not.toBe(undefined);
    expect(client.getQueryData(qk.experiments("other-project"))).toBe(undefined);
  });

  test("bootstrap queries fetch in parallel, not in sequence", async () => {
    const client = makeTestQueryClient();
    const inFlight = [client.fetchQuery(workspacesQuery()), client.fetchQuery(projectsQuery())];
    await flushMicrotasks();
    const started = harness.requests.length;
    await Promise.all(inFlight);

    expect(started).toBe(2);
  });
});

describe("TestWorkspaceStateRefresh", () => {
  test("refreshing the runs view leaves project data untouched", async () => {
    const client = makeTestQueryClient();
    client.setQueryData(qk.projects(), [{ id: "p1" }]);
    client.setQueryData(qk.experiments("p1"), [{ id: "e1" }]);
    client.setQueryData(qk.runsIndex(null), { runs: [] });

    await createInvalidators(client).invalidateView("runs");

    expect(client.getQueryState(qk.runsIndex(null))?.isInvalidated).toBe(true);
    expect(client.getQueryState(qk.experiments("p1"))?.isInvalidated).toBeFalsy();
    expect(client.getQueryData(qk.experiments("p1"))).toEqual([{ id: "e1" }]);
  });

  test("a file write invalidates only its parent listing", async () => {
    const client = makeTestQueryClient();
    client.setQueryData(qk.tree("", 2), []);
    client.setQueryData(qk.tree("notes", 1), []);
    client.setQueryData(qk.tree("data", 1), []);

    await createInvalidators(client).afterFsWrite("notes/new.md");

    expect(client.getQueryState(qk.tree("notes", 1))?.isInvalidated).toBe(true);
    expect(client.getQueryState(qk.tree("data", 1))?.isInvalidated).toBeFalsy();
  });

  test("a workspace switch drops workspace-bound data but keeps the served list", async () => {
    const client = makeTestQueryClient();
    client.setQueryData(qk.workspaces(), [{ key: "ws1" }]);
    client.setQueryData(qk.targets(), []);
    client.setQueryData(qk.projects(), [{ id: "p1" }]);
    client.setQueryData(qk.experiments("p1"), [{ id: "e1" }]);

    await createInvalidators(client).afterWorkspaceSwitch();

    expect(client.getQueryData(qk.workspaces())).toEqual([{ key: "ws1" }]);
    expect(client.getQueryData(qk.targets())).toEqual([]);
    expect(client.getQueryData(qk.projects())).toBe(undefined);
    expect(client.getQueryData(qk.experiments("p1"))).toBe(undefined);
  });

  test("an experiment delete keeps sibling experiments cached", async () => {
    const client = makeTestQueryClient();
    client.setQueryData(qk.experimentRuns("p1", "e1"), [{ id: "r1" }]);
    client.setQueryData(qk.experimentRuns("p1", "e2"), [{ id: "r2" }]);

    await createInvalidators(client).afterExperimentDelete({
      projectId: "p1",
      experimentId: "e1",
    });

    expect(client.getQueryData(qk.experimentRuns("p1", "e1"))).toBe(undefined);
    expect(client.getQueryData(qk.experimentRuns("p1", "e2"))).toEqual([{ id: "r2" }]);
  });
});
