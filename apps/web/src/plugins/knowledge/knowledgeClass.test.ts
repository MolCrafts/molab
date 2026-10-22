import { describe, expect, it } from "@rstest/core";
import {
  KNOWLEDGE_CLASSES,
  KNOWLEDGE_HEAD_FILES,
  knowledgeClassOf,
  knowledgeHeadFile,
} from "./knowledgeClass";

describe("knowledgeClass", () => {
  it("exports exactly the six product classes", () => {
    expect([...KNOWLEDGE_CLASSES]).toEqual([
      "Note",
      "Literature",
      "Report",
      "Finding",
      "Plan",
      "Observation",
    ]);
  });

  it("maps each class to its class-named json head", () => {
    expect([...KNOWLEDGE_HEAD_FILES]).toEqual([
      "note.json",
      "literature.json",
      "report.json",
      "finding.json",
      "plan.json",
      "observation.json",
    ]);
    expect(knowledgeHeadFile("Note")).toBe("note.json");
    expect(knowledgeHeadFile("Literature")).toBe("literature.json");
    expect(knowledgeHeadFile("Report")).toBe("report.json");
    expect(knowledgeHeadFile("Finding")).toBe("finding.json");
    expect(knowledgeHeadFile("Plan")).toBe("plan.json");
    expect(knowledgeHeadFile("Observation")).toBe("observation.json");
  });

  it("reads cls from a list row and falls back to Note", () => {
    expect(knowledgeClassOf({ cls: "Finding" })).toBe("Finding");
    expect(knowledgeClassOf({ cls: "nope" })).toBe("Note");
    expect(knowledgeClassOf({})).toBe("Note");
  });
});
