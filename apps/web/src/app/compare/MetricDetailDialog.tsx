/**
 * One metric, drawn across the selected runs.
 *
 * The matrix answers "what differs"; this answers "by how much, and how did it
 * get there" for the one row the user pointed at. Which chart depends on what
 * the runs actually recorded, not on a preference:
 *
 * - every run logged a single value → **bars**, one per run. A line through
 *   one point per series says nothing the number did not already say.
 * - some run logged a series → **lines**, overlaid, with the aggregation and
 *   grouping controls that only make sense once there is a curve.
 *
 * The frame is the one the single-run metrics view already uses: a Display
 * sidebar that folds away to a rail, and the chart taking every pixel that is
 * left. Two ways to look at a curve, laid out two different ways, is a tax on
 * whoever moves between them — and here the chart is the whole point of the
 * dialog, so prose around it is prose in the way. What the reader still has to
 * be told (a step counter that restarts, steps dropped in alignment, an
 * aggregation that could not run) is a warning icon in the title bar, not a
 * paragraph under the plot.
 */

import { AlertTriangle, RotateCcw, X } from "lucide-react";
import { type JSX, useMemo, useRef, useState } from "react";

import { EmptyState } from "@/app/components/entity";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { WorkbenchIconAction } from "@/components/workbench";
import type { AggregateOp, MolplotLineChartHandle } from "@/plugins/molplot";
import {
  ChartLegend,
  ChartWorkbench,
  MolplotBarChart,
  MolplotLineChart,
  pickKeySeries,
  type RunAllSeries,
  selectAggregateConfig,
  stepResets,
} from "@/plugins/molplot";
import {
  aggregateFeasibility,
  type XMode,
  type YNormalize,
  type YScale,
} from "@/plugins/molplot/aggregateSeries";
import { PALETTE } from "@/plugins/molplot/RunMetricsView";

import {
  type ColorBy,
  colorByFromValue,
  colorByToValue,
  groupableParameters,
  groupLabels,
} from "./grouping";
import { shortestUniqueLabels } from "./labels";
import type { CompareEntry } from "./types";

export interface MetricDetailDialogProps {
  metricKey: string | null;
  entries: CompareEntry[];
  perRunAll: RunAllSeries[];
  onClose: () => void;
}

interface ViewSettings {
  op: AggregateOp;
  colorBy: ColorBy;
  xMode: XMode;
  yScale: YScale;
  normalize: YNormalize;
  smoothing: number;
}

const DEFAULT_VIEW: ViewSettings = {
  op: "overlay",
  colorBy: { kind: "run" },
  xMode: "step",
  yScale: "linear",
  normalize: "none",
  smoothing: 0,
};

const Field = ({ label, children }: { label: string; children: JSX.Element }): JSX.Element => (
  <div className="flex flex-col gap-2">
    <span className="font-medium text-foreground text-label">{label}</span>
    {children}
  </div>
);

export const MetricDetailDialog = ({
  metricKey,
  entries,
  perRunAll,
  onClose,
}: MetricDetailDialogProps): JSX.Element | null => {
  const [view, setView] = useState<ViewSettings>(DEFAULT_VIEW);
  const chartRef = useRef<MolplotLineChartHandle | null>(null);
  const { op, colorBy, xMode, yScale, normalize, smoothing } = view;
  const patch = (next: Partial<ViewSettings>): void =>
    setView((current) => ({ ...current, ...next }));

  const names = useMemo(() => shortestUniqueLabels(entries), [entries]);
  const groups = useMemo(() => groupLabels(entries, colorBy), [entries, colorBy]);
  const parameters = useMemo(() => groupableParameters(entries), [entries]);

  const grouped = useMemo(
    () => perRunAll.map((row) => ({ ...row, label: groups.get(row.key) ?? row.label })),
    [perRunAll, groups],
  );

  const picked = useMemo(
    () => (metricKey ? pickKeySeries(grouped, metricKey) : []),
    [grouped, metricKey],
  );

  // The data decides the chart: one point everywhere means there is no curve.
  const isScalarOnly = picked.length > 0 && picked.every((r) => r.series.points.length === 1);

  // A step axis that goes backwards is a solver restarting its counter, not a
  // broken file — say so, because a curve that doubles back looks like damage.
  const resetRuns = useMemo(() => picked.filter((r) => stepResets(r.series) > 0).length, [picked]);

  const feasibility = useMemo(
    () => (picked.length > 0 ? aggregateFeasibility(picked.map((r) => r.series)) : null),
    [picked],
  );

  const line = useMemo(() => {
    if (isScalarOnly || picked.length === 0 || !metricKey) return null;
    return selectAggregateConfig(op, picked, {
      xMode,
      yScale,
      smoothing,
      normalize,
      metricKey,
    });
  }, [isScalarOnly, picked, op, xMode, yScale, smoothing, normalize, metricKey]);

  // Bars are grouped the same way lines are: one colour per group, one bar per
  // run, so switching "colour by" reads the same in both charts.
  const bars = useMemo(() => {
    if (!isScalarOnly || !metricKey) return null;
    const order: string[] = [];
    for (const row of picked) {
      if (!order.includes(row.label)) order.push(row.label);
    }
    return {
      series: order.map((label) => ({
        id: label,
        label,
        color: PALETTE[order.indexOf(label) % PALETTE.length],
        points: picked
          .filter((row) => row.label === label)
          .map((row) => ({
            x: names.get(row.key) ?? row.key,
            y: row.series.points[0].y,
          })),
      })),
      orientation: "h" as const,
      xAxis: { label: metricKey },
      // The legend is drawn in HTML beneath the plot, where a run's full
      // ancestry is one hover away instead of clipped into the canvas.
      showLegend: false,
      theme: "auto" as const,
    };
  }, [isScalarOnly, picked, metricKey, names]);

  const lineConfig = useMemo(() => (line ? { ...line.config, showLegend: false } : null), [line]);

  const warnings = useMemo(() => {
    const out: string[] = [];
    if (!isScalarOnly && resetRuns > 0 && xMode === "step") {
      out.push(
        `${resetRuns} run${resetRuns === 1 ? "" : "s"} restart the step counter (a minimisation block, or reset_timestep), so the curve doubles back — switch the X axis to wall time.`,
      );
    }
    if (line && line.dropped > 0) out.push(`${line.dropped} unaligned steps dropped.`);
    if (line?.blockedReason) out.push(`Showing overlay — ${line.blockedReason}`);
    return out;
  }, [isScalarOnly, line, resetRuns, xMode]);

  if (!metricKey) return null;

  const perStepBlocked = feasibility?.ok === false;

  /** Back to the view the dialog opened with — settings and pan/zoom alike. */
  const reset = (): void => {
    setView(DEFAULT_VIEW);
    void chartRef.current?.resetZoom();
  };

  const controls = (
    <>
      <Field label="Colour by">
        <Select
          value={colorByToValue(colorBy)}
          onValueChange={(value) => patch({ colorBy: colorByFromValue(value) })}
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="run">Run</SelectItem>
            <SelectItem value="experiment">Experiment</SelectItem>
            <SelectItem value="project">Project</SelectItem>
            <SelectItem value="workspace">Workspace</SelectItem>
            {parameters.map((name) => (
              <SelectItem key={name} value={`param:${name}`}>
                Parameter · {name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>

      {/* Aggregation, axes and smoothing only mean anything for a curve. */}
      {!isScalarOnly && (
        <>
          <Field label="Combine">
            <Select value={op} onValueChange={(value) => patch({ op: value as AggregateOp })}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="overlay">Overlay</SelectItem>
                <SelectItem value="mean" disabled={perStepBlocked}>
                  Mean
                </SelectItem>
                <SelectItem value="errorbar" disabled={perStepBlocked}>
                  Errorbar (±std)
                </SelectItem>
              </SelectContent>
            </Select>
          </Field>
          <Field label="X axis">
            <Select value={xMode} onValueChange={(value) => patch({ xMode: value as XMode })}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="step">Step</SelectItem>
                <SelectItem value="wall">Wall time</SelectItem>
                <SelectItem value="progress">Progress (0-1)</SelectItem>
              </SelectContent>
            </Select>
          </Field>
          <Field label="Y axis">
            <Select value={yScale} onValueChange={(value) => patch({ yScale: value as YScale })}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="linear">Linear</SelectItem>
                <SelectItem value="log">Log</SelectItem>
              </SelectContent>
            </Select>
          </Field>
          <Field label="Rescale">
            <Select
              value={normalize}
              onValueChange={(value) => patch({ normalize: value as YNormalize })}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">None</SelectItem>
                <SelectItem value="first">Relative to first</SelectItem>
                <SelectItem value="minmax">Normalised 0-1</SelectItem>
              </SelectContent>
            </Select>
          </Field>
          <Field label="Smoothing">
            <div className="flex items-center gap-2">
              <Slider
                min={0}
                max={0.99}
                step={0.01}
                value={[smoothing]}
                onValueChange={([value]) => patch({ smoothing: value })}
                className="flex-1"
                aria-label="EMA smoothing weight"
              />
              <span className="w-control text-right font-mono tabular-nums text-muted-foreground">
                {smoothing.toFixed(2)}
              </span>
            </div>
          </Field>
        </>
      )}
    </>
  );

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      {/* Same fraction of each viewport dimension, so the dialog keeps the
          screen's aspect ratio instead of forcing a fixed 4xl box — a wide
          monitor gets a wide chart. `max-w-none` overrides the base
          `sm:max-w-lg`. */}
      <DialogContent
        showCloseButton={false}
        className="flex h-[85vh] w-[85vw] max-w-none flex-col gap-0 overflow-hidden p-0 sm:max-w-none"
      >
        <header className="flex h-[35px] shrink-0 items-center gap-1 border-b border-border px-2">
          <DialogTitle className="min-w-0 flex-1 truncate font-mono text-body-lg font-medium">
            {metricKey}
          </DialogTitle>
          {/* A status, not an action — so it is a marked-up icon with its text
              in `title` and for screen readers, rather than a button that
              does nothing when pressed. */}
          {warnings.length > 0 && (
            <span
              title={warnings.join(" ")}
              className="flex size-control-compact items-center justify-center text-status-warning-foreground"
            >
              <AlertTriangle className="h-3.5 w-3.5" aria-hidden />
              <span className="sr-only">{warnings.join(" ")}</span>
            </span>
          )}
          <WorkbenchIconAction label="Reset the view" onClick={reset}>
            <RotateCcw className="h-3.5 w-3.5" />
          </WorkbenchIconAction>
          <WorkbenchIconAction label="Close" onClick={onClose}>
            <X className="h-3.5 w-3.5" />
          </WorkbenchIconAction>
        </header>

        <ChartWorkbench settings={controls} defaultOpen>
          {picked.length === 0 ? (
            <div className="flex h-full items-center justify-center">
              <EmptyState
                density="compact"
                title="Not recorded"
                description="No loaded run wrote this metric."
              />
            </div>
          ) : (
            <div className="flex min-h-0 flex-1">
              <div className="min-h-0 min-w-0 flex-1">
                {bars ? (
                  <MolplotBarChart config={bars} style={{ width: "100%", height: "100%" }} />
                ) : lineConfig ? (
                  <MolplotLineChart
                    ref={chartRef}
                    config={lineConfig}
                    style={{ width: "100%", height: "100%" }}
                  />
                ) : null}
              </div>
              <ChartLegend series={bars?.series ?? lineConfig?.series ?? []} />
            </div>
          )}
        </ChartWorkbench>
      </DialogContent>
    </Dialog>
  );
};
