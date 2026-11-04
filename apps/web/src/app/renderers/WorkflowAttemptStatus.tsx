import { useQueries } from "@tanstack/react-query";
import { type JSX, useMemo } from "react";
import { STATUS_GROUPS } from "@/app/runs/statusGroups";
import { executionJournalQueryOptions } from "@/app/state/entityQueries";
import type { RunSummary } from "@/app/types";
import { normalizeTaskGraph } from "@/plugins/workflow/flowgram-document";
import { rollupTaskStatus } from "./workflowStatus";

const labelFor = (group: (typeof STATUS_GROUPS)[number]["id"]): string =>
  STATUS_GROUPS.find((item) => item.id === group)?.label ?? group;

/**
 * Per-task status across the latest attempt of every run in one experiment.
 * The workflow graph beside this is the definition; these counts are what ran.
 */
export const WorkflowAttemptStatus = ({
  runs,
}: {
  runs: readonly RunSummary[];
}): JSX.Element | null => {
  const attempts = useMemo(
    () =>
      runs.flatMap((run) => {
        const executionId = run.executionHistory.at(-1)?.executionId;
        return executionId ? [{ run, executionId }] : [];
      }),
    [runs],
  );
  const journals = useQueries({
    queries: attempts.map(({ run, executionId }) => ({
      ...executionJournalQueryOptions(run.projectId, run.experimentId, run.id, executionId),
    })),
  });
  const rows = useMemo(
    () =>
      rollupTaskStatus(
        journals.map((query) => (query.data ? normalizeTaskGraph(query.data) : null)),
      ),
    [journals],
  );
  if (attempts.length === 0 || rows.length === 0) return null;
  return (
    <section
      aria-label="Workflow status"
      className="shrink-0 space-y-2 border-b border-border px-4 py-3"
    >
      <h3 className="text-body-lg font-medium text-foreground">Workflow status</h3>
      <p className="text-label text-muted-foreground">
        Latest attempt of {attempts.length} {attempts.length === 1 ? "run" : "runs"}. The graph
        below is the definition.
      </p>
      <ul className="space-y-1">
        {rows.map((row) => {
          const parts = STATUS_GROUPS.flatMap((group) => {
            const count = row.counts[group.id];
            return count > 0 ? [`${count} ${labelFor(group.id).toLowerCase()}`] : [];
          });
          return (
            <li key={row.id} className="flex min-w-0 flex-wrap items-baseline gap-x-3 gap-y-1">
              <span className="font-mono text-label text-foreground">{row.id}</span>
              <span className="text-label text-muted-foreground">{parts.join(" · ")}</span>
            </li>
          );
        })}
      </ul>
    </section>
  );
};
