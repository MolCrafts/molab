import { describe, expect, it } from "@rstest/core";
import type { GraphViewState } from "./graph-view";
import { DEFAULT_GRAPH_VIEW, projectGraphView, revealGraphNode } from "./graph-view";
import type { MapNode } from "./research-map";

const node = (id: string, cls = "Finding", state: string | null = null): MapNode => ({
  id,
  cls,
  state,
  title: id,
  status: null,
  excerpt: "",
  note: "",
  host: null,
  refs: [],
});
const map = {
  nodes: [
    node("a", "Plan"),
    node("b"),
    node("c", "Decision", "open"),
    node("d", "Hypothesis", "open"),
    node("isolated"),
  ],
  edges: [
    { from: "b", to: "a", role: "derived_from" },
    { from: "c", to: "b", role: "derived_from" },
    { from: "b", to: "d", role: "supports" },
    { from: "b", to: "d", role: "cites" },
  ],
};
const view = (patch: Partial<GraphViewState> = {}): GraphViewState => ({
  ...DEFAULT_GRAPH_VIEW,
  ...patch,
});
const shown = (v: GraphViewState) => [...projectGraphView(map, v).visible].sort();

describe("orthogonal graph view", () => {
  it("defaults to every node, including isolated nodes, and every relation", () => {
    expect(shown(view())).toEqual(["a", "b", "c", "d", "isolated"]);
    expect(projectGraphView(map, view()).edges).toEqual(map.edges);
  });
  it("role filters leave nodes alone, including an empty role selection", () => {
    expect(shown(view({ roles: [] }))).toEqual(shown(view()));
    expect(projectGraphView(map, view({ roles: [] })).edges).toEqual([]);
    expect(
      projectGraphView(map, view({ roles: ["supports"] })).edges.map((edge) => edge.role),
    ).toEqual(["supports"]);
  });
  it("keeps state filters local to their class and intersects manual/type filters", () => {
    expect(shown(view({ hiddenStates: { Decision: ["open"] } }))).toContain("d");
    expect(
      shown(
        view({ hiddenStates: { Decision: ["open"] }, hiddenClasses: ["Plan"], hiddenNodes: ["b"] }),
      ),
    ).toEqual(["d", "isolated"]);
  });
  it("traverses relation direction and bounded depth from a fixed anchor", () => {
    expect(shown(view({ focus: { anchor: "a", direction: "incoming", depth: 1 } }))).toEqual([
      "a",
      "b",
    ]);
    expect(shown(view({ focus: { anchor: "a", direction: "incoming", depth: 2 } }))).toEqual([
      "a",
      "b",
      "c",
    ]);
    expect(shown(view({ focus: { anchor: "a", direction: "outgoing", depth: "all" } }))).toEqual([
      "a",
    ]);
    expect(
      shown(
        view({ roles: ["derived_from"], focus: { anchor: "a", direction: "both", depth: "all" } }),
      ),
    ).toEqual(["a", "b", "c"]);
  });
  it("hidden intermediates do not hide reachable descendants or synthesize edges", () => {
    const v = view({
      hiddenNodes: ["b"],
      roles: ["derived_from"],
      focus: { anchor: "a", direction: "incoming", depth: "all" },
    });
    expect(shown(v)).toEqual(["a", "c"]);
    expect(projectGraphView(map, v).edges).toEqual([]);
  });
  it("pins the focus anchor even if its type/state/manual visibility is excluded", () => {
    expect(
      shown(
        view({
          hiddenClasses: ["Decision"],
          hiddenStates: { Decision: ["open"] },
          hiddenNodes: ["c"],
          roles: [],
          focus: { anchor: "c", direction: "both", depth: 1 },
        }),
      ),
    ).toEqual(["c"]);
  });
  it("handles cycles and stale anchors without dropping the project graph", () => {
    const cyclic = { ...map, edges: [...map.edges, { from: "a", to: "c", role: "derived_from" }] };
    expect(
      [
        ...projectGraphView(
          cyclic,
          view({ focus: { anchor: "a", direction: "both", depth: "all" } }),
        ).visible,
      ].sort(),
    ).toEqual(["a", "b", "c", "d"]);
    expect(shown(view({ focus: { anchor: "deleted", direction: "both", depth: 1 } }))).toEqual(
      shown(view()),
    );
  });
  it("search recovery preserves unrelated filters and only leaves focus when needed", () => {
    const v = view({
      hiddenClasses: ["Decision", "Plan"],
      hiddenStates: { Decision: ["open", "made"], Hypothesis: ["open"] },
      hiddenNodes: ["c", "b"],
      roles: ["supports"],
      focus: { anchor: "a", direction: "outgoing", depth: 1 },
    });
    const recovered = revealGraphNode(map, v, map.nodes[2]);
    expect(recovered).toMatchObject({
      hiddenClasses: ["Plan"],
      hiddenStates: { Decision: ["made"], Hypothesis: ["open"] },
      hiddenNodes: ["b"],
      roles: ["supports"],
      focus: null,
    });
    expect(projectGraphView(map, recovered).visible.has("c")).toBe(true);
    expect(v.hiddenNodes).toEqual(["c", "b"]);
  });
  it("preserves only enabled roles when multiple relations share endpoints", () => {
    const edges = projectGraphView(map, view({ roles: ["supports"] })).edges;
    expect(edges.map((edge) => edge.role)).toEqual(["supports"]);
    expect(
      projectGraphView(map, view())
        .edges.filter((edge) => edge.to === "d")
        .map((edge) => edge.role),
    ).toEqual(["supports", "cites"]);
  });
});
