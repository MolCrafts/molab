/**
 * Knowledge-tab cache contract (plan P2 §2c).
 *
 * The point of the migration is that entering Knowledge costs **one**
 * `GET /api/knowledge`, shared by the doc tree, its facet filter, the global
 * command palette and the knowledge viewer; that a note body is fetched once
 * for both the viewer and the inspector; and that a write invalidates the
 * `["knowledge"]` keys and nothing else.
 *
 * Headless: rstest has no DOM environment, so these drive `QueryObserver`
 * directly — the same machinery the hooks wrap — with msw as the network.
 */

import { afterAll, afterEach, beforeAll, describe, expect, it } from "@rstest/core";
import { QueryObserver } from "@tanstack/react-query";
import { HttpResponse, http } from "msw";
import { OpenAPI } from "@/api/generated";
import { createInvalidators } from "@/app/state/queries/invalidation";
import { qk } from "@/app/state/queries/keys";
import {
  knowledgeQueries,
  selectFacets,
  selectFiltered,
  selectIsNotePath,
} from "@/app/state/queries/knowledge";
import { makeMswServer, makeTestQueryClient } from "@/test/queryTestUtils";

// msw resolves its relative handler paths against `location`, which node has
// no notion of (the same shim `mocks/handlers/__tests__` installs).
Reflect.set(globalThis, "location", new URL("http://localhost/"));

const harness = makeMswServer();

// The generated client builds `BASE + path`; node's fetch needs it absolute.
const ORIGINAL_BASE = OpenAPI.BASE;

beforeAll(() => {
  OpenAPI.BASE = "http://localhost";
  harness.server.listen({ onUnhandledRequest: "error" });
});
afterEach(() => harness.reset());
afterAll(() => {
  OpenAPI.BASE = ORIGINAL_BASE;
  harness.server.close();
});

/** Requests whose pathname is exactly `path` (so `/api/knowledge` excludes `/note`). */
const callsTo = (path: string): number =>
  harness.requests.filter((r) => new URL(r.url).pathname === path).length;

/** Subscribe an observer and resolve once it holds settled data. */
const observe = async <T>(
  client: ReturnType<typeof makeTestQueryClient>,
  options: Parameters<typeof client.fetchQuery>[0],
): Promise<{ observer: QueryObserver<T>; unsubscribe: () => void }> => {
  // biome-ignore lint/suspicious/noExplicitAny: QueryObserver's generics are structural here
  const observer = new QueryObserver<T>(client, options as any);
  const unsubscribe = observer.subscribe(() => {});
  await client.getQueryCache().find({ queryKey: options.queryKey })?.promise;
  return { observer, unsubscribe };
};

describe("knowledge list cache", () => {
  it("serves four consumers from one GET /api/knowledge", async () => {
    const client = makeTestQueryClient();
    const options = knowledgeQueries.list();

    // DocTree, its facet filter, the command palette and the viewer.
    const consumers = await Promise.all([
      observe(client, options),
      observe(client, options),
      observe(client, options),
      observe(client, options),
    ]);

    expect(callsTo("/api/knowledge")).toBe(1);
    for (const c of consumers) c.unsubscribe();
    client.clear();
  });

  it("projects the same response through each select without refetching", async () => {
    const client = makeTestQueryClient();
    const data = await client.fetchQuery(knowledgeQueries.list());

    const facets = selectFacets(data);
    const all = selectFiltered(null, null)(data);

    expect(all).toBe(data.notes); // unfiltered is the identity — no copy
    expect(facets.tags).toEqual([...facets.tags].sort());
    expect(facets.statuses).toEqual([...facets.statuses].sort());
    // Facets come from the *unfiltered* list, so they never collapse.
    const tag = facets.tags[0];
    if (tag) {
      const narrowed = selectFiltered(tag, null)(data);
      expect(narrowed.length).toBeLessThanOrEqual(data.notes.length);
      expect(narrowed.every((n) => (n.tags ?? []).includes(tag))).toBe(true);
      expect(selectFacets(data).tags).toEqual(facets.tags);
    }
    expect(callsTo("/api/knowledge")).toBe(1);
    client.clear();
  });

  it("is a cache hit on revisit within staleTime", async () => {
    const client = makeTestQueryClient();
    const first = await observe(client, knowledgeQueries.list());
    expect(callsTo("/api/knowledge")).toBe(1);
    first.unsubscribe();

    // Leaving and re-entering the Knowledge tab.
    const second = await observe(client, knowledgeQueries.list());
    expect(callsTo("/api/knowledge")).toBe(1);
    second.unsubscribe();
    client.clear();
  });

  it("classifies a path as a note only when the list says so", async () => {
    const client = makeTestQueryClient();
    const data = await client.fetchQuery(knowledgeQueries.list());
    const notePath = data.notes[0]?.relPath;
    const refPath = data.references[0]?.relPath;
    if (notePath) expect(selectIsNotePath(notePath)(data)).toBe(true);
    if (refPath) expect(selectIsNotePath(refPath)(data)).toBe(false);
    expect(selectIsNotePath("kb/does-not-exist")(data)).toBe(false);
    client.clear();
  });
});

describe("knowledge note cache", () => {
  it("serves the viewer and the inspector from one getNote", async () => {
    const client = makeTestQueryClient();
    const list = await client.fetchQuery(knowledgeQueries.list());
    const path = list.notes[0]?.relPath;
    expect(path).toBeTruthy();
    if (!path) return;
    harness.reset();

    const viewer = await observe(client, knowledgeQueries.note(path));
    const inspector = await observe(client, knowledgeQueries.note(path));

    expect(callsTo("/api/knowledge/note")).toBe(1);
    viewer.unsubscribe();
    inspector.unsubscribe();

    // Reopening the same note within staleTime issues nothing.
    const again = await observe(client, knowledgeQueries.note(path));
    expect(callsTo("/api/knowledge/note")).toBe(1);
    again.unsubscribe();
    client.clear();
  });
});

describe("knowledge search", () => {
  it("issues nothing for an empty query", async () => {
    const client = makeTestQueryClient();
    const observer = new QueryObserver(client, {
      ...knowledgeQueries.search(""),
      enabled: false,
    });
    const unsubscribe = observer.subscribe(() => {});
    expect(callsTo("/api/knowledge/search")).toBe(0);
    expect(observer.getCurrentResult().data).toBeUndefined();
    unsubscribe();
    client.clear();
  });

  it("keeps the previous hits on screen while the next query resolves", async () => {
    const client = makeTestQueryClient();
    // One observer whose key moves as the debounced query changes — exactly
    // what `useKnowledgeSearchQuery` does between keystrokes.
    // biome-ignore lint/suspicious/noExplicitAny: QueryObserver generics are structural here
    const observer = new QueryObserver(client, knowledgeQueries.search("alpha") as any);
    const unsubscribe = observer.subscribe(() => {});
    await client.getQueryCache().find({ queryKey: qk.knowledgeSearch("alpha") })?.promise;

    const first = observer.getCurrentResult().data;
    expect(first).toBeDefined();

    // Hold the next response open so the in-flight state is observable.
    let release: () => void = () => {};
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    harness.server.use(
      http.get("/api/knowledge/search", async () => {
        await held;
        return HttpResponse.json({ hits: [], truncated: false });
      }),
    );

    // biome-ignore lint/suspicious/noExplicitAny: QueryObserver generics are structural here
    observer.setOptions(knowledgeQueries.search("alphab") as any);
    await Promise.resolve();

    const result = observer.getCurrentResult();
    expect(result.isPlaceholderData).toBe(true);
    expect(result.data).toBe(first); // previous hits still rendering
    expect(result.isFetching).toBe(true);

    release();
    unsubscribe();
    client.clear();
  });
});

describe("knowledge mutation invalidation", () => {
  it("invalidates only the knowledge keys", async () => {
    const client = makeTestQueryClient();
    client.setQueryData(qk.knowledge(null), { notes: [], references: [], total: 0 });
    client.setQueryData(qk.knowledgeNote("kb/a"), {
      name: "a",
      relPath: "kb/a",
      body: "",
      links: [],
    });
    client.setQueryData(qk.knowledgeBacklinks("kb/a"), []);
    client.setQueryData(qk.knowledgeSearch("a"), { hits: [], truncated: false });
    // Neighbours that must NOT be touched.
    client.setQueryData(qk.projects(), []);
    client.setQueryData(qk.runsIndex(null), []);
    client.setQueryData(qk.info(), { root: "/ws" });
    client.setQueryData(qk.agentSessions(), []);

    await createInvalidators(client).afterNoteMutation("kb/a");

    const stale = (key: readonly unknown[]): boolean =>
      client.getQueryState(key)?.isInvalidated === true;

    expect(stale(qk.knowledge(null))).toBe(true);
    expect(stale(qk.knowledgeNote("kb/a"))).toBe(true);
    expect(stale(qk.knowledgeBacklinks("kb/a"))).toBe(true);
    expect(stale(qk.knowledgeSearch("a"))).toBe(true);

    expect(stale(qk.projects())).toBe(false);
    expect(stale(qk.runsIndex(null))).toBe(false);
    expect(stale(qk.info())).toBe(false);
    expect(stale(qk.agentSessions())).toBe(false);
    client.clear();
  });

  it("realigns the tree: an active list observer refetches once after a write", async () => {
    const client = makeTestQueryClient();
    const tree = await observe(client, knowledgeQueries.list());
    expect(callsTo("/api/knowledge")).toBe(1);

    await createInvalidators(client).afterNoteMutation("kb/new-note");

    expect(callsTo("/api/knowledge")).toBe(2);
    tree.unsubscribe();
    client.clear();
  });
});
