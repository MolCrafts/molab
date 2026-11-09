/**
 * The compare set as columns (L05-4): each run with its title, status, parameters,
 * the scalar results of its result attempt (the latest sealed success) and that
 * attempt's wall time. Results come through the shared outputs query, so the
 * experiment's Runs table and this page read each attempt once.
 */

import { useQueries } from "@tanstack/react-query";
import { useMemo } from "react";
import { runPresentationStatus } from "@/app/runs/projections";
import { runLabel } from "@/app/runs/runTitle";
import type { WorkspaceExecutionRow, WorkspaceRunRow } from "@/app/runs/types";
import { useWorkspaceRuns } from "@/app/runs/useWorkspaceRuns";
import { executionOutputsQueryOptions } from "@/app/state/entityQueries";
import { normalizeStatus } from "@/app/status/vocabulary";
import { parseInstant } from "@/lib/format-time";
import type { ComparedColumn } from "./compareModel";
import type { CompareEntry } from "./types";
import { refKey } from "./types";

export interface ComparedRun extends ComparedColumn {
  entry: CompareEntry;
  title: string;
  status: string;
  /** The attempt the results come from. */
  executionId: string | null;
}

const resultAttempt = (
  row: WorkspaceRunRow | undefined,
  pinned: string | null,
): WorkspaceExecutionRow | null => {
  const executions = row?.executions ?? [];
  if (pinned) return executions.find((execution) => execution.executionId === pinned) ?? null;
  return (
    [...executions]
      .reverse()
      .find((execution) => normalizeStatus(execution.status) === "succeeded") ??
    executions.at(-1) ??
    null
  );
};

const secondsOf = (execution: WorkspaceExecutionRow | null): number | null => {
  if (!execution) return null;
  if (execution.durationSeconds !== null) return execution.durationSeconds;
  const start = parseInstant(execution.startedAt);
  const end = parseInstant(execution.finishedAt);
  return start === null ? null : Math.max(0, (end ?? Date.now()) - start) / 1000;
};

/** Module-level so TanStack re-runs it only when an outputs read changes. */
const combineResults = (queries: readonly { data?: { results?: unknown } }[]) =>
  queries.map((query) => (query.data?.results as Record<string, unknown> | undefined) ?? null);

export const useComparedRuns = (
  entries: readonly CompareEntry[],
): { runs: ComparedRun[]; loading: boolean } => {
  const { rows, loading } = useWorkspaceRuns();
  const found = useMemo(
    () =>
      entries.map((entry) => {
        const row = rows.find(
          (candidate) =>
            candidate.id === entry.ref.runId && candidate.workspaceKey === entry.ref.workspaceKey,
        );
        return { entry, row, attempt: resultAttempt(row, entry.executionId) };
      }),
    [entries, rows],
  );
  const results = useQueries({
    queries: found.map(({ entry, attempt }) => ({
      ...executionOutputsQueryOptions(
        entry.ref.projectId,
        entry.ref.experimentId,
        entry.ref.runId,
        attempt?.executionId ?? "",
      ),
      enabled: attempt !== null,
      staleTime: 60_000,
    })),
    combine: combineResults,
  });
  const runs = useMemo(
    () =>
      found.map(
        ({ entry, row, attempt }, index): ComparedRun => ({
          key: refKey(entry.ref),
          entry,
          title: row ? runLabel(row) : entry.runName || entry.ref.runId,
          status: row ? runPresentationStatus(row) : "unknown",
          parameters: row?.parameters ?? entry.parameters ?? {},
          results: results[index] ?? null,
          seconds: secondsOf(attempt),
          executionId: attempt?.executionId ?? null,
        }),
      ),
    [found, results],
  );
  return { runs, loading };
};
