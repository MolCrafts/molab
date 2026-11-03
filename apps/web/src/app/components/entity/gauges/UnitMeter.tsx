// ─────────────────────────────────────────────────────────────────────────────
// Unit meter — one mark per item, so "3 running, 1 queued" is seen as four
// marks before it is read as a number, and each mark names the item it is.
// A mark may carry a level (elapsed time against a typical duration); a dashed
// reference rule then shows where "typical" sits, so the overdue mark stands
// above it. Drawn by Vega: hover names the item, click opens it. Marks past the
// capacity fold into a "+N".
// ─────────────────────────────────────────────────────────────────────────────

import { type JSX, type ReactNode, useMemo } from "react";

import type { StatusGroupId } from "@/app/runs/statusGroups";
import { cn } from "@/lib/utils";

import { useStatusColors } from "../InstrumentChart";
import { UNIT_HEIGHT, UNIT_STEP, unitSpec } from "./vega/instrumentSpecs";
import { OverviewChart } from "./vega/OverviewChart";

export interface UnitMark {
  key: string;
  status: StatusGroupId;
  /** What this one item is: its name and its age. */
  title: string;
  /** Filled share of the slot, 0..1. Omit for a full mark. */
  level?: number;
  /** Waiting work is drawn as an outline. */
  outline?: boolean;
}

interface UnitMeterProps {
  marks: readonly UnitMark[];
  /** Whole-meter description for assistive tech. */
  label: string;
  /** Height share (0..1) of the "typical" rule across levelled marks. */
  reference?: number;
  /** Under the meter: what the marks are ordered by, or what the rule means — a symbol, ideally. */
  note?: ReactNode;
  onPick?: (key: string) => void;
  /** Marks drawn before the rest fold into "+N". */
  capacity?: number;
  /** What an empty meter says, beside a dashed track. */
  emptyLabel: string;
  className?: string;
}

const clamp01 = (value: number): number => Math.min(1, Math.max(0, value));

export const UnitMeter = ({
  marks,
  label,
  reference,
  note,
  onPick,
  capacity = 18,
  emptyLabel,
  className,
}: UnitMeterProps): JSX.Element => {
  const colors = useStatusColors();
  const shown = useMemo(() => marks.slice(0, capacity), [marks, capacity]);
  const folded = marks.length - shown.length;
  const ref = reference === undefined ? null : clamp01(reference);
  const data = useMemo(
    () => ({
      units: shown.map((mark, order) => ({
        key: mark.key,
        order,
        level: mark.level === undefined ? 1 : Math.max(0.08, clamp01(mark.level)),
        levelled: mark.level !== undefined,
        outline: Boolean(mark.outline),
        color: colors?.[mark.status] ?? "transparent",
        tip: mark.title,
      })),
    }),
    [shown, colors],
  );

  if (marks.length === 0) {
    return (
      <div className={cn("flex min-w-0 items-center gap-2", className)}>
        <span
          aria-hidden
          className="h-8 min-w-8 flex-1 rounded-hairline border border-dashed border-border"
        />
        <span className="shrink-0 text-micro text-muted-foreground">{emptyLabel}</span>
      </div>
    );
  }

  return (
    <div className={cn("min-w-0", className)}>
      <div className="flex min-w-0 items-end gap-2">
        <OverviewChart
          label={label}
          spec={(palette) => unitSpec(palette, ref)}
          specKey={`units:${ref}`}
          data={data}
          width={shown.length * UNIT_STEP}
          height={UNIT_HEIGHT}
          onPick={onPick}
        />
        {folded > 0 ? (
          <span className="pb-1 font-mono text-micro tabular-nums text-muted-foreground">
            +{folded}
          </span>
        ) : null}
      </div>
      {note ? <div className="mt-1 text-micro text-muted-foreground">{note}</div> : null}
    </div>
  );
};
