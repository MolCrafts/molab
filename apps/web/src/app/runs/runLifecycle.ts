/**
 * Run lifecycle — status to allowed verbs, and the four creation modes.
 *
 * `executionModeOptions` mirrors the server rule:
 *   initial    — only when the run has no attempt
 *   rerun      — any terminal predecessor, including skipped and succeeded
 *   resume     — a failed, cancelled, or interrupted predecessor
 *   reproduce  — a succeeded predecessor; the request always bypasses the cache
 * An active predecessor (queued, pending, running, finalizing) enables nothing.
 *
 * Harvest is not a creation mode. It is available on succeeded, failed, and cancelled.
 */

export const RETRYABLE_STATUSES = new Set(["failed", "cancelled"]);

/** Terminal outcomes that may be interpreted into Knowledge. */
export const HARVESTABLE_STATUSES = new Set(["succeeded", "failed", "cancelled"]);

export const TERMINAL_STATUSES = new Set([
  "succeeded",
  "failed",
  "cancelled",
  "interrupted",
  "skipped",
]);

export const RESUMABLE_STATUSES = new Set(["failed", "cancelled", "interrupted"]);

const ACTIVE_STATUSES = new Set(["queued", "pending", "running", "finalizing"]);

export type ExecutionModeValue = "initial" | "rerun" | "resume" | "reproduce";

export interface ExecutionModeOption {
  value: ExecutionModeValue;
  label: string;
  description: string;
  enabled: boolean;
  reason: string | null;
}

export type RunLifecyclePhase = "pending" | "running" | "retryable" | "succeeded" | "other";

export function runPhase(status: string): RunLifecyclePhase {
  const s = status.toLowerCase();
  if (s === "pending") return "pending";
  if (s === "running") return "running";
  if (RETRYABLE_STATUSES.has(s)) return "retryable";
  if (s === "succeeded") return "succeeded";
  return "other";
}

export function canStart(status: string): boolean {
  return status.toLowerCase() === "pending";
}

export function canCancel(status: string): boolean {
  return status.toLowerCase() === "running";
}

export function canResume(status: string): boolean {
  return RESUMABLE_STATUSES.has(status.toLowerCase());
}

export function canRerun(status: string): boolean {
  return TERMINAL_STATUSES.has(status.toLowerCase());
}

export function canReproduce(status: string): boolean {
  return status.toLowerCase() === "succeeded";
}

export function executionModeOptions(input: {
  attempts: number;
  basedOnStatus: string | null;
}): ExecutionModeOption[] {
  const status = input.basedOnStatus?.toLowerCase() ?? null;
  const hasAttempt = input.attempts > 0;
  const active = status !== null && ACTIVE_STATUSES.has(status);
  const initialReason = hasAttempt ? "This run already has an attempt." : null;
  const missing = "This run has no attempt yet; start with Initial.";
  const activeReason = "The predecessor execution is still active; cancel it first.";

  const reasonFor = (enabled: boolean, succeededReason: string | null): string | null => {
    if (!hasAttempt) return missing;
    if (active) return activeReason;
    if (enabled) return null;
    return succeededReason;
  };

  return [
    {
      value: "initial",
      label: "Initial",
      description: "Create an independent first realization.",
      enabled: !hasAttempt,
      reason: initialReason,
    },
    {
      value: "rerun",
      label: "Rerun",
      description: "Run the same scientific definition again.",
      enabled: hasAttempt && !active && (status === null || canRerun(status)),
      reason: reasonFor(hasAttempt && !active && (status === null || canRerun(status)), null),
    },
    {
      value: "resume",
      label: "Resume",
      description: "Continue from an optional checkpoint artifact.",
      enabled: hasAttempt && !active && status !== null && canResume(status),
      reason: reasonFor(
        hasAttempt && !active && status !== null && canResume(status),
        status === "succeeded"
          ? "A succeeded execution has nothing to resume; use Rerun or Reproduce."
          : null,
      ),
    },
    {
      value: "reproduce",
      label: "Reproduce",
      description: "Create a reproducibility verification execution.",
      enabled: hasAttempt && !active && status !== null && canReproduce(status),
      reason: reasonFor(hasAttempt && !active && status !== null && canReproduce(status), null),
    },
  ];
}

export function defaultExecutionMode(options: ExecutionModeOption[]): ExecutionModeValue {
  if (options.find((option) => option.value === "initial")?.enabled) return "initial";
  if (options.find((option) => option.value === "rerun")?.enabled) return "rerun";
  return options.find((option) => option.enabled)?.value ?? "rerun";
}

export function bypassCacheFor(mode: ExecutionModeValue, requested: boolean): boolean {
  return mode === "reproduce" || requested;
}

export function canHarvest(status: string): boolean {
  return HARVESTABLE_STATUSES.has(status.toLowerCase());
}

/** Failed-only domain for analyze_run_failure (cancelled needs force). */
export function canAnalyzeFailure(status: string): boolean {
  return status.toLowerCase() === "failed";
}

export function isTerminalStatus(status: string): boolean {
  return TERMINAL_STATUSES.has(status.toLowerCase());
}

/** After a verb that kicks off work, land on Executions (live graph). */
export const POST_DISPATCH_TAB = "executions" as const;
