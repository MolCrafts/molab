import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "@rstest/core";

const here = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(here, "ApprovalsInbox.tsx"), "utf8");
const commands = readFileSync(join(here, "commands.ts"), "utf8");

describe("ApprovalsInbox three-action contract", () => {
  it("offers Approve, Reject, and Revise", () => {
    expect(source).toContain("Approve");
    expect(source).toContain("Reject");
    expect(source).toContain("Revise");
    expect(commands).toContain('ApprovalAction = "approve" | "reject" | "revise"');
  });

  it("sends fieldValues when the form has values (approve and revise)", () => {
    expect(source).toContain("fieldValues");
    expect(source).toContain("Object.keys(fieldValues).length > 0 ? fieldValues : undefined");
  });

  it("hosts ReviewSurface for form packs", () => {
    expect(source).toContain("ReviewSurface");
    expect(source).toContain("formDocument");
  });

  it("calls ApprovalsService decide endpoint", () => {
    expect(source).toContain("useApprovalDecision");
    expect(commands).toContain("ApprovalsService.decideApproval");
    expect(commands).toContain("invalidateQueries");
  });
});

describe("PlanDecisionBar (agent-answer decide strip)", () => {
  const bar = readFileSync(join(here, "PlanDecisionBar.tsx"), "utf8");
  it("is a slim decide strip without embedding the plan document", () => {
    expect(bar).toContain("Approve & generate workflow");
    expect(bar).toContain("Reject");
    expect(bar).toContain("Revise");
    expect(bar).not.toContain("PlanDocumentCard");
    expect(bar).toContain("useApprovalDecision");
  });
});
