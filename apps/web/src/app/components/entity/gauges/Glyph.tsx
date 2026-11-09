// ─────────────────────────────────────────────────────────────────────────────
// Symbols instead of sentences. A tally is an icon and a number; the words a
// sentence would have said live in its hover title and accessible name, so the
// page reads at a glance and still says everything to a screen reader.
// Status uses the status icon set (shape + colour), never colour alone.
// ─────────────────────────────────────────────────────────────────────────────

import type { LucideIcon } from "lucide-react";
import type { JSX, ReactNode } from "react";

import { CHART_GROUPS, type ChartGroupId, type StatusCounts } from "@/app/status/vocabulary";
import { cn } from "@/lib/utils";

import { StatusIcon } from "../StatusIcon";

const labelOf = (id: ChartGroupId): string =>
  CHART_GROUPS.find((group) => group.id === id)?.label ?? id;

/** An icon and a value; `label` is the sentence, shown on hover and read aloud. */
export const Tally = ({
  icon: Icon,
  value,
  label,
  className,
}: {
  icon: LucideIcon;
  value: ReactNode;
  label: string;
  className?: string;
}): JSX.Element => (
  <span
    role="img"
    aria-label={label}
    title={label}
    className={cn("inline-flex items-center gap-1 tabular-nums", className)}
  >
    <Icon aria-hidden className="size-icon-sm shrink-0 opacity-80" />
    <span aria-hidden>{value}</span>
  </span>
);

/** One status icon and its count. */
export const StatusTally = ({
  status,
  count,
  unit,
  className,
}: {
  status: ChartGroupId;
  count: number;
  /** Plural noun for the hover title: "executions". */
  unit: string;
  className?: string;
}): JSX.Element => (
  <span
    role="img"
    aria-label={`${count} ${labelOf(status).toLowerCase()} ${unit}`}
    title={`${labelOf(status)}: ${count} ${unit}`}
    className={cn("inline-flex items-center gap-1 tabular-nums text-foreground", className)}
  >
    <StatusIcon status={status} label="" className="pointer-events-none" />
    <span aria-hidden>{count}</span>
  </span>
);

/** A row of status tallies; zero counts are dropped unless `keepZero`. */
export const StatusTallies = ({
  counts,
  statuses,
  unit,
  keepZero = false,
  className,
}: {
  counts: StatusCounts;
  statuses: readonly ChartGroupId[];
  unit: string;
  keepZero?: boolean;
  className?: string;
}): JSX.Element => (
  <span className={cn("inline-flex flex-wrap items-center gap-x-3 gap-y-1 text-label", className)}>
    {statuses
      .filter((status) => keepZero || counts[status] > 0)
      .map((status) => (
        <StatusTally key={status} status={status} count={counts[status]} unit={unit} />
      ))}
  </span>
);

/** The status key as icons; each names itself on hover. */
export const StatusGlyphLegend = ({ className }: { className?: string }): JSX.Element => (
  <ul aria-label="Status key" className={cn("flex flex-wrap items-center gap-3", className)}>
    {CHART_GROUPS.map((group) => (
      <li key={group.id} title={group.label} className="inline-flex">
        <StatusIcon status={group.id} label={group.label} />
      </li>
    ))}
  </ul>
);
