// ─────────────────────────────────────────────────────────────────────────────
// What a run's page says about one attempt, derived once and without React:
// the verdict line (level 2), its one line of evidence (level 3), the tasks on
// a clock, and the run result. Comparison with siblings lives in `runCompare`.
// ─────────────────────────────────────────────────────────────────────────────

import { formatSpan } from "@/app/components/entity";
import { executionErrorText } from "@/app/renderers/run/executionFailure";
import { normalizeStatus, STATUS, type StatusKey } from "@/app/status/vocabulary";
import type { ExecutionRecordSummary, RunSummary } from "@/app/types";
import { parseInstant } from "@/lib/format-time";
import type { TaskGraphJson, TaskNodeJson } from "@/plugins/workflow/task-graph-ir";

/** A journal status (`completed`, `skipped`, none yet) in the vocabulary. */
const taskStatus = (task: TaskNodeJson): StatusKey => normalizeStatus(task.status ?? "pending");

const taskName = (task: TaskNodeJson): string => task.label || task.id;

const stringOf = (value: unknown): string | null =>
  typeof value === "string" && value.length > 0 ? value : null;

/** Where an attempt ran: its target, else its backend. */
export const attemptTarget = (execution: ExecutionRecordSummary | undefined): string | null =>
  stringOf(execution?.executor?.target) ?? stringOf(execution?.executor?.backend);

const pad2 = (value: number): string => value.toString().padStart(2, "0");

/** A wall-clock time as `14:51`, or null. */
export const clockOf = (iso: string | null | undefined): string | null => {
  const at = parseInstant(iso);
  if (at === null) return null;
  const date = new Date(at);
  return `${pad2(date.getHours())}:${pad2(date.getMinutes())}`;
};

/** Wall time of one attempt in seconds; in-flight work counts up to `now`. */
export const attemptSeconds = (
  execution: ExecutionRecordSummary,
  now = Date.now(),
): number | null => {
  const start = parseInstant(execution.startedAt ?? execution.createdAt);
  if (start === null) return null;
  return Math.max(0, (parseInstant(execution.finishedAt) ?? now) - start) / 1000;
};

// ── Results ──────────────────────────────────────────────────────────────────

export interface ResultFigure {
  key: string;
  value: string;
}

/** A result number as a person reads it: 1.50e-4, 300.48, 51. */
export const formatFigure = (value: number): string => {
  if (Number.isInteger(value)) return value.toLocaleString("en-US");
  const abs = Math.abs(value);
  if (abs !== 0 && (abs < 1e-2 || abs >= 1e6)) return value.toExponential(2);
  return Number(value.toPrecision(5)).toString();
};

/** Scalar results the attempt reported, numbers first; structured values stay on their tab. */
export const resultFigures = (results: Record<string, unknown> | undefined): ResultFigure[] =>
  Object.entries(results ?? {})
    .filter(([, value]) => ["number", "string", "boolean"].includes(typeof value))
    .sort(
      ([, left], [, right]) => Number(typeof right === "number") - Number(typeof left === "number"),
    )
    .map(([key, value]) => ({
      key,
      value: typeof value === "number" ? formatFigure(value) : String(value),
    }));

export interface RunResultExecution {
  execution: ExecutionRecordSummary;
  /** 1-based place in the run's history. */
  index: number;
}

/**
 * The attempt that holds the run's result: the latest sealed success.
 * A later running, failed, or cancelled attempt does not replace it.
 */
export const runResultExecution = (
  history: readonly ExecutionRecordSummary[],
): RunResultExecution | null => {
  for (let index = history.length - 1; index >= 0; index -= 1) {
    const execution = history[index];
    if (!execution) continue;
    if (normalizeStatus(execution.status) === "succeeded") {
      return { execution, index: index + 1 };
    }
  }
  return null;
};

// ── Verdict ──────────────────────────────────────────────────────────────────

export interface RunVerdict {
  status: StatusKey | "none";
  /** The status word: "Failed". */
  word: string;
  /** What it is about, phrased to follow the word: "at Molecular dynamics", "in 35m", "on hpc-slurm". */
  subject: string | null;
  /**
   * The same, standing alone beside the status glyph (icon OR text, retrofit R3):
   * "Molecular dynamics", "35m", "hpc-slurm". Null when there is nothing to say.
   */
  label: string | null;
  /** The attempt's wall time for the right edge; null when the subject already says it. */
  elapsed: string | null;
  /** The sentence, for hover and assistive tech. */
  headline: string;
  /** Level 3: one line under the verdict. */
  evidence: string | null;
  /** The full error, shown when the evidence expands. */
  error: string | null;
  /** The task the verdict is about, when there is one. */
  taskId: string | null;
}

const NOT_RUN: RunVerdict = {
  status: "none",
  word: "Not run yet",
  subject: null,
  label: "Not run yet",
  elapsed: null,
  headline: "Not run yet",
  evidence: null,
  error: null,
  taskId: null,
};

const firstLine = (text: string | null): string | null =>
  text
    ? (text
        .split("\n")
        .find((line) => line.trim().length > 0)
        ?.trim() ?? null)
    : null;

const errorMessage = (error: Record<string, unknown> | null): string | null =>
  stringOf(error?.message) ?? stringOf(error?.type);

export const MODE_WORD: Record<string, string> = {
  initial: "Initial",
  resume: "Resume",
  rerun: "Rerun",
  reproduce: "Reproduce",
};

const plural = (count: number, word: string): string => `${count} ${word}${count === 1 ? "" : "s"}`;

/**
 * The verdict for the latest attempt of `run` (a caller scoping to an older
 * attempt passes the history up to it). `figures` are that attempt's results,
 * the evidence a success shows.
 */
export const runVerdict = (
  run: Pick<RunSummary, "executionHistory" | "errorMessage">,
  graph: TaskGraphJson | null,
  now = Date.now(),
  figures: readonly ResultFigure[] = [],
): RunVerdict => {
  const history = run.executionHistory;
  const attempt = history[history.length - 1];
  if (!attempt) return NOT_RUN;
  const status = normalizeStatus(attempt.status);
  const word = STATUS[status].word;
  const seconds = attemptSeconds(attempt, now);
  const took = seconds === null ? null : formatSpan(seconds);
  const tasks = graph?.task_configs ?? [];
  const done = tasks.filter((task) => taskStatus(task) === "succeeded").length;
  const reused = tasks.filter((task) => taskStatus(task) === "cached").length;
  const finished = `${done + reused} of ${tasks.length} tasks finished`;
  const stopped = tasks.find((task) => ["failed", "interrupted"].includes(taskStatus(task)));
  const running = tasks.find((task) => ["running", "finalizing"].includes(taskStatus(task)));
  const target = attemptTarget(attempt);
  const message = errorMessage(attempt.error) ?? stopped?.error ?? run.errorMessage ?? null;
  const fullError = executionErrorText(attempt.error) ?? stopped?.error ?? run.errorMessage ?? null;
  const parts = (...items: (string | null | false | undefined)[]): string | null => {
    const kept = items.filter((item): item is string => Boolean(item));
    return kept.length > 0 ? kept.join(" · ") : null;
  };
  const attemptNote =
    history.length > 1
      ? `Attempt ${history.length} of ${history.length} (${attempt.mode})`
      : attempt.mode !== "initial"
        ? MODE_WORD[attempt.mode]
        : null;

  let subject: string | null = null;
  let elapsed: string | null = took;
  let evidence: string | null = null;
  let error: string | null = null;
  let taskId: string | null = null;
  switch (status) {
    case "succeeded":
      subject = took ? `in ${took}` : null;
      elapsed = null;
      evidence = parts(...figures.slice(0, 3).map((figure) => `${figure.key} ${figure.value}`));
      break;
    case "failed":
    case "interrupted":
    case "cancelled":
      subject = stopped ? `at ${taskName(stopped)}` : null;
      taskId = stopped?.id ?? null;
      evidence =
        status === "cancelled"
          ? parts(
              clockOf(attempt.finishedAt) ? `Cancelled at ${clockOf(attempt.finishedAt)}` : null,
              tasks.length > 0 && finished,
            )
          : status === "interrupted"
            ? parts(firstLine(message), tasks.length > 0 && finished)
            : firstLine(message);
      error = status === "cancelled" ? null : fullError;
      break;
    case "running":
      subject = running ? taskName(running) : null;
      taskId = running?.id ?? null;
      evidence = parts(attemptNote, target && `on ${target}`, tasks.length > 0 && finished);
      elapsed = took ? `${took} so far` : null;
      break;
    case "finalizing":
      subject = "sealing results";
      evidence = tasks.length > 0 ? `All ${plural(tasks.length, "task")} finished` : null;
      break;
    case "queued": {
      subject = target ? `on ${target}` : null;
      const waiting = tasks.length - reused;
      evidence = parts(
        attempt.mode !== "initial" && attempt.basedOnExecutionId
          ? `${MODE_WORD[attempt.mode] ?? attempt.mode} of ${attempt.basedOnExecutionId}`
          : attemptNote,
        reused > 0 && `${reused} reused`,
        tasks.length > 0 && `${plural(waiting, "task")} to run`,
      );
      elapsed = took;
      break;
    }
    default:
      break;
  }
  const headline = [word, subject, elapsed && status !== "succeeded" ? `(${elapsed})` : null]
    .filter(Boolean)
    .join(" ");
  // The subject without its joining word, to stand beside the glyph.
  const label = subject ? subject.replace(/^(at|in|on) /, "") : null;
  return { status, word, subject, label, elapsed, headline, evidence, error, taskId };
};

// ── Tasks on a clock ─────────────────────────────────────────────────────────

export interface ClockRow {
  key: string;
  label: string;
  status: StatusKey;
  /** Epoch ms; null when the task never started. */
  start: number | null;
  /** Null while it runs (drawn to now) or when it never started. */
  end: number | null;
  /** Text in place of a bar: "not run", "waiting", "reused from e01". */
  note: string | null;
  tip: string;
}

/** Why a task that never started did not: said in words where its bar would be. */
const unstartedNote = (
  task: TaskNodeJson,
  attempt: ExecutionRecordSummary | null,
): string | null => {
  const status = taskStatus(task);
  if (status === "cached") {
    return attempt?.basedOnExecutionId ? `reused from ${attempt.basedOnExecutionId}` : "reused";
  }
  const attemptStatus = attempt ? normalizeStatus(attempt.status) : "pending";
  if (attemptStatus === "queued" || attemptStatus === "pending") return "waiting";
  if (attemptStatus === "running" || attemptStatus === "finalizing") return "not started";
  return "not run";
};

/** Every task of the attempt in journal order: a bar for the ones that ran, a word for the rest. */
export const taskClock = (
  graph: TaskGraphJson | null,
  attempt: ExecutionRecordSummary | null,
  now = Date.now(),
): ClockRow[] =>
  (graph?.task_configs ?? []).map((task) => {
    const status = taskStatus(task);
    const start = parseInstant(task.startedAt);
    const live = status === "running" || status === "finalizing";
    const end = start === null || live ? null : parseInstant(task.finishedAt);
    const seconds = start === null ? null : Math.max(0, (end ?? now) - start) / 1000;
    const note = start === null ? unstartedNote(task, attempt) : null;
    return {
      key: task.id,
      label: taskName(task),
      // A task that never started reads as waiting in a queued attempt and "not
      // started" otherwise, whatever the journal called it (skipped).
      status:
        start === null && status !== "cached"
          ? attempt && normalizeStatus(attempt.status) === "queued"
            ? "queued"
            : "pending"
          : status,
      start,
      end,
      note,
      tip: [
        `${taskName(task)} · ${STATUS[status].word}${seconds === null ? "" : ` · ${formatSpan(seconds)}`}`,
        task.type,
        task.error ?? "",
      ]
        .filter(Boolean)
        .join("\n"),
    };
  });

/** The clock's span as `14:51 → 15:49`, or `→ now` while it runs. */
export const clockWindow = (rows: readonly ClockRow[]): string | null => {
  const starts = rows.flatMap((row) => (row.start === null ? [] : [row.start]));
  if (starts.length === 0) return null;
  const from = clockOf(new Date(Math.min(...starts)).toISOString());
  const live = rows.some((row) => row.start !== null && row.end === null);
  const ends = rows.flatMap((row) => (row.end === null ? [] : [row.end]));
  const to = live || ends.length === 0 ? "now" : clockOf(new Date(Math.max(...ends)).toISOString());
  return `${from} → ${to}`;
};

/**
 * The log line an error points at: the last line that carries the error's
 * first line, else the last `Traceback` header. 1-based, or null.
 */
export const errorLine = (text: string | null | undefined, error: string | null): number | null => {
  if (!text) return null;
  const lines = text.split("\n");
  const needle = firstLine(error);
  const tail = needle?.split(": ").pop() ?? null;
  for (let index = lines.length - 1; index >= 0; index -= 1) {
    const line = lines[index] ?? "";
    if (needle && (line.includes(needle) || (tail && tail.length > 8 && line.includes(tail)))) {
      return index + 1;
    }
  }
  for (let index = lines.length - 1; index >= 0; index -= 1) {
    if ((lines[index] ?? "").startsWith("Traceback")) return index + 1;
  }
  return null;
};
