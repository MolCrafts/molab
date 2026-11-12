/**
 * The research map a workbench draws. Every node is a knowledge document
 * Molab holds, and every arrow is a link one document makes to another, in
 * the direction of the reference and with the role the link declares. Molab's
 * knowledge graph is the model: the map adds no class, no relation and no node
 * of its own. Experiments, runs and assets are Molab's workflow and workspace;
 * a document's references to them are listed with the document, not drawn.
 */
import type { KnowledgeGraphResponse as KnowledgeGraph } from "@/api/generated/models/KnowledgeGraphResponse";

/** The classes that are research content. Plain notes are not drawn. */
export const MAP_CLASSES: ReadonlySet<string> = new Set([
  "Plan",
  "Hypothesis",
  "Observation",
  "Finding",
  "Report",
  "Literature",
]);

/**
 * The classes whose fields carry the state of the reasoning: the field that
 * holds it and what Molab reads when the document does not say.
 */
export const STATEFUL: Readonly<Record<string, { field: string; initial: string }>> = {
  Hypothesis: { field: "verdict", initial: "open" },
};

export interface MapNode {
  /** The document's workspace path. */
  id: string;
  /** The document's Molab class. */
  cls: string;
  title: string;
  excerpt: string;
  /** One recorded fact worth a line on the node. */
  note: string;
  /** A Hypothesis's verdict (`open`, `supported`, `refuted`, `unsettled`); null for every other class. */
  state: string | null;
  /** The experiment this document is filed under, by name. */
  host: string | null;
  /** The document's references that leave the map: workspace entities, URLs, files no document has. */
  refs: { target: string; role: string; kind: string }[];
}

export interface MapEdge {
  /** The document that makes the reference. */
  from: string;
  /** The document referred to. */
  to: string;
  /** The link's Molab role. */
  role: string;
}

export interface ResearchMap {
  nodes: MapNode[];
  edges: MapEdge[];
}

const EXPERIMENT_KNOWLEDGE = /(?:^|\/)experiments\/([^/]+)\/knowledges\//;

/**
 * Build the map from Molab's knowledge graph and the own fields of the documents
 * in {@link STATEFUL} classes, by path.
 */
export function buildResearchMap(
  graph: KnowledgeGraph,
  fields: Readonly<Record<string, Record<string, unknown>>> = {},
  classes: ReadonlySet<string> = MAP_CLASSES,
): ResearchMap {
  const docs = graph.nodes.filter((doc) => classes.has(doc.cls ?? "Note"));
  const shown = new Set(docs.map((doc) => doc.relPath));
  const onMap = (edge: KnowledgeGraph["edges"][number]): boolean =>
    edge.kind === "document" && shown.has(edge.target);

  const nodes: MapNode[] = docs.map((doc) => {
    const host = doc.relPath.match(EXPERIMENT_KNOWLEDGE)?.[1] ?? null;
    const stateful = STATEFUL[doc.cls ?? "Note"];
    const value = stateful === undefined ? undefined : fields[doc.relPath]?.[stateful.field];
    return {
      id: doc.relPath,
      cls: doc.cls ?? "Note",
      title: doc.title || doc.name,
      excerpt: doc.excerpt,
      note: host === null ? "" : `Filed under ${host}`,
      state:
        stateful === undefined
          ? null
          : typeof value === "string" && value !== ""
            ? value
            : stateful.initial,
      host,
      refs: graph.edges
        .filter((edge) => edge.source === doc.relPath && !onMap(edge))
        .map((edge) => ({ target: edge.target, role: edge.role, kind: edge.kind })),
    };
  });

  const links = graph.edges
    .filter((edge) => onMap(edge) && shown.has(edge.source) && edge.source !== edge.target)
    .map((edge) => ({ from: edge.source, to: edge.target, role: edge.role }));
  const key = (edge: MapEdge): string => `${edge.from}\n${edge.to}\n${edge.role}`;
  const edges = links.filter(
    (edge, index) => links.findIndex((other) => key(other) === key(edge)) === index,
  );

  return { nodes, edges };
}
