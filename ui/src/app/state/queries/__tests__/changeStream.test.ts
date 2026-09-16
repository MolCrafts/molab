/**
 * Change-stream controller contract, driven headlessly with a scripted
 * `EventSource` and fake timers: coalescing, targeted invalidation, hidden-tab
 * behaviour, reconnect backoff with `since=`, gap handling, and teardown.
 */

import { afterEach, beforeEach, describe, expect, it, rs } from "@rstest/core";
import { hashKey, type QueryClient } from "@tanstack/react-query";
import {
  buildStreamUrl,
  type ChangeStreamController,
  coalesce,
  getChangeStreamState,
  parseChange,
  resetChangeStreamState,
  startChangeStream,
} from "@/app/state/queries/changeStream";
import { qk } from "@/app/state/queries/keys";
import {
  FakeEventSource,
  fakeEventSourceFactory,
  makeTestQueryClient,
} from "@/test/queryTestUtils";

interface InvalidateCall {
  queryKey?: readonly unknown[];
  refetchType?: string;
}

/** Record every `invalidateQueries` call while keeping the real behaviour. */
const spyInvalidate = (client: QueryClient): InvalidateCall[] => {
  const calls: InvalidateCall[] = [];
  const original = client.invalidateQueries.bind(client);
  client.invalidateQueries = ((filters?: InvalidateCall) => {
    calls.push({ queryKey: filters?.queryKey, refetchType: filters?.refetchType });
    return original(filters as Parameters<typeof original>[0]);
  }) as typeof client.invalidateQueries;
  return calls;
};

const isStale = (client: QueryClient, key: readonly unknown[]): boolean =>
  client.getQueryCache().find({ queryKey: key, exact: true })?.state.isInvalidated === true;

let client: QueryClient;
let controller: ChangeStreamController | null;

beforeEach(() => {
  rs.useFakeTimers();
  FakeEventSource.reset();
  resetChangeStreamState();
  client = makeTestQueryClient();
  client.setQueryData(qk.run("r1"), { seeded: true });
  client.setQueryData(qk.run("r2"), { seeded: true });
  client.setQueryData(qk.projects(), { seeded: true });
  client.setQueryData(qk.runsIndex(null), { seeded: true });
  controller = null;
});

afterEach(() => {
  controller?.stop();
  rs.useRealTimers();
});

const start = (overrides: { isVisible?: () => boolean } = {}): ChangeStreamController => {
  controller = startChangeStream({
    client,
    eventSourceFactory: fakeEventSourceFactory,
    minBackoffMs: 1000,
    maxBackoffMs: 4000,
    ...overrides,
  });
  return controller;
};

describe("startChangeStream", () => {
  it("coalesces changes inside the debounce window and invalidates each target once", () => {
    const calls = spyInvalidate(client);
    start();
    const source = FakeEventSource.latest;
    source.open();
    expect(getChangeStreamState().connected).toBe(true);

    source.emit("change", { kind: "run", ref: "r1", seq: 11 });
    source.emit("change", { kind: "run", ref: "r1", seq: 12 });
    expect(isStale(client, qk.run("r1"))).toBe(false); // still buffered

    rs.advanceTimersByTime(250);
    expect(isStale(client, qk.run("r1"))).toBe(true);
    expect(isStale(client, qk.run("r2"))).toBe(false);
    expect(
      calls.filter((c) => c.queryKey && hashKey(c.queryKey) === hashKey(qk.run("r1"))),
    ).toHaveLength(1);
    expect(getChangeStreamState().lastSeq).toBe(12);
  });

  it("marks stale without refetching while the tab is hidden", () => {
    const calls = spyInvalidate(client);
    start({ isVisible: () => false });
    const source = FakeEventSource.latest;
    source.open();
    source.emit("change", { kind: "run", ref: "r1", seq: 1 });
    rs.advanceTimersByTime(250);
    expect(calls.length).toBeGreaterThan(0);
    expect(calls.every((c) => c.refetchType === "none")).toBe(true);
    expect(isStale(client, qk.run("r1"))).toBe(true);
  });

  it("reconnects with since=<lastSeq> and exponential backoff", () => {
    start();
    const first = FakeEventSource.latest;
    first.open();
    first.emit("hello", { seq: 12, versions: {} });
    expect(first.url).not.toContain("since=");

    first.fail();
    expect(getChangeStreamState().connected).toBe(false);
    expect(first.closed).toBe(true);
    expect(FakeEventSource.instances).toHaveLength(1);

    rs.advanceTimersByTime(1000);
    expect(FakeEventSource.instances).toHaveLength(2);
    expect(FakeEventSource.latest.url).toContain("since=12");

    FakeEventSource.latest.fail(); // backoff doubles to 2000
    rs.advanceTimersByTime(1000);
    expect(FakeEventSource.instances).toHaveLength(2);
    rs.advanceTimersByTime(1000);
    expect(FakeEventSource.instances).toHaveLength(3);
  });

  it("refreshes the list-level keys once on a reconnect without replay, not with one", () => {
    start();
    const first = FakeEventSource.latest;
    first.open();
    first.emit("hello", { seq: 5 });
    expect(isStale(client, qk.projects())).toBe(false);

    first.fail();
    rs.advanceTimersByTime(1000);
    const second = FakeEventSource.latest;
    second.open();
    second.emit("hello", { seq: 9, replayed: true });
    expect(isStale(client, qk.projects())).toBe(false);

    second.fail();
    rs.advanceTimersByTime(1000);
    const third = FakeEventSource.latest;
    third.open();
    third.emit("hello", { seq: 9 });
    expect(isStale(client, qk.projects())).toBe(true);
    expect(isStale(client, qk.runsIndex(null))).toBe(true);
    expect(isStale(client, qk.run("r1"))).toBe(false);
  });

  it("stays quiet and keeps retrying when EventSource cannot be created", () => {
    let attempts = 0;
    controller = startChangeStream({
      client,
      minBackoffMs: 1000,
      eventSourceFactory: () => {
        attempts += 1;
        throw new Error("no EventSource here");
      },
    });
    expect(attempts).toBe(1);
    expect(getChangeStreamState().connected).toBe(false);
    rs.advanceTimersByTime(1000);
    expect(attempts).toBe(2);
  });

  it("stop closes the source and cancels reconnects; restart forgets lastSeq", () => {
    const ctl = start();
    const source = FakeEventSource.latest;
    source.open();
    source.emit("hello", { seq: 3 });
    expect(getChangeStreamState().lastSeq).toBe(3);

    ctl.restart();
    expect(FakeEventSource.instances).toHaveLength(2);
    expect(FakeEventSource.latest.url).not.toContain("since=");
    expect(getChangeStreamState().lastSeq).toBeNull();

    FakeEventSource.latest.fail();
    ctl.stop();
    rs.advanceTimersByTime(60_000);
    expect(FakeEventSource.instances).toHaveLength(2);
    expect(FakeEventSource.latest.closed).toBe(true);
    expect(getChangeStreamState().connected).toBe(false);
  });

  it("ignores malformed frames", () => {
    start();
    const source = FakeEventSource.latest;
    source.open();
    source.emit("change", { kind: "bogus", ref: "x" });
    source.emit("change", "not json");
    rs.advanceTimersByTime(250);
    expect(isStale(client, qk.run("r1"))).toBe(false);
  });
});

describe("pure helpers", () => {
  it("coalesce keeps one entry per kind+ref with the highest seq", () => {
    const merged = coalesce([
      { kind: "run", ref: "r1", seq: 1 },
      { kind: "asset", ref: "a1", seq: 2 },
      { kind: "run", ref: "r1", seq: 3, projectId: "p1" },
      { kind: "run", ref: "r1", seq: 2 },
    ]);
    expect(merged).toEqual([
      { kind: "run", ref: "r1", seq: 3, projectId: "p1" },
      { kind: "asset", ref: "a1", seq: 2 },
    ]);
  });

  it("parseChange accepts known kinds and drops the rest", () => {
    expect(parseChange({ kind: "run", ref: "r1", seq: 4, runId: "r1" })).toEqual({
      kind: "run",
      ref: "r1",
      seq: 4,
      runId: "r1",
    });
    expect(parseChange({ kind: "nope" })).toBeNull();
    expect(parseChange(null)).toBeNull();
  });

  it("buildStreamUrl appends since= with the right separator", () => {
    expect(buildStreamUrl("/api/s", null)).toBe("/api/s");
    expect(buildStreamUrl("/api/s", 7)).toBe("/api/s?since=7");
    expect(buildStreamUrl("/api/s?x=1", 7)).toBe("/api/s?x=1&since=7");
  });
});
