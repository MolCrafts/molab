import { describe, expect, it } from "@rstest/core";
import {
  KNOWLEDGE_CLASSES,
  KNOWLEDGE_HEAD_FILES,
  knowledgeClassOf,
  knowledgeHeadFile,
} from "./knowledgeClass";

describe("knowledgeClass", () => {
  it("exports the product classes", () => {
    expect([...KNOWLEDGE_CLASSES]).toEqual([
      "Note",
      "Literature",
      "Report",
      "Finding",
      "Plan",
      "Roadmap",
      "Todo",
      "Milestone",
      "Observation",
      "Hypothesis",
      "Decision",
      "Delegation",
    ]);
  });

  it("maps each class to its class-named json head", () => {
    expect([...KNOWLEDGE_HEAD_FILES]).toEqual([
      "note.json",
      "literature.json",
      "report.json",
      "finding.json",
      "plan.json",
      "roadmap.json",
      "todo.json",
      "milestone.json",
      "observation.json",
      "hypothesis.json",
      "decision.json",
      "delegation.json",
    ]);
    expect(knowledgeHeadFile("Note")).toBe("note.json");
    expect(knowledgeHeadFile("Literature")).toBe("literature.json");
    expect(knowledgeHeadFile("Report")).toBe("report.json");
    expect(knowledgeHeadFile("Finding")).toBe("finding.json");
    expect(knowledgeHeadFile("Plan")).toBe("plan.json");
    expect(knowledgeHeadFile("Roadmap")).toBe("roadmap.json");
    expect(knowledgeHeadFile("Todo")).toBe("todo.json");
    expect(knowledgeHeadFile("Milestone")).toBe("milestone.json");
    expect(knowledgeHeadFile("Observation")).toBe("observation.json");
    expect(knowledgeHeadFile("Hypothesis")).toBe("hypothesis.json");
    expect(knowledgeHeadFile("Decision")).toBe("decision.json");
    expect(knowledgeHeadFile("Delegation")).toBe("delegation.json");
  });

  it("reads cls from a list row and falls back to Note", () => {
    expect(knowledgeClassOf({ cls: "Finding" })).toBe("Finding");
    expect(knowledgeClassOf({ cls: "Roadmap" })).toBe("Roadmap");
    expect(knowledgeClassOf({ cls: "nope" })).toBe("Note");
    expect(knowledgeClassOf({})).toBe("Note");
  });
});
