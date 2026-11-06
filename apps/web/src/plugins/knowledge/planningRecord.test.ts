import { describe, expect, it } from "@rstest/core";
import { buildPlanningRecord, emptyPlanningDraft, planningView } from "./planningModel";

describe("buildPlanningRecord", () => {
  it("keeps a roadmap to stages", () => {
    const draft = emptyPlanningDraft();
    draft.stages = [
      { key: "1", id: "bind", title: "Bind", experiment: "thermostat", depends: "" },
      { key: "2", id: "compare", title: "Compare", experiment: "", depends: "bind, " },
      { key: "3", id: "", title: "", experiment: "", depends: "" },
    ];
    const built = buildPlanningRecord("Roadmap", draft);
    expect(built).toEqual({
      ok: true,
      record: {
        stages: [
          { id: "bind", title: "Bind", experiment: "thermostat" },
          { id: "compare", title: "Compare", depends_on: ["bind"] },
        ],
      },
    });
  });

  it("rejects a roadmap stage that has no id", () => {
    const draft = emptyPlanningDraft();
    draft.stages = [{ key: "1", id: "", title: "Bind", experiment: "", depends: "" }];
    expect(buildPlanningRecord("Roadmap", draft)).toEqual({
      ok: false,
      message: "Each stage needs an id and a title.",
    });
  });

  it("keeps a todo to items and a milestone to its checkpoint", () => {
    const todos = emptyPlanningDraft();
    todos.items = [
      { key: "1", id: "bind-workflow", title: "Bind a workflow", status: "blocked", stage: "bind" },
    ];
    expect(buildPlanningRecord("Todo", todos)).toEqual({
      ok: true,
      record: {
        items: [
          { id: "bind-workflow", title: "Bind a workflow", status: "blocked", stage: "bind" },
        ],
      },
    });
    const milestone = emptyPlanningDraft();
    milestone.milestone = { stage: "compare", criterion: "Times compared.", status: "open" };
    expect(buildPlanningRecord("Milestone", milestone).ok).toBe(true);
  });
});

describe("planningView", () => {
  it("reads stages, items, a checkpoint, and a delegation", () => {
    expect(
      planningView("Roadmap", {
        stages: [{ id: "bind", title: "Bind", experiment: "thermostat", depends_on: ["setup"] }],
      }),
    ).toEqual({
      kind: "roadmap",
      stages: [{ id: "bind", title: "Bind", experiment: "thermostat", dependsOn: ["setup"] }],
    });
    expect(
      planningView("Todo", {
        items: [{ id: "bind-workflow", title: "Bind", status: "open", stage: "bind" }],
      })?.kind,
    ).toBe("todo");
    expect(
      planningView("Milestone", { stage: "compare", criterion: "Done.", status: "met" }),
    ).toMatchObject({ kind: "milestone", status: "met" });
    expect(
      planningView("Delegation", { goal: "Check 300 K", scope: "nve", state: "open" })?.kind,
    ).toBe("delegation");
  });

  it("renders nothing for an empty record or the wrong class", () => {
    expect(planningView("Plan", {})).toBeNull();
    expect(planningView("Roadmap", {})).toBeNull();
    expect(planningView("Roadmap", { stages: [{ id: 1 }] })).toBeNull();
    expect(planningView("Note", { stages: [{ id: "a", title: "A" }] })).toBeNull();
  });
});
