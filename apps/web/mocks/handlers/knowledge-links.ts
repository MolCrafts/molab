/** Inline-link subset used by the offline showcase. Production resolution stays
 * in Concept.scan_links; no mock reverse index or second lineage store. */
import { KnowledgeGraphEdge } from "@/api/generated/models/KnowledgeGraphEdge";
import type { DocRelation } from "@/api/knowledge";
import { dirname, join, normalize } from "@/lib/workspace-path";

const roles = new Set<string>(Object.values(KnowledgeGraphEdge.role));
type MockNote = { relPath: string; body: string };

export interface ShowcaseLink extends DocRelation {
  start: number;
  end: number;
  labelStart: number;
  labelEnd: number;
}

/** Offsets always address the original narrative, including around code. */
export const showcaseKnowledgeLinks = (
  note: MockNote,
  notes: ReadonlyMap<string, MockNote>,
): ShowcaseLink[] => {
  const blank = (text: string) => text.replace(/[^\n]/g, " ");
  const prose = note.body
    .replace(/^ {0,3}(`{3,}|~{3,})[^\n]*\n[\s\S]*?^ {0,3}\1[^\n]*(?:\n|$)/gm, blank)
    .replace(/(?<!`)(`+)(?!`)[\s\S]+?(?<!`)\1(?!`)/g, blank);
  const links: ShowcaseLink[] = [];
  for (const match of prose.matchAll(
    /(?<!!)\[([^\]]*)\]\(\s*(<[^>]+>|[^\s)]+)(?:\s+["'][^\n]*?["'])?\s*\)/g,
  )) {
    const raw = match[2].replace(/^<|>$/g, "");
    if (!raw || raw.startsWith("#")) continue;
    const token = match[1].match(/^@(\w+)(?:\s|$)/)?.[1];
    const knownRole = token && roles.has(token);
    let role = (knownRole ? token : "references") as KnowledgeGraphEdge.role;
    const label = knownRole ? match[1].slice(token.length + 1).trimStart() : match[1];
    let target = raw;
    let kind: KnowledgeGraphEdge.kind;
    if (raw.startsWith("molab:")) kind = KnowledgeGraphEdge.kind.REF;
    else if (/^https?:\/\//.test(raw)) {
      kind = KnowledgeGraphEdge.kind.EXTERNAL;
      if (role !== "cites" && role !== "derived_from") role = KnowledgeGraphEdge.role.REFERENCES;
    } else {
      if (/^[a-z][\w+.-]*:/i.test(raw)) continue;
      const [path, fragment] = raw.split("#", 2);
      const decoded = decodeURIComponent(path);
      // Older fixtures spell paths from the workspace root; new fixtures use
      // normal document-relative links, as the production API does.
      const resolved = normalize(
        decoded.startsWith("/")
          ? decoded.slice(1)
          : notes.has(decoded) || /^(projects|knowledges|references)\//.test(decoded)
            ? decoded
            : join(dirname(note.relPath), decoded),
      );
      target = fragment === undefined ? resolved : `${resolved}#${fragment}`;
      kind = notes.has(resolved)
        ? KnowledgeGraphEdge.kind.DOCUMENT
        : KnowledgeGraphEdge.kind.MISSING;
    }
    links.push({
      id: links.length,
      target,
      role,
      label,
      kind,
      start: match.index,
      end: match.index + match[0].length,
      labelStart: match.index + 1,
      labelEnd: match.index + 1 + match[1].length,
    });
  }
  return links;
};

export const showcaseKnowledgeEdges = (
  notes: ReadonlyMap<string, MockNote>,
): KnowledgeGraphEdge[] => {
  const edges = new Map<string, KnowledgeGraphEdge>();
  for (const note of notes.values()) {
    for (const link of showcaseKnowledgeLinks(note, notes)) {
      const target =
        link.kind === "document" || link.kind === "missing"
          ? link.target.split("#")[0]
          : link.target;
      const edge = {
        source: note.relPath,
        target,
        role: link.role as KnowledgeGraphEdge.role,
        kind: link.kind as KnowledgeGraphEdge.kind,
      };
      edges.set(JSON.stringify([edge.source, target, edge.role, edge.kind]), edge);
    }
  }
  return [...edges.values()];
};
