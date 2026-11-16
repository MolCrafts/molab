import type { EntityCard } from "@/api/generated/models/EntityCard";
import type { KnowledgeGraphEdge } from "@/api/generated/models/KnowledgeGraphEdge";
import type { KnowledgeGraphResponse } from "@/api/generated/models/KnowledgeGraphResponse";
import { knowledgeLineage } from "./knowledge-map";

export type KnowledgeAuditCode =
  | "missing-reference"
  | "unresolved-contradiction"
  | "verdict-evidence-review";

export interface KnowledgeAuditIssue {
  id: string;
  code: KnowledgeAuditCode;
  severity: "error" | "review" | "info";
  document: string;
  title: string;
  detail: string;
  /** Existing documents that explain the issue; suitable for graph navigation. */
  related: string[];
  /** Literal source target when it is a missing file or entity reference. */
  target?: string;
}

export interface KnowledgeAuditContext {
  /** Each document's own fields (a Hypothesis `verdict`), by path. */
  fields?: Readonly<Record<string, Record<string, unknown> | undefined>>;
  cardsByPath?: Readonly<Record<string, readonly EntityCard[] | undefined>>;
}

/** Read-only review prompts over declared relations. A counter-edge never
 * changes a verdict, and an unloaded entity catalog never proves a broken ref. */
export const auditKnowledge = (
  graph: KnowledgeGraphResponse,
  context: KnowledgeAuditContext = {},
) => {
  const nodes = new Map(graph.nodes.map((node) => [node.relPath, node]));
  const issues = new Map<string, KnowledgeAuditIssue>();
  const outgoing = new Map<string, KnowledgeGraphEdge[]>();
  const incoming = new Map<string, KnowledgeGraphEdge[]>();
  for (const edge of graph.edges) {
    outgoing.set(edge.source, [...(outgoing.get(edge.source) ?? []), edge]);
    incoming.set(edge.target, [...(incoming.get(edge.target) ?? []), edge]);
  }
  const add = (issue: Omit<KnowledgeAuditIssue, "id">): void => {
    const id = JSON.stringify([issue.code, issue.document, issue.target ?? ""]);
    issues.set(id, { ...issue, id, related: [...new Set(issue.related)] });
  };

  for (const edge of graph.edges) {
    if (!nodes.has(edge.source)) continue;
    const card = context.cardsByPath?.[edge.source]?.find(
      (entry) => entry.ref === edge.target || entry.relPath === edge.target,
    );
    if (edge.kind === "missing" || (edge.kind === "ref" && card?.missing)) {
      add({
        code: "missing-reference",
        severity: "error",
        document: edge.source,
        title: "Source does not resolve",
        detail: "Repair or remove this reference after checking the original document.",
        related: [],
        target: edge.target,
      });
    }
  }

  const uncheckedHypotheses: string[] = [];
  for (const node of graph.nodes) {
    if (node.cls !== "Hypothesis") continue;
    const evidence = (incoming.get(node.relPath) ?? []).filter(
      (edge) => edge.kind === "document" && nodes.has(edge.source) && edge.source !== node.relPath,
    );
    const against = evidence.filter((edge) => edge.role === "contradicts");
    const forClaim = evidence.filter((edge) => edge.role === "supports");
    const fields = context.fields?.[node.relPath];
    if (fields === undefined) {
      uncheckedHypotheses.push(node.relPath);
      continue;
    }
    const verdict = fields.verdict ?? "open";
    if (against.length > 0 && (verdict === "open" || verdict === "unsettled")) {
      add({
        code: "unresolved-contradiction",
        severity: "review",
        document: node.relPath,
        title: "Contradicting evidence needs review",
        detail: `This hypothesis is recorded as ${verdict} and has ${against.length} contradicting document${against.length === 1 ? "" : "s"}. Review the evidence and record the conclusion explicitly.`,
        related: against.map((edge) => edge.source),
      });
    }
    const counterEvidence =
      verdict === "supported" ? against : verdict === "refuted" ? forClaim : [];
    if (counterEvidence.length > 0) {
      add({
        code: "verdict-evidence-review",
        severity: "review",
        document: node.relPath,
        title:
          verdict === "supported"
            ? "Counter-evidence to a supported hypothesis"
            : "Support remains for a refuted hypothesis",
        detail: `The recorded verdict is ${verdict}. This is a review prompt, not proof that the verdict is wrong; explain how the opposing evidence was weighed.`,
        related: counterEvidence.map((edge) => edge.source),
      });
    }
  }

  const severityOrder = { error: 0, review: 1, info: 2 };
  return {
    issues: [...issues.values()].sort(
      (left, right) =>
        severityOrder[left.severity] - severityOrder[right.severity] ||
        left.document.localeCompare(right.document) ||
        left.code.localeCompare(right.code),
    ),
    uncheckedHypotheses,
  };
};

export interface KnowledgeImpactEntry {
  id: string;
  title: string;
  cls: string;
  depth: number;
  via: string;
  /** Provenance requires rechecking; citations and evidence prompt inspection. */
  reasons: ("provenance" | "citation" | "claim")[];
}

/** Reuse the canonical provenance closure. Direct readers and the claims this
 * document supports/contradicts are additional review targets, not new lineage. */
export const knowledgeChangeImpact = (
  graph: KnowledgeGraphResponse,
  path: string,
): KnowledgeImpactEntry[] => {
  const nodes = new Map(graph.nodes.map((node) => [node.relPath, node]));
  if (!nodes.has(path)) return [];
  const affected = new Map<string, KnowledgeImpactEntry>();
  const add = (
    id: string,
    depth: number,
    via: string,
    reason: KnowledgeImpactEntry["reasons"][number],
  ): void => {
    const node = nodes.get(id);
    if (!node || id === path) return;
    const existing = affected.get(id);
    if (existing) {
      if (!existing.reasons.includes(reason)) existing.reasons.push(reason);
      if (depth < existing.depth) {
        existing.depth = depth;
        existing.via = via;
      }
      return;
    }
    affected.set(id, {
      id,
      title: node.title || node.name,
      cls: node.cls,
      depth,
      via,
      reasons: [reason],
    });
  };
  for (const entry of knowledgeLineage(graph, path).descendants)
    add(entry.id, entry.depth, entry.via, "provenance");
  for (const edge of graph.edges) {
    if (edge.kind !== "document") continue;
    const reader = edge.target === path && edge.source !== path ? edge.source : null;
    const claim =
      edge.source === path && ["supports", "contradicts"].includes(edge.role) ? edge.target : null;
    const id = reader ?? claim;
    if (!id || !nodes.has(id)) continue;
    const reason = claim ? "claim" : edge.role === "derived_from" ? "provenance" : "citation";
    add(id, 1, path, reason);
    for (const descendant of knowledgeLineage(graph, id).descendants)
      add(descendant.id, descendant.depth + 1, descendant.via, reason);
  }
  return [...affected.values()].sort(
    (left, right) => left.depth - right.depth || left.title.localeCompare(right.title),
  );
};
