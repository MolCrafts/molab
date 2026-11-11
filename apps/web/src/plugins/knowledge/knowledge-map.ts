import type { KnowledgeGraphResponse } from "@/api/generated/models/KnowledgeGraphResponse";
import { knowledgeClassOf } from "./knowledgeClass";
import { foldedReferences, layoutKnowledgeMap } from "./map-layout";
import { planningView } from "./planningModel";
import { buildResearchMap, type Campaign, type ResearchMap } from "./research-map";

/** A project's context includes its own documents and the connected workspace
 * knowledge they rely on (in either direction). Never cross into another
 * project through a shared workspace plan; unlinked workspace notes stay out. */
export const projectKnowledgeMap = (graph: KnowledgeGraphResponse, projectPath: string) => {
  const prefix = `${projectPath.replace(/\/+$/, "")}/`;
  const local = new Set(
    graph.nodes
      .filter((node) => projectPath !== "" && node.relPath.startsWith(prefix))
      .map((node) => node.relPath),
  );
  const eligible = new Set(
    graph.nodes
      .filter(
        (node) =>
          local.has(node.relPath) ||
          node.hostPath === "" ||
          (node.hostPath === undefined && node.relPath.startsWith("knowledges/")),
      )
      .map((node) => node.relPath),
  );
  const neighbours = new Map<string, Set<string>>();
  for (const edge of graph.edges) {
    if (edge.kind !== "document" || !eligible.has(edge.source) || !eligible.has(edge.target))
      continue;
    if (!neighbours.has(edge.source)) neighbours.set(edge.source, new Set());
    if (!neighbours.has(edge.target)) neighbours.set(edge.target, new Set());
    neighbours.get(edge.source)?.add(edge.target);
    neighbours.get(edge.target)?.add(edge.source);
  }
  const ids = new Set(local);
  const queue = [...local];
  for (let index = 0; index < queue.length; index += 1) {
    for (const id of neighbours.get(queue[index]) ?? []) {
      if (ids.has(id)) continue;
      ids.add(id);
      queue.push(id);
    }
  }
  const nodes = graph.nodes
    .filter((node) => ids.has(node.relPath))
    .map((node) => ({ ...node, id: node.relPath, cls: knowledgeClassOf(node) }));
  const seen = new Set<string>();
  const edges = graph.edges.flatMap((edge) => {
    const key = JSON.stringify([edge.source, edge.target, edge.role]);
    if (
      edge.kind !== "document" ||
      !ids.has(edge.source) ||
      !ids.has(edge.target) ||
      edge.source === edge.target ||
      seen.has(key)
    )
      return [];
    seen.add(key);
    return [{ from: edge.source, to: edge.target, role: edge.role }];
  });
  return { nodes, edges };
};

/** Adapt Molab's cached planning records to the original Tack map model.
 * References leaving this project stay with their document, never disappear. */
export const projectResearchMap = (
  graph: KnowledgeGraphResponse,
  projectPath: string,
  records: Readonly<Record<string, Record<string, unknown>>>,
  unreadable: Campaign["unreadable"] = [],
): ResearchMap => {
  const scope = projectKnowledgeMap(graph, projectPath);
  const ids = new Set(scope.nodes.map((node) => node.id));
  const campaign: Campaign = {
    plans: [],
    roadmaps: [],
    todos: [],
    milestones: [],
    unreadable: [...unreadable],
  };
  for (const node of scope.nodes) {
    if (node.cls === "Plan") campaign.plans.push({ path: node.id, excerpt: node.excerpt });
    const view = planningView(node.cls, records[node.id]);
    if (view?.kind === "roadmap")
      campaign.roadmaps.push({
        path: node.id,
        stages: view.stages.map((stage) => ({ ...stage, depends_on: stage.dependsOn })),
      });
    if (view?.kind === "todo") campaign.todos.push({ path: node.id, items: view.items });
    if (view?.kind === "milestone")
      campaign.milestones.push({
        path: node.id,
        stage: view.stage,
        status: view.status,
        criterion: view.criterion,
      });
  }
  return buildResearchMap(
    { nodes: scope.nodes, edges: graph.edges.filter((edge) => ids.has(edge.source)) },
    campaign,
    records,
    new Set(scope.nodes.map((node) => node.cls)),
  );
};

/** Tack's graph conversion retains roles and neighbours. A single FlowGram
 * line per pair carries all the pair's roles; no reference is dropped. */
export const toResearchGraph = (map: ResearchMap) => {
  const placed = new Map(layoutKnowledgeMap(map).map((node) => [node.id, node]));
  const index = new Map(map.nodes.map((node, position) => [node.id, position]));
  const folded = foldedReferences(map);
  const pairs = new Map<
    string,
    { from: string; to: string; roles: Set<string>; folded: boolean }
  >();
  map.edges.forEach((edge, position) => {
    const key = JSON.stringify([edge.from, edge.to]);
    const pair = pairs.get(key) ?? {
      from: edge.from,
      to: edge.to,
      roles: new Set<string>(),
      folded: true,
    };
    pair.roles.add(edge.role);
    pair.folded &&= folded[position];
    pairs.set(key, pair);
  });
  const links = new Map(map.nodes.map((node) => [node.id, new Set([node.id])]));
  for (const edge of map.edges) {
    links.get(edge.from)?.add(edge.to);
    links.get(edge.to)?.add(edge.from);
  }
  const roles = new Map(
    [...pairs.values()].map((pair) => [
      JSON.stringify([pair.from, pair.to]),
      `${[...pair.roles].map((role) => `tw-role-${role}`).join(" ")} tw-edge-a${index.get(pair.from)} tw-edge-b${index.get(pair.to)} ${pair.folded ? "tw-edge-folded" : ""}`,
    ]),
  );
  return {
    graph: {
      nodes: map.nodes.flatMap((node) => {
        const at = placed.get(node.id);
        return at
          ? [{ id: node.id, type: at.shape, meta: { position: { x: at.x, y: at.y } }, data: node }]
          : [];
      }),
      edges: [...pairs.values()]
        .filter((edge) => placed.has(edge.from) && placed.has(edge.to))
        .map((edge) => ({ sourceNodeID: edge.from, targetNodeID: edge.to })),
    },
    roles,
    links,
    index,
    foldedCount: folded.filter(Boolean).length,
  };
};

export interface LineageEntry {
  id: string;
  depth: number;
  /** The preceding document on a shortest provenance path. */
  via: string;
  role: string;
}

/** Origins and dependants follow provenance/revisions only. Evidence and
 * citations remain direct semantic links; they do not imply derivation.
 * Breadth-first traversal chooses shortest paths and terminates on cycles. */
export const knowledgeLineage = (graph: KnowledgeGraphResponse, path: string) => {
  const ids = new Set(graph.nodes.map((node) => node.relPath));
  const outgoing = new Map<string, { id: string; role: string }[]>();
  const incoming = new Map<string, { id: string; role: string }[]>();
  for (const edge of graph.edges) {
    if (
      edge.kind !== "document" ||
      !["derived_from", "supersedes"].includes(edge.role) ||
      !ids.has(edge.source) ||
      !ids.has(edge.target)
    )
      continue;
    outgoing.set(edge.source, [
      ...(outgoing.get(edge.source) ?? []),
      { id: edge.target, role: edge.role },
    ]);
    incoming.set(edge.target, [
      ...(incoming.get(edge.target) ?? []),
      { id: edge.source, role: edge.role },
    ]);
  }
  const walk = (adjacency: typeof outgoing): LineageEntry[] => {
    if (!ids.has(path)) return [];
    const seen = new Set([path]);
    const queue = [{ id: path, depth: 0 }];
    const entries: LineageEntry[] = [];
    for (let index = 0; index < queue.length; index += 1) {
      const current = queue[index];
      for (const next of adjacency.get(current.id) ?? []) {
        if (seen.has(next.id)) continue;
        seen.add(next.id);
        const entry = { ...next, depth: current.depth + 1, via: current.id };
        entries.push(entry);
        queue.push(entry);
      }
    }
    return entries;
  };
  return { ancestors: walk(outgoing), descendants: walk(incoming) };
};
