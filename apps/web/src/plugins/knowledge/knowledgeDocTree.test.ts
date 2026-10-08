import { describe, expect, it } from "@rstest/core";
import {
  buildDocTree,
  buildOutline,
  type DocEntry,
  type DocTreeNode,
  KB_GROUP_ID,
  listHostOptions,
} from "@/plugins/knowledge/knowledgeDocTree";

/** Depth-first search for the first node whose `relPath` matches. */
const findByRelPath = (nodes: DocTreeNode[], relPath: string): DocTreeNode | null => {
  for (const node of nodes) {
    if (node.relPath === relPath) return node;
    const hit = findByRelPath(node.children, relPath);
    if (hit) return hit;
  }
  return null;
};

describe("buildDocTree", () => {
  it("groups by hostPath, knowledge base first, documents flat", () => {
    const entries: DocEntry[] = [
      { relPath: "knowledges/a.md", hostPath: "", name: "A" },
      { relPath: "projects/p/knowledges/b.md", hostPath: "projects/p", name: "B" },
    ];

    const tree = buildDocTree(entries);

    expect(tree).toHaveLength(2);
    expect(tree[0]?.id).toBe(KB_GROUP_ID);
    expect(tree[0]?.hostPath).toBe("");
    expect(tree[1]?.hostPath).toBe("projects/p");
    expect(tree[1]?.id).toBe("group:host:projects/p");
    expect(tree.every((group) => group.children.every((child) => child.kind === "doc"))).toBe(true);
    expect(findByRelPath(tree, "knowledges/a.md")?.kind).toBe("doc");
    expect(findByRelPath(tree, "projects/p/knowledges/b.md")?.kind).toBe("doc");
  });

  it("yields an empty tree for empty input", () => {
    expect(buildDocTree([])).toEqual([]);
  });
});

describe("buildOutline (ac-002)", () => {
  it("returns ordered H1–H3 headings in document order", () => {
    const md = ["# Title", "intro", "## Section", "### Sub", "## Another"].join("\n");

    expect(buildOutline(md)).toEqual([
      { level: 1, text: "Title", slug: "title" },
      { level: 2, text: "Section", slug: "section" },
      { level: 3, text: "Sub", slug: "sub" },
      { level: 2, text: "Another", slug: "another" },
    ]);
  });

  it("skips H4+ headings", () => {
    const md = ["# A", "#### D", "##### E", "###### F", "## B"].join("\n");

    expect(buildOutline(md).map((h) => h.text)).toEqual(["A", "B"]);
    expect(buildOutline(md).every((h) => h.level <= 3)).toBe(true);
  });

  it("ignores '#' lines inside fenced code blocks", () => {
    const md = [
      "# Real",
      "```py",
      "# not a heading",
      "## also not a heading",
      "```",
      "## After",
    ].join("\n");

    expect(buildOutline(md)).toEqual([
      { level: 1, text: "Real", slug: "real" },
      { level: 2, text: "After", slug: "after" },
    ]);
  });

  it("returns an empty outline for a heading-free document", () => {
    expect(buildOutline("plain text\nmore text\n")).toEqual([]);
    expect(buildOutline("")).toEqual([]);
  });

  it("slugifies punctuation and whitespace", () => {
    expect(buildOutline("## Hello, World!")).toEqual([
      { level: 2, text: "Hello, World!", slug: "hello-world" },
    ]);
  });
});

describe("listHostOptions", () => {
  const entities = {
    projects: [{ path: "projects/peo", name: "PEO" }],
    experiments: [{ path: "projects/peo/experiments/tg", name: "Tg" }],
    runs: [{ path: "projects/peo/experiments/tg/runs/n=8", name: "n=8" }],
  };

  it("lists the workspace root first and disables the current host", () => {
    expect(listHostOptions(entities, "projects/peo")).toEqual([
      { hostPath: "", kind: "workspace", label: "Workspace root", disabled: false },
      { hostPath: "projects/peo", kind: "project", label: "PEO", disabled: true },
      {
        hostPath: "projects/peo/experiments/tg",
        kind: "experiment",
        label: "Tg",
        disabled: false,
      },
      {
        hostPath: "projects/peo/experiments/tg/runs/n=8",
        kind: "run",
        label: "n=8",
        disabled: false,
      },
    ]);
  });

  it("sorts hosts by path", () => {
    const options = listHostOptions(
      {
        projects: [
          { path: "projects/b", name: "B" },
          { path: "projects/a", name: "A" },
        ],
        experiments: [],
        runs: [],
      },
      "elsewhere",
    );
    expect(options.map((option) => option.hostPath)).toEqual(["", "projects/a", "projects/b"]);
  });

  it("disables the workspace root when the document already lives there", () => {
    const [root] = listHostOptions(entities, "");
    expect(root).toEqual({
      hostPath: "",
      kind: "workspace",
      label: "Workspace root",
      disabled: true,
    });
  });
});
