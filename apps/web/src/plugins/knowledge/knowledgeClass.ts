import { DocCreateRequest } from "@/api/generated/models/DocCreateRequest";

/** A knowledge class name, as the server's class table spells it. */
export type KnowledgeClass = `${DocCreateRequest.cls}`;

/** The knowledge classes, in the server's table order (generated from its OpenAPI). */
export const KNOWLEDGE_CLASSES: readonly KnowledgeClass[] = Object.values(DocCreateRequest.cls);

const CLASS_SET = new Set<string>(KNOWLEDGE_CLASSES);

/** Class name from a list row. A TeX manuscript row (`Tex`) has no knowledge class and reads as a Note. */
export const knowledgeClassOf = (row: { cls?: string | null }): KnowledgeClass => {
  const raw = row.cls ?? "";
  return CLASS_SET.has(raw) ? (raw as KnowledgeClass) : "Note";
};
