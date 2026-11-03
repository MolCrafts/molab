// ─────────────────────────────────────────────────────────────────────────────
// What a run's Overview says, derived once and without React: the verdict
// sentence, the latest attempt's tasks on a clock, where the run sits among its
// experiment's other runs, the parameters that set it apart, and its results.
// A run is one point of a sweep; its page is about what happened inside it and
// how it compares — not a rollup of one item.
// ─────────────────────────────────────────────────────────────────────────────

import { formatSpan, type SiblingPoint, type TimelineSpan } from "@/app/components/entity";
import { formatScalar } from "@/app/renderers/dashboardData";
import { executionErrorText } from "@/app/renderers/run/executionFailure";
import { runFinishedAt, runPresentationStatus, runStartedAt } from "@/app/runs/projections";
import { groupForStatus, STATUS_GROUPS, type StatusGroupId } from "@/app/runs/statusGroups";
import type { WorkspaceRunRow } from "@/app/runs/types";
import type { ExecutionRecordSummary, RunSummary } from "@/app/types";
import type { TaskGraphJson, TaskNodeJson } from "@/plugins/workflow/task-graph-ir";

const time = (value: string | null | undefined): number | null => {
  const parsed = value ? Date.parse(value) : Number.NaN;
  return Number.isFinite(parsed) ? parsed : null;
};

const wordOf = (status: StatusGroupId): string =>
  STATUS_GROUPS.find((group) => group.id === status)?.label ?? status;

/** Journal statuses (`completed`, `skipped`) mapped onto the UI's groups. */
const taskStatus = (task: TaskNodeJson): StatusGroupId =>
  groupForStatus(task.status ?? "pending") ?? "pending";

const taskName = (task: TaskNodeJson): string => task.label || task.id;

// ── Verdict ──────────────────────────────────────────────────────────────────

export interface RunVerdict {
  status: StatusGroupId | "none";
  /** The sentence, for hover and assistive tech: "Failed at Train model after 48m". */
  headline: string;
  /** What the verdict is about: the failing or running task. */
  subject: string | null;
  /** The attempt's wall time: "48m". */
  elapsed: string | null;
  tasks: { done: number; total: number };
  /** Present only when the run has been retried. */
  attempt: { index: number; total: number; mode: string } | null;
  /** The failing attempt's own error, first. */
  error: string | null;
}

const attemptElapsed = (execution: ExecutionRecordSummary, now: number): number | null => {
  const start = time(execution.startedAt ?? execution.createdAt);
  if (start === null) return null;
  return Math.max(0, (time(execution.finishedAt) ?? now) - start) / 1000;
};

export const runVerdict = (
  run: RunSummary,
  graph: TaskGraphJson | null,
  now = Date.now(),
): RunVerdict => {
  const history = run.executionHistory;
  const latest = history[history.length - 1];
  if (!latest) {
    return {
      status: "none",
      headline: "Not run yet",
      subject: null,
      elapsed: null,
      tasks: { done: 0, total: 0 },
      attempt: null,
      error: null,
    };
  }
  const status = groupForStatus(latest.status) ?? "pending";
  const seconds = attemptElapsed(latest, now);
  const elapsed = seconds === null ? null : formatSpan(seconds);
  const tasks = graph?.task_configs ?? [];
  const failedTask = tasks.find((task) => taskStatus(task) === "failed");
  const runningTask = tasks.find((task) => taskStatus(task) === "running");
  const subject =
    status === "failed" && failedTask
      ? taskName(failedTask)
      : status === "running" && runningTask
        ? taskName(runningTask)
        : null;
  const took = elapsed ?? "";
  const headline =
    status === "succeeded"
      ? `Completed${took ? ` in ${took}` : ""}`
      : status === "failed"
        ? `Failed${subject ? ` at ${subject}` : ""}${took ? ` after ${took}` : ""}`
        : status === "running"
          ? `Running${subject ? ` ${subject}` : ""}${took ? ` · ${took} so far` : ""}`
          : status === "cancelled"
            ? `Cancelled${took ? ` after ${took}` : ""}`
            : `Queued${took ? ` for ${took}` : ""}`;
  return {
    status,
    headline,
    subject,
    elapsed,
    tasks: {
      done: tasks.filter((task) => taskStatus(task) === "succeeded").length,
      total: tasks.length,
    },
    attempt:
      history.length > 1
        ? { index: history.length, total: history.length, mode: latest.mode }
        : null,
    error:
      status === "failed" || status === "cancelled"
        ? (executionErrorText(latest.error) ?? failedTask?.error ?? run.errorMessage ?? null)
        : null,
  };
};

// ── Tasks on a clock ─────────────────────────────────────────────────────────

/** The latest attempt's tasks that started, in journal order, each from start to finish. */
export const taskSpans = (graph: TaskGraphJson | null, now = Date.now()): TimelineSpan[] =>
  (graph?.task_configs ?? []).flatMap((task) => {
    const start = time(task.startedAt);
    if (start === null) return [];
    const status = taskStatus(task);
    const end = time(task.finishedAt);
    const seconds = Math.max(0, (end ?? now) - start) / 1000;
    return [
      {
        key: task.id,
        label: taskName(task),
        start,
        end: status === "running" ? null : end,
        status,
        tip: [
          `${taskName(task)} · ${wordOf(status)} · ${formatSpan(seconds)}`,
          task.type,
          task.error ?? "",
        ]
          .filter(Boolean)
          .join("\n"),
      },
    ];
  });

/** Tasks the journal lists that never started: shown as a count, not drawn. */
export const unstartedTasks = (graph: TaskGraphJson | null): number =>
  (graph?.task_configs ?? []).filter((task) => !task.startedAt).length;

// ── Among its siblings ───────────────────────────────────────────────────────

const runSeconds = (row: WorkspaceRunRow): number | null => {
  const status = groupForStatus(runPresentationStatus(row));
  if (status !== "succeeded" && status !== "failed" && status !== "cancelled") return null;
  const start = time(runStartedAt(row));
  const end = time(runFinishedAt(row));
  return start === null || end === null || end < start ? null : (end - start) / 1000;
};

export interface SiblingStanding {
  points: SiblingPoint[];
  /** "faster than 2 of 3 other runs", or null when it cannot be said. */
  rank: string | null;
  /** Place by duration, 1 = fastest, among all runs on the chart: "2/4" ("=" for a tie). */
  place: string | null;
}

const plural = (count: number): string => (count === 1 ? "run" : "runs");

/**
 * The run among its experiment's finished runs, by duration. A run still
 * going is placed at its elapsed time so far, so the chart can already say
 * "slower than every finished sibling" while it runs.
 */
export const siblingStanding = (
  runId: string,
  siblings: readonly WorkspaceRunRow[],
  now = Date.now(),
): SiblingStanding => {
  const points: SiblingPoint[] = siblings.flatMap((row) => {
    const self = row.id === runId;
    const finished = runSeconds(row);
    const start = time(runStartedAt(row));
    const seconds = finished ?? (self && start !== null ? Math.max(0, now - start) / 1000 : null);
    if (seconds === null) return [];
    const status = groupForStatus(runPresentationStatus(row));
    const soFar = finished === null;
    return [
      {
        key: row.id,
        seconds,
        status,
        self,
        tip: `${self ? "This run" : row.name || row.id} · ${formatSpan(seconds)}${
          soFar ? " so far" : ""
        }${status ? ` · ${wordOf(status)}` : ""}`,
      },
    ];
  });
  const self = points.find((point) => point.self);
  const others = points.filter((point) => !point.self);
  if (!self || others.length === 0) return { points, rank: null, place: null };
  const ongoing = runSeconds(siblings.find((row) => row.id === runId) as WorkspaceRunRow) === null;
  const slower = others.filter((point) => point.seconds > self.seconds).length;
  const faster = others.filter((point) => point.seconds < self.seconds).length;
  const n = others.length;
  const rank =
    slower === 0 && faster === 0
      ? `as long as the ${n} other ${plural(n)}`
      : ongoing
        ? faster > 0
          ? `already longer than ${faster} of ${n} other ${plural(n)}`
          : `shorter so far than ${n === 1 ? "the other run" : `all ${n} other runs`}`
        : slower >= faster
          ? `faster than ${slower} of ${n} other ${plural(n)}`
          : `slower than ${faster} of ${n} other ${plural(n)}`;
  const place = slower === 0 && faster === 0 ? "=" : `${faster + 1}/${points.length}`;
  return { points, rank, place };
};

/**
 * Parameters on which this run differs from at least one sibling — its
 * coordinates in the sweep. Shared values are the experiment's, not the run's.
 */
export const distinguishingParameters = (
  parameters: Record<string, unknown>,
  siblings: readonly WorkspaceRunRow[],
): Array<{ key: string; value: string }> =>
  Object.entries(parameters).flatMap(([key, value]) => {
    const mine = formatScalar(value);
    const varies = siblings.some(
      (row) => row.parameters && formatScalar(row.parameters[key]) !== mine,
    );
    return varies ? [{ key, value: mine }] : [];
  });

// ── Results ──────────────────────────────────────────────────────────────────

export interface ResultFigure {
  key: string;
  value: string;
}

/** Scalar results the attempt reported, numbers first; structured values stay on their tab. */
export const resultFigures = (results: Record<string, unknown> | undefined): ResultFigure[] =>
  Object.entries(results ?? {})
    .filter(([, value]) => ["number", "string", "boolean"].includes(typeof value))
    .sort(
      ([, left], [, right]) => Number(typeof right === "number") - Number(typeof left === "number"),
    )
    .map(([key, value]) => ({
      key,
      value:
        typeof value === "number"
          ? Number.isInteger(value)
            ? value.toLocaleString("en-US")
            : Number(value.toPrecision(4)).toString()
          : String(value),
    }));
