import type { LineChartConfig, SeriesPoint } from "@molcrafts/molplot";
import type { JSX, ReactNode } from "react";
import { useCallback, useEffect, useImperativeHandle, useMemo, useRef } from "react";

import { bandBox, boxToRanges, type PlotPoint } from "./boxZoom";

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
  /** Drop a box zoom and let both axes fit the data again. */
  resetZoom(): Promise<void>;
}

interface MolplotLineChartProps {
  config: LineChartConfig;
  /** Imperative handle for streaming / cross-pane interaction. */
  ref?: React.Ref<MolplotLineChartHandle>;
  /** Tailwind utility classes for the container. */
  className?: string;
  /** Inline style overrides for the container. */
  style?: React.CSSProperties;
  /**
   * Chrome drawn over the plot — a legend, a badge.
   *
   * It goes *inside* the frame rather than beside it so the drag gesture still
   * belongs to the chart: the box-zoom listener sits on the frame, so a drag
   * that starts on a floating legend zooms the region under it instead of
   * being swallowed by a sibling that happens to be in the way.
   */
  overlay?: ReactNode;
}

/**
 * The live Vega view behind the chart, as much of it as the box zoom needs.
 *
 * molplot keeps this internal — deliberately, since nothing about a *chart*
 * should require knowing Vega. Reading the scales is the one thing a
 * host-drawn gesture cannot do without: only the view knows the domain after
 * a wheel zoom has moved it. Every field is feature-detected at use, so a
 * molplot that stops exposing it disables the gesture instead of throwing.
 */
interface PlotView {
  origin(): number[];
  signal(name: string): unknown;
  scale(name: string): { invert?: (pixel: number) => number } | undefined;
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

/**
 * The chart's live view, or null before its first render lands.
 *
 * `result` is protected on molplot's class, so the read is a cast — and it is
 * guarded rather than trusted: a molplot that no longer holds one here simply
 * leaves the box zoom inert.
 */
const viewOf = (chart: LineChartInstance | null): PlotView | null => {
  const held = (chart as unknown as { result?: { view?: PlotView } | null } | null)?.result;
  const view = held?.view;
  return view && typeof view.origin === "function" ? view : null;
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

/** Where the plot rectangle sits, in client coordinates. */
interface PlotGeometry {
  /** Client x/y of the plot rectangle's top-left corner. */
  left: number;
  top: number;
  width: number;
  height: number;
}

const asFiniteNumber = (value: unknown): number | null =>
  typeof value === "number" && Number.isFinite(value) ? value : null;

/**
 * Locate the plot rectangle of a live chart, or null when it has none yet.
 *
 * Mirrors molplot's own axis-hover hit test: the canvas' client box plus the
 * view origin gives the interior's top-left, and the `width` / `height`
 * signals give its size.
 */
const plotGeometryOf = (
  chart: LineChartInstance | null,
  container: HTMLElement | null,
): PlotGeometry | null => {
  const view = viewOf(chart);
  const canvas = container?.querySelector("canvas");
  if (!view || !canvas) return null;
  const origin = view.origin();
  const width = asFiniteNumber(view.signal("width"));
  const height = asFiniteNumber(view.signal("height"));
  if (width === null || height === null) return null;
  const rect = canvas.getBoundingClientRect();
  return {
    left: rect.left + (origin[0] ?? 0),
    top: rect.top + (origin[1] ?? 0),
    width,
    height,
  };
};

/**
 * Thin React wrapper around molplot's imperative ``LineChart``.
 *
 * Mounts once per spec structure. New points are ``appendPoints`` only;
 * ``setSeries`` is reserved for a reset (cursor mismatch).
 *
 * Dragging inside the plot rubber-bands a region and zooms to it — the
 * gesture scientific plotters put on the plain drag, because reading a
 * feature off a curve is "that region, exactly", not "a bit closer around
 * here" (which is what the wheel already does). Vega's own drag-pan is still
 * there under Shift, and a double click, like the reset control, fits both
 * axes to the data again.
 */
export const MolplotLineChart = ({
  config,
  ref,
  className,
  style,
  overlay,
}: MolplotLineChartProps): JSX.Element => {
  const frameRef = useRef<HTMLDivElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const bandRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<LineChartInstance | null>(null);
  const dragRef = useRef<{ geometry: PlotGeometry; start: PlotPoint } | null>(null);
  const configRef = useRef(config);
  const cursorRef = useRef<Map<string, SeriesCursor>>(new Map());
  configRef.current = config;
  const structureKey = useMemo(() => lineChartStructureKey(config), [config]);

  const resetZoom = useCallback(async (): Promise<void> => {
    const chart = chartRef.current;
    if (!chart) return;
    await chart.setAxisRange("x", "auto");
    await chart.setAxisRange("y", "auto");
  }, []);

  useImperativeHandle(
    ref,
    () => ({
      appendPoint: async (id, point) => chartRef.current?.appendPoint(id, point),
      appendPoints: async (id, points) => chartRef.current?.appendPoints(id, points),
      setSeries: async (id, points) => chartRef.current?.setSeries(id, points),
      setWindow: async (n) => chartRef.current?.setWindow(n),
      setAxisRange: async (axis, range) => chartRef.current?.setAxisRange(axis, range),
      clear: async (id) => chartRef.current?.clear(id),
      resetZoom,
    }),
    [resetZoom],
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

  // Drag → box zoom. Bound on the frame in the capture phase so the press
  // never reaches Vega's own drag-pan, which would otherwise translate the
  // scales under the rubber band. A modified drag is left alone: Shift+drag
  // still pans, and the browser keeps its own gestures.
  useEffect(() => {
    const frame = frameRef.current;
    if (!frame) return;

    const localPoint = (event: MouseEvent, geometry: PlotGeometry): PlotPoint => ({
      x: event.clientX - geometry.left,
      y: event.clientY - geometry.top,
    });

    const claims = (event: MouseEvent): PlotGeometry | null => {
      if (event.button !== 0 || event.shiftKey || event.altKey || event.ctrlKey || event.metaKey) {
        return null;
      }
      const geometry = plotGeometryOf(chartRef.current, containerRef.current);
      if (!geometry) return null;
      const point = localPoint(event, geometry);
      const inside =
        point.x >= 0 && point.x <= geometry.width && point.y >= 0 && point.y <= geometry.height;
      return inside ? geometry : null;
    };

    const drawBand = (geometry: PlotGeometry, start: PlotPoint, end: PlotPoint): void => {
      const band = bandRef.current;
      const host = frameRef.current;
      if (!band || !host) return;
      const box = bandBox(start, end, geometry);
      const hostRect = host.getBoundingClientRect();
      band.style.display = "block";
      band.style.left = `${geometry.left - hostRect.left + box.left}px`;
      band.style.top = `${geometry.top - hostRect.top + box.top}px`;
      band.style.width = `${box.width}px`;
      band.style.height = `${box.height}px`;
    };

    const hideBand = (): void => {
      if (bandRef.current) bandRef.current.style.display = "none";
    };

    const onMove = (event: PointerEvent): void => {
      const drag = dragRef.current;
      if (!drag) return;
      drawBand(drag.geometry, drag.start, localPoint(event, drag.geometry));
    };

    const onUp = (event: PointerEvent): void => {
      const drag = dragRef.current;
      dragRef.current = null;
      hideBand();
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      if (!drag) return;

      const view = viewOf(chartRef.current);
      const invert = (axis: "x" | "y", pixel: number): number => {
        const scale = view?.scale?.(axis);
        return typeof scale?.invert === "function" ? scale.invert(pixel) : Number.NaN;
      };
      const ranges = boxToRanges(
        drag.start,
        localPoint(event, drag.geometry),
        drag.geometry,
        invert,
      );
      if (!ranges) return;
      const chart = chartRef.current;
      if (!chart) return;
      void (async () => {
        if (ranges.x) await chart.setAxisRange("x", ranges.x);
        if (ranges.y) await chart.setAxisRange("y", ranges.y);
      })();
    };

    // Propagation only: cancelling `pointerdown` would suppress the
    // compatibility mouse events, and with them the click pair the
    // double-click reset is built from. Selection and focus are suppressed on
    // `mousedown` instead, where cancelling costs nothing.
    const onPointerDown = (event: PointerEvent): void => {
      const geometry = claims(event);
      if (!geometry) return;
      event.stopPropagation();
      dragRef.current = { geometry, start: localPoint(event, geometry) };
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
    };

    // Vega-Lite compiles an interval selection onto pointer events, but the
    // mouse pair still reaches any listener bound the older way — and it is
    // what starts a text selection across the page mid-drag.
    const onMouseDown = (event: MouseEvent): void => {
      if (!claims(event)) return;
      event.stopPropagation();
      event.preventDefault();
    };

    const onDoubleClick = (event: MouseEvent): void => {
      if (!claims(event)) return;
      event.stopPropagation();
      void resetZoom();
    };

    const options = { capture: true } as const;
    frame.addEventListener("pointerdown", onPointerDown, options);
    frame.addEventListener("mousedown", onMouseDown, options);
    frame.addEventListener("dblclick", onDoubleClick, options);
    return () => {
      frame.removeEventListener("pointerdown", onPointerDown, options);
      frame.removeEventListener("mousedown", onMouseDown, options);
      frame.removeEventListener("dblclick", onDoubleClick, options);
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      dragRef.current = null;
    };
  }, [resetZoom]);

  // The band is a sibling of the chart, not a child: molplot re-embeds into
  // its container on every theme change and resize, and anything living in
  // there goes with it.
  return (
    <div
      ref={frameRef}
      className={className}
      style={{ position: "relative", touchAction: "none", ...style }}
    >
      <div ref={containerRef} style={{ position: "absolute", inset: 0 }} />
      {overlay}
      {/* Last, so the rubber band draws over the overlay as well as the plot. */}
      <div
        ref={bandRef}
        aria-hidden
        style={{ display: "none" }}
        className="pointer-events-none absolute border border-accent bg-accent/15"
      />
    </div>
  );
};
