import { describe, expect, it } from "@rstest/core";
import { parseInstant } from "./format-time";

describe("parseInstant", () => {
  it("reads an ISO instant and refuses what is missing or malformed", () => {
    expect(parseInstant("2026-03-01T12:00:00Z")).toBe(Date.UTC(2026, 2, 1, 12));
    expect(parseInstant(null)).toBeNull();
    expect(parseInstant("")).toBeNull();
    expect(parseInstant("not a date")).toBeNull();
  });
});
