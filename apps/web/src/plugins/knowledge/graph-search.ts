import type { MapNode } from "./research-map";

/** Search only the project's existing map; filtering never changes its graph or lineage. */
export function searchResearchNodes(nodes: readonly MapNode[], query: string): MapNode[] {
  const words = query.normalize("NFKC").toLowerCase().trim().split(/\s+/u).filter(Boolean);
  return nodes.filter((node) => {
    const text = [
      node.title,
      node.cls,
      node.state,
      node.status,
      node.excerpt,
      node.note,
      node.host,
      node.id,
    ]
      .join(" ")
      .normalize("NFKC")
      .toLowerCase();
    return words.every((word) => text.includes(word));
  });
}
