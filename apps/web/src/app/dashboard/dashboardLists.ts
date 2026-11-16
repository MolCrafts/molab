// ─────────────────────────────────────────────────────────────────────────────
// The Dashboard side bar's three lists (L01 decision 2), without React: runs
// whose latest attempt needs a person, runs going now, and runs whose latest
// attempt finished in the last day. A run sits in exactly one list.
// ─────────────────────────────────────────────────────────────────────────────

import { runActivityAt, runFinishedAt, runPresentationStatus } from "@/app/runs/projections";
import type { WorkspaceRunRow } from "@/app/runs/types";
import { chartGroupOf, isActiveStatus, needsAttention } from "@/app/status/vocabulary";
import { parseInstant } from "@/lib/format-time";

export const FINISHED_WINDOW_MS = 24 * 60 * 60 * 1000;

export interface DashboardLists {
  attention: WorkspaceRunRow[];
  active: WorkspaceRunRow[];
  finished: WorkspaceRunRow[];
}

const newest =
  (at: (run: WorkspaceRunRow) => string | null) =>
  (left: WorkspaceRunRow, right: WorkspaceRunRow): number =>
    (parseInstant(at(right)) ?? 0) - (parseInstant(at(left)) ?? 0);

export const dashboardLists = (
  rows: readonly WorkspaceRunRow[],
  now = Date.now(),
): DashboardLists => {
  const attention: WorkspaceRunRow[] = [];
  const active: WorkspaceRunRow[] = [];
  const finished: WorkspaceRunRow[] = [];
  for (const run of rows) {
    const status = runPresentationStatus(run);
    if (needsAttention(status)) attention.push(run);
    else if (isActiveStatus(status)) active.push(run);
    else {
      const at = parseInstant(runFinishedAt(run));
      if (at !== null && now - at <= FINISHED_WINDOW_MS) finished.push(run);
    }
  }
  // Running before queued; each newest first.
  const running = (run: WorkspaceRunRow): number =>
    chartGroupOf(runPresentationStatus(run)) === "running" ? 0 : 1;
  return {
    attention: attention.sort(newest(runActivityAt)),
    active: active.sort(
      (left, right) => running(left) - running(right) || newest(runActivityAt)(left, right),
    ),
    finished: finished.sort(newest(runFinishedAt)),
  };
};
