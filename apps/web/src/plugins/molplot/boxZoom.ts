/**
 * Turning a dragged rectangle into axis ranges.
 *
 * Wheel zoom answers "a bit closer around here"; reading a feature off a curve
 * needs "that region, exactly" — a rubber band over the interesting stretch of
 * a 200k-step thermo log, the gesture every solver-log viewer already has.
 *
 * A band drawn along one axis only is not a failed rectangle, it is a
 * narrower request: dragging a thin horizontal strip means "these steps, all
 * of y", and forcing a y range out of an 8px-tall drag would crop the curve to
 * nothing. So each axis is zoomed only if the drag actually spent pixels on
 * it, and a drag that spent pixels on neither is a click, not a zoom.
 *
 * The pixel→data inversion is injected: the caller owns the live chart's
 * scales, and keeping the geometry pure is what lets it be tested without a
 * DOM. Screen y grows downwards, so the returned range is min/max of the two
 * inverted corners rather than start/end.
 */

/** The plot rectangle's interior size, in pixels. */
export interface PlotFrame {
  width: number;
  height: number;
}

/** A point in the plot rectangle's own frame — its interior is [0,w]×[0,h]. */
export interface PlotPoint {
  x: number;
  y: number;
}

export interface BoxRanges {
  x?: [number, number];
  y?: [number, number];
}

/** Below this, a drag is a click that wobbled — not a request to zoom. */
export const MIN_DRAG_PX = 8;

export const clampToFrame = (point: PlotPoint, frame: PlotFrame): PlotPoint => ({
  x: Math.min(Math.max(point.x, 0), frame.width),
  y: Math.min(Math.max(point.y, 0), frame.height),
});

const ordered = (a: number, b: number): [number, number] => (a <= b ? [a, b] : [b, a]);

/**
 * Ranges for the axes the drag actually covered, or `null` for a click.
 *
 * `invert` maps a pixel offset in the plot frame back to a data value on that
 * axis — a live Vega scale's `invert`, whatever its type, so a log axis needs
 * no special case here.
 */
export const boxToRanges = (
  start: PlotPoint,
  end: PlotPoint,
  frame: PlotFrame,
  invert: (axis: "x" | "y", pixel: number) => number,
): BoxRanges | null => {
  const from = clampToFrame(start, frame);
  const to = clampToFrame(end, frame);
  const wideEnough = Math.abs(to.x - from.x) >= MIN_DRAG_PX;
  const tallEnough = Math.abs(to.y - from.y) >= MIN_DRAG_PX;
  if (!wideEnough && !tallEnough) return null;

  const ranges: BoxRanges = {};
  if (wideEnough) {
    const [lo, hi] = ordered(invert("x", from.x), invert("x", to.x));
    if (Number.isFinite(lo) && Number.isFinite(hi) && lo !== hi) ranges.x = [lo, hi];
  }
  if (tallEnough) {
    const [lo, hi] = ordered(invert("y", from.y), invert("y", to.y));
    if (Number.isFinite(lo) && Number.isFinite(hi) && lo !== hi) ranges.y = [lo, hi];
  }
  return ranges.x || ranges.y ? ranges : null;
};

/** The rubber band's box in the frame, for drawing it. */
export const bandBox = (
  start: PlotPoint,
  end: PlotPoint,
  frame: PlotFrame,
): { left: number; top: number; width: number; height: number } => {
  const from = clampToFrame(start, frame);
  const to = clampToFrame(end, frame);
  const [x0, x1] = ordered(from.x, to.x);
  const [y0, y1] = ordered(from.y, to.y);
  return { left: x0, top: y0, width: x1 - x0, height: y1 - y0 };
};
