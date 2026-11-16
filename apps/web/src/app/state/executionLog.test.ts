import { beforeEach, describe, expect, it, rs } from "@rstest/core";
import { QueryClient } from "@tanstack/react-query";
import { runsApi } from "@/api";
import type { RunLogChunkResponse } from "@/api/runs";
import { runKeys } from "./entityQueries";
import {
  type ExecutionLogData,
  executionLogQueryOptions,
  executionLogRefetchInterval,
  LOG_TEXT_CAP,
  readLogWindows,
} from "./executionLog";

rs.mock("@/api", () => ({
  runsApi: { getRunExecutionLogChunk: rs.fn() },
  assetsApi: {},
  projectsApi: {},
  workspaceApi: {},
}));

const coords = { projectId: "p", experimentId: "x", runId: "r", executionId: "e01" };

/** A log file the fake server reads windows from, `window` bytes at a time. */
const serveFile = (content: () => string, window = 4) => {
  return async (offset: number): Promise<RunLogChunkResponse> => {
    const body = content();
    const text = body.slice(offset, offset + window);
    const nextOffset = offset + text.length;
    return {
      stream: "stdout" as RunLogChunkResponse.stream,
      text,
      offset,
      nextOffset,
      size: body.length,
      eof: nextOffset >= body.length,
    };
  };
};

const mockChunks = (fetch: (offset: number) => Promise<RunLogChunkResponse>) => {
  rs.mocked(runsApi.getRunExecutionLogChunk).mockImplementation(
    (_p, _x, _r, _e, _stream, offset) =>
      fetch(offset) as unknown as ReturnType<typeof runsApi.getRunExecutionLogChunk>,
  );
};

describe("useExecutionLog query", () => {
  beforeEach(() => {
    rs.clearAllMocks();
  });

  it("appends each read to the text already held, from the previous nextOffset", async () => {
    let body = "line 1\n";
    mockChunks(serveFile(() => body, 64));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const options = executionLogQueryOptions(coords, "stdout", { live: true });

    const first = await client.fetchQuery(options);
    expect(first).toMatchObject({ text: "line 1\n", nextOffset: 7, eof: true });

    body += "line 2\n";
    const second = await client.fetchQuery({ ...options, staleTime: 0 });
    expect(second.text).toBe("line 1\nline 2\n");
    expect(second.nextOffset).toBe(14);
    const offsets = rs.mocked(runsApi.getRunExecutionLogChunk).mock.calls.map((call) => call[5]);
    expect(offsets).toEqual([0, 7]);
    // The accumulated text is the cache entry, under the run's log key.
    expect(client.getQueryData(runKeys.log("p", "x", "r", "e01", "stdout"))).toEqual(second);
  });

  it("fetches the next window at once while eof is false", async () => {
    mockChunks(serveFile(() => "abcdefghij", 4));
    const client = new QueryClient();

    const data = await client.fetchQuery(
      executionLogQueryOptions(coords, "stderr", { live: false }),
    );

    expect(data.text).toBe("abcdefghij");
    expect(data.eof).toBe(true);
    expect(rs.mocked(runsApi.getRunExecutionLogChunk)).toHaveBeenCalledTimes(3);
    expect(rs.mocked(runsApi.getRunExecutionLogChunk).mock.calls.map((call) => call[4])).toEqual([
      "stderr",
      "stderr",
      "stderr",
    ]);
  });

  it("polls while live, makes one closing read once terminal, then stops at eof", () => {
    const at = (eof: boolean, readWhileLive: boolean): ExecutionLogData => ({
      text: "",
      nextOffset: 0,
      size: 0,
      eof,
      truncated: false,
      readWhileLive,
    });
    // Short of the end: the next window comes at once, live or not.
    expect(executionLogRefetchInterval(at(false, false), false)).toBeLessThan(1500);
    // Active attempt at the end: the journal's interval.
    expect(executionLogRefetchInterval(at(true, true), true)).toBe(1500);
    // Just turned terminal: one more read for lines written after the last poll.
    expect(executionLogRefetchInterval(at(true, true), false)).not.toBe(false);
    // Terminal and read as terminal, at the end: no more polling.
    expect(executionLogRefetchInterval(at(true, false), false)).toBe(false);
    expect(executionLogRefetchInterval(undefined, false)).toBe(false);
  });

  it("stops a terminal attempt's query from polling once it reached eof", async () => {
    mockChunks(serveFile(() => "done\n", 64));
    const client = new QueryClient();
    const options = executionLogQueryOptions(coords, "run", { live: false });
    await client.fetchQuery(options);
    const query = client.getQueryCache().find<ExecutionLogData>({ queryKey: options.queryKey });
    expect(query?.state.data?.eof).toBe(true);
    const interval = options.refetchInterval;
    expect(typeof interval).toBe("function");
    if (typeof interval !== "function" || !query) return;
    expect(interval(query as unknown as Parameters<typeof interval>[0])).toBe(false);
    expect(options.refetchIntervalInBackground).toBe(false);
  });
});

describe("readLogWindows", () => {
  it("skips to the last 2 MB of a larger log rather than reading it all", async () => {
    const size = LOG_TEXT_CAP + 1_000_000;
    const offsets: number[] = [];
    const fetchChunk = async (offset: number): Promise<RunLogChunkResponse> => {
      offsets.push(offset);
      const length = Math.min(256 * 1024, size - offset);
      return {
        stream: "stdout" as RunLogChunkResponse.stream,
        text: "x".repeat(length),
        offset,
        nextOffset: offset + length,
        size,
        eof: offset + length >= size,
      };
    };

    const data = await readLogWindows(fetchChunk, undefined, { live: false });

    expect(offsets[0]).toBe(0);
    expect(offsets[1]).toBe(size - LOG_TEXT_CAP);
    expect(data.eof).toBe(true);
    expect(data.truncated).toBe(true);
    expect(data.text.length).toBe(LOG_TEXT_CAP);
    expect(data.nextOffset).toBe(size);
  });

  it("drops the head once appended text passes the cap", async () => {
    const previous: ExecutionLogData = {
      text: `old\n${"a".repeat(96)}`,
      nextOffset: 100,
      size: 100,
      eof: true,
      truncated: false,
      readWhileLive: true,
    };
    const fetchChunk = async (offset: number): Promise<RunLogChunkResponse> => ({
      stream: "stdout" as RunLogChunkResponse.stream,
      text: "b".repeat(50),
      offset,
      nextOffset: offset + 50,
      size: offset + 50,
      eof: true,
    });

    const data = await readLogWindows(fetchChunk, previous, { live: true, cap: 120 });

    expect(data.truncated).toBe(true);
    expect(data.text.length).toBeLessThanOrEqual(120);
    expect(data.text.endsWith("b".repeat(50))).toBe(true);
    expect(data.text.startsWith("old")).toBe(false);
    expect(data.nextOffset).toBe(150);
  });

  it("reads a rewritten (shorter) file again from the start", async () => {
    const previous: ExecutionLogData = {
      text: "stale",
      nextOffset: 500,
      size: 500,
      eof: true,
      truncated: false,
      readWhileLive: true,
    };
    const data = await readLogWindows(
      serveFile(() => "fresh\n", 64),
      previous,
      { live: true },
    );
    expect(data.text).toBe("fresh\n");
    expect(data.nextOffset).toBe(6);
  });
});
