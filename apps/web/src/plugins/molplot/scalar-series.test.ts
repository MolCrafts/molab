import { describe, expect, it } from "@rstest/core";
import type { MetricRecordSample as MetricRecord } from "@/lib/contribution-types";
import { buildScalarSeries, filterByTask, listTasks, unitsOf } from "./scalar-series";

// Two scalar keys over out-of-order steps, plus a histogram that is ignored.
const RECORDS: MetricRecord[] = [
  { t: "scalar", k: "train/loss", s: 2, w: "2026-06-15T00:00:02Z", v: 0.5 },
  { t: "scalar", k: "eval/loss", s: 1, w: "2026-06-15T00:00:01Z", v: 0.9 },
  { t: "scalar", k: "train/loss", s: 0, w: "2026-06-15T00:00:00Z", v: 1.0 },
  { t: "scalar", k: "train/loss", s: 1, w: "2026-06-15T00:00:01Z", v: 0.7 },
  { t: "scalar", k: "eval/loss", s: 0, v: 1.2 },
  { t: "histogram", k: "weights/layer0", s: 0, v: [1, 2, 3] },
];

describe("buildScalarSeries", () => {
  it("returns one series per scalar key, ignoring other record types", () => {
    expect(buildScalarSeries(RECORDS).map((series) => series.key)).toEqual([
      "eval/loss",
      "train/loss",
    ]);
  });

  it("sorts points by step and keeps the last value", () => {
    const train = buildScalarSeries(RECORDS).find((series) => series.key === "train/loss");
    expect(train?.points.map((point) => point.step)).toEqual([0, 1, 2]);
    expect(train?.points.map((point) => point.y)).toEqual([1.0, 0.7, 0.5]);
    expect(train?.latest).toBe(0.5);
  });

  it("is timed only when every point measured a wall clock", () => {
    const [evalLoss, train] = buildScalarSeries(RECORDS);
    expect(train.timed).toBe(true);
    expect(evalLoss.timed).toBe(false);
  });

  it("names the attempts a series was replayed from", () => {
    const [series] = buildScalarSeries([
      { t: "scalar", k: "e", s: 0, v: 1, tags: { replayed_from: "e01" } },
    ]);
    expect(series.replayedFrom).toEqual(["e01"]);
  });
});

describe("tasks and units", () => {
  const tagged: MetricRecord[] = [
    { t: "scalar", k: "a", s: 0, v: 1, tags: { task: "relax", unit: "eV" } },
    { t: "scalar", k: "b", s: 0, v: 2, tags: { task: "md" } },
    { t: "scalar", k: "a", s: 1, v: 3, tags: { task: "md", unit: "kJ/mol" } },
  ];

  it("lists the tasks the records name, sorted", () => {
    expect(listTasks(tagged)).toEqual(["md", "relax"]);
  });

  it("narrows to one task, or keeps all for null", () => {
    expect(filterByTask(tagged, "md")).toHaveLength(2);
    expect(filterByTask(tagged, null)).toHaveLength(3);
  });

  it("takes each key's first declared unit and guesses none", () => {
    const units = unitsOf(tagged);
    expect(units.get("a")).toBe("eV");
    expect(units.has("b")).toBe(false);
  });
});
