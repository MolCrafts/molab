/**
 * The runs beside a run, as the comparison reads them (`runCompare`): every
 * run of its experiment with its title, parameters, status and — when asked —
 * the scalar results of its run-result attempt. One outputs query per sibling,
 * shared with every other view of that attempt through its query key.
 */

import { useQueries } from "@tanstack/react-query";
import { useMemo } from "react";
import { useScopeRuns } from "@/app/dashboard/useScopeRuns";
import type { ComparedRun } from "@/app/renderers/run/runCompare";
import { runPresentationStatus } from "@/app/runs/projections";
import { runLabel } from "@/app/runs/runTitle";
import { executionOutputsQueryOptions } from "@/app/state/entityQueries";
import { normalizeStatus } from "@/app/status/vocabulary";

/** Siblings whose results are read; past this the chart would not be legible anyway. */
const MAX_SIBLINGS_READ = 60;

/**
 * Module-level so its reference is stable: TanStack then re-runs it only when a
 * result changes, and the comparison is not rebuilt every render.
 */
const combineResults = (
  queries: readonly { data?: { results?: unknown }; isPending: boolean; isFetching: boolean }[],
) => ({
  results: queries.map(
    (item) => (item.data?.results as Record<string, unknown> | undefined) ?? null,
  ),
  pending: queries.some((item) => item.isPending && item.isFetching),
});

export const useRunSiblings = (
  run: { id: string; experimentId: string } | null,
  { results = false }: { results?: boolean } = {},
): { siblings: ComparedRun[]; loading: boolean } => {
  const { rows, query } = useScopeRuns({ experimentId: run?.experimentId ?? "" }, Boolean(run));
  const resultAttempts = useMemo(
    () =>
      rows.slice(0, MAX_SIBLINGS_READ).map((row) => ({
        row,
        executionId:
          [...row.executions]
            .reverse()
            .find((execution) => normalizeStatus(execution.status) === "succeeded")?.executionId ??
          null,
      })),
    [rows],
  );
  const outputs = useQueries({
    queries: resultAttempts.map(({ row, executionId }) => ({
      ...executionOutputsQueryOptions(row.projectId, row.experimentId, row.id, executionId ?? ""),
      enabled: results && executionId !== null,
      staleTime: 60_000,
    })),
    combine: combineResults,
  });
  const siblings = useMemo(
    () =>
      resultAttempts.map(
        ({ row }, index): ComparedRun => ({
          id: row.id,
          title: runLabel(row),
          parameters: row.parameters ?? {},
          status: runPresentationStatus(row),
          results: outputs.results[index] ?? null,
        }),
      ),
    [resultAttempts, outputs.results],
  );
  return {
    siblings,
    loading: query.isPending || (results && outputs.pending),
  };
};
