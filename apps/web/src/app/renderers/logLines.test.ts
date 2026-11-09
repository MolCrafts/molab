import { describe, expect, it } from "@rstest/core";
import { classifyLines, findLines, lineStops, stepTo } from "./logLines";

describe("log lines", () => {
  const lines = [
    "Step Temp",
    "WARNING: energy drift 0.0031 above warn threshold",
    "Traceback (most recent call last):",
    '  File "md.py", line 12, in run',
    "molab.tasks.md.NumericalInstability: Energy drift exceeded the tolerance",
    "  tolerance 0.005, observed 0.0123",
    "done",
  ];

  it("reads a traceback as one error block, its exception line included", () => {
    expect(classifyLines(lines)).toEqual([null, "warning", "error", "error", "error", null, null]);
  });

  it("stops once per block and counts errors and warnings", () => {
    expect(lineStops(classifyLines(lines))).toEqual({ errors: 1, warnings: 1, stops: [1, 2] });
  });

  it("finds lines case-insensitively and steps between them, wrapping", () => {
    const found = findLines(lines, "DRIFT");
    expect(found).toEqual([1, 4]);
    expect(stepTo(found, null, 1)).toBe(1);
    expect(stepTo(found, 1, 1)).toBe(4);
    expect(stepTo(found, 4, 1)).toBe(1);
    expect(stepTo(found, 1, -1)).toBe(4);
    expect(stepTo([], 3, 1)).toBeNull();
  });
});
