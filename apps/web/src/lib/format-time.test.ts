import { describe, expect, it } from "@rstest/core";
import { formatRelative } from "./format-time";

describe("formatRelative", () => {
  it("returns dash when input is null", () => {
    expect(formatRelative(null)).toBe("—");
  });

  it("falls back to the raw string when not a date", () => {
    expect(formatRelative("not-a-date")).toBe("not-a-date");
  });

  it("returns 'just now' for recent timestamps", () => {
    const recent = new Date(Date.now() - 5_000).toISOString();
    expect(formatRelative(recent)).toBe("just now");
  });

  it("returns minutes when delta is < 1 hour", () => {
    const t = new Date(Date.now() - 5 * 60 * 1000).toISOString();
    expect(formatRelative(t)).toBe("5m ago");
  });
});
