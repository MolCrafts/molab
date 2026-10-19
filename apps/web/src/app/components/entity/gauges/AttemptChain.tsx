// ─────────────────────────────────────────────────────────────────────────────
// Attempt chain — a run's executions in order, e01 → e02 → …. A handful of
// attempts is a sequence, not a distribution: each node names its mode, its
// outcome and its wall-clock, and a length rule under it compares the attempts
// ("did the resume get further, and was it slower?") without a chart.
// ─────────────────────────────────────────────────────────────────────────────

import type { JSX } from "react";

import { groupForStatus } from "@/app/runs/statusGroups";
import { formatRelative } from "@/lib/format-time";
import { cn } from "@/lib/utils";

import { StatusIcon } from "../StatusIcon";
import { STATUS_FILL, STATUS_INK } from "./Gauge";
import { formatSpan } from "./scale";

export interface Attempt {
  executionId: string;
  mode: string;
  status: string;
  createdAt: string;
  startedAt: string | null;
  finishedAt: string | null;
}

const MODE_WORD: Record<string, string> = {
  initial: "initial",
  rerun: "rerun",
  retry: "rerun",
  resume: "resume",
  reproduce: "reproduce",
};

const instant = (value: string | null): number | null => {
  const parsed = value ? Date.parse(value) : Number.NaN;
  return Number.isFinite(parsed) ? parsed : null;
};

const wallSeconds = (attempt: Attempt, now: number): number | null => {
  const start = instant(attempt.startedAt);
  if (start === null) return null;
  const end = instant(attempt.finishedAt) ?? now;
  return end >= start ? (end - start) / 1000 : null;
};

export const AttemptChain = ({
  attempts,
  className,
}: {
  attempts: readonly Attempt[];
  className?: string;
}): JSX.Element => {
  const now = Date.now();
  const spans = attempts.map((attempt) => wallSeconds(attempt, now));
  const longest = Math.max(1, ...spans.map((span) => span ?? 0));

  return (
    <ol className={cn("flex min-w-0 flex-wrap items-start gap-y-6", className)}>
      {attempts.map((attempt, index) => {
        const group = groupForStatus(attempt.status);
        const span = spans[index] ?? null;
        const live = attempt.finishedAt === null && attempt.startedAt !== null;
        return (
          <li key={attempt.executionId} className="flex min-w-0 items-start">
            {index > 0 ? (
              <span aria-hidden className="mx-3 mt-2 h-px w-8 shrink-0 bg-border sm:w-12" />
            ) : null}
            <div className="min-w-0 space-y-1">
              <p className="flex items-center gap-2">
                <StatusIcon status={attempt.status} />
                <span className="font-mono text-body font-medium text-foreground">
                  {attempt.executionId}
                </span>
                <span
                  className={cn("text-label", group ? STATUS_INK[group] : "text-muted-foreground")}
                >
                  {attempt.status.replace(/_/g, " ")}
                </span>
              </p>
              <p className="pl-6 text-label text-muted-foreground">
                {MODE_WORD[attempt.mode] ?? attempt.mode}
                {span !== null ? (
                  <>
                    {" · "}
                    <span className="font-mono tabular-nums text-foreground">
                      {formatSpan(span)}
                    </span>
                    {live ? " so far" : ""}
                  </>
                ) : (
                  " · not started"
                )}
                {` · ${attempt.startedAt ? "started" : "created"} `}
                {formatRelative(attempt.startedAt ?? attempt.createdAt)}
              </p>
              <span aria-hidden className="ml-6 block h-1 w-32 rounded-hairline bg-muted">
                {span !== null ? (
                  <span
                    className={cn(
                      "block h-full rounded-hairline",
                      group ? STATUS_FILL[group] : "bg-muted-foreground",
                      live && "mol-motion-progress-pulse",
                    )}
                    style={{ width: `${Math.max(4, (span / longest) * 100)}%` }}
                  />
                ) : null}
              </span>
            </div>
          </li>
        );
      })}
    </ol>
  );
};
