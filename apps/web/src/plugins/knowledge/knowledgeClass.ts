/** The knowledge product classes and their class-named head files. */

export const KNOWLEDGE_CLASSES = [
  "Note",
  "Literature",
  "Report",
  "Finding",
  "Plan",
  "Roadmap",
  "Todo",
  "Milestone",
  "Observation",
  "Hypothesis",
  "Decision",
  "Delegation",
] as const;

export type KnowledgeClass = (typeof KNOWLEDGE_CLASSES)[number];

export const KNOWLEDGE_HEAD_FILES = [
  "note.json",
  "literature.json",
  "report.json",
  "finding.json",
  "plan.json",
  "roadmap.json",
  "todo.json",
  "milestone.json",
  "observation.json",
  "hypothesis.json",
  "decision.json",
  "delegation.json",
] as const;

export type KnowledgeHeadFile = (typeof KNOWLEDGE_HEAD_FILES)[number];

const HEAD_BY_CLASS: Record<KnowledgeClass, KnowledgeHeadFile> = {
  Note: "note.json",
  Literature: "literature.json",
  Report: "report.json",
  Finding: "finding.json",
  Plan: "plan.json",
  Roadmap: "roadmap.json",
  Todo: "todo.json",
  Milestone: "milestone.json",
  Observation: "observation.json",
  Hypothesis: "hypothesis.json",
  Decision: "decision.json",
  Delegation: "delegation.json",
};

export const knowledgeHeadFile = (cls: KnowledgeClass): KnowledgeHeadFile => HEAD_BY_CLASS[cls];

const CLASS_SET = new Set<string>(KNOWLEDGE_CLASSES);

/** Class name from a list row (`cls` from the server, else Note). */
export const knowledgeClassOf = (row: { cls?: string | null }): KnowledgeClass => {
  const raw = row.cls ?? "";
  return CLASS_SET.has(raw) ? (raw as KnowledgeClass) : "Note";
};
