import { DocCreateRequest } from "@/api/generated/models/DocCreateRequest";

/** A knowledge class name, as the server's class table spells it. */
export type KnowledgeClass = `${DocCreateRequest.cls}`;

/** The knowledge classes, in the server's table order (generated from its OpenAPI). */
export const KNOWLEDGE_CLASSES: readonly KnowledgeClass[] = Object.values(DocCreateRequest.cls);

const CLASS_SET = new Set<string>(KNOWLEDGE_CLASSES);

/** Knowledge class of a row, or `null` when the row names no knowledge class. */
export const knowledgeClassOf = (row: { cls: string }): KnowledgeClass | null =>
  CLASS_SET.has(row.cls) ? (row.cls as KnowledgeClass) : null;
