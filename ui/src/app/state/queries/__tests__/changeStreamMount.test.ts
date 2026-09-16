/**
 * Change-stream behaviour against the shapes the server actually sends.
 *
 * The frames here are copied from `stream_workspace_changes` in
 * `server/routes/workspace.py`: `hello` carries `{versions, seq, replayed}`
 * and each `change` carries `{kind, ref, seq, projectId, experimentId, runId}`.
 * The replay-gap cases are the ones worth locking — getting them wrong means
 * the cache silently serves stale data after a reconnect.
 */

import { afterEach, describe, expect, it } from "@rstest/core";
import { QueryClient } from "@tanstack/react-query";
import {
  acquireChangeStream,
  getChangeStreamState,
  resetChangeStreamState,
  startChangeStream,
} from "../changeStream";
import { qk } from "../keys";

class FakeSource {
  static instances: FakeSource[] = [];
  listeners = new Map<string, ((event: { data?: unknown }) => void)[]>();
  closed = false;

  constructor(readonly url: string) {
    FakeSource.instances.push(this);
  }

  addEventListener(type: string, listener: (event: { data?: unknown }) => void): void {
    const list = this.listeners.get(type) ?? [];
    list.push(listener);
    this.listeners.set(type, list);
  }

  emit(type: string, data?: unknown): void {
    for (const fn of this.listeners.get(type) ?? []) {
      fn({ data: data === undefined ? undefined : JSON.stringify(data) });
    }
  }

  close(): void {
    this.closed = true;
  }

  static reset(): void {
    FakeSource.instances = [];
  }

  static get latest(): FakeSource {
    const last = FakeSource.instances.at(-1);
    if (!last) throw new Error("no stream opened");
    return last;
  }
}

const makeClient = (): QueryClient =>
  new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });

/** Seed a query so invalidation is observable without a network. */
const seed = (client: QueryClient, key: readonly unknown[]): void => {
  client.setQueryData(key, { seeded: true });
};

const isStale = (client: QueryClient, key: readonly unknown[]): boolean =>
  client
    .getQueryCache()
    .find({ queryKey: key as unknown[] })
    ?.isStaleByTime(Infinity) ?? false;

afterEach(() => {
  FakeSource.reset();
  resetChangeStreamState();
});

describe("change stream", () => {
  it("reports connected once the server opens the stream", () => {
    const client = makeClient();
    const controller = startChangeStream({
      client,
      eventSourceFactory: (url) => new FakeSource(url),
    });

    expect(getChangeStreamState().connected).toBe(false);
    FakeSource.latest.emit("open");
    expect(getChangeStreamState().connected).toBe(true);

    controller.stop();
    expect(getChangeStreamState().connected).toBe(false);
  });

  it("invalidates only the keys a change names", async () => {
    const client = makeClient();
    seed(client, qk.run("r1"));
    seed(client, qk.knowledge(null));
    const controller = startChangeStream({
      client,
      debounceMs: 0,
      eventSourceFactory: (url) => new FakeSource(url),
    });
    FakeSource.latest.emit("open");
    FakeSource.latest.emit("hello", { versions: {}, seq: 1, replayed: false });
    FakeSource.latest.emit("change", { kind: "run", ref: "r1", seq: 2 });

    await new Promise((r) => setTimeout(r, 5));

    expect(isStale(client, qk.run("r1"))).toBe(true);
    expect(isStale(client, qk.knowledge(null))).toBe(false);
    controller.stop();
  });

  it("tracks the server seq so a reconnect resumes from it", () => {
    const client = makeClient();
    const controller = startChangeStream({
      client,
      eventSourceFactory: (url) => new FakeSource(url),
    });
    FakeSource.latest.emit("open");
    FakeSource.latest.emit("hello", { versions: {}, seq: 42, replayed: false });

    expect(getChangeStreamState().lastSeq).toBe(42);
    expect(FakeSource.latest.url).not.toContain("since=");
    controller.stop();
  });

  it("does not invalidate list keys on the very first hello", async () => {
    const client = makeClient();
    seed(client, qk.projects());
    const controller = startChangeStream({
      client,
      debounceMs: 0,
      eventSourceFactory: (url) => new FakeSource(url),
    });
    FakeSource.latest.emit("open");
    // First connection: `replayed` is false because there was nothing to
    // replay, which must not be mistaken for a gap.
    FakeSource.latest.emit("hello", { versions: {}, seq: 5, replayed: false });

    await new Promise((r) => setTimeout(r, 5));
    expect(isStale(client, qk.projects())).toBe(false);
    controller.stop();
  });

  it("treats a reconnect without replay as a gap and refreshes list keys", async () => {
    const client = makeClient();
    const controller = startChangeStream({
      client,
      debounceMs: 0,
      minBackoffMs: 1,
      eventSourceFactory: (url) => new FakeSource(url),
    });
    FakeSource.latest.emit("open");
    FakeSource.latest.emit("hello", { versions: {}, seq: 5, replayed: false });

    seed(client, qk.projects());
    FakeSource.latest.emit("error");
    await new Promise((r) => setTimeout(r, 10));

    FakeSource.latest.emit("open");
    FakeSource.latest.emit("hello", { versions: {}, seq: 9, replayed: false });
    await new Promise((r) => setTimeout(r, 5));

    expect(isStale(client, qk.projects())).toBe(true);
    controller.stop();
  });

  it("refreshes when the server reports a replay it could not complete", async () => {
    // A backlog larger than the server's replay cap comes back as
    // `replayed: false` with no change frames, however far `seq` has advanced.
    const client = makeClient();
    const controller = startChangeStream({
      client,
      debounceMs: 0,
      minBackoffMs: 1,
      eventSourceFactory: (url) => new FakeSource(url),
    });
    FakeSource.latest.emit("open");
    FakeSource.latest.emit("hello", { versions: {}, seq: 1, replayed: false });

    seed(client, qk.projects());
    FakeSource.latest.emit("error");
    await new Promise((r) => setTimeout(r, 10));

    FakeSource.latest.emit("open");
    FakeSource.latest.emit("hello", {
      versions: {},
      seq: 5_000,
      replayed: false,
    });
    await new Promise((r) => setTimeout(r, 5));

    expect(isStale(client, qk.projects())).toBe(true);
    controller.stop();
  });

  it("trusts a replay that fits inside the server cap", async () => {
    const client = makeClient();
    const controller = startChangeStream({
      client,
      debounceMs: 0,
      minBackoffMs: 1,
      eventSourceFactory: (url) => new FakeSource(url),
    });
    FakeSource.latest.emit("open");
    FakeSource.latest.emit("hello", { versions: {}, seq: 1, replayed: false });

    seed(client, qk.projects());
    FakeSource.latest.emit("error");
    await new Promise((r) => setTimeout(r, 10));

    FakeSource.latest.emit("open");
    FakeSource.latest.emit("hello", { versions: {}, seq: 5, replayed: true });
    await new Promise((r) => setTimeout(r, 5));

    expect(isStale(client, qk.projects())).toBe(false);
    controller.stop();
  });

  it("opens exactly one connection for many mounts", () => {
    const client = makeClient();
    // `acquireChangeStream` is what the React hook calls; two mounts must not
    // mean two sockets.
    const releaseA = acquireChangeStream(client);
    const opened = FakeSource.instances.length;
    const releaseB = acquireChangeStream(client);
    expect(FakeSource.instances.length).toBe(opened);
    releaseA();
    releaseB();
  });
});
