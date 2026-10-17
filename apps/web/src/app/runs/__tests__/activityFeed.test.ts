import { describe, expect, it } from "@rstest/core";

import { eventsFromRuns, eventVisualFor, WORKSPACE_EVENT_TYPES } from "@/app/runs/activityFeed";

describe("eventVisualFor", () => {
  it("maps run lifecycle types", () => {
    expect(WORKSPACE_EVENT_TYPES).toEqual([
      "run.created",
      "run.started",
      "run.failed",
      "run.completed",
    ]);
    expect(eventVisualFor("run.failed").label).toBe("Run failed");
  });
});

describe("eventsFromRuns", () => {
  it("builds created/started/completed from a succeeded run", () => {
    const rows = eventsFromRuns([
      {
        id: "r1",
        status: "succeeded",
        createdAt: "2026-01-01T00:00:00Z",
        startedAt: "2026-01-01T00:01:00Z",
        finishedAt: "2026-01-01T00:02:00Z",
      },
    ]);
    expect(rows.map((r) => r.type)).toEqual(["run.completed", "run.started", "run.created"]);
  });
});
