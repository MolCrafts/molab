/**
 * Pure, React-free, IO-free builders for the Knowledge document shell:
 *
 * - {@link buildDocTree} nests hosts under their workspace, project and
 *   experiment, with files under the server-reported `hostPath`.
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
const KB_GROUP_NAME = "Workspace";

/** Workspace → project → experiment hosts, with files under their actual
 * host. Empty hosts remain visible. Parentage uses server paths, not ids. */
export const buildDocTree = (
  entries: DocEntry[],
  hosts: ReadonlyArray<{ path: string; name: string }> = [],
): DocTreeNode[] => {
  const groups = new Map<string, DocTreeNode>();
  for (const host of [
    { path: "", name: KB_GROUP_NAME },
    ...hosts,
    ...entries.map((entry) => ({ path: entry.hostPath, name: entry.hostPath })),
  ]) {
    if (groups.has(host.path)) continue;
    groups.set(host.path, {
      id: host.path === "" ? KB_GROUP_ID : `group:host:${host.path}`,
      name: host.name,
      kind: "group",
      relPath: null,
      hostPath: host.path,
      children: [],
    });
  }
  for (const entry of entries) {
    groups.get(entry.hostPath)?.children.push({
      id: entry.relPath,
      name: entry.name,
      kind: "doc",
      relPath: entry.relPath,
      hostPath: entry.hostPath,
      children: [],
    });
  }
  for (const group of groups.values()) {
    if (group.hostPath === "") continue;
    const parent = [...groups.values()]
      .filter(
        (candidate) =>
          candidate.hostPath === "" || group.hostPath.startsWith(`${candidate.hostPath}/`),
      )
      .sort((a, b) => b.hostPath.length - a.hostPath.length)[0];
    parent.children.push(group);
  }
  for (const group of groups.values()) {
    group.children.sort(
      (a, b) =>
        Number(b.kind === "group") - Number(a.kind === "group") || a.name.localeCompare(b.name),
    );
  }
  const root = groups.get("");
  return root ? [root] : [];
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
