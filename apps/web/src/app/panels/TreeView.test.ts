import { describe, expect, it } from "@rstest/core";

import { type TreeNode, visiblePreorder } from "./TreeView";

const node = (id: string, selectionKey?: string, children?: TreeNode[]): TreeNode => ({
  id,
  label: id,
  selectionKey,
  children,
});

describe("visiblePreorder", () => {
  const tree: TreeNode[] = [
    node("p", "ws/p", [
      node("e", "ws/p/e", [node("r1", "ws/p/e/r1"), node("r2", "ws/p/e/r2")]),
      node("e2", "ws/p/e2"),
    ]),
  ];

  it("skips collapsed subtrees and nodes without selectionKey", () => {
    const expanded = new Set<string>(["p"]);
    expect(visiblePreorder(tree, expanded)).toEqual(["ws/p", "ws/p/e", "ws/p/e2"]);
  });

  it("includes expanded children in display order", () => {
    const expanded = new Set<string>(["p", "e"]);
    expect(visiblePreorder(tree, expanded)).toEqual([
      "ws/p",
      "ws/p/e",
      "ws/p/e/r1",
      "ws/p/e/r2",
      "ws/p/e2",
    ]);
  });

  it("omits a folder that has no selectionKey", () => {
    const root: TreeNode[] = [node("ws"), node("p", "ws/p")];
    expect(visiblePreorder(root, new Set())).toEqual(["ws/p"]);
  });
});
