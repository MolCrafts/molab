import { describe, expect, it } from "@rstest/core";
import {
  CHART_GROUPS,
  chartGroupOf,
  EXECUTION_STATUSES,
  latestStatus,
  normalizeStatus,
  STATUS,
  statusWord,
} from "./vocabulary";

describe("the status vocabulary (DS v1.4 §3)", () => {
  it("names nine execution states, each with one glyph, word and chart group", () => {
    expect(EXECUTION_STATUSES).toEqual([
      "succeeded",
      "failed",
      "interrupted",
      "running",
      "finalizing",
      "queued",
      "pending",
      "cancelled",
      "cached",
    ]);
    const table = EXECUTION_STATUSES.map((s) => [s, STATUS[s].word, chartGroupOf(s)]);
    expect(table).toEqual([
      ["succeeded", "Succeeded", "succeeded"],
      ["failed", "Failed", "failed"],
      ["interrupted", "Interrupted", "interrupted"],
      ["running", "Running", "running"],
      ["finalizing", "Finalizing", "running"],
      ["queued", "Queued", "queued"],
      ["pending", "Not started", "queued"],
      ["cancelled", "Cancelled", "cancelled"],
      ["cached", "Reused", null],
    ]);
  });

  it("gives interrupted its own colour and keeps queued / not started apart", () => {
    expect(STATUS.interrupted.tone).not.toBe(STATUS.cancelled.tone);
    expect(STATUS.queued.glyph).not.toBe(STATUS.pending.glyph);
    expect(STATUS.finalizing.tone).toBe(STATUS.running.tone);
  });

  it("normalises wire spellings and never invents a state", () => {
    expect(normalizeStatus("completed")).toBe("succeeded");
    expect(normalizeStatus("SUCCESS")).toBe("succeeded");
    expect(normalizeStatus("interrupted")).toBe("interrupted");
    expect(normalizeStatus("finalizing")).toBe("finalizing");
    expect(normalizeStatus("not_started")).toBe("pending");
    expect(normalizeStatus("submitted")).toBe("queued");
    expect(normalizeStatus("canceled")).toBe("cancelled");
    expect(normalizeStatus("timed_out")).toBe("failed");
    expect(normalizeStatus("waiting_for_review")).toBe("attention");
    expect(normalizeStatus("draft")).toBe("draft");
    expect(normalizeStatus("something-new")).toBe("unknown");
    expect(normalizeStatus(null)).toBe("unknown");
  });

  it("orders the chart groups once, for every chart and legend", () => {
    expect(CHART_GROUPS.map((group) => group.id)).toEqual([
      "running",
      "queued",
      "succeeded",
      "failed",
      "interrupted",
      "cancelled",
    ]);
  });

  it("reads a run by its latest attempt, not by any past success", () => {
    expect(latestStatus([{ status: "succeeded" }, { status: "failed" }])).toBe("failed");
    expect(latestStatus([])).toBe("pending");
  });

  it("words a status for people", () => {
    expect(statusWord("completed")).toBe("Succeeded");
    expect(statusWord("not_started")).toBe("Not started");
  });
});

describe("status counts", () => {
  it("counts every status in the total and each in its group", async () => {
    const { countStatuses } = await import("./vocabulary");
    expect(
      countStatuses(["succeeded", "interrupted", "finalizing", "not_started", "cached", null]),
    ).toEqual({
      total: 6,
      running: 1,
      queued: 1,
      succeeded: 1,
      failed: 0,
      interrupted: 1,
      cancelled: 0,
    });
  });
});

describe("finished and attention", () => {
  it("counts interrupted as finished and as needing a person; cancelled only as finished", async () => {
    const { ATTENTION_GROUPS, FINISHED_GROUPS, needsAttention } = await import("./vocabulary");
    expect(FINISHED_GROUPS).toEqual(["succeeded", "failed", "interrupted", "cancelled"]);
    expect(ATTENTION_GROUPS).toEqual(["failed", "interrupted"]);
    expect(["failed", "interrupted", "cancelled", "succeeded", null].map(needsAttention)).toEqual([
      true,
      true,
      false,
      false,
      false,
    ]);
  });
});
