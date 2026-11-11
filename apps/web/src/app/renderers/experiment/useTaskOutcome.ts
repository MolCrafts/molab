/**
 * Each task's status across the latest attempt of every run (L03 Outcome “by
 * task”): what the Workflow view used to spell out as text above the graph.
 * One journal query per run, shared with every other view of that attempt.
 */

import { useQueries } from "@tanstack/react-query";
import { useMemo } from "react";
import type { OutcomeGroup } from "@/app/renderers/experiment/experimentStory";
import { executionJournalQueryOptions } from "@/app/state/entityQueries";
import { countStatuses } from "@/app/status/vocabulary";
import type { RunSummary } from "@/app/types";
import { normalizeTaskGraph } from "@/plugins/workflow/flowgram-document";
import type { TaskGraphJson } from "@/plugins/workflow/task-graph-ir";

/** Runs whose journals are read; a bigger sweep shows the first ones and says so. */
export const TASK_OUTCOME_LIMIT = 60;

/** Count each task across the given journals, in first-seen order. A task not started is queued. */
export const rollupTasks = (
  graphs: readonly (TaskGraphJson | null | undefined)[],
): OutcomeGroup[] => {
  const tasks = new Map<string, { label: string; statuses: string[] }>();
  for (const graph of graphs) {
    for (const task of graph?.task_configs ?? []) {
      const entry = tasks.get(task.id) ?? { label: task.label || task.id, statuses: [] };
      tasks.set(task.id, { ...entry, statuses: [...entry.statuses, task.status ?? "queued"] });
    }
  }
  return [...tasks].map(([id, task]) => ({
    id,
    label: task.label,
    counts: countStatuses(task.statuses),
  }));
};

/** Module-level so TanStack re-runs it only when a journal changes. */
const combineGraphs = (queries: readonly { data?: unknown }[]) =>
  queries.map((query) => (query.data ? normalizeTaskGraph(query.data as never) : null));

export const useTaskOutcome = (
  runs: readonly RunSummary[],
  enabled: boolean,
): { groups: OutcomeGroup[]; partial: boolean } => {
  const attempts = useMemo(
    () =>
      runs.slice(0, TASK_OUTCOME_LIMIT).flatMap((run) => {
        const executionId = run.executionHistory.at(-1)?.executionId;
        return executionId ? [{ run, executionId }] : [];
      }),
    [runs],
  );
  const graphs = useQueries({
    queries: attempts.map(({ run, executionId }) => ({
      ...executionJournalQueryOptions(run.projectId, run.experimentId, run.id, executionId),
      enabled,
      staleTime: 30_000,
    })),
    combine: combineGraphs,
  });
  const groups = useMemo(() => rollupTasks(graphs), [graphs]);
  return { groups, partial: runs.length > TASK_OUTCOME_LIMIT };
};
