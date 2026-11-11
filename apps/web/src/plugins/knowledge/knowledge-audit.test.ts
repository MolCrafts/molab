import { describe, expect, it } from "@rstest/core";
import type { EntityCard } from "@/api/generated/models/EntityCard";
import { KnowledgeGraphEdge as Edge } from "@/api/generated/models/KnowledgeGraphEdge";
import type { KnowledgeGraphResponse } from "@/api/generated/models/KnowledgeGraphResponse";
import { auditKnowledge, knowledgeChangeImpact } from "./knowledge-audit";

const doc = (relPath: string, cls = "Note") => ({ relPath, cls, name: relPath, excerpt: "" });
const edge = (
  source: string,
  target: string,
  role = Edge.role.DERIVED_FROM,
  kind = Edge.kind.DOCUMENT,
) => ({ source, target, role, kind });
const card = (ref: string, kind: string, missing = false): EntityCard => ({
  ref,
  kind,
  missing,
  id: ref,
  title: ref,
});
const codes = (graph: KnowledgeGraphResponse, context = {}) =>
  auditKnowledge(graph, context).issues.map((issue) => issue.code);

describe("knowledge evidence audit", () => {
  it("distinguishes actual evidence from a plan and ordinary document mentions", () => {
    const graph = {
      nodes: [doc("finding", "Finding"), doc("plan", "Plan"), doc("observation", "Observation")],
      edges: [edge("finding", "plan"), edge("finding", "observation", Edge.role.REFERENCES)],
    };
    expect(codes(graph)).toEqual(["ungrounded-finding"]);
    expect(
      codes({ ...graph, edges: [...graph.edges, edge("finding", "observation", Edge.role.CITES)] }),
    ).toEqual([]);
    expect(
      codes({
        ...graph,
        edges: [edge("finding", "https://source.test", Edge.role.CITES, Edge.kind.EXTERNAL)],
      }),
    ).toEqual([]);
    expect(
      codes({
        ...graph,
        edges: [edge("finding", "https://source.test", Edge.role.REFERENCES, Edge.kind.EXTERNAL)],
      }),
    ).toEqual(["ungrounded-finding"]);
  });

  it("follows provenance through a report to its actual run source", () => {
    const graph = {
      nodes: [doc("finding", "Finding"), doc("report", "Report")],
      edges: [
        edge("finding", "report"),
        edge("report", "molab:run/one", Edge.role.RECORDS, Edge.kind.REF),
      ],
    };
    expect(codes(graph, { cardsByPath: { report: [card("molab:run/one", "run")] } })).toEqual([]);
    expect(codes(graph)).toEqual(["evidence-unverified"]);
  });

  it("requires a real source anchor in Finding cycles and follows citations to grounded Findings", () => {
    const graph = {
      nodes: [doc("a", "Finding"), doc("b", "Finding"), doc("observation", "Observation")],
      edges: [edge("a", "b", Edge.role.CITES), edge("b", "a")],
    };
    expect(codes(graph)).toEqual(["ungrounded-finding", "ungrounded-finding"]);
    expect(
      codes({ ...graph, edges: [...graph.edges, edge("b", "observation", Edge.role.RECORDS)] }),
    ).toEqual([]);
    expect(
      codes({ ...graph, edges: [...graph.edges, edge("b", "observation", Edge.role.REFERENCES)] }),
    ).toEqual(["ungrounded-finding", "ungrounded-finding"]);
  });

  it("recognizes bare run/asset refs and server-indexed run descendants without guessing ref grammar", () => {
    const graph = {
      nodes: [doc("finding", "Finding")],
      edges: [edge("finding", "molab:run/one/artifact/table", Edge.role.REFERENCES, Edge.kind.REF)],
    };
    expect(
      codes(graph, {
        refIndex: new Map([["molab:run/one", { kind: "run", label: "one", path: "runs/one" }]]),
      }),
    ).toEqual([]);
    expect(
      codes(graph, { cardsByPath: { finding: [card(graph.edges[0].target, "asset")] } }),
    ).toEqual([]);
    expect(
      codes(graph, { cardsByPath: { finding: [card(graph.edges[0].target, "experiment")] } }),
    ).toEqual(["ungrounded-finding"]);
    expect(codes(graph)).toEqual(["evidence-unverified"]);
  });

  it("only reports server-declared missing refs, deduplicates repeated roles, and ignores absent catalog entries", () => {
    const graph = {
      nodes: [doc("note")],
      edges: [
        edge("note", "lost.md", Edge.role.CITES, Edge.kind.MISSING),
        edge("note", "lost.md", Edge.role.REFERENCES, Edge.kind.MISSING),
        edge("note", "molab:run/missing", Edge.role.RECORDS, Edge.kind.REF),
        edge("note", "molab:run/unloaded", Edge.role.RECORDS, Edge.kind.REF),
      ],
    };
    const result = auditKnowledge(graph, {
      cardsByPath: { note: [card("molab:run/missing", "run", true)] },
    });
    expect(result.issues.map((issue) => issue.target)).toEqual(["lost.md", "molab:run/missing"]);
    expect(result.issues.every((issue) => issue.severity === "error")).toBe(true);
  });

  it("reviews explicit opposing evidence using persisted verdicts, without inferring or modifying a verdict", () => {
    const graph = {
      nodes: [doc("h", "Hypothesis"), doc("a"), doc("b")],
      edges: [edge("a", "h", Edge.role.SUPPORTS), edge("b", "h", Edge.role.CONTRADICTS)],
    };
    const supported = { h: { verdict: "supported" } };
    const issue = auditKnowledge(graph, { records: supported }).issues[0];
    expect(issue).toMatchObject({ code: "verdict-evidence-review", document: "h", related: ["b"] });
    expect(supported.h.verdict).toBe("supported");
    expect(
      auditKnowledge(graph, { records: { h: { verdict: "refuted" } } }).issues[0].related,
    ).toEqual(["a"]);
    expect(codes(graph, { records: { h: { verdict: "open" } } })).toEqual([
      "unresolved-contradiction",
    ]);
    expect(codes(graph, { records: { h: { verdict: "unsettled" } } })).toEqual([
      "unresolved-contradiction",
    ]);
    expect(
      codes({ ...graph, edges: [graph.edges[1]] }, { records: { h: { verdict: "refuted" } } }),
    ).toEqual([]);
    expect(auditKnowledge(graph)).toMatchObject({ issues: [], uncheckedHypotheses: ["h"] });
  });

  it("does not treat an ordinary incoming mention or an outgoing evidence link as counter-evidence", () => {
    const graph = {
      nodes: [doc("h", "Hypothesis"), doc("note")],
      edges: [edge("note", "h", Edge.role.REFERENCES), edge("h", "note", Edge.role.CONTRADICTS)],
    };
    expect(codes(graph, { records: { h: { verdict: "supported" } } })).toEqual([]);
  });

  it("identifies stale readers while preserving replacement provenance and historical citation intent", () => {
    const graph = {
      nodes: [doc("old"), doc("new"), doc("reader")],
      edges: [
        edge("new", "old", Edge.role.SUPERSEDES),
        edge("reader", "old", Edge.role.CITES),
        edge("reader", "old", Edge.role.REFERENCES),
      ],
    };
    const result = auditKnowledge(graph);
    expect(result.issues).toHaveLength(1);
    expect(result.issues[0]).toMatchObject({
      code: "superseded-reference",
      document: "reader",
      target: "old",
      related: ["old", "new"],
    });
    expect(result.issues[0].detail).toContain("intentional historical citation");
  });
});

describe("knowledge change impact", () => {
  it("combines provenance closure, direct readers and judged claims while keeping shortest paths", () => {
    const graph = {
      nodes: [
        doc("source", "Finding"),
        doc("report", "Report"),
        doc("reader"),
        doc("leaf"),
        doc("claim", "Hypothesis"),
        doc("decision", "Decision"),
        doc("unrelated"),
      ],
      edges: [
        edge("report", "source"),
        edge("leaf", "report"),
        edge("leaf", "source"),
        edge("reader", "source", Edge.role.CITES),
        edge("decision", "reader"),
        edge("source", "claim", Edge.role.SUPPORTS),
        edge("decision", "claim"),
        edge("source", "leaf"), // cycle cannot return the changed source as its own impact
      ],
    };
    const impact = knowledgeChangeImpact(graph, "source");
    expect(impact.map((entry) => entry.id).sort()).toEqual([
      "claim",
      "decision",
      "leaf",
      "reader",
      "report",
    ]);
    expect(impact.find((entry) => entry.id === "leaf")).toMatchObject({
      depth: 1,
      via: "source",
      reasons: ["provenance"],
    });
    expect(impact.find((entry) => entry.id === "claim")).toMatchObject({
      depth: 1,
      reasons: ["claim"],
    });
    expect(impact.find((entry) => entry.id === "reader")).toMatchObject({
      depth: 1,
      reasons: ["citation"],
    });
    expect(impact.find((entry) => entry.id === "decision")).toMatchObject({
      depth: 2,
      reasons: ["citation", "claim"],
    });
    expect(knowledgeChangeImpact(graph, "unknown")).toEqual([]);
  });

  it("does not turn arbitrary outgoing sources or missing refs into downstream impact", () => {
    const graph = {
      nodes: [doc("finding"), doc("plan"), doc("source")],
      edges: [
        edge("finding", "plan"),
        edge("finding", "source", Edge.role.CITES),
        edge("missing-reader", "finding"),
        edge("finding", "missing", Edge.role.CITES, Edge.kind.MISSING),
      ],
    };
    expect(knowledgeChangeImpact(graph, "finding")).toEqual([]);
  });
});
