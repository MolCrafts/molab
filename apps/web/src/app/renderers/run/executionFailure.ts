import type { ExecutionOutputsResponse } from "@/api/generated/models/ExecutionOutputsResponse";
import type { TaskGraphJson } from "@/components/workflow/task-graph-ir";

const FAILURE_STATUSES = new Set(["failed", "cancelled", "interrupted"]);

export const isFailureStatus = (status: string): boolean =>
  FAILURE_STATUSES.has(status.toLowerCase());

/** `type: message` when the attempt record has both, otherwise the message. */
export const executionErrorText = (error: Record<string, unknown> | null): string | null => {
  if (!error) return null;
  const type = typeof error.type === "string" && error.type.length > 0 ? error.type : null;
  const message =
    typeof error.message === "string" && error.message.length > 0 ? error.message : null;
  if (type && message) return `${type}: ${message}`;
  if (message) return message;
  if (type) return type;
  return null;
};

export interface FailedTask {
  id: string;
  error: string | null;
}

/** First task the journal marked failed, or that carries an error string. */
export const failedTask = (graph: TaskGraphJson | null): FailedTask | null => {
  if (!graph) return null;
  const task = graph.task_configs.find(
    (item) =>
      item.status?.toLowerCase() === "failed" ||
      (typeof item.error === "string" && item.error.length > 0),
  );
  if (!task) return null;
  return { id: task.id, error: task.error ?? null };
};

export type FailureSelection = { kind: "file"; path: string } | { kind: "stdio"; name: "stderr" };

/**
 * Where a failed attempt's evidence is. A file under `out/<task>/` wins.
 * Otherwise stderr, when the outputs payload has that field.
 */
export const preferredFailureOutput = (
  taskId: string | null,
  outputs: ExecutionOutputsResponse | null,
): FailureSelection | null => {
  if (!outputs) return null;
  if (taskId) {
    const prefix = `out/${taskId}`;
    const file = (outputs.unregistered ?? []).find((row) => {
      const path = row.relPath.replaceAll("\\", "/");
      return path === prefix || path.startsWith(`${prefix}/`);
    });
    if (file) return { kind: "file", path: file.relPath };
  }
  if (typeof outputs.stderr === "string") return { kind: "stdio", name: "stderr" };
  return null;
};

/** Sentence above the graph. Null when this attempt did not fail. */
export const failureHeadline = (input: {
  status: string;
  error: Record<string, unknown> | null;
  task: FailedTask | null;
}): string | null => {
  const status = input.status.toLowerCase();
  if (status === "succeeded" || status === "skipped") return null;
  if (!isFailureStatus(status) && !input.task) return null;
  const message = input.task?.error ?? executionErrorText(input.error);
  if (input.task && message) return `${input.task.id} failed. ${message}`;
  if (input.task) return `${input.task.id} failed.`;
  return message;
};

export const failureRecovery = (selection: FailureSelection | null): string => {
  if (!selection) return "Outputs lists this attempt's files and stderr.";
  if (selection.kind === "file") return `Read ${selection.path} in Outputs.`;
  return "Read stderr in Outputs.";
};
