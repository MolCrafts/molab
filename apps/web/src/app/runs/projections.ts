import type { WorkspaceExecutionRow, WorkspaceRunRow } from "./types";

const timestamp = (value: string | null | undefined): number | null => {
  if (!value) return null;
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? null : parsed;
};

const newestFirst = (left: WorkspaceExecutionRow, right: WorkspaceExecutionRow): number =>
  (timestamp(right.createdAt) ?? 0) - (timestamp(left.createdAt) ?? 0) ||
  right.executionId.localeCompare(left.executionId);

/**
 * A deliberately UI-only interpretation of a Run's Execution history.
 * It is never persisted and must not be sent back as Run domain state.
 */
export const runPresentationStatus = (run: WorkspaceRunRow): string => {
  const counts = run.statusSummary.byStatus;
  if ((counts.running ?? 0) > 0) return "running";
  if ((counts.finalizing ?? 0) > 0) return "running";
  if ((counts.queued ?? 0) > 0) return "pending";
  const latest = run.executions.slice().sort(newestFirst)[0]?.status;
  if (latest === "interrupted") return "failed";
  return latest ?? "pending";
};

export const runStartedAt = (run: WorkspaceRunRow): string | null => {
  const values = run.executions
    .map((execution) => execution.startedAt)
    .filter((value): value is string => timestamp(value) !== null)
    .sort((left, right) => (timestamp(left) ?? 0) - (timestamp(right) ?? 0));
  return values[0] ?? null;
};

export const runFinishedAt = (run: WorkspaceRunRow): string | null => {
  const values = run.executions
    .map((execution) => execution.finishedAt)
    .filter((value): value is string => timestamp(value) !== null)
    .sort((left, right) => (timestamp(right) ?? 0) - (timestamp(left) ?? 0));
  return values[0] ?? null;
};

export const runActivityAt = (run: WorkspaceRunRow): string => {
  const values = run.executions.flatMap((execution) => [
    execution.finishedAt,
    execution.startedAt,
    execution.createdAt,
  ]);
  return (
    values
      .filter((value): value is string => timestamp(value) !== null)
      .sort((left, right) => (timestamp(right) ?? 0) - (timestamp(left) ?? 0))[0] ?? run.createdAt
  );
};

export const runExecutorFacet = (
  run: WorkspaceRunRow,
  key: "backend" | "cluster_name" | "scheduler" | "profile" | "target",
): string[] => {
  const values = run.executions.flatMap((execution) => {
    const value = key === "backend" ? execution.backend : execution.backendMetadata[key];
    return value ? [value] : [];
  });
  return [...new Set(values)].sort((left, right) => left.localeCompare(right));
};

export const runExecutorFacetLabel = (
  run: WorkspaceRunRow,
  key: "backend" | "cluster_name" | "scheduler" | "profile" | "target",
): string | null => {
  const values = runExecutorFacet(run, key);
  if (values.length === 0) return null;
  if (values.length === 1) return values[0] ?? null;
  return `${values[0]} +${values.length - 1}`;
};
