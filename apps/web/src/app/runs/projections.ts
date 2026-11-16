import { latestStatus, type StatusKey } from "@/app/status/vocabulary";
import type { RunSummary } from "@/app/types";
import { parseInstant } from "@/lib/format-time";
import type { WorkspaceExecutionRow, WorkspaceRunRow } from "./types";

const newestFirst = (left: WorkspaceExecutionRow, right: WorkspaceExecutionRow): number =>
  (parseInstant(right.createdAt) ?? 0) - (parseInstant(left.createdAt) ?? 0) ||
  right.executionId.localeCompare(left.executionId);

/**
 * A deliberately UI-only interpretation of a Run's Execution history.
 * It is never persisted and must not be sent back as Run domain state.
 */
export const runPresentationStatus = (run: WorkspaceRunRow): StatusKey =>
  latestStatus(run.executions.slice().sort(newestFirst).reverse());

export const runStartedAt = (run: WorkspaceRunRow): string | null => {
  const values = run.executions
    .map((execution) => execution.startedAt)
    .filter((value): value is string => parseInstant(value) !== null)
    .sort((left, right) => (parseInstant(left) ?? 0) - (parseInstant(right) ?? 0));
  return values[0] ?? null;
};

export const runFinishedAt = (run: WorkspaceRunRow): string | null => {
  const values = run.executions
    .map((execution) => execution.finishedAt)
    .filter((value): value is string => parseInstant(value) !== null)
    .sort((left, right) => (parseInstant(right) ?? 0) - (parseInstant(left) ?? 0));
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
      .filter((value): value is string => parseInstant(value) !== null)
      .sort((left, right) => (parseInstant(right) ?? 0) - (parseInstant(left) ?? 0))[0] ??
    run.createdAt
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

/**
 * A runs-table row as a run summary: the attempts without their errors. Enough
 * for a Preview and for the selection verbs (`planSelection`).
 */
export const runSummaryFromRow = (row: WorkspaceRunRow): RunSummary =>
  ({
    id: row.id,
    name: row.name,
    title: row.title,
    path: row.path,
    status: row.executions.at(-1)?.status ?? "pending",
    summary: "",
    updatedAt: row.createdAt,
    projectId: row.projectId,
    experimentId: row.experimentId,
    definitionHash: row.definitionHash,
    experimentRevisionId: row.experimentRevisionId,
    inputs: row.inputs,
    statusSummary: row.statusSummary,
    parameters: row.parameters,
    workflowSource: null,
    workflowSnapshot: null,
    startedAt: null,
    finishedAt: null,
    executionHistory: row.executions.map((execution) => ({
      executionId: execution.executionId,
      mode: execution.mode,
      createdAt: execution.createdAt,
      startedAt: execution.startedAt,
      finishedAt: execution.finishedAt,
      status: execution.status,
      basedOnExecutionId: execution.basedOnExecutionId,
      executor: {
        ...execution.backendMetadata,
        ...(execution.backend ? { backend: execution.backend } : {}),
      },
      environment: {},
      error: null,
    })),
    errorMessage: null,
    workspaceKey: row.workspaceKey,
  }) as unknown as RunSummary;
