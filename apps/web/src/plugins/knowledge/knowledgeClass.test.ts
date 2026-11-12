import { describe, expect, it } from "@rstest/core";
import { knowledgeClassOf } from "./knowledgeClass";

describe("knowledgeClass", () => {
  it("reads cls from a list row and reads a TeX row as Note", () => {
    expect(knowledgeClassOf({ cls: "Finding" })).toBe("Finding");
    expect(knowledgeClassOf({ cls: "Hypothesis" })).toBe("Hypothesis");
    expect(knowledgeClassOf({ cls: "Tex" })).toBe("Note");
  });
});
