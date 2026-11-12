import { describe, expect, it } from "@rstest/core";
import type { KnowledgeGraphResponse as KnowledgeGraph } from "@/api/generated/models/KnowledgeGraphResponse";
import { foldedReferences, layoutKnowledgeMap } from "./map-layout";
import { buildResearchMap } from "./research-map";

const node = (relPath: string, cls: string, name: string, excerpt = "", title = "") => ({
  relPath,
  cls,
  name,
  title,
  excerpt,
  hostPath: "",
});
const link = (source: string, target: string, role = "derived_from", kind = "document") => ({
  source,
  target,
  role: role as KnowledgeGraph["edges"][number]["role"],
  kind: kind as KnowledgeGraph["edges"][number]["kind"],
});

const PLAN = "knowledges/plan.md";
const HYP = "knowledges/hypothesis.md";
const OBS = "knowledges/observation.md";
const REPORT = "knowledges/stage-1.md";
const FFV = "projects/p/experiments/porosity/knowledges/ffv.md";
const WATER = "projects/p/experiments/water-network/knowledges/water.md";
const REVISED = "knowledges/plan-rev2.md";

/** The shape of ~/work/pbix-aem: documents derived from the Plan, findings filed under experiments. */
const graph: KnowledgeGraph = {
  nodes: [
    node(PLAN, "Plan", "PBIX AEM modeling plan", "How do crosslinks change free volume?"),
    node(HYP, "Hypothesis", "hypothesis"),
    node(OBS, "Observation", "observation"),
    node(REPORT, "Report", "Stage 1 equilibrated"),
    node(FFV, "Finding", "ffv-psd-dry-wet", "Dry FFV rises with crosslinking"),
    node(WATER, "Finding", "water-network-80c"),
    node(REVISED, "Plan", "Plan, revision 2"),
    node("knowledges/brief.md", "Note", "brief"),
  ],
  edges: [
    link(HYP, PLAN),
    link(OBS, PLAN),
    link(REPORT, PLAN),
    link(REPORT, FFV),
    link(REVISED, PLAN, "supersedes"),
    link(REVISED, FFV),
    link(FFV, "molab:asset/01a", "derived_from", "ref"),
    link(FFV, "https://doi.org/10.1/x", "cites", "external"),
    link(FFV, "knowledges/gone.md", "references", "missing"),
    link("knowledges/brief.md", PLAN),
    link(FFV, FFV, "references"),
    link(REPORT, PLAN),
  ],
};
describe("research map", () => {
  const map = buildResearchMap(graph);
  const at = (id: string) => map.nodes.find((entry) => entry.id === id)!;
  const has = (from: string, to: string, role: string) =>
    map.edges.some((edge) => edge.from === from && edge.to === to && edge.role === role);

  it("makes every research document a node, and nothing that is not a knowledge document", () => {
    expect(map.nodes.map((entry) => entry.id)).toEqual([
      PLAN,
      HYP,
      OBS,
      REPORT,
      FFV,
      WATER,
      REVISED,
    ]);
    expect(at(PLAN)).toMatchObject({
      cls: "Plan",
      title: "PBIX AEM modeling plan",
      excerpt: "How do crosslinks change free volume?",
    });
    expect(at(FFV).host).toBe("porosity");
    expect(at(PLAN).host).toBeNull();
  });

  it("shows a document's display title, and its name only when it has none", () => {
    const titled = buildResearchMap({
      nodes: [
        node("a.md", "Hypothesis", "h-dry-ffv", "", "交联降低干态自由体积"),
        node("b.md", "Finding", "ffv-psd"),
      ],
      edges: [],
    });
    expect(titled.nodes.map((entry) => entry.title)).toEqual(["交联降低干态自由体积", "ffv-psd"]);
  });

  it("breaks a long column into shorter ones, one class after another, without moving anything past what refers to it", () => {
    const many = [...Array(9).keys()].map((index) =>
      node(`h${index}.md`, "Hypothesis", `h${index}`),
    );
    const observations = [...Array(5).keys()].map((index) =>
      node(`o${index}.md`, "Observation", `o${index}`),
    );
    const wide = buildResearchMap({
      nodes: [
        node("plan.md", "Plan", "plan"),
        ...observations,
        ...many,
        node("finding.md", "Finding", "finding"),
      ],
      edges: [...many, ...observations]
        .map((doc) => link(doc.relPath, "plan.md"))
        .concat([link("finding.md", "h0.md", "supports"), link("finding.md", "o0.md")]),
    });
    const laid = layoutKnowledgeMap(wide);
    const x = (id: string) => laid.find((entry) => entry.id === id)!.x;
    const perColumn = new Map<number, number>();
    for (const entry of laid) perColumn.set(entry.x, (perColumn.get(entry.x) ?? 0) + 1);
    expect(Math.max(...perColumn.values())).toBeLessThanOrEqual(6);
    // Hypotheses come before observations, and a class does not share a column with another unless both fit.
    expect(Math.max(...many.map((doc) => x(doc.relPath)))).toBeLessThan(
      Math.min(...observations.map((doc) => x(doc.relPath))),
    );
    for (const edge of wide.edges) expect(x(edge.to)).toBeLessThan(x(edge.from));
  });

  it("draws an arrow for every link between two nodes, in the direction of the reference, with the link's role", () => {
    expect(has(HYP, PLAN, "derived_from")).toBe(true);
    expect(has(REPORT, FFV, "derived_from")).toBe(true);
    expect(has(REVISED, PLAN, "supersedes")).toBe(true);
    expect(has(PLAN, HYP, "derived_from")).toBe(false);
    // Links from hidden documents, self-links and links that leave the map are not arrows; the same link twice is one arrow.
    expect(map.edges).toHaveLength(6);
    expect(map.edges.filter((edge) => edge.from === REPORT && edge.to === PLAN)).toHaveLength(1);
  });

  it("keeps a document's references that leave the map, for its preview", () => {
    expect(at(FFV).refs).toEqual([
      { target: "molab:asset/01a", role: "derived_from", kind: "ref" },
      { target: "https://doi.org/10.1/x", role: "cites", kind: "external" },
      { target: "knowledges/gone.md", role: "references", kind: "missing" },
    ]);
    expect(at(PLAN).refs).toEqual([]);
  });

  it("notes the experiment a document is filed under", () => {
    expect(at(FFV).note).toBe("Filed under porosity");
    expect(at(PLAN).note).toBe("");
  });

  it("reads a hypothesis's verdict from its fields, and the class default when they do not say", () => {
    const H = "knowledges/h-dry-ffv.md";
    const H_BARE = "knowledges/h-water-model.md";
    const reasoned = buildResearchMap(
      {
        nodes: [
          node(PLAN, "Plan", "plan"),
          node(H, "Hypothesis", "Crosslinking lowers dry FFV"),
          node(FFV, "Finding", "ffv"),
          node(H_BARE, "Hypothesis", "Flexible TIP3P suffices"),
        ],
        edges: [link(H, PLAN), link(FFV, H, "contradicts"), link(H_BARE, PLAN)],
      },
      { [H]: { verdict: "refuted" }, [H_BARE]: {} },
    );
    const state = (id: string) => reasoned.nodes.find((entry) => entry.id === id)!.state;
    expect(state(H)).toBe("refuted");
    // Fields that do not say are the class's default, as Molab reads it.
    expect(state(H_BARE)).toBe("open");
    expect(state(FFV)).toBeNull();
    expect(reasoned.edges).toContainEqual({ from: FFV, to: H, role: "contradicts" });
    // Evidence sits to the right of the claim it judges.
    const laid = layoutKnowledgeMap(reasoned);
    const x = (id: string) => laid.find((entry) => entry.id === id)!.x;
    expect(x(PLAN)).toBeLessThan(x(H));
    expect(x(H)).toBeLessThan(x(FFV));
    expect(foldedReferences(reasoned)).toEqual([false, false, false]);
  });

  it("does not mutate its input and is empty, not broken, for an empty workspace", () => {
    const before = JSON.stringify(graph);
    buildResearchMap(graph);
    expect(JSON.stringify(graph)).toBe(before);
    const empty = buildResearchMap({ nodes: [], edges: [] });
    expect(empty).toEqual({ nodes: [], edges: [] });
    expect(layoutKnowledgeMap(empty)).toEqual([]);
  });
});

describe("research map layout", () => {
  const map = buildResearchMap(graph);
  const placed = layoutKnowledgeMap(map);
  const at = (id: string) => placed.find((entry) => entry.id === id)!;

  it("places every node once, each to the right of everything it rests on", () => {
    expect(placed.map((entry) => entry.id).sort()).toEqual(
      map.nodes.map((entry) => entry.id).sort(),
    );
    for (const edge of map.edges)
      expect([edge.from, edge.to, at(edge.to).x < at(edge.from).x]).toEqual([
        edge.from,
        edge.to,
        true,
      ]);
  });

  it("does not let a mention move a document: the plan stays leftmost though it cites literature", () => {
    const cited = buildResearchMap({
      nodes: [
        node("plan.md", "Plan", "plan"),
        node("paper.md", "Literature", "paper"),
        node("finding.md", "Finding", "finding"),
      ],
      edges: [
        link("plan.md", "paper.md", "cites"),
        link("finding.md", "plan.md"),
        link("finding.md", "paper.md", "cites"),
      ],
    });
    const laid = layoutKnowledgeMap(cited);
    const x = (id: string) => laid.find((entry) => entry.id === id)!.x;
    expect(x("plan.md")).toBe(0);
    expect(x("finding.md")).toBeGreaterThan(x("plan.md"));
    // A document nothing rests on, and that rests on nothing, sits in the first column.
    expect(x("paper.md")).toBe(0);
  });

  it("never overlaps two nodes", () => {
    for (const a of placed)
      for (const b of placed) {
        if (a.id >= b.id) continue;
        const apart =
          a.x + a.width <= b.x ||
          b.x + b.width <= a.x ||
          a.y + a.height <= b.y ||
          b.y + b.height <= a.y;
        expect([a.id, b.id, apart]).toEqual([a.id, b.id, true]);
      }
  });

  it("gives each class of document its own shape", () => {
    expect(at(PLAN).shape).toBe("question");
    expect(at(HYP).shape).toBe("card");
    expect(at(FFV).shape).toBe("pill");
  });

  it("folds away a reference another chain of references already implies, and every mere mention", () => {
    const folded = foldedReferences(map);
    const state = (from: string, to: string) =>
      folded[map.edges.findIndex((edge) => edge.from === from && edge.to === to)];
    // The report rests on the finding and on the plan directly: both are its only route to each, so both stay.
    expect(state(REPORT, FFV)).toBe(false);
    expect(state(HYP, PLAN)).toBe(false);
    expect(state(REVISED, PLAN)).toBe(false);
    const chain = buildResearchMap({
      nodes: [
        node("plan.md", "Plan", "plan"),
        node("finding.md", "Finding", "finding"),
        node("report.md", "Report", "report"),
        node("paper.md", "Literature", "paper"),
      ],
      edges: [
        link("finding.md", "plan.md"),
        link("report.md", "finding.md"),
        link("report.md", "plan.md"),
        link("finding.md", "paper.md", "cites"),
        link("report.md", "paper.md", "references"),
      ],
    });
    expect(
      chain.edges.map((edge, index) => [edge.from, edge.to, foldedReferences(chain)[index]]),
    ).toEqual([
      ["finding.md", "plan.md", false],
      ["report.md", "finding.md", false],
      ["report.md", "plan.md", true],
      ["finding.md", "paper.md", true],
      ["report.md", "paper.md", true],
    ]);
  });

  it("keeps only the nearest column's arrows when more than six documents rest on the same one", () => {
    const hypotheses = [...Array(5).keys()].map((index) =>
      node(`h${index}.md`, "Hypothesis", `h${index}`),
    );
    const observations = [...Array(4).keys()].map((index) =>
      node(`o${index}.md`, "Observation", `o${index}`),
    );
    const hub = buildResearchMap({
      nodes: [node("plan.md", "Plan", "plan"), ...hypotheses, ...observations],
      edges: [...hypotheses, ...observations].map((doc) => link(doc.relPath, "plan.md")),
    });
    const folded = foldedReferences(hub);
    expect(hub.edges.filter((_edge, index) => !folded[index]).map((edge) => edge.from)).toEqual(
      hypotheses.map((doc) => doc.relPath),
    );
    // Six or fewer is not a crowd: every arrow stays.
    const few = buildResearchMap({
      nodes: [node("plan.md", "Plan", "plan"), ...hypotheses],
      edges: hypotheses.map((doc) => link(doc.relPath, "plan.md")),
    });
    expect(foldedReferences(few)).toEqual(hypotheses.map(() => false));
  });

  it("does not fold both halves of a circle", () => {
    const circular = buildResearchMap({
      nodes: [node("a.md", "Finding", "a"), node("b.md", "Finding", "b")],
      edges: [link("a.md", "b.md"), link("b.md", "a.md")],
    });
    expect(foldedReferences(circular)).toEqual([false, false]);
  });

  it("terminates when documents refer to each other in a circle", () => {
    const circular = buildResearchMap({
      nodes: [node("a.md", "Finding", "a"), node("b.md", "Finding", "b")],
      edges: [link("a.md", "b.md"), link("b.md", "a.md")],
    });
    const laid = layoutKnowledgeMap(circular);
    expect(laid.map((entry) => entry.id).sort()).toEqual(["a.md", "b.md"]);
    expect(new Set(laid.map((entry) => entry.x)).size).toBe(2);
  });
});
