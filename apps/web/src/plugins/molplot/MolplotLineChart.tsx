import type { LineChartConfig, SeriesPoint } from "@molcrafts/molplot";
import type { JSX } from "react";
import { useEffect, useImperativeHandle, useMemo, useRef } from "react";

export interface MolplotLineChartHandle {
  /** Push a single point onto an existing series (cheap extendTraces). */
  appendPoint(seriesId: string, point: SeriesPoint): Promise<void>;
  /** Batch-push points; preferred for streaming sources. */
  appendPoints(seriesId: string, points: SeriesPoint[]): Promise<void>;
  /** Replace an entire series in one restyle. */
  setSeries(seriesId: string, points: SeriesPoint[]): Promise<void>;
  /** Update the sliding window; null = unbounded. */
  setWindow(maxPoints: number | null): Promise<void>;
  /** Pin or auto-fit an axis range. */
  setAxisRange(axis: "x" | "y", range: [number, number] | "auto"): Promise<void>;
  /** Clear one series, or every series if no id is given. */
  clear(seriesId?: string): Promise<void>;
}

interface MolplotLineChartProps {
  config: LineChartConfig;
  /** Imperative handle for streaming / cross-pane interaction. */
  ref?: React.Ref<MolplotLineChartHandle>;
  /** Tailwind utility classes for the container. */
  className?: string;
  /** Inline style overrides for the container. */
  style?: React.CSSProperties;
}

type LineChartInstance = {
  dispose: () => void;
  ready: () => Promise<void>;
  appendPoint: (id: string, p: SeriesPoint) => Promise<void>;
  appendPoints: (id: string, p: SeriesPoint[]) => Promise<void>;
  setSeries: (id: string, p: SeriesPoint[]) => Promise<void>;
  setWindow: (n: number | null) => Promise<void>;
  setAxisRange: (axis: "x" | "y", range: [number, number] | "auto") => Promise<void>;
  clear: (id?: string) => Promise<void>;
};

export interface SeriesCursor {
  length: number;
  lastX: number;
  lastY: number;
}

export const cursorFromPoints = (points: ReadonlyArray<SeriesPoint>): SeriesCursor => {
  if (points.length === 0) return { length: 0, lastX: Number.NaN, lastY: Number.NaN };
  const last = points[points.length - 1];
  return { length: points.length, lastX: last.x, lastY: last.y };
};

export type SeriesUpdatePlan =
  | { op: "noop" }
  | { op: "append"; points: SeriesPoint[] }
  | { op: "replace" };

/**
 * Decide whether incoming points are a tail append (streaming poll) or a
 * full replace (reset / smoothing / x-axis change).
 */
export const planSeriesUpdate = (
  cursor: SeriesCursor | undefined,
  points: ReadonlyArray<SeriesPoint>,
): SeriesUpdatePlan => {
  if (!cursor) return points.length === 0 ? { op: "noop" } : { op: "replace" };
  if (points.length === cursor.length) {
    if (points.length === 0) return { op: "noop" };
    const last = points[points.length - 1];
    if (last.x === cursor.lastX && last.y === cursor.lastY) return { op: "noop" };
    return { op: "replace" };
  }
  if (points.length > cursor.length) {
    if (cursor.length === 0) return { op: "append", points: points.slice() };
    const hinge = points[cursor.length - 1];
    if (hinge && hinge.x === cursor.lastX && hinge.y === cursor.lastY) {
      return { op: "append", points: points.slice(cursor.length) };
    }
  }
  return { op: "replace" };
};

/**
 * Identity of the Vega spec (not the data). Polling new points must not
 * remount the chart — that wipes pan/zoom on the container.
 */
export const lineChartStructureKey = (config: LineChartConfig): string =>
  JSON.stringify({
    series: config.series.map((s) => ({
      id: s.id,
      label: s.label,
      color: s.color,
      width: s.width,
      opacity: s.opacity,
      mode: s.mode,
    })),
    xAxis: config.xAxis,
    yAxis: config.yAxis,
    theme: config.theme,
    preset: config.preset,
    hovermode: config.hovermode,
    showLegend: config.showLegend,
    windowSize: config.windowSize,
  });

/**
 * Thin React wrapper around molplot's imperative ``LineChart``.
 *
 * Mounts once per spec structure. New points are ``appendPoints`` only;
 * ``setSeries`` is reserved for a reset (cursor mismatch).
 */
export const MolplotLineChart = ({
  config,
  ref,
  className,
  style,
}: MolplotLineChartProps): JSX.Element => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<LineChartInstance | null>(null);
  const configRef = useRef(config);
  const cursorRef = useRef<Map<string, SeriesCursor>>(new Map());
  configRef.current = config;
  const structureKey = useMemo(() => lineChartStructureKey(config), [config]);

  useImperativeHandle(
    ref,
    () => ({
      appendPoint: async (id, point) => chartRef.current?.appendPoint(id, point),
      appendPoints: async (id, points) => chartRef.current?.appendPoints(id, points),
      setSeries: async (id, points) => chartRef.current?.setSeries(id, points),
      setWindow: async (n) => chartRef.current?.setWindow(n),
      setAxisRange: async (axis, range) => chartRef.current?.setAxisRange(axis, range),
      clear: async (id) => chartRef.current?.clear(id),
    }),
    [],
  );

  useEffect(() => {
    void structureKey;
    const container = containerRef.current;
    if (!container) return;
    let cancelled = false;
    void (async () => {
      const { LineChart } = await import("@molcrafts/molplot");
      if (cancelled) return;
      const initial = configRef.current;
      const chart = new LineChart(container, initial);
      const cursors = new Map<string, SeriesCursor>();
      for (const series of initial.series) {
        cursors.set(series.id, cursorFromPoints(series.initialPoints ?? []));
      }
      cursorRef.current = cursors;
      chartRef.current = chart;
      await chart.ready();
    })();
    return () => {
      cancelled = true;
      chartRef.current?.dispose();
      chartRef.current = null;
    };
  }, [structureKey]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    for (const series of config.series) {
      const points = series.initialPoints ?? [];
      const plan = planSeriesUpdate(cursorRef.current.get(series.id), points);
      cursorRef.current.set(series.id, cursorFromPoints(points));
      if (plan.op === "append" && plan.points.length > 0) {
        void chart.appendPoints(series.id, plan.points).catch(() => {
          void chart.setSeries(series.id, points);
        });
      } else if (plan.op === "replace") {
        void chart.setSeries(series.id, points);
      }
    }
  }, [config]);

  // Vega container owns the wheel: prevent the parent overflow scroller from
  // eating it. Do not stopPropagation — molplot's capture listener must stamp
  // axis flags on the same event.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const onWheel = (event: WheelEvent): void => {
      event.preventDefault();
    };
    el.addEventListener("wheel", onWheel, { capture: true, passive: false });
    return () => el.removeEventListener("wheel", onWheel, { capture: true });
  }, []);

  return <div ref={containerRef} className={className} style={{ touchAction: "none", ...style }} />;
};
