/**
 * Activity rows derived from run records already in the snapshot.
 * There is no workspace event store.
 */

import { CheckCircle2, CircleDot, PlusCircle, XCircle } from "lucide-react";

export interface ActivityRun {
  id: string;
  status: string;
  createdAt?: string | null;
  startedAt?: string | null;
  finishedAt?: string | null;
  updatedAt?: string | null;
}

export interface WorkspaceEventRow {
  id: string;
  type: string;
  created_at: string;
  refs: string[];
}

export interface EventVisual {
  icon: typeof CircleDot;
  label: string;
  dotClass: string;
}

// Keep the legacy filter order explicit and aligned with the server contract;
// Object key order is not a product-facing ordering mechanism.
export const WORKSPACE_EVENT_TYPES = [
  "run.created",
  "run.started",
  "run.failed",
  "run.completed",
] as const;

const VISUALS: Record<string, EventVisual> = {
  "run.created": { icon: PlusCircle, label: "Run created", dotClass: "bg-muted-foreground/40" },
  "run.started": { icon: CircleDot, label: "Run started", dotClass: "bg-info" },
  "run.failed": { icon: XCircle, label: "Run failed", dotClass: "bg-destructive" },
  "run.completed": { icon: CheckCircle2, label: "Run completed", dotClass: "bg-success" },
};

export const eventTypeFilterLabel = (type: string): string => VISUALS[type]?.label ?? type;

const FALLBACK_VISUAL: EventVisual = {
  icon: CircleDot,
  label: "",
  dotClass: "bg-muted-foreground/40",
};

export const eventVisualFor = (type: string): EventVisual =>
  VISUALS[type] ?? { ...FALLBACK_VISUAL, label: type };

export const FEED_EMPTY_TEXT = "No run activity yet.";

export const eventsFromRuns = (
  runs: readonly ActivityRun[],
  eventType?: string | null,
  max = 20,
): WorkspaceEventRow[] => {
  const rows: WorkspaceEventRow[] = [];
  for (const run of runs) {
    const created = run.createdAt ?? run.updatedAt;
    if (created) {
      rows.push({
        id: `${run.id}:run.created`,
        type: "run.created",
        created_at: created,
        refs: [run.id],
      });
    }
    if (run.startedAt) {
      rows.push({
        id: `${run.id}:run.started`,
        type: "run.started",
        created_at: run.startedAt,
        refs: [run.id],
      });
    }
    if (run.finishedAt && run.status === "succeeded") {
      rows.push({
        id: `${run.id}:run.completed`,
        type: "run.completed",
        created_at: run.finishedAt,
        refs: [run.id],
      });
    }
    if (run.finishedAt && run.status === "failed") {
      rows.push({
        id: `${run.id}:run.failed`,
        type: "run.failed",
        created_at: run.finishedAt,
        refs: [run.id],
      });
    }
  }
  const filtered = eventType ? rows.filter((row) => row.type === eventType) : rows;
  filtered.sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
  return filtered.slice(0, max);
};
