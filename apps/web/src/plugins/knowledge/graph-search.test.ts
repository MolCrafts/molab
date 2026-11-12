import { describe, expect, it } from "@rstest/core";
import { searchResearchNodes } from "./graph-search";
import type { MapNode } from "./research-map";

const node = (id: string, overrides: Partial<MapNode>): MapNode => ({
  id,
  cls: "Finding",
  title: id,
  excerpt: "",
  note: "",
  state: null,
  host: null,
  refs: [],
  ...overrides,
});
const nodes = [
  node("projects/pbix/knowledges/charge.md", {
    title: "Charge transport in PBIX",
    cls: "Hypothesis",
    state: "supported",
  }),
  node("projects/pbix/knowledges/hydration.md", {
    title: "Compare membrane hydration",
    cls: "Hypothesis",
    state: "open",
  }),
  node("projects/pbix/experiments/hydration/knowledges/plan.md", {
    title: "水合扫描计划",
    cls: "Plan",
    host: "hydration",
  }),
  node("projects/pbix/knowledges/report.md", {
    title: "Charge transport report",
    cls: "Report",
  }),
];

describe("research graph navigation search", () => {
  it("combines title, class and reasoning state tokens without changing graph order", () => {
    const results = searchResearchNodes(nodes, "  SUPPORTED charge hypothesis ");
    expect(results.map((entry) => entry.id)).toEqual([nodes[0].id]);
    expect(searchResearchNodes(nodes, "charge")).toEqual([nodes[0], nodes[3]]);
    expect(results[0]).toBe(nodes[0]);
  });

  it("finds the reasoning state and the class as search terms", () => {
    expect(searchResearchNodes(nodes, "Hypothesis open")).toEqual([nodes[1]]);
    expect(searchResearchNodes(nodes, "charge report")).toEqual([nodes[3]]);
  });

  it("supports non-Latin titles, Unicode width variants and experiment/path lookup", () => {
    expect(searchResearchNodes(nodes, "水合")).toEqual([nodes[2]]);
    expect(searchResearchNodes(nodes, "ＰＢＩＸ supported")).toEqual([nodes[0]]);
    expect(searchResearchNodes(nodes, "experiments/hydration plan")).toEqual([nodes[2]]);
  });

  it("returns the existing nodes for an empty query and no matches for unknown state", () => {
    expect(searchResearchNodes(nodes, "  ")).toEqual(nodes);
    expect(searchResearchNodes(nodes, "refuted")).toEqual([]);
    expect(searchResearchNodes([], "charge")).toEqual([]);
    expect(nodes.map((entry) => entry.id)).toEqual([
      "projects/pbix/knowledges/charge.md",
      "projects/pbix/knowledges/hydration.md",
      "projects/pbix/experiments/hydration/knowledges/plan.md",
      "projects/pbix/knowledges/report.md",
    ]);
  });
});
