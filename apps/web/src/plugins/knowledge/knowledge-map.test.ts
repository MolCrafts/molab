import { describe, expect, it } from "@rstest/core";
import { KnowledgeGraphEdge as Edge } from "@/api/generated/models/KnowledgeGraphEdge";
import type { KnowledgeGraphResponse } from "@/api/generated/models/KnowledgeGraphResponse";
import {
  knowledgeLineage,
  projectKnowledgeMap,
  projectResearchMap,
  toResearchGraph,
} from "./knowledge-map";
import { foldedReferences, layoutKnowledgeMap } from "./map-layout";

const root = "projects/a";
const plan = `${root}/knowledges/plan.md`;
const finding = `${root}/experiments/e/knowledges/finding.md`;
const report = `${root}/knowledges/report.md`;
const doc = (relPath: string, cls = "Note") => ({ relPath, cls, name: relPath, excerpt: "" });
const link = (
  source: string,
  target: string,
  role = Edge.role.DERIVED_FROM,
  kind = Edge.kind.DOCUMENT,
) => ({ source, target, role, kind });
const graph: KnowledgeGraphResponse = {
  nodes: [
    doc(plan, "Plan"),
    doc(finding, "Finding"),
    doc(report, "Report"),
    doc("projects/ab/knowledges/other.md"),
    doc("knowledges/shared.md"),
  ],
  edges: [
    link(finding, plan),
    link(report, finding),
    link(report, plan),
    link(finding, plan, Edge.role.SUPPORTS),
    link(finding, plan),
    link(plan, plan),
    link(plan, "https://example.org", Edge.role.CITES, Edge.kind.EXTERNAL),
  ],
};

describe("project knowledge relations", () => {
  it("includes experiment documents and excludes sibling prefixes and unlinked workspace documents", () => {
    const map = projectKnowledgeMap(graph, root);
    expect(map.nodes.map((node) => node.id)).toEqual([plan, finding, report]);
    expect(projectKnowledgeMap(graph, `${root}/`)).toEqual(map);
    expect(projectKnowledgeMap(graph, "").nodes).toEqual([]);
    expect(map.edges).toHaveLength(4);
    expect(map.edges.filter((edge) => edge.from === finding)).toHaveLength(2);
    expect(graph.edges).toHaveLength(7);
  });

  it("includes workspace plans, reverse hypotheses and their citations without importing other projects", () => {
    const shared = "knowledges/plan.md";
    const observation = "knowledges/observation.md";
    const hypothesis = "knowledges/hypothesis.md";
    const literature = "knowledges/literature.md";
    const note = `${root}/knowledges/context.md`;
    const other = "projects/b/knowledges/finding.md";
    const source: KnowledgeGraphResponse = {
      nodes: [
        doc(finding, "Finding"),
        doc(shared, "Plan"),
        doc(observation, "Observation"),
        doc(hypothesis, "Hypothesis"),
        doc(literature, "Literature"),
        doc(note),
        doc(other, "Finding"),
        doc("knowledges/unrelated.md"),
      ],
      edges: [
        link(finding, shared),
        link(observation, shared),
        link(hypothesis, finding),
        link(shared, literature, Edge.role.CITES),
        link(other, shared),
      ],
    };
    const scope = projectKnowledgeMap(source, root);
    expect(scope.nodes.map((node) => node.id)).toEqual([
      finding,
      shared,
      observation,
      hypothesis,
      literature,
      note,
    ]);
    const research = projectResearchMap(source, root, {
      [hypothesis]: { verdict: "supported" },
    });
    expect(research.nodes.map((node) => node.id)).toEqual(scope.nodes.map((node) => node.id));
    expect(research.nodes.find((node) => node.id === hypothesis)?.state).toBe("supported");
    expect(research.edges).toHaveLength(4);
    expect(projectKnowledgeMap(source, "projects/empty").nodes).toEqual([]);
  });

  it("preserves external, missing and cross-project references in the source graph only", () => {
    const source = {
      ...graph,
      edges: [
        ...graph.edges,
        link(plan, "projects/ab/knowledges/other.md"),
        link(plan, "missing.md", Edge.role.REFERENCES, Edge.kind.MISSING),
      ],
    };
    expect(projectKnowledgeMap(source, root).edges).toEqual(projectKnowledgeMap(graph, root).edges);
    expect(source.edges).toHaveLength(9);
  });

  it("keeps structural direction, role folding and non-overlap", () => {
    const map = projectKnowledgeMap(graph, root);
    const placed = layoutKnowledgeMap(map);
    const x = (id: string) => placed.find((node) => node.id === id)?.x ?? -1;
    expect(x(plan)).toBeLessThan(x(finding));
    expect(x(finding)).toBeLessThan(x(report));
    expect(foldedReferences(map)).toEqual([false, false, true, false]);
    for (const a of placed)
      for (const b of placed) {
        if (a.id === b.id) continue;
        expect(
          a.x + a.width <= b.x ||
            b.x + b.width <= a.x ||
            a.y + a.height <= b.y ||
            b.y + b.height <= a.y,
        ).toBe(true);
      }
  });

  it("places cycles, isolated documents and empty projects without losing nodes", () => {
    const map = projectKnowledgeMap(
      { nodes: graph.nodes, edges: [link(plan, finding), link(finding, plan)] },
      root,
    );
    expect(
      layoutKnowledgeMap(map)
        .map((node) => node.id)
        .sort(),
    ).toEqual([plan, finding, report].sort());
    expect(foldedReferences(map)).toEqual([false, false]);
    expect(layoutKnowledgeMap(projectKnowledgeMap(graph, "projects/empty"))).toEqual([]);
  });
});

describe("research map integration", () => {
  it("retains recorded verdicts, document classes and the full preview references", () => {
    const hypothesis = `${root}/knowledges/hypothesis.md`;
    const input = {
      nodes: [...graph.nodes, doc(hypothesis, "Hypothesis")],
      edges: [...graph.edges, link(hypothesis, finding, Edge.role.CONTRADICTS)],
    };
    const map = projectResearchMap(input, root, {
      [hypothesis]: { verdict: "refuted" },
    });
    expect(map.nodes.find((node) => node.id === finding)?.note).toBe("Filed under e");
    expect(map.nodes.find((node) => node.id === hypothesis)?.state).toBe("refuted");
    expect(map.nodes.find((node) => node.id === plan)?.refs).toContainEqual({
      target: "https://example.org",
      role: "cites",
      kind: "external",
    });
    const canvas = toResearchGraph(map);
    // One visible line per pair; the model and its line classes keep both roles.
    expect(canvas.graph.edges).toHaveLength(4);
    const roles = canvas.roles.get(JSON.stringify([finding, plan]));
    expect(roles).toContain("tw-role-derived_from");
    expect(roles).toContain("tw-role-supports");
    expect([...canvas.roles.values()].some((role) => role.includes("tw-role-contradicts"))).toBe(
      true,
    );
  });
});

describe("knowledge provenance lineage", () => {
  it("walks origins and downstream consumers by shortest path, across projects", () => {
    const outside = "projects/b/knowledges/source.md";
    const diamond: KnowledgeGraphResponse = {
      nodes: [doc(plan), doc(finding), doc(report), doc(outside)],
      edges: [
        link(finding, plan),
        link(report, finding),
        link(report, plan),
        link(plan, outside, Edge.role.SUPERSEDES),
        link(report, finding),
      ],
    };
    const trace = knowledgeLineage(diamond, report);
    expect(trace.ancestors.map((entry) => [entry.id, entry.depth])).toEqual([
      [finding, 1],
      [plan, 1],
      [outside, 2],
    ]);
    expect(trace.descendants).toEqual([]);
    expect(knowledgeLineage(diamond, outside).descendants.map((entry) => entry.id)).toEqual([
      plan,
      finding,
      report,
    ]);
  });

  it("keeps evidence, citations, missing targets and ordinary mentions out of provenance", () => {
    const source: KnowledgeGraphResponse = {
      nodes: [doc(plan), doc(finding)],
      edges: [
        link(finding, plan, Edge.role.SUPPORTS),
        link(finding, plan, Edge.role.CONTRADICTS),
        link(finding, plan, Edge.role.CITES),
        link(finding, plan, Edge.role.REFERENCES),
        link(finding, "https://example.org", Edge.role.DERIVED_FROM, Edge.kind.EXTERNAL),
        link(finding, "gone.md", Edge.role.DERIVED_FROM, Edge.kind.MISSING),
      ],
    };
    expect(knowledgeLineage(source, finding)).toEqual({ ancestors: [], descendants: [] });
  });

  it("terminates on cycles and self-links without returning the selected document", () => {
    const source: KnowledgeGraphResponse = {
      nodes: [doc(plan), doc(finding), doc(report)],
      edges: [link(plan, finding), link(finding, plan), link(plan, plan), link(report, finding)],
    };
    expect(knowledgeLineage(source, plan).ancestors.map((entry) => entry.id)).toEqual([finding]);
    expect(knowledgeLineage(source, plan).descendants.map((entry) => entry.id)).toEqual([
      finding,
      report,
    ]);
    expect(knowledgeLineage(source, "unknown")).toEqual({ ancestors: [], descendants: [] });
  });
});
