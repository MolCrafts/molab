import type { MapNode, ResearchMap } from "./research-map";

export const RELATION_GROUPS = [
  {
    label: "Lineage",
    roles: [
      { value: "derived_from", label: "Derived from" },
      { value: "supersedes", label: "Supersedes" },
    ],
  },
  {
    label: "Evidence",
    roles: [
      { value: "supports", label: "Supports" },
      { value: "contradicts", label: "Contradicts" },
    ],
  },
  {
    label: "Citations & records",
    roles: [
      { value: "cites", label: "Cites" },
      { value: "records", label: "Records" },
      { value: "references", label: "References" },
    ],
  },
] as const;
export const RELATION_ROLES: readonly string[] = RELATION_GROUPS.flatMap((group) =>
  group.roles.map((role) => role.value),
);

export interface GraphViewState {
  hiddenClasses: string[];
  hiddenStates: Record<string, string[]>;
  hiddenNodes: string[];
  /** null includes every role, including roles added by future plugins; [] hides all edges. */
  roles: string[] | null;
  focus: {
    anchor: string;
    direction: "incoming" | "outgoing" | "both";
    depth: 1 | 2 | "all";
  } | null;
}
export const DEFAULT_GRAPH_VIEW: GraphViewState = {
  hiddenClasses: [],
  hiddenStates: {},
  hiddenNodes: [],
  roles: null,
  focus: null,
};
export type HiddenReason = "type" | "state" | "manual" | "scope";

/** Relation traversal precedes node visibility. Hiding an intermediate document
 * never hides its descendants implicitly and never creates a replacement edge. */
export function projectGraphView(map: Pick<ResearchMap, "nodes" | "edges">, view: GraphViewState) {
  const ids = new Set(map.nodes.map((node) => node.id));
  const edges = map.edges.filter(
    (edge) =>
      ids.has(edge.from) &&
      ids.has(edge.to) &&
      (view.roles === null || view.roles.includes(edge.role)),
  );
  const focus = view.focus && ids.has(view.focus.anchor) ? view.focus : null;
  const scope = focus ? new Set([focus.anchor]) : ids;
  if (focus) {
    const neighbours = new Map<string, Set<string>>();
    for (const edge of edges) {
      for (const [from, to] of [
        ...(focus.direction !== "incoming" ? [[edge.from, edge.to]] : []),
        ...(focus.direction !== "outgoing" ? [[edge.to, edge.from]] : []),
      ]) {
        if (!neighbours.has(from)) neighbours.set(from, new Set());
        neighbours.get(from)?.add(to);
      }
    }
    const queue = [{ id: focus.anchor, depth: 0 }];
    for (let index = 0; index < queue.length; index += 1) {
      const current = queue[index];
      if (focus.depth !== "all" && current.depth >= focus.depth) continue;
      for (const id of neighbours.get(current.id) ?? []) {
        if (scope.has(id)) continue;
        scope.add(id);
        queue.push({ id, depth: current.depth + 1 });
      }
    }
  }
  const visible = new Set<string>();
  const hidden = new Map<string, HiddenReason[]>();
  for (const node of map.nodes) {
    const reasons: HiddenReason[] = [];
    if (node.id !== focus?.anchor) {
      if (view.hiddenClasses.includes(node.cls)) reasons.push("type");
      const state = node.state ?? node.status;
      if (state && view.hiddenStates[node.cls]?.includes(state)) reasons.push("state");
      if (view.hiddenNodes.includes(node.id)) reasons.push("manual");
      if (!scope.has(node.id)) reasons.push("scope");
    }
    if (reasons.length) hidden.set(node.id, reasons);
    else visible.add(node.id);
  }
  return {
    visible,
    hidden,
    edges: edges.filter((edge) => visible.has(edge.from) && visible.has(edge.to)),
  };
}

/** Explicit search recovery changes only the conditions hiding this result. */
export function revealGraphNode(
  map: Pick<ResearchMap, "nodes" | "edges">,
  view: GraphViewState,
  node: MapNode,
): GraphViewState {
  const reasons = projectGraphView(map, view).hidden.get(node.id) ?? [];
  if (!reasons.length) return view;
  const state = node.state ?? node.status;
  return {
    ...view,
    hiddenClasses: view.hiddenClasses.filter((cls) => cls !== node.cls),
    hiddenStates: {
      ...view.hiddenStates,
      [node.cls]: (view.hiddenStates[node.cls] ?? []).filter((value) => value !== state),
    },
    hiddenNodes: view.hiddenNodes.filter((id) => id !== node.id),
    focus: reasons.includes("scope") ? null : view.focus,
  };
}
