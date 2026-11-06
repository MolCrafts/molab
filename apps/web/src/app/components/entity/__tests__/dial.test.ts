import type { ChartTheme } from "@molcrafts/ui-vega-lite";
import { describe, expect, it } from "@rstest/core";

import { barSpec, statusBarSpec } from "../instruments";

const theme = {
  foreground: "#0f172a",
  mutedForeground: "#64748b",
  background: "#ffffff",
  border: "#e2e8f0",
  primary: "#2563eb",
  secondary: "#f8fafc",
  danger: "#dc2626",
  font: "monospace",
  labelSize: 12,
  titleSize: 13,
} satisfies ChartTheme;

describe("overview chart specs", () => {
  it("draws status as horizontal bars", () => {
    const encoded = JSON.stringify(statusBarSpec(theme));
    expect(encoded).not.toContain('"arc"');
    expect(encoded).not.toContain("theta");
    expect(encoded).toContain('"type":"bar"');
    expect(encoded).toContain('"field":"label"');
    expect(encoded).toContain('"type":"ordinal"');
    expect(encoded).toContain('"field":"value"');
    expect(encoded).toContain('"type":"quantitative"');
  });

  it("draws a duration histogram as columns in the accent", () => {
    const encoded = JSON.stringify(barSpec(theme, true));
    expect(encoded).not.toContain('"arc"');
    expect(encoded).not.toContain("theta");
    expect(encoded).toContain('"type":"bar"');
    expect(encoded).toContain('"color":"#2563eb"');
    expect(encoded).toContain('"field":"axis"');
  });
});
