/**
 * What the Molq run view reads off one attempt (L14): its scheduler files, the
 * job's name, its submission facts and its lifetime. Pure, so the view only
 * paints. Every value comes from the execution record; nothing is invented.
 */

import type { AttemptFile, FileTypeMatcher } from "@molcrafts/molab-plugin";
import type { ExecutionResponse } from "@/api/generated/models/ExecutionResponse";
import { formatDateTime } from "@/lib/datetime";
import { parseInstant } from "@/lib/format-time";

/**
 * Scheduler evidence, flat under the attempt's `jobs/` (`execution_dirs.JOBS`):
 * the submit script, its stdout and its stderr. Only a scheduler submission
 * writes them, so the view exists exactly for the attempts that have them.
 */
export const SCHEDULER_FILES: FileTypeMatcher = {
  patterns: ["jobs/*.sh", "jobs/*.out", "jobs/*.err"],
};

const FILE_ORDER = [".sh", ".out", ".err"];

/** The scheduler files, a job's script, stdout and stderr together. */
export const sortSchedulerFiles = (files: readonly AttemptFile[]): AttemptFile[] => {
  const stem = (path: string): string => path.replace(/\.[^.]+$/, "");
  const rank = (path: string): number => FILE_ORDER.findIndex((ext) => path.endsWith(ext));
  return [...files].sort(
    (a, b) => stem(a.relPath).localeCompare(stem(b.relPath)) || rank(a.relPath) - rank(b.relPath),
  );
};

/** The record's executor metadata as text (molq stores `dict[str, str]`). */
export const executorText = (record: ExecutionResponse | undefined): Record<string, string> =>
  Object.fromEntries(
    Object.entries(record?.executor ?? {})
      .filter(([, value]) => value !== null && value !== undefined && value !== "")
      .map(([key, value]) => [key, typeof value === "string" ? value : JSON.stringify(value)]),
  );

export const isMolqExecutor = (executor: Record<string, string>): boolean =>
  executor.backend === "molq";

/** "Job 421337" — the scheduler's id first, molq's own when that is all there is. */
export const jobLabel = (executor: Record<string, string>): string => {
  const id = executor.scheduler_job_id ?? executor.job_id;
  return id ? `Job ${id}` : "Job";
};

/** "Job 421337 on hpc-slurm" — where it ran is the target, else the cluster. */
export const jobVerdict = (executor: Record<string, string>): string => {
  const where = executor.target ?? executor.cluster_name;
  return where ? `${jobLabel(executor)} on ${where}` : jobLabel(executor);
};

const FACTS: readonly (readonly [string, string])[] = [
  ["backend", "Backend"],
  ["cluster_name", "Cluster"],
  ["scheduler", "Scheduler"],
  ["scheduler_job_id", "Job id"],
  ["job_id", "Molq job id"],
  ["target", "Target"],
];

const sentenceCase = (key: string): string => {
  const words = key.replace(/_/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
};

/** Submission facts in sentence case: the known keys in a fixed order, then the rest. */
export const submissionFacts = (
  executor: Record<string, string>,
): (readonly [string, string])[] => {
  const known = new Set(FACTS.map(([key]) => key));
  const ordered = FACTS.flatMap(([key, label]) =>
    executor[key] ? [[label, executor[key]] as const] : [],
  );
  const rest = Object.keys(executor)
    .filter((key) => !known.has(key))
    .sort()
    .map((key) => [sentenceCase(key), executor[key] ?? ""] as const);
  return [...ordered, ...rest];
};

export type LifetimeKey = "submitted" | "started" | "ended";

export interface LifetimePoint {
  key: LifetimeKey;
  iso: string;
  at: number;
  /** 0 … 1 along the bar. */
  fraction: number;
}

export interface LifetimeLabel {
  fraction: number;
  text: string;
}

export interface Lifetime {
  points: LifetimePoint[];
  /** Two neighbouring points; `run` is started → ended, `wait` anything before. */
  segments: { from: number; to: number; kind: "wait" | "run" }[];
  /** Labels under the bar; points too close to read apart share one. */
  labels: LifetimeLabel[];
}

/** Labels closer than this share one, so they never print over each other. */
const LABEL_GAP = 0.2;

const clock = (iso: string, first: string): string => {
  const full = formatDateTime(iso);
  return full.slice(0, 10) === formatDateTime(first).slice(0, 10) ? full.slice(11) : full;
};

/**
 * The job's lifetime from the times the record holds: submitted (the record is
 * created before submit), started, ended. A missing time is left out.
 */
export const lifetime = (record: ExecutionResponse | undefined): Lifetime => {
  const raw: { key: LifetimeKey; iso: string | null | undefined }[] = [
    { key: "submitted", iso: record?.createdAt },
    { key: "started", iso: record?.startedAt },
    { key: "ended", iso: record?.finishedAt },
  ];
  const timed = raw.flatMap(({ key, iso }) => {
    const at = parseInstant(iso);
    return iso && at !== null ? [{ key, iso, at }] : [];
  });
  const start = timed[0]?.at ?? 0;
  const span = (timed.at(-1)?.at ?? start) - start;
  const points = timed.map((point) => ({
    ...point,
    fraction: span > 0 ? Math.min(1, Math.max(0, (point.at - start) / span)) : 0,
  }));
  const segments = points.slice(1).map((point, index) => ({
    from: points[index]?.fraction ?? 0,
    to: point.fraction,
    kind:
      points[index]?.key === "started" && point.key === "ended"
        ? ("run" as const)
        : ("wait" as const),
  }));
  const first = points[0]?.iso ?? "";
  const labels = points.reduce<LifetimeLabel[]>((acc, point) => {
    const text = `${point.key} ${clock(point.iso, first)}`;
    const last = acc.at(-1);
    if (last && point.fraction - last.fraction < LABEL_GAP) {
      return [...acc.slice(0, -1), { ...last, text: `${last.text} · ${text}` }];
    }
    return acc.concat({ fraction: point.fraction, text });
  }, []);
  return { points, segments, labels };
};

/** Seconds from started to ended; null unless the record holds both. */
export const jobSeconds = (record: ExecutionResponse | undefined): number | null => {
  const started = parseInstant(record?.startedAt);
  const ended = parseInstant(record?.finishedAt);
  return started !== null && ended !== null && ended >= started ? (ended - started) / 1000 : null;
};
