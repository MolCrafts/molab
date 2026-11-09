/**
 * The one status vocabulary (DS v1.4 §3). Every place that draws, colours,
 * words, groups or filters a status reads this table; nothing else maps
 * status strings. Nine execution states, plus the few lifecycle words of
 * non-execution entities (draft, attention) and an honest "unknown".
 */

import {
  Circle,
  CircleAlert,
  CircleCheck,
  CircleDashed,
  CircleDot,
  CircleDotDashed,
  CircleHelp,
  CircleSlash2,
  CircleX,
  LoaderCircle,
  type LucideIcon,
  PencilLine,
  TriangleAlert,
} from "lucide-react";

export const EXECUTION_STATUSES = [
  "succeeded",
  "failed",
  "interrupted",
  "running",
  "finalizing",
  "queued",
  "pending",
  "cancelled",
  "cached",
] as const;

export type ExecutionStatus = (typeof EXECUTION_STATUSES)[number];
/** Execution states + lifecycle words of other entities + unknown. */
export type StatusKey = ExecutionStatus | "draft" | "attention" | "unknown";

/** Chart / filter groups — the colours a chart or a legend may use. */
export type ChartGroupId =
  | "running"
  | "queued"
  | "succeeded"
  | "failed"
  | "interrupted"
  | "cancelled";

/** A colour token of the constitution status ramp (`--status-<tone>`). */
export type StatusTone =
  | "completed"
  | "failed"
  | "warning"
  | "running"
  | "queued"
  | "ready"
  | "cancelled"
  | "cached"
  | "draft";

export interface StatusSpec {
  key: StatusKey;
  word: string;
  glyph: LucideIcon;
  tone: StatusTone;
  group: ChartGroupId | null;
  /** The glyph turns (running). */
  spin?: boolean;
}

const spec = (
  key: StatusKey,
  word: string,
  glyph: LucideIcon,
  tone: StatusTone,
  group: ChartGroupId | null,
  spin = false,
): StatusSpec => ({ key, word, glyph, tone, group, spin });

export const STATUS: Record<StatusKey, StatusSpec> = {
  succeeded: spec("succeeded", "Succeeded", CircleCheck, "completed", "succeeded"),
  failed: spec("failed", "Failed", CircleX, "failed", "failed"),
  interrupted: spec("interrupted", "Interrupted", CircleAlert, "warning", "interrupted"),
  running: spec("running", "Running", LoaderCircle, "running", "running", true),
  finalizing: spec("finalizing", "Finalizing", CircleDot, "running", "running"),
  queued: spec("queued", "Queued", Circle, "queued", "queued"),
  pending: spec("pending", "Not started", CircleDashed, "ready", "queued"),
  cancelled: spec("cancelled", "Cancelled", CircleSlash2, "cancelled", "cancelled"),
  cached: spec("cached", "Reused", CircleDotDashed, "cached", null),
  draft: spec("draft", "Draft", PencilLine, "draft", null),
  attention: spec("attention", "Needs review", TriangleAlert, "warning", null),
  unknown: spec("unknown", "Unknown", CircleHelp, "draft", null),
};

/** Static class strings (Tailwind only sees literal names). */
export const TONE_TEXT: Record<StatusTone, string> = {
  completed: "text-status-completed",
  failed: "text-status-failed",
  warning: "text-status-warning",
  running: "text-status-running",
  queued: "text-status-queued",
  ready: "text-status-ready",
  cancelled: "text-status-cancelled",
  cached: "text-status-cached",
  draft: "text-status-draft",
};

export const TONE_FILL: Record<StatusTone, string> = {
  completed: "bg-status-completed",
  failed: "bg-status-failed",
  warning: "bg-status-warning",
  running: "bg-status-running",
  queued: "bg-status-queued",
  ready: "bg-status-ready",
  cancelled: "bg-status-cancelled",
  cached: "bg-status-cached",
  draft: "bg-status-draft",
};

/** A word or numeral in its status colour, at reading contrast. Quiet states stay muted. */
export const TONE_INK: Record<StatusTone, string> = {
  completed: "text-status-completed-foreground",
  failed: "text-status-failed-foreground",
  warning: "text-status-warning-foreground",
  running: "text-status-running-foreground",
  queued: "text-muted-foreground",
  ready: "text-muted-foreground",
  cancelled: "text-muted-foreground",
  cached: "text-muted-foreground",
  draft: "text-muted-foreground",
};

export const toneColor = (tone: StatusTone): string => `var(--status-${tone})`;

const ALIASES: Record<string, StatusKey> = {
  succeeded: "succeeded",
  success: "succeeded",
  completed: "succeeded",
  done: "succeeded",
  ok: "succeeded",
  passed: "succeeded",
  granted: "succeeded",
  approved: "succeeded",
  failed: "failed",
  error: "failed",
  invalid: "failed",
  lost: "failed",
  rejected: "failed",
  timed_out: "failed",
  interrupted: "interrupted",
  running: "running",
  in_progress: "running",
  retrying: "running",
  finalizing: "finalizing",
  queued: "queued",
  submitted: "queued",
  scheduled: "queued",
  created: "queued",
  pending: "pending",
  not_started: "pending",
  cancelled: "cancelled",
  canceled: "cancelled",
  user_cancelled: "cancelled",
  aborted: "cancelled",
  killed: "cancelled",
  stopped: "cancelled",
  skipped: "cancelled",
  superseded: "cancelled",
  archived: "cancelled",
  expired: "cancelled",
  cached: "cached",
  reused: "cached",
  draft: "draft",
  warning: "attention",
  awaiting_review: "attention",
  waiting_for_review: "attention",
  blocked: "attention",
  conflicting: "attention",
  paused: "attention",
  stale: "attention",
};

/** Any wire spelling → the vocabulary. An unknown word stays "unknown". */
export const normalizeStatus = (raw: string | null | undefined): StatusKey =>
  raw ? (ALIASES[raw.trim().toLowerCase()] ?? "unknown") : "unknown";

export const statusSpec = (raw: string | null | undefined): StatusSpec =>
  STATUS[normalizeStatus(raw)];

export const statusWord = (raw: string | null | undefined): string => statusSpec(raw).word;

export const chartGroupOf = (raw: string | null | undefined): ChartGroupId | null =>
  statusSpec(raw).group;

export interface ChartGroupSpec {
  id: ChartGroupId;
  label: string;
  tone: StatusTone;
  /** CSS colour (`var(--status-<tone>)`). */
  color: string;
  /** Waiting work is drawn as an outline, not a fill. */
  outline: boolean;
}

const group = (
  id: ChartGroupId,
  label: string,
  tone: StatusTone,
  outline = false,
): ChartGroupSpec => ({ id, label, tone, color: toneColor(tone), outline });

/** One order for every chart, legend and filter list. */
export const CHART_GROUPS: readonly ChartGroupSpec[] = [
  group("running", "Running", "running"),
  group("queued", "Queued", "queued", true),
  group("succeeded", "Succeeded", "completed"),
  group("failed", "Failed", "failed"),
  group("interrupted", "Interrupted", "warning"),
  group("cancelled", "Cancelled", "cancelled"),
];

export const chartGroup = (id: ChartGroupId): ChartGroupSpec =>
  CHART_GROUPS.find((item) => item.id === id) as ChartGroupSpec;

/** Outcomes a finished attempt can have — the basis of every success share. */
export const FINISHED_GROUPS: readonly ChartGroupId[] = [
  "succeeded",
  "failed",
  "interrupted",
  "cancelled",
];

/**
 * Work that needs a person: it stopped without the result. Cancelled is a
 * person's own decision and does not ask for one. The status bar counts these,
 * the Attention list shows them, and `/runs?status=failed,interrupted` opens them.
 */
export const ATTENTION_GROUPS: readonly ChartGroupId[] = ["failed", "interrupted"];

export const needsAttention = (raw: string | null | undefined): boolean => {
  const id = chartGroupOf(raw);
  return id !== null && ATTENTION_GROUPS.includes(id);
};

/** Work the server will still stop: queued, running, finalizing. */
export const isActiveStatus = (raw: string | null | undefined): boolean => {
  const key = normalizeStatus(raw);
  return key === "queued" || key === "running" || key === "finalizing";
};

/** A run reads as its latest attempt; no attempt yet is "not started". */
export const latestStatus = (attempts: readonly { status: string }[]): StatusKey =>
  attempts.length === 0 ? "pending" : normalizeStatus(attempts[attempts.length - 1]?.status);

/** Counts per chart group, plus the total (which includes uncounted states). */
export type StatusCounts = { total: number } & Record<ChartGroupId, number>;

export const emptyCounts = (): StatusCounts => ({
  total: 0,
  running: 0,
  queued: 0,
  succeeded: 0,
  failed: 0,
  interrupted: 0,
  cancelled: 0,
});

/** Roll statuses up into the chart groups; every status counts in the total. */
export const countStatuses = (statuses: Iterable<string | null | undefined>): StatusCounts => {
  const counts = emptyCounts();
  for (const status of statuses) {
    counts.total += 1;
    const id = chartGroupOf(status);
    if (id) counts[id] += 1;
  }
  return counts;
};
