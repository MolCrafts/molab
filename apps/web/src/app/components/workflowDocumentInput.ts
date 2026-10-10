/**
 * Parse an optional workflow-document field.
 * Blank means none; a JSON object is the document; anything else is an error.
 */

export type WorkflowDocumentInputResult =
  | { ok: true; document: Record<string, unknown> | undefined }
  | { ok: false; error: string };

const isJsonObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

/** Accept empty input or one JSON object. Reject paths, arrays, and other JSON. */
export const parseWorkflowDocumentInput = (text: string): WorkflowDocumentInputResult => {
  const trimmed = text.trim();
  if (trimmed.length === 0) {
    return { ok: true, document: undefined };
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmed);
  } catch {
    return { ok: false, error: "Workflow document must be a JSON object." };
  }
  if (!isJsonObject(parsed)) {
    return { ok: false, error: "Workflow document must be a JSON object." };
  }
  return { ok: true, document: parsed };
};
