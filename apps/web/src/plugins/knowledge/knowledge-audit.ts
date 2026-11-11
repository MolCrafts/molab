import type { EntityCard } from "@/api/generated/models/EntityCard";
import type { KnowledgeGraphEdge } from "@/api/generated/models/KnowledgeGraphEdge";
import type { KnowledgeGraphResponse } from "@/api/generated/models/KnowledgeGraphResponse";
import { type MolabRefTarget, resolveMolabRef } from "@/lib/molab-ref";
import { knowledgeLineage } from "./knowledge-map";
import { knowledgeClassOf } from "./knowledgeClass";

export type KnowledgeAuditCode =
  | "missing-reference"
  | "ungrounded-finding"
  | "evidence-unverified"
  | "unresolved-contradiction"
  | "verdict-evidence-review"
  | "superseded-reference";

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
  records?: Readonly<Record<string, Record<string, unknown> | undefined>>;
  cardsByPath?: Readonly<Record<string, readonly EntityCard[] | undefined>>;
  /** Canonical server refs already resolved by the workbench, never parsed here. */
  refIndex?: ReadonlyMap<string, MolabRefTarget>;
}

const EVIDENCE_CLASSES = new Set(["Observation", "Literature"]);
const SOURCE_ROLES = new Set(["derived_from", "records", "cites"]);

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

  for (const node of graph.nodes) {
    if (knowledgeClassOf(node) !== "Finding") continue;
    const links = outgoing.get(node.relPath) ?? [];
    // Follow only declared provenance/citation sources. A Finding-to-Finding
    // cycle is not evidence by itself; every path needs an actual source anchor.
    const visited = new Set<string>();
    let grounded = false;
    let unresolvedEntity = false;
    const inspectSources = (path: string): void => {
      const sourcePaths = [
        path,
        ...knowledgeLineage(graph, path).ancestors.map((entry) => entry.id),
      ];
      for (const source of sourcePaths) {
        if (visited.has(source)) continue;
        visited.add(source);
        if (EVIDENCE_CLASSES.has(knowledgeClassOf(nodes.get(source) ?? {}))) grounded = true;
        for (const edge of outgoing.get(source) ?? []) {
          if (edge.source === edge.target || edge.kind === "missing") continue;
          if (edge.kind === "document" && SOURCE_ROLES.has(edge.role) && nodes.has(edge.target)) {
            inspectSources(edge.target);
          } else if (edge.kind === "external" && SOURCE_ROLES.has(edge.role)) {
            grounded = true;
          } else if (edge.kind === "ref") {
            const card = context.cardsByPath?.[edge.source]?.find(
              (entry) => entry.ref === edge.target,
            );
            if (card?.missing) continue;
            const resolved = context.refIndex
              ? resolveMolabRef(edge.target, context.refIndex)
              : null;
            const kind = card?.kind ?? resolved?.kind;
            if (kind === "asset" || kind === "run") grounded = true;
            else if (kind === undefined) unresolvedEntity = true;
          }
        }
      }
    };
    inspectSources(node.relPath);
    if (!grounded) {
      add({
        code: unresolvedEntity ? "evidence-unverified" : "ungrounded-finding",
        severity: unresolvedEntity ? "info" : "review",
        document: node.relPath,
        title: unresolvedEntity
          ? "Resolve entity sources to check evidence"
          : "Finding has no declared evidence",
        detail: unresolvedEntity
          ? "The graph has entity references whose kinds are not loaded. Resolve them before deciding whether this finding is grounded."
          : "No run, asset, cited external source, or provenance/citation path to an observation or literature is declared. A plan or ordinary mention alone is not evidence.",
        related: links
          .filter((edge) => edge.kind === "document" && nodes.has(edge.target))
          .map((edge) => edge.target),
      });
    }
  }

  const uncheckedHypotheses: string[] = [];
  for (const node of graph.nodes) {
    if (knowledgeClassOf(node) !== "Hypothesis") continue;
    const evidence = (incoming.get(node.relPath) ?? []).filter(
      (edge) => edge.kind === "document" && nodes.has(edge.source) && edge.source !== node.relPath,
    );
    const against = evidence.filter((edge) => edge.role === "contradicts");
    const forClaim = evidence.filter((edge) => edge.role === "supports");
    const record = context.records?.[node.relPath];
    if (record === undefined) {
      uncheckedHypotheses.push(node.relPath);
      continue;
    }
    const verdict = record.verdict ?? "open";
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

  const replacements = new Map<string, Set<string>>();
  for (const edge of graph.edges) {
    if (
      edge.kind !== "document" ||
      edge.role !== "supersedes" ||
      edge.source === edge.target ||
      !nodes.has(edge.source) ||
      !nodes.has(edge.target)
    )
      continue;
    if (!replacements.has(edge.target)) replacements.set(edge.target, new Set());
    replacements.get(edge.target)?.add(edge.source);
  }
  for (const edge of graph.edges) {
    const newer = replacements.get(edge.target);
    if (
      edge.kind !== "document" ||
      !nodes.has(edge.source) ||
      !newer ||
      newer.has(edge.source) ||
      edge.source === edge.target
    )
      continue;
    add({
      code: "superseded-reference",
      severity: "review",
      document: edge.source,
      title: "References a superseded document",
      detail:
        "This may be an intentional historical citation. Check the replacement before updating the reference.",
      target: edge.target,
      related: [edge.target, ...newer],
    });
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
      cls: knowledgeClassOf(node),
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
    const reason = claim
      ? "claim"
      : ["derived_from", "supersedes"].includes(edge.role)
        ? "provenance"
        : "citation";
    add(id, 1, path, reason);
    for (const descendant of knowledgeLineage(graph, id).descendants)
      add(descendant.id, descendant.depth + 1, descendant.via, reason);
  }
  return [...affected.values()].sort(
    (left, right) => left.depth - right.depth || left.title.localeCompare(right.title),
  );
};
