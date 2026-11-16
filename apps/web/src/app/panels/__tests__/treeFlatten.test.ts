import { describe, expect, it } from "@rstest/core";
import type { TreeNode } from "@/app/panels/TreeView";
import { flattenVisible, indexOfNode, levelReservesChevron } from "@/app/panels/treeFlatten";

/** A leaf: no `children` key at all, so it is not expandable. */
const leaf = (id: string): TreeNode => ({ id, label: id });

/** A branch: `children` present (possibly empty) makes it expandable. */
const branch = (id: string, children: TreeNode[], emptyChildLabel?: string): TreeNode => ({
  id,
  label: id,
  children,
  ...(emptyChildLabel ? { emptyChildLabel } : {}),
});

const ids = (rows: ReturnType<typeof flattenVisible>): string[] => rows.map((r) => r.key);

describe("flattenVisible", () => {
  it("lists only root rows when nothing is expanded", () => {
    const nodes = [branch("p1", [leaf("r1")]), leaf("p2")];

    const rows = flattenVisible(nodes, new Set());

    expect(ids(rows)).toEqual(["p1", "p2"]);
    expect(rows.every((r) => r.depth === 0)).toBe(true);
  });

  it("splices children in depth-first render order under an expanded node", () => {
    const nodes = [branch("p1", [leaf("r1"), leaf("r2")]), leaf("p2")];

    const rows = flattenVisible(nodes, new Set(["p1"]));

    // r1/r2 come between p1 and p2 — the order the recursion renders.
    expect(ids(rows)).toEqual(["p1", "r1", "r2", "p2"]);
    expect(rows.map((r) => r.depth)).toEqual([0, 1, 1, 0]);
  });

  it("hides grandchildren when the intermediate node is collapsed", () => {
    const nodes = [branch("p", [branch("e", [leaf("run")])])];

    // Only the project is expanded; the experiment stays shut.
    const rows = flattenVisible(nodes, new Set(["p"]));

    expect(ids(rows)).toEqual(["p", "e"]);
  });

  it("requires the whole ancestor chain to be expanded, not just the parent", () => {
    const nodes = [branch("p", [branch("e", [leaf("run")])])];

    // "e" is expanded but its parent is not, so nothing below "p" is visible.
    const rows = flattenVisible(nodes, new Set(["e"]));

    expect(ids(rows)).toEqual(["p"]);
  });

  it("emits one placeholder row for an expanded node with no children", () => {
    const nodes = [branch("p", [], "No runs yet")];

    const rows = flattenVisible(nodes, new Set(["p"]));

    expect(rows).toHaveLength(2);
    expect(rows[1].kind).toBe("empty");
    expect(rows[1].depth).toBe(1);
    expect(rows[1].node.emptyChildLabel).toBe("No runs yet");
    // Keyed apart from the parent so React never sees a duplicate key.
    expect(rows[1].key).not.toBe(rows[0].key);
  });

  it("emits nothing extra for an expanded childless node with no placeholder text", () => {
    const rows = flattenVisible([branch("p", [])], new Set(["p"]));

    expect(ids(rows)).toEqual(["p"]);
  });

  it("reserves the chevron gutter for a whole level when any sibling is expandable", () => {
    const nodes = [leaf("a"), branch("b", [leaf("c")])];

    const rows = flattenVisible(nodes, new Set());

    // "a" is a leaf but still reserves, so its label aligns with "b"'s.
    expect(rows.map((r) => r.reserveChevron)).toEqual([true, true]);
  });

  it("does not reserve the gutter on a level of pure leaves", () => {
    const rows = flattenVisible([leaf("a"), leaf("b")], new Set());

    expect(rows.map((r) => r.reserveChevron)).toEqual([false, false]);
  });

  it("computes the gutter per level, not globally", () => {
    // Root level is expandable; the child level is all leaves.
    const nodes = [branch("p", [leaf("r1"), leaf("r2")])];

    const rows = flattenVisible(nodes, new Set(["p"]));

    expect(rows.map((r) => r.reserveChevron)).toEqual([true, false, false]);
  });

  it("returns an empty list for an empty forest", () => {
    expect(flattenVisible([], new Set())).toEqual([]);
  });

  it("scales to a wide expanded level without losing order", () => {
    const runs = Array.from({ length: 5000 }, (_, i) => leaf(`run-${i}`));
    const rows = flattenVisible([branch("exp", runs)], new Set(["exp"]));

    expect(rows).toHaveLength(5001);
    expect(rows[1].key).toBe("run-0");
    expect(rows[5000].key).toBe("run-4999");
  });
});

describe("levelReservesChevron", () => {
  it("treats an empty children array as expandable", () => {
    // `children: []` means "loaded, nothing inside" — still a disclosure row.
    expect(levelReservesChevron([branch("p", [])])).toBe(true);
  });

  it("is false when no sibling declares children", () => {
    expect(levelReservesChevron([leaf("a"), leaf("b")])).toBe(false);
  });
});

describe("indexOfNode", () => {
  it("finds the flattened index of the active row", () => {
    const rows = flattenVisible([branch("p", [leaf("r1"), leaf("r2")])], new Set(["p"]));

    expect(indexOfNode(rows, "r2")).toBe(2);
  });

  it("returns -1 for an unknown or absent id", () => {
    const rows = flattenVisible([leaf("a")], new Set());

    expect(indexOfNode(rows, "nope")).toBe(-1);
    expect(indexOfNode(rows, undefined)).toBe(-1);
  });

  it("never matches a placeholder row", () => {
    const rows = flattenVisible([branch("p", [], "empty")], new Set(["p"]));

    // The placeholder borrows its parent's node, so a naive search would hit it.
    expect(indexOfNode(rows, "p")).toBe(0);
  });
});
