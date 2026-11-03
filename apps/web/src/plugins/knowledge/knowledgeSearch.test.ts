import { describe, expect, it } from "@rstest/core";
import { KNOWLEDGE_CLASSES } from "./knowledgeClass";

describe("knowledge search inventory", () => {
  it("is the product classes — search hits stay on the knowledge surface", () => {
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
      "Delegation",
    ]);
  });
});
