/**
 * Pure, React-free, IO-free builders for the Knowledge document shell:
 *
 * - {@link buildDocTree} groups documents by the server-reported `hostPath`.
 *   The empty host is the knowledge-base group; every other host is one flat
 *   group. Documents are never nested.
 * - {@link buildOutline} extracts a document's H1–H3 headings, in order,
 *   ignoring H4+ and any `#` lines inside fenced code blocks.
 */

export interface DocEntry {
  /** Workspace-relative path of the markdown file. */
  relPath: string;
  /** Display name. */
  name: string;
  /** Workspace-relative host directory. `""` is the workspace root. */
  hostPath: string;
}

export type DocTreeNodeKind = "group" | "doc";

export interface DocTreeNode {
  /** Stable id: the document relPath, `group:knowledge-base`, or `group:host:<hostPath>`. */
  id: string;
  /** Display label. */
  name: string;
  kind: DocTreeNodeKind;
  /** The document path — set only for `kind === "doc"`. */
  relPath: string | null;
  /** Workspace-relative host. `""` is the workspace root. */
  hostPath: string;
  children: DocTreeNode[];
}

export interface OutlineHeading {
  level: 1 | 2 | 3;
  text: string;
  slug: string;
}

export const KB_GROUP_ID = "group:knowledge-base";
const KB_GROUP_NAME = "Knowledge base";

/**
 * Group documents by `hostPath`. The workspace root (`""`) is the knowledge-base
 * group and leads. Every other host is `group:host:<hostPath>`. Children are
 * flat documents. Empty input yields an empty tree.
 */
export const buildDocTree = (entries: DocEntry[]): DocTreeNode[] => {
  const groups = new Map<string, DocTreeNode>();

  for (const entry of entries) {
    const hostPath = entry.hostPath;
    const id = hostPath === "" ? KB_GROUP_ID : `group:host:${hostPath}`;
    let group = groups.get(id);
    if (!group) {
      group = {
        id,
        name: hostPath === "" ? KB_GROUP_NAME : hostPath,
        kind: "group",
        relPath: null,
        hostPath,
        children: [],
      };
      groups.set(id, group);
    }
    group.children.push({
      id: entry.relPath,
      name: entry.name,
      kind: "doc",
      relPath: entry.relPath,
      hostPath,
      children: [],
    });
  }

  const ordered = [...groups.values()].sort((a, b) => {
    if (a.hostPath === "" && b.hostPath !== "") return -1;
    if (b.hostPath === "" && a.hostPath !== "") return 1;
    return a.hostPath.localeCompare(b.hostPath);
  });
  for (const group of ordered) {
    group.children.sort((a, b) => a.name.localeCompare(b.name));
  }
  return ordered;
};

const FENCE_RE = /^[ \t]{0,3}(?:`{3,}|~{3,})/;
const HEADING_RE = /^[ \t]{0,3}(#{1,6})[ \t]+(.*)$/;

/** GitHub-flavored slug: lowercase, punctuation stripped, spaces → hyphens. */
const slugify = (text: string): string =>
  text
    .toLowerCase()
    .replace(/[^\w\s-]/g, "")
    .trim()
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-");

/**
 * Extract a document's H1–H3 headings in document order. H4+ headings are
 * skipped, and any `#` line inside a fenced code block (``` or ~~~) is ignored.
 */
export const buildOutline = (markdown: string): OutlineHeading[] => {
  const headings: OutlineHeading[] = [];
  let inFence = false;

  for (const line of markdown.split("\n")) {
    if (FENCE_RE.test(line)) {
      inFence = !inFence;
      continue;
    }
    if (inFence) continue;

    const match = line.match(HEADING_RE);
    if (!match) continue;
    const level = match[1].length;
    if (level > 3) continue;

    // Strip an optional ATX closing sequence (`## Heading ##`).
    const text = match[2].replace(/[ \t]+#+[ \t]*$/, "").trim();
    if (!text) continue;
    headings.push({ level: level as 1 | 2 | 3, text, slug: slugify(text) });
  }

  return headings;
};

export type HostKind = "workspace" | "project" | "experiment" | "run";

export interface HostOption {
  hostPath: string;
  kind: HostKind;
  label: string;
  disabled: boolean;
}

/**
 * Hosts a document can move to. The first option is the workspace root.
 * Every other option copies the entity's server `path` and is sorted by it.
 * The document's current host is disabled. No path is composed.
 */
export const listHostOptions = (
  entities: {
    projects: ReadonlyArray<{ path: string; name: string }>;
    experiments: ReadonlyArray<{ path: string; name: string }>;
    runs: ReadonlyArray<{ path: string; name: string }>;
  },
  currentHostPath: string,
): HostOption[] => {
  const rest: Array<Omit<HostOption, "disabled">> = [
    ...entities.projects.map((item) => ({
      hostPath: item.path,
      kind: "project" as const,
      label: item.name,
    })),
    ...entities.experiments.map((item) => ({
      hostPath: item.path,
      kind: "experiment" as const,
      label: item.name,
    })),
    ...entities.runs.map((item) => ({
      hostPath: item.path,
      kind: "run" as const,
      label: item.name,
    })),
  ];
  rest.sort((a, b) => a.hostPath.localeCompare(b.hostPath));
  return [
    {
      hostPath: "",
      kind: "workspace",
      label: "Workspace root",
      disabled: currentHostPath === "",
    },
    ...rest.map((item) => ({ ...item, disabled: item.hostPath === currentHostPath })),
  ];
};
