import { describe, expect, it } from "@rstest/core";

import { buildCampaigns } from "./campaignProgress";

describe("buildCampaigns", () => {
  it("attaches milestones and todos to roadmap stages", () => {
    const campaigns = buildCampaigns([
      { cls: "Plan", name: "PBIX plan", relPath: "knowledges/plan.md", record: {} },
      {
        cls: "Roadmap",
        name: "PBIX roadmap",
        relPath: "knowledges/roadmap.md",
        record: {
          stages: [
            { id: "monomers", title: "Build fragments", experiment: "monomers" },
            { id: "stage1", title: "Equilibrate", experiment: "stage1-equilibrate" },
          ],
        },
      },
      {
        cls: "Milestone",
        name: "Monomers confirmed",
        relPath: "knowledges/monomers-confirmed.md",
        record: { stage: "monomers", criterion: "2D and 3D", status: "open" },
      },
      {
        cls: "Todo",
        name: "Todos",
        relPath: "knowledges/todo.md",
        record: {
          items: [
            { id: "a", title: "Show fragments", status: "blocked", stage: "monomers" },
            { id: "b", title: "Confirm", status: "open", stage: "monomers" },
          ],
        },
      },
    ]);
    expect(campaigns).toHaveLength(1);
    expect(campaigns[0]?.planTitle).toBe("PBIX plan");
    expect(campaigns[0]?.stages[0]).toMatchObject({
      id: "monomers",
      word: "Blocked",
      experiment: "monomers",
      todos: { done: 0, open: 1, blocked: 1, total: 2 },
    });
    expect(campaigns[0]?.stages[1]?.word).toBe("Open");
  });

  it("marks a stage met when its milestone is met", () => {
    const campaigns = buildCampaigns([
      {
        cls: "Roadmap",
        name: "Road",
        relPath: "road.md",
        record: { stages: [{ id: "done", title: "Done" }] },
      },
      {
        cls: "Milestone",
        name: "Gate",
        relPath: "gate.md",
        record: { stage: "done", criterion: "shipped", status: "met" },
      },
    ]);
    expect(campaigns[0]?.stages[0]?.word).toBe("Met");
  });
});
