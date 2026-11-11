import { describe, expect, it } from "@rstest/core";
import { parseWorkflowDocumentInput } from "@/app/components/workflowDocumentInput";

const errorText = (result: unknown): string | undefined => {
  if (typeof result !== "object" || result === null || !("error" in result)) {
    return undefined;
  }
  return typeof result.error === "string" ? result.error : undefined;
};

const expectRejected = (text: string): void => {
  const result: unknown = parseWorkflowDocumentInput(text);
  expect(result).toMatchObject({ ok: false });
  const error = errorText(result);
  expect(typeof error).toBe("string");
  expect((error ?? "").length).toBeGreaterThan(0);
};

describe("parseWorkflowDocumentInput", () => {
  it("returns no document for an empty string", () => {
    expect(parseWorkflowDocumentInput("")).toEqual({ ok: true, document: undefined });
  });

  it("returns no document for whitespace", () => {
    expect(parseWorkflowDocumentInput("  ")).toEqual({ ok: true, document: undefined });
  });

  it("parses a JSON object as the document", () => {
    expect(parseWorkflowDocumentInput('{"task_configs":[],"links":[]}')).toEqual({
      ok: true,
      document: { task_configs: [], links: [] },
    });
  });

  it("rejects a file path", () => {
    expectRejected("path/to/workflow.yaml");
  });

  it("rejects a JSON array", () => {
    expectRejected("[]");
  });

  it("rejects JSON null", () => {
    expectRejected("null");
  });

  it("rejects a JSON number", () => {
    expectRejected("3");
  });
});
