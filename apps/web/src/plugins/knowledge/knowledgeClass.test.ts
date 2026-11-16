import { describe, expect, it } from "@rstest/core";
import { knowledgeClassOf } from "./knowledgeClass";

describe("knowledgeClass", () => {
  it("reads cls from a list row", () => {
    expect(knowledgeClassOf({ cls: "Finding" })).toBe("Finding");
    expect(knowledgeClassOf({ cls: "Hypothesis" })).toBe("Hypothesis");
  });

  it("gives a row with no knowledge class none, not Note", () => {
    expect(knowledgeClassOf({ cls: "Tex" })).toBeNull();
    expect(knowledgeClassOf({ cls: "" })).toBeNull();
  });
});
