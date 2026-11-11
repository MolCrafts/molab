import { describe, expect, it } from "@rstest/core";
import { renderToStaticMarkup } from "react-dom/server";

import { DurationRange } from "./DurationRange";
import { spanScale } from "./scale";
import { UnitMeter } from "./UnitMeter";

describe("UnitMeter", () => {
  it("says what an empty meter means", () => {
    const html = renderToStaticMarkup(<UnitMeter emptyLabel="All clear" label="none" marks={[]} />);
    expect(html).toContain("All clear");
  });

  it("folds marks past capacity into +N and prints its note", () => {
    const marks = Array.from({ length: 5 }, (_, index) => ({
      key: `run-${index}`,
      status: "failed" as const,
      title: `run ${index}`,
    }));
    const html = renderToStaticMarkup(
      <UnitMeter
        emptyLabel="Idle"
        label="5 failed"
        capacity={3}
        marks={marks}
        note="newest first"
      />,
    );
    expect(html).toContain("+2");
    expect(html).toContain("newest first");
  });
});

describe("DurationRange", () => {
  it("names the spread for assistive tech, not just the median", () => {
    const html = renderToStaticMarkup(<DurationRange seconds={[60, 120, 180, 240, 3600]} />);
    expect(html).toContain("Fastest 1m");
    expect(html).toContain("median 3m");
    expect(html).toContain("slowest 1h");
  });

  it("draws nothing for an empty sample", () => {
    expect(renderToStaticMarkup(<DurationRange seconds={[]} />)).toBe("");
  });
});

describe("spanScale domain", () => {
  it("pads a linear axis around the sample and a log axis by decades", () => {
    const linear = spanScale([600, 1200]);
    expect(linear.log).toBe(false);
    expect(linear.domain[0]).toBeLessThan(600);
    expect(linear.domain[1]).toBeGreaterThan(1200);
    const log = spanScale([4, 21600]);
    expect(log.log).toBe(true);
    expect(log.domain[0]).toBeLessThan(4);
    expect(log.domain[1]).toBeGreaterThan(21600);
  });
});
