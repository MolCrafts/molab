/**
 * Runs-index caching contract, driven headlessly through `QueryObserver`.
 *
 * These lock the properties the old module-level poller had to hand-write:
 * one shared request per key, no polling on a hidden tab, and no refetch for a
 * revisit inside `staleTime`.
 */

import { afterEach, beforeEach, describe, expect, it, rs } from "@rstest/core";
import { type QueryClient, QueryObserver } from "@tanstack/react-query";

import { applyFilters } from "@/app/runs/aggregates";
import { runsIndexUrl } from "@/app/runs/api";
import type { WorkspaceRunRow, WorkspaceRunsResponse } from "@/app/runs/types";
import {
  RUN_EXECUTION_POLL_MS,
  RUN_LOGS_POLL_MS,
  RUNS_INDEX_LIMIT,
  RUNS_INDEX_STALE_MS,
  runExecutionRefetchInterval,
  runLogsEnabled,
  runLogsRefetchInterval,
  runsIndexKey,
} from "@/app/state/queries/runs";
import { makeTestQueryClient } from "@/test/queryTestUtils";

const row = (id: string, overrides: Partial<WorkspaceRunRow> = {}): WorkspaceRunRow =>
  ({
    id,
    name: id,
    status: "succeeded",
    projectId: "p1",
    experimentId: "e1",
    createdAt: new Date("2026-01-01T00:00:00Z").toISOString(),
    startedAt: null,
    finishedAt: null,
    executions: [],
    executorInfo: { backend: "local" },
    ...overrides,
  }) as unknown as WorkspaceRunRow;

const payload = (rows: WorkspaceRunRow[]): WorkspaceRunsResponse => ({
  runs: rows,
  stats: { total: rows.length, running: 0, pending: 0, failed: 0, succeeded: rows.length },
  total: rows.length,
  truncated: false,
});

/** A queryFn that counts calls, standing in for the network. */
const countingFetcher = (response: WorkspaceRunsResponse) => {
  const calls = { count: 0 };
  const fn = async (): Promise<WorkspaceRunsResponse> => {
    calls.count += 1;
    return response;
  };
  return { calls, fn };
};

let client: QueryClient;

beforeEach(() => {
  rs.useFakeTimers();
  client = makeTestQueryClient();
});

afterEach(() => {
  client.clear();
  rs.useRealTimers();
});

describe("runs index URL + key", () => {
  it("asks the server for the row cap, not for the UI filter", () => {
    expect(runsIndexUrl({ limit: RUNS_INDEX_LIMIT })).toBe(
      `/api/workspace/runs?limit=${RUNS_INDEX_LIMIT}`,
    );
    // The key names the request, so every filter shares one cache entry.
    expect(runsIndexKey()).toEqual(["runs-index", { limit: RUNS_INDEX_LIMIT }]);
  });
});

describe("runs index caching", () => {
  it("shares one request between two observers of the same key", async () => {
    const { calls, fn } = countingFetcher(payload([row("r1")]));
    const options = { queryKey: runsIndexKey(), queryFn: fn, staleTime: RUNS_INDEX_STALE_MS };

    const a = new QueryObserver(client, options);
    const b = new QueryObserver(client, options);
    const stopA = a.subscribe(() => undefined);
    const stopB = b.subscribe(() => undefined);
    await rs.advanceTimersByTimeAsync(0);

    expect(calls.count).toBe(1);
    stopA();
    stopB();
  });

  it("issues no request when an observer resubscribes inside staleTime", async () => {
    const { calls, fn } = countingFetcher(payload([row("r1")]));
    const options = { queryKey: runsIndexKey(), queryFn: fn, staleTime: RUNS_INDEX_STALE_MS };

    const first = new QueryObserver(client, options);
    const stopFirst = first.subscribe(() => undefined);
    await rs.advanceTimersByTimeAsync(0);
    expect(calls.count).toBe(1);
    stopFirst();

    // Navigating away and back well inside staleTime.
    await rs.advanceTimersByTimeAsync(RUNS_INDEX_STALE_MS / 2);
    const second = new QueryObserver(client, options);
    const stopSecond = second.subscribe(() => undefined);
    await rs.advanceTimersByTimeAsync(0);

    expect(calls.count).toBe(1);
    stopSecond();
  });

  it("leaves background polling off on the shared client", async () => {
    // A hidden tab must not poll. That is a property of the app's client
    // defaults, not of any one hook — drive it from there so it cannot drift.
    const { queryClient } = await import("@/app/state/queries/queryClient");
    expect(queryClient.getDefaultOptions().queries?.refetchIntervalInBackground).toBe(false);
  });
});

describe("poll intervals are functions of the data", () => {
  it("stops the execution poll once the attempt is terminal", () => {
    expect(runExecutionRefetchInterval({ status: "running" }, false)).toBe(RUN_EXECUTION_POLL_MS);
    expect(runExecutionRefetchInterval({ status: "succeeded" }, false)).toBe(false);
    expect(runExecutionRefetchInterval({ status: "failed" }, false)).toBe(false);
    // A still-running run keeps the poll alive even before the first response.
    expect(runExecutionRefetchInterval(undefined, true)).toBe(RUN_EXECUTION_POLL_MS);
    expect(runExecutionRefetchInterval(undefined, false)).toBe(false);
  });

  it("polls logs only while the attempt is producing output", () => {
    expect(runLogsRefetchInterval(true)).toBe(RUN_LOGS_POLL_MS);
    expect(runLogsRefetchInterval(false)).toBe(false);
  });

  it("disables the logs query until the Logs tab is active", () => {
    const coords = { projectId: "p1", experimentId: "e1", runId: "r1" };
    expect(runLogsEnabled(coords, { enabled: false })).toBe(false);
    expect(runLogsEnabled(coords, { enabled: true })).toBe(true);
    expect(runLogsEnabled(null, { enabled: true })).toBe(false);
  });
});

describe("runs index filtering", () => {
  it("filters in the client so the request never changes", () => {
    const rows = [row("r1", { status: "failed" }), row("r2", { status: "succeeded" })];
    expect(applyFilters(rows, {}).length).toBe(2);
    expect(applyFilters(rows, { status: ["failed"] }).map((r) => r.id)).toEqual(["r1"]);
  });
});
