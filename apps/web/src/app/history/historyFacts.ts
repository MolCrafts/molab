/**
 * Recorded facts as people read them (L11 Settings › History): grouped by
 * day, newest first, an attempt named by its experiment and run title (not
 * the run's directory slug the commit message carries), and a status taken
 * from the event (`execution.failed` → failed).
 */

import type { HistoryFact } from "@/api/history";
import { runLabel } from "@/app/runs/runTitle";
import type { WorkspaceRunRow } from "@/app/runs/types";

export interface FactView {
  key: string;
  title: string;
  event: string;
  /** A run status when the event is one, else null. */
  status: string | null;
  occurredAt: string;
}

export interface FactDay {
  label: string;
  facts: FactView[];
}

const STATUSES = new Set([
  "queued",
  "running",
  "finalizing",
  "succeeded",
  "failed",
  "cancelled",
  "interrupted",
]);

export const factStatus = (event: string): string | null => {
  const last = event.split(".").at(-1) ?? "";
  return STATUSES.has(last) ? last : null;
};

/** Title of a fact: the attempt's experiment and run title when the run is known. */
export const factTitle = (fact: HistoryFact, runs: readonly WorkspaceRunRow[]): string => {
  if (fact.subjectType === "execution") {
    const run = runs.find((row) =>
      row.executions.some((item) => item.executionId === fact.subjectId),
    );
    if (run) return `${run.experimentName || run.experimentId} · ${runLabel(run)}`;
  }
  return fact.summary || fact.event;
};

const dayKey = (iso: string): string => {
  const date = new Date(iso);
  return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
};

const dayLabel = (iso: string, now: Date): string => {
  const date = new Date(iso);
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const that = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const days = Math.round((today.getTime() - that.getTime()) / 86_400_000);
  if (days === 0) return "Today";
  if (days === 1) return "Yesterday";
  return date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
};

export const groupFactsByDay = (
  facts: readonly HistoryFact[],
  runs: readonly WorkspaceRunRow[],
  now: Date = new Date(),
): FactDay[] => {
  const sorted = [...facts].sort((left, right) => right.occurredAt.localeCompare(left.occurredAt));
  const days: FactDay[] = [];
  let currentKey = "";
  for (const fact of sorted) {
    const key = dayKey(fact.occurredAt);
    if (key !== currentKey) {
      days.push({ label: dayLabel(fact.occurredAt, now), facts: [] });
      currentKey = key;
    }
    days.at(-1)?.facts.push({
      key: `${fact.commit}-${fact.subjectId}-${fact.event}`,
      title: factTitle(fact, runs),
      event: fact.event,
      status: factStatus(fact.event),
      occurredAt: fact.occurredAt,
    });
  }
  return days;
};
