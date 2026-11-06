// ─────────────────────────────────────────────────────────────────────────────
// The one viewer every overview chart renders through. It owns the palette
// (resolved once from the theme), the dataset hand-off, and translating the
// chart's `pick` / `brush` signals into plain callbacks.
// ─────────────────────────────────────────────────────────────────────────────

import type { VegaLiteSpec, VegaLiteViewProps } from "@molcrafts/ui-vega-lite";
import { type ChartData, type ChartTheme, VegaLiteView } from "@molcrafts/ui-vega-lite";
import { type JSX, type ReactNode, useCallback, useMemo, useRef } from "react";

import { cn } from "@/lib/utils";

import { readCssColor, useStatusColors } from "../../InstrumentChart";
import { brushedWindow, clickedKey, type OverviewPalette, paletteOf } from "./common";

/** Resolved palette for the current theme; null until the status ramp has been read. */
export const useOverviewPalette = (): ((theme: ChartTheme) => OverviewPalette) | null => {
  const status = useStatusColors();
  return useMemo(
    () => (status ? (theme: ChartTheme) => paletteOf(theme, status, readCssColor) : null),
    [status],
  );
};

/** The Vega view, typed through the adapter so the shell never imports `vega`. */
type View = Parameters<NonNullable<VegaLiteViewProps["onReady"]>>[0];

/** Stands in while the palette resolves, so nothing recompiles per render. */
const PENDING_SPEC: VegaLiteSpec = { data: { values: [] }, mark: "point" };

interface OverviewChartProps {
  label: string;
  /** Builds the spec from the resolved palette. Keep it stable: a new spec re-mounts the view. */
  spec: (palette: OverviewPalette) => VegaLiteSpec;
  /** Structural inputs of `spec` (sizes, axis domain); data changes go through `data`. */
  specKey: string;
  data: ChartData;
  height: number;
  width?: number;
  onPick?: (key: string) => void;
  /** Field the brush is on; `onBrush` receives [from, to] ms, or null when cleared. */
  brushField?: string;
  onBrush?: (window: [number, number] | null) => void;
  className?: string;
  empty?: boolean;
  emptyFallback?: ReactNode;
}

export const OverviewChart = ({
  label,
  spec,
  specKey,
  data,
  height,
  width,
  onPick,
  brushField,
  onBrush,
  className,
  empty,
  emptyFallback,
}: OverviewChartProps): JSX.Element => {
  const palette = useOverviewPalette();
  const build = useRef(spec);
  build.current = spec;
  // The spec follows the palette and the structural key, never a fresh closure.
  // biome-ignore lint/correctness/useExhaustiveDependencies: specKey stands in for `spec`.
  const themed = useMemo(
    () => (palette ? (theme: ChartTheme) => build.current(palette(theme)) : null),
    [palette, specKey],
  );
  const handlers = useRef({ onPick, onBrush, brushField });
  handlers.current = { onPick, onBrush, brushField };
  const signalNames = useMemo(() => (onBrush ? ["brush"] : []), [onBrush]);
  const onSignalChange = useCallback((name: string, value: unknown) => {
    const current = handlers.current;
    if (name === "brush" && current.brushField) {
      current.onBrush?.(brushedWindow(value, current.brushField));
    }
  }, []);
  // A click listener, not a point selection: a selection does not fire when the
  // same mark is clicked twice, and a second click is how a filter is undone.
  const onReady = useCallback((view: View) => {
    view.addEventListener("click", (_event, item) => {
      const key = clickedKey(item);
      if (key) handlers.current.onPick?.(key);
    });
  }, []);

  return (
    <VegaLiteView
      spec={themed ?? PENDING_SPEC}
      loading={themed === null}
      data={data}
      label={label}
      labelHidden
      height={height}
      width={width}
      renderer="svg"
      signalNames={signalNames}
      onSignalChange={onSignalChange}
      onReady={onReady}
      empty={empty}
      emptyFallback={emptyFallback}
      loadingFallback={null}
      className={cn("outline-none focus-visible:ring-1 focus-visible:ring-ring", className)}
      style={{ padding: 0 }}
    />
  );
};
