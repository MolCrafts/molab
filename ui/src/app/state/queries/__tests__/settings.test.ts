/**
 * Settings queries — the properties the migration was actually for.
 *
 * These panels were never slow, so nothing here asserts timing. They assert
 * the two things that were genuinely wrong: the same endpoint was fetched once
 * per consumer, and a write left the other consumers showing stale values
 * until they happened to remount.
 *
 * Headless: rstest has no DOM environment, so these drive the `QueryClient`
 * directly — the same machinery the hooks wrap — with msw as the network.
 */

import { afterAll, afterEach, beforeAll, describe, expect, it } from "@rstest/core";
import { HttpResponse, http } from "msw";
import { OpenAPI } from "@/api/generated";
import { qk } from "@/app/state/queries/keys";
import { resetForWorkspaceSwitch } from "@/app/state/queries/queryClient";
import {
  agentProviderQuery,
  agentSkillsQuery,
  knowledgeSourcesQuery,
  workspaceTargetsQuery,
} from "@/app/state/queries/settings";
import { targetsQuery } from "@/app/state/queries/workspace";
import { makeMswServer, makeTestQueryClient } from "@/test/queryTestUtils";

// msw resolves its relative handler paths against `location`, which node lacks.
Reflect.set(globalThis, "location", new URL("http://localhost/"));

const PROVIDER = {
  provider: "deepseek",
  model: "deepseek:chat",
  models: { cheap: "a", default: "deepseek:chat", heavy: "b" },
  instructions: "be brief",
  configurations: [],
};

const harness = makeMswServer([
  http.get("*/api/agent/provider", () => HttpResponse.json(PROVIDER)),
  http.get("*/api/targets", () =>
    HttpResponse.json({
      targets: [{ name: "local", scheduler: "local", isRemote: false, scratchRoot: "/tmp" }],
    }),
  ),
  http.get("*/api/workspace/targets", () =>
    HttpResponse.json({ targets: [{ name: "hpc", host: "login", root_path: "/scratch" }] }),
  ),
  http.get("*/api/agent/skills", () => HttpResponse.json([{ id: "s1", name: "Review" }])),
]);

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

/** Requests whose pathname is exactly `path`. */
const callsTo = (path: string): number =>
  harness.requests.filter((r) => new URL(r.url).pathname === path).length;

describe("settings queries", () => {
  it("serves every provider consumer from one request", async () => {
    const client = makeTestQueryClient();
    // Four consumers in the real app: the composer's model picker plus three
    // settings sections. Each used to issue its own GET on mount.
    await Promise.all([
      client.fetchQuery(agentProviderQuery()),
      client.fetchQuery(agentProviderQuery()),
      client.fetchQuery(agentProviderQuery()),
      client.fetchQuery(agentProviderQuery()),
    ]);
    expect(callsTo("/api/agent/provider")).toBe(1);
    expect(client.getQueryData(qk.agentProvider())).toMatchObject({ model: "deepseek:chat" });
  });

  it("shares the compute-target key with the run dialogs", async () => {
    const client = makeTestQueryClient();
    // `targetsQuery` is what CreateRunDialog / RunToolbar already used; the
    // settings panel has to land on that entry, not a parallel one.
    expect(targetsQuery().queryKey).toEqual(qk.targets());
    await client.fetchQuery(targetsQuery());
    await client.fetchQuery(targetsQuery());
    expect(callsTo("/api/targets")).toBe(1);
  });

  it("publishes a provider write to every consumer without refetching", async () => {
    const client = makeTestQueryClient();
    await client.fetchQuery(agentProviderQuery());
    expect(callsTo("/api/agent/provider")).toBe(1);

    // What `useApplyAgentProvider` does after a model switch: the response is
    // the full document, so there is nothing to go back and ask for.
    client.setQueryData(qk.agentProvider(), { ...PROVIDER, model: "deepseek:reasoner" });

    expect(client.getQueryData(qk.agentProvider())).toMatchObject({ model: "deepseek:reasoner" });
    expect(callsTo("/api/agent/provider")).toBe(1);
  });

  it("keeps the remote-workspace registry across a workspace switch", async () => {
    const client = makeTestQueryClient();
    await client.fetchQuery(workspaceTargetsQuery());
    await client.fetchQuery(agentSkillsQuery());

    await resetForWorkspaceSwitch(client);

    // The list you switch *between* must survive the switch; per-workspace
    // agent state must not.
    expect(client.getQueryData(qk.workspaceTargets())).toBeDefined();
    expect(client.getQueryData(qk.agentSkills())).toBeUndefined();
  });

  it("does not retry a 503 from an unconfigured agent backend", async () => {
    harness.server.use(
      http.get("*/api/agent/knowledge-sources", () => new HttpResponse(null, { status: 503 })),
    );
    const client = makeTestQueryClient();
    await client.fetchQuery(knowledgeSourcesQuery()).catch(() => null);
    // `retry: false` — "not configured" is an answer, not a transient failure.
    expect(callsTo("/api/agent/knowledge-sources")).toBe(1);
  });
});
