import { describe, expect, it } from "@rstest/core";
import type { AgentSessionSummary } from "@/app/types";
import { buildAgentExplorerNodes } from "./AgentExplorer";

const SESSION: AgentSessionSummary = {
  id: "task-1",
  sessionId: "session-1",
  title: "Analyze the trajectory",
  goal: "Analyze the trajectory and summarize the result.",
  status: "waiting_for_review",
  createdAt: "2026-08-30T12:00:00Z",
  eventCount: 3,
};

describe("buildAgentExplorerNodes", () => {
  it("keeps destructive task actions permission-gated", () => {
    const [node] = buildAgentExplorerNodes({
      sessions: [SESSION],
      onSelect: () => undefined,
      onDelete: () => undefined,
      writeDeniedReason: "Viewer role cannot delete tasks.",
    });
    const deletion = node?.actions?.find((action) => action.id === "delete");

    expect(deletion).toMatchObject({
      destructive: true,
      disabled: true,
      title: "Viewer role cannot delete tasks.",
    });
  });

  it("uses a compact title while preserving the full goal as hover copy", () => {
    const [node] = buildAgentExplorerNodes({
      sessions: [SESSION],
      onSelect: () => undefined,
      onDelete: () => undefined,
      writeDeniedReason: null,
    });

    expect(node?.label.length).toBeLessThanOrEqual(32);
    expect(node?.hoverTitle).toBe(SESSION.goal);
  });
});
