import {
  type ChartData,
  type ChartTheme,
  type VegaLiteSpec,
  VegaLiteView,
} from "@molcrafts/ui-vega-lite";
import { type JSX, useEffect, useMemo, useRef, useState } from "react";
import { STATUS_GROUPS, type StatusGroupId } from "@/app/runs/statusGroups";
import { cn } from "@/lib/utils";

import type { StatusCountRollup } from "./Dashboard";
import { type BarDatum, barSpec, statusBarSpec } from "./instruments";

const STATUS_VARS: Record<StatusGroupId, string> = {
  running: "--status-running",
  pending: "--status-queued",
  succeeded: "--status-completed",
  failed: "--status-failed",
  cancelled: "--status-cancelled",
};

/** Resolved status ramp. Vega cannot paint `var(--status-*)` itself. */
export const useStatusColors = (): Record<StatusGroupId, string> | null => {
  const [colors, setColors] = useState<Record<StatusGroupId, string> | null>(null);
  useEffect(() => {
    const read = (): void => {
      const probe = document.createElement("span");
      probe.style.display = "none";
      document.documentElement.append(probe);
      const next = {} as Record<StatusGroupId, string>;
      for (const [id, name] of Object.entries(STATUS_VARS)) {
        probe.style.color = `var(${name})`;
        next[id as StatusGroupId] = getComputedStyle(probe).color;
      }
      probe.remove();
      setColors((previous) =>
        JSON.stringify(previous) === JSON.stringify(next) ? previous : next,
      );
    };
    const observer = new MutationObserver(read);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class", "style", "data-mol-theme"],
    });
    const media = matchMedia("(prefers-color-scheme: dark)");
    media.addEventListener("change", read);
    read();
    return () => {
      observer.disconnect();
      media.removeEventListener("change", read);
    };
  }, []);
  return colors;
};

const chartClass = "outline-none focus-visible:ring-1 focus-visible:ring-ring";

/** Product color. `--primary` is not set on this page, so the chart theme falls through to a system color. */
const readCssColor = (name: string, fallback: string): string => {
  if (typeof document === "undefined") return fallback;
  const probe = document.createElement("span");
  probe.style.display = "none";
  document.documentElement.append(probe);
  probe.style.color = `var(${name}, ${fallback})`;
  const resolved = getComputedStyle(probe).color;
  probe.remove();
  return resolved || fallback;
};

const asRows = (rows: readonly object[]): Record<string, unknown>[] =>
  rows.map((row) => ({ ...row }));

export const InstrumentChart = ({
  spec,
  data,
  label,
  width,
  height,
  loading = false,
  className,
}: {
  spec: (theme: ChartTheme) => VegaLiteSpec;
  data?: ChartData;
  label: string;
  width?: number;
  height: number;
  loading?: boolean;
  className?: string;
}): JSX.Element => (
  <VegaLiteView
    spec={spec}
    data={data}
    label={label}
    labelHidden
    width={width}
    height={height}
    loading={loading}
    renderer="svg"
    className={cn(chartClass, className)}
  />
);

/** One horizontal bar per occupied status. Height tracks the row count. */
export const StatusBarChart = ({
  counts,
  groups,
  label,
  height,
}: {
  counts: StatusCountRollup;
  groups?: readonly StatusGroupId[];
  label: string;
  /** Pixel height. Omit to size the chart from the number of status rows. */
  height?: number;
}): JSX.Element => {
  const colors = useStatusColors();
  const specs = groups ? STATUS_GROUPS.filter((group) => groups.includes(group.id)) : STATUS_GROUPS;
  const occupied = specs.filter((group) => counts[group.id] > 0);
  const colorKey = colors == null ? "" : occupied.map((group) => colors[group.id]).join("|");
  const signature = `${occupied.map((group) => `${group.id}:${counts[group.id]}`).join(",")}|${colorKey}`;
  const latest = useRef({ occupied, colors, counts });
  latest.current = { occupied, colors, counts };
  const spec = useMemo(
    () => (theme: ChartTheme) =>
      statusBarSpec({
        ...theme,
        foreground: readCssColor("--molab-foreground", theme.foreground),
        border: readCssColor("--molab-border", theme.border),
        mutedForeground: readCssColor("--molab-muted-foreground", theme.mutedForeground),
      }),
    [],
  );
  const data = useMemo((): ChartData => {
    const current = latest.current;
    const stamp = signature;
    return {
      statuses: asRows(
        current.occupied.map((group, index) => ({
          order: String(index).padStart(4, "0"),
          label: group.label,
          value: current.counts[group.id],
          color: current.colors?.[group.id] ?? "transparent",
          tooltip: `${group.label}: ${current.counts[group.id]}`,
          stamp,
        })),
      ),
    };
  }, [signature]);
  return (
    <InstrumentChart
      spec={spec}
      data={data}
      label={label}
      height={height ?? Math.max(88, occupied.length * 28 + 36)}
      loading={colors == null}
    />
  );
};

/** Visible tick text. Repeated and blank labels stay distinct without showing the suffix. */
const axisLabel = (label: string, seen: Map<string, number>): string => {
  const count = seen.get(label) ?? 0;
  seen.set(label, count + 1);
  return count === 0 ? label : `${label}${"\u200b".repeat(count)}`;
};

export const BarInstrument = ({
  label,
  bars,
  className,
  height = 128,
}: {
  label: string;
  bars: readonly BarDatum[];
  className?: string;
  height?: number;
}): JSX.Element => {
  const signature = bars
    .map((bar) => `${bar.id}:${bar.label}:${bar.value}:${bar.tooltip}`)
    .join("|");
  const single = bars.length === 1;
  const latest = useRef(bars);
  latest.current = bars;
  const spec = useMemo(
    () => (theme: ChartTheme) =>
      barSpec(
        {
          ...theme,
          primary: readCssColor("--molab-accent", theme.primary),
          border: readCssColor("--molab-border", theme.border),
          mutedForeground: readCssColor("--molab-muted-foreground", theme.mutedForeground),
        },
        single,
      ),
    [single],
  );
  const data = useMemo((): ChartData => {
    const stamp = signature;
    const seen = new Map<string, number>();
    return {
      bars: asRows(
        latest.current.map((bar, index) => ({
          order: String(index).padStart(4, "0"),
          axis: axisLabel(bar.label, seen),
          value: bar.value,
          tooltip: bar.tooltip,
          stamp,
        })),
      ),
    };
  }, [signature]);
  return (
    <InstrumentChart spec={spec} data={data} label={label} height={height} className={className} />
  );
};
