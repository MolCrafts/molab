/**
 * Following one attempt's log, window by window.
 *
 * The server hands back at most 256 KiB of `stdout.log` / `stderr.log` /
 * `run.log` per call, with the offset to ask from next. The accumulated text
 * *is* the query data: each fetch reads the cached `{text, nextOffset}` and
 * appends what came after it, so nothing about the log lives in component
 * state and two views of the same stream share one cache entry.
 */

import { queryOptions, useQuery } from "@tanstack/react-query";
import { runsApi } from "@/api";
import type { RunLogChunkResponse } from "@/api/runs";
import { journalRefetchInterval, runKeys } from "@/app/state/entityQueries";

export type LogStream = "stdout" | "stderr" | "run";

export const LOG_STREAMS: readonly LogStream[] = ["stdout", "stderr", "run"];

/** The file a stream is read from, relative to the attempt. */
export const logFileOf = (stream: LogStream): string => `${stream}.log`;

/** How much text the browser keeps per stream, in characters (about 2 MB). */
export const LOG_TEXT_CAP = 2 * 1024 * 1024;

/**
 * Windows one fetch reads back to back before it hands the text over.
 *
 * A finished log of any size needs at most `LOG_TEXT_CAP` / 256 KiB windows
 * once the head is skipped; the bound only matters for a log that grows
 * faster than it is read, and the next fetch then follows at once.
 */
const MAX_WINDOWS_PER_FETCH = 16;

/** Poll interval while a fetch stopped short of the end. */
const CATCH_UP_INTERVAL = 100;

export interface ExecutionLogCoords {
  projectId: string;
  experimentId: string;
  runId: string;
  executionId: string;
}

export interface ExecutionLogData {
  /** The tail of the log the browser holds — at most `LOG_TEXT_CAP` characters. */
  text: string;
  /** Byte offset the next read starts from. */
  nextOffset: number;
  /** The file's size at the last read; `0` when it does not exist yet. */
  size: number;
  eof: boolean;
  /** The head of the log was dropped (or never read) to stay under the cap. */
  truncated: boolean;
  /** Whether the attempt was still active when this was read. */
  readWhileLive: boolean;
}

type FetchChunk = (offset: number) => Promise<RunLogChunkResponse>;

/** Keep the last `cap` characters, starting on a line when one begins close by. */
const keepTail = (text: string, cap: number): string => {
  const cut = text.length - cap;
  const tail = text.slice(cut);
  const newline = tail.indexOf("\n");
  return newline >= 0 && newline < 4096 ? tail.slice(newline + 1) : tail;
};

/**
 * Read from where `previous` stopped until the end of the file.
 *
 * A first read of a log larger than the cap skips straight to its last
 * `cap` bytes — fetching 100 MB to show the last two is not a read worth
 * doing. A file that shrank (rewritten) is read again from the start.
 */
export const readLogWindows = async (
  fetchChunk: FetchChunk,
  previous: ExecutionLogData | undefined,
  options: { live: boolean; cap?: number },
): Promise<ExecutionLogData> => {
  const cap = options.cap ?? LOG_TEXT_CAP;
  let text = previous?.text ?? "";
  let offset = previous?.nextOffset ?? 0;
  let truncated = previous?.truncated ?? false;
  let size = previous?.size ?? 0;
  let eof = false;
  let skipped = previous !== undefined;

  for (let window = 0; window < MAX_WINDOWS_PER_FETCH; window += 1) {
    const chunk = await fetchChunk(offset);
    if (chunk.size < offset) {
      text = "";
      offset = 0;
      truncated = false;
      skipped = true;
      continue;
    }
    if (!skipped && chunk.offset === 0 && chunk.size > cap) {
      skipped = true;
      truncated = true;
      offset = chunk.size - cap;
      continue;
    }
    skipped = true;
    text += chunk.text;
    if (text.length > cap) {
      text = keepTail(text, cap);
      truncated = true;
    }
    size = chunk.size;
    eof = chunk.eof;
    const advanced = chunk.nextOffset > offset;
    offset = chunk.nextOffset;
    if (eof || !advanced) break;
  }

  return { text, nextOffset: offset, size, eof, truncated, readWhileLive: options.live };
};

/** The journal's poll interval: what "while the attempt is active" means here. */
const LIVE_INTERVAL = journalRefetchInterval("running") || 1500;

/**
 * When the next read happens.
 *
 * Short of the end: at once. While the attempt is active: on the journal's
 * interval. Once it is terminal: one closing read (lines written after the
 * last live poll), then never again.
 */
export const executionLogRefetchInterval = (
  data: ExecutionLogData | undefined,
  live: boolean,
): number | false => {
  if (data && !data.eof) return CATCH_UP_INTERVAL;
  if (live) return LIVE_INTERVAL;
  if (data?.readWhileLive) return CATCH_UP_INTERVAL;
  return false;
};

export const executionLogQueryOptions = (
  coords: ExecutionLogCoords,
  stream: LogStream,
  options: { live: boolean },
) => {
  const { projectId, experimentId, runId, executionId } = coords;
  const { live } = options;
  return queryOptions({
    queryKey: runKeys.log(projectId, experimentId, runId, executionId, stream),
    queryFn: ({ client, queryKey }) =>
      readLogWindows(
        (offset) =>
          runsApi.getRunExecutionLogChunk(
            projectId,
            experimentId,
            runId,
            executionId,
            stream,
            offset,
          ),
        client.getQueryData<ExecutionLogData>(queryKey),
        { live },
      ),
    refetchInterval: (query) => executionLogRefetchInterval(query.state.data, live),
    refetchIntervalInBackground: false,
  });
};

/**
 * One log stream of one attempt, accumulated across reads.
 *
 * `live` is the journal's gate on the attempt's status
 * (`journalRefetchInterval(status) !== false`): it polls only while that is
 * true, never on a hidden tab, and stops at the end of the file once the
 * attempt is terminal. An empty `executionId` disables it.
 */
export const useExecutionLog = (
  projectId: string,
  experimentId: string,
  runId: string,
  executionId: string,
  stream: LogStream,
  options: { live: boolean; enabled?: boolean },
) =>
  useQuery({
    ...executionLogQueryOptions({ projectId, experimentId, runId, executionId }, stream, options),
    enabled:
      Boolean(projectId && experimentId && runId && executionId) && (options.enabled ?? true),
  });
