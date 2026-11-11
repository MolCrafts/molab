import { describe, expect, it } from "@rstest/core";
import { workflowEditPolicy } from "@/plugins/workflow/workflowEditPolicy";

describe("workflowEditPolicy", () => {
  it("edits a document workflow", () => {
    expect(workflowEditPolicy("document")).toEqual({ mode: "edit" });
  });

  it("edits an unbound experiment", () => {
    expect(workflowEditPolicy(null)).toEqual({ mode: "edit" });
    expect(workflowEditPolicy(undefined)).toEqual({ mode: "edit" });
  });

  it("requires a convert before editing a code workflow", () => {
    expect(workflowEditPolicy("code")).toEqual({ mode: "convert", kind: "code" });
  });
});
