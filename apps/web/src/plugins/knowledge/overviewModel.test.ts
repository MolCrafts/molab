import { describe, expect, it } from "@rstest/core";
import { byRecent, writingDays } from "./overviewModel";

describe("writingDays / byRecent", () => {
  const now = new Date(2026, 10, 9, 12).getTime();
  const at = (daysAgo: number): string => new Date(now - daysAgo * 86_400_000).toISOString();

  it("counts last edits per day, oldest day first, zeros kept", () => {
    const days = writingDays(
      [{ updatedAt: at(0) }, { updatedAt: at(0) }, { updatedAt: at(2) }, {}],
      now,
      3,
    );
    expect(days.map((d) => d.edits)).toEqual([1, 0, 2]);
    expect(days).toHaveLength(3);
  });

  it("puts the newest edit first and undated documents last", () => {
    const rows = [
      { name: "b", updatedAt: at(3) },
      { name: "a", updatedAt: null },
      { name: "c", updatedAt: at(1) },
    ];
    expect(byRecent(rows).map((row) => row.name)).toEqual(["c", "b", "a"]);
  });
});
