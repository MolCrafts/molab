/**
 * Loading metrics for the comparison set.
 *
 * Reading a set of runs costs two round-trips each (list the attempt's files,
 * then fetch whichever ones a reader claims) and the parsing happens in the
 * browser. Gathering in the dock stays cheap; the Compare page is the ask, and
 * it scans when it has a set. Cached (run, attempt) reads are not repeated.
 *
 * Results are cached per (run, attempt) for the life of the session, so
 * revisiting the page — or changing which metric is plotted — re-reads nothing.
 */

import { useCallback, useRef, useState } from "react";

import { runsApi } from "@/api/runs";
import { collectRunSeries, type MetricRunSource, type RunAllSeries } from "@/plugins/molplot";
import { readExecutionMetrics } from "@/plugins/molplot/read-metrics";
import { STEP_INTERVAL } from "@/plugins/molplot/resolution";

import type { CompareEntry } from "./types";
import { refKey } from "./types";

/** Attempt statuses worth plotting, best first. */
const PREFERRED_STATUS = ["succeeded", "finalizing", "running", "interrupted", "failed"];

/**
 * Pick the attempt to plot when the entry does not name one.
 *
 * A run's last attempt is not always the interesting one — a failed retry
 * after a good run would hide the result. Prefer the most recent attempt in
 * the best available state, and fall back to the most recent of any state so a
 * run is never silently skipped.
 */
export const pickExecutionId = (
  executions: readonly { id: string; status: string; createdAt: string }[],
): string | null => {
  if (executions.length === 0) return null;
  const byRecency = [...executions].sort((a, b) => b.createdAt.localeCompare(a.createdAt));
  for (const status of PREFERRED_STATUS) {
    const match = byRecency.find((execution) => execution.status.toLowerCase() === status);
    if (match) return match.id;
  }
  return byRecency[0].id;
};

export interface CompareMetricsState {
  perRunAll: RunAllSeries[];
  /** Run titles whose metrics could not be read. */
  failures: string[];
  /** Runs with no attempt at all — nothing has been executed yet. */
  unexecuted: string[];
  loading: boolean;
  error: string | null;
  /** True once a scan has completed, so the page can tell "empty" from "unasked". */
  scanned: boolean;
}

const EMPTY: CompareMetricsState = {
  perRunAll: [],
  failures: [],
  unexecuted: [],
  loading: false,
  error: null,
  scanned: false,
};

/** Cache key: a run's metrics depend on which attempt was read. */
const cacheKey = (entry: CompareEntry, executionId: string): string =>
  `${refKey(entry.ref)}@${executionId}`;

export interface UseCompareMetrics extends CompareMetricsState {
  /** Read every entry's metrics. Safe to call again; cached runs are not re-read. */
  scan: (entries: readonly CompareEntry[], groupOf: (entry: CompareEntry) => string) => void;
  reset: () => void;
}

export const useCompareMetrics = (): UseCompareMetrics => {
  const [state, setState] = useState<CompareMetricsState>(EMPTY);
  const cache = useRef(new Map<string, RunAllSeries>());
  const runToken = useRef(0);

  const scan = useCallback(
    (entries: readonly CompareEntry[], groupOf: (entry: CompareEntry) => string) => {
      const token = ++runToken.current;
      setState((current) => ({ ...current, loading: true, error: null }));

      void (async () => {
        try {
          // Resolve "latest" per entry first: which attempt to read is part of
          // the cache key, so it has to be settled before the cache is consulted.
          const resolved = await Promise.all(
            entries.map(async (entry) => {
              if (entry.executionId) return { entry, executionId: entry.executionId };
              const { workspaceKey, projectId, experimentId, runId } = entry.ref;
              try {
                const executions = workspaceKey
                  ? await runsApi.listExecutionsWs(workspaceKey, projectId, experimentId, runId)
                  : await runsApi.listExecutions(projectId, experimentId, runId);
                return { entry, executionId: pickExecutionId(executions) };
              } catch {
                return { entry, executionId: null };
              }
            }),
          );
          if (token !== runToken.current) return;

          const unexecuted: string[] = [];
          const cached: RunAllSeries[] = [];
          const toRead: { entry: CompareEntry; source: MetricRunSource }[] = [];

          for (const { entry, executionId } of resolved) {
            if (!executionId) {
              unexecuted.push(entry.runName);
              continue;
            }
            const key = refKey(entry.ref);
            const hit = cache.current.get(cacheKey(entry, executionId));
            if (hit) {
              // Grouping is a display choice and may have changed since the
              // read; re-stamp it rather than re-fetching the numbers.
              cached.push({ ...hit, label: groupOf(entry) });
              continue;
            }
            toRead.push({
              entry,
              source: {
                key,
                label: groupOf(entry),
                title: entry.runName,
                coords: {
                  workspaceKey: entry.ref.workspaceKey || undefined,
                  projectId: entry.ref.projectId,
                  experimentId: entry.ref.experimentId,
                  runId: entry.ref.runId,
                  executionId,
                },
              },
            });
          }

          const { perRunAll, failures } = await collectRunSeries(
            (coords) =>
              readExecutionMetrics(coords, { stepInterval: STEP_INTERVAL }).then(
                (read) => read.records,
              ),
            toRead.map((item) => item.source),
          );
          if (token !== runToken.current) return;

          for (const loaded of perRunAll) {
            const match = toRead.find((item) => item.source.key === loaded.key);
            if (match) {
              cache.current.set(cacheKey(match.entry, match.source.coords.executionId), loaded);
            }
          }

          // Restore the caller's order; the fan-out resolves out of order.
          const byKey = new Map([...cached, ...perRunAll].map((row) => [row.key, row]));
          const ordered = entries
            .map((entry) => byKey.get(refKey(entry.ref)))
            .filter((row): row is RunAllSeries => row !== undefined);

          setState({
            perRunAll: ordered,
            failures,
            unexecuted,
            loading: false,
            error:
              ordered.length === 0 && (failures.length > 0 || unexecuted.length > 0)
                ? "None of the selected runs had readable metrics."
                : null,
            scanned: true,
          });
        } catch (error) {
          if (token !== runToken.current) return;
          setState({
            ...EMPTY,
            scanned: true,
            error: error instanceof Error ? error.message : "Failed to read metrics",
          });
        }
      })();
    },
    [],
  );

  const reset = useCallback(() => {
    runToken.current += 1;
    setState(EMPTY);
  }, []);

  return { ...state, scan, reset };
};
