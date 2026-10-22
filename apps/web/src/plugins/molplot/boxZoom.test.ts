import { describe, expect, it } from "@rstest/core";

import { bandBox, boxToRanges, clampToFrame, MIN_DRAG_PX, type PlotFrame } from "./boxZoom";

const frame: PlotFrame = { width: 400, height: 200 };

/**
 * A stand-in for a live Vega scale: x maps 0..400px onto 0..1000 data units,
 * y maps 0..200px onto 50..0 (screen y grows downwards, data y upwards).
 */
const invert = (axis: "x" | "y", pixel: number): number =>
  axis === "x" ? (pixel / frame.width) * 1000 : 50 - (pixel / frame.height) * 50;

describe("clampToFrame", () => {
  it("keeps a drag that left the plot on the plot's edge", () => {
    // Dragging past the axis is how you say "everything from here out"; it
    // must not invert into a value the scale never covered.
    expect(clampToFrame({ x: -30, y: 260 }, frame)).toEqual({ x: 0, y: 200 });
    expect(clampToFrame({ x: 900, y: -5 }, frame)).toEqual({ x: 400, y: 0 });
  });
});

describe("boxToRanges", () => {
  it("zooms both axes for a rectangle", () => {
    const ranges = boxToRanges({ x: 100, y: 40 }, { x: 300, y: 160 }, frame, invert);
    expect(ranges?.x).toEqual([250, 750]);
    expect(ranges?.y).toEqual([10, 40]);
  });

  it("orders the range regardless of drag direction", () => {
    const forward = boxToRanges({ x: 100, y: 40 }, { x: 300, y: 160 }, frame, invert);
    const backward = boxToRanges({ x: 300, y: 160 }, { x: 100, y: 40 }, frame, invert);
    expect(backward).toEqual(forward);
  });

  it("zooms x alone for a thin horizontal band", () => {
    // A strip along the x axis means "these steps, all of y" — cropping y to
    // an 8px sliver would throw the curve away.
    const ranges = boxToRanges({ x: 100, y: 100 }, { x: 300, y: 103 }, frame, invert);
    expect(ranges?.x).toEqual([250, 750]);
    expect(ranges?.y).toBeUndefined();
  });

  it("zooms y alone for a thin vertical band", () => {
    const ranges = boxToRanges({ x: 100, y: 40 }, { x: 102, y: 160 }, frame, invert);
    expect(ranges?.y).toEqual([10, 40]);
    expect(ranges?.x).toBeUndefined();
  });

  it("is a click, not a zoom, below the drag threshold on both axes", () => {
    const wobble = MIN_DRAG_PX - 1;
    expect(
      boxToRanges({ x: 100, y: 100 }, { x: 100 + wobble, y: 100 + wobble }, frame, invert),
    ).toBe(null);
  });

  it("drops an axis whose inverted range is degenerate", () => {
    // A scale that cannot invert (no domain yet) must disable the zoom rather
    // than pin the axis to [NaN, NaN].
    expect(boxToRanges({ x: 0, y: 0 }, { x: 300, y: 160 }, frame, () => Number.NaN)).toBe(null);
  });
});

describe("bandBox", () => {
  it("normalises the dragged rectangle for drawing", () => {
    expect(bandBox({ x: 300, y: 160 }, { x: 100, y: 40 }, frame)).toEqual({
      left: 100,
      top: 40,
      width: 200,
      height: 120,
    });
  });

  it("clips the drawn band to the plot", () => {
    expect(bandBox({ x: -50, y: -50 }, { x: 500, y: 500 }, frame)).toEqual({
      left: 0,
      top: 0,
      width: 400,
      height: 200,
    });
  });
});
