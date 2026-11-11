/**
 * Flatten a `TreeView` node forest into the exact row sequence it renders.
 *
 * Virtualization needs a list, not a recursion: the windowing layer has to know
 * how many rows exist and what sits at index `i` without walking the tree. This
 * module is the pure half of that — no React, no DOM — so the traversal rules
 * (which node is visible, at what depth, whether its level reserves a chevron
 * column) can be tested directly. `TreeView` owns only the rendering.
 *
 * The output must mirror the recursive render one-for-one, including the
 * "expanded but childless" placeholder, which is a paragraph rather than a row
 * and therefore has its own height.
 */

import type { TreeNode } from "./TreeView";

/** One rendered line: either a node row or a childless-parent placeholder. */
export interface FlatTreeRow {
  /** `"node"` renders a `TreeRow`; `"empty"` renders `emptyChildLabel` text. */
  kind: "node" | "empty";
  /** Stable React key — unique across the flattened list. */
  key: string;
  /** For `"empty"`, the *parent* whose `emptyChildLabel` is shown. */
  node: TreeNode;
  /** Indent level; the placeholder sits one level below its parent. */
  depth: number;
  /**
   * Whether this row's level reserves the chevron gutter — true when any
   * sibling at the same level is expandable, so labels stay aligned.
   */
  reserveChevron: boolean;
}

/** True when a level needs the chevron gutter (any sibling is expandable). */
export const levelReservesChevron = (siblings: readonly TreeNode[]): boolean =>
  siblings.some((node) => node.children !== undefined);

/**
 * Depth-first list of every currently visible row.
 *
 * A node is visible when every ancestor is in `expanded`. An expanded node with
 * no children contributes a single `"empty"` row when it declares
 * `emptyChildLabel`, and nothing otherwise — matching the recursive render.
 *
 * @param nodes Root-level nodes.
 * @param expanded Ids of expanded nodes.
 * @returns Rows in render order; index `i` is the `i`-th visible line.
 */
export const flattenVisible = (
  nodes: readonly TreeNode[],
  expanded: ReadonlySet<string>,
): FlatTreeRow[] => {
  const rows: FlatTreeRow[] = [];

  const walk = (siblings: readonly TreeNode[], depth: number): void => {
    const reserveChevron = levelReservesChevron(siblings);
    for (const node of siblings) {
      rows.push({ kind: "node", key: node.id, node, depth, reserveChevron });
      const children = node.children;
      if (children === undefined || !expanded.has(node.id)) continue;
      if (children.length === 0) {
        if (node.emptyChildLabel) {
          rows.push({
            kind: "empty",
            key: `${node.id}::empty`,
            node,
            depth: depth + 1,
            reserveChevron: false,
          });
        }
        continue;
      }
      walk(children, depth + 1);
    }
  };

  walk(nodes, 0);
  return rows;
};

/** Index of `activeId` in a flattened list, or `-1` — the scroll-into-view target. */
export const indexOfNode = (rows: readonly FlatTreeRow[], activeId: string | undefined): number => {
  if (activeId === undefined) return -1;
  return rows.findIndex((row) => row.kind === "node" && row.node.id === activeId);
};
