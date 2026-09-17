import { describe, expect, it } from "@rstest/core";

import { type MultiSelectState, nextSelection } from "./nextSelection";

const IDS = ["r0", "r1", "r2", "r3", "r4"];
const TREE = ["p", "e", "r1", "r2", "e2"];
const empty = (): MultiSelectState => ({ selected: new Set<string>(), anchor: null });
const selectedArray = (state: MultiSelectState): string[] => Array.from(state.selected).sort();

describe("nextSelection", () => {
  it("plain click selects only the clicked row and sets the anchor", () => {
    const next = nextSelection(empty(), 2, IDS, { shift: false, meta: false });
    expect(selectedArray(next)).toEqual(["r2"]);
    expect(next.anchor).toBe(2);
  });

  it("ctrl/meta click toggles a single row without clearing others", () => {
    const a = nextSelection(empty(), 1, IDS, { shift: false, meta: false });
    const b = nextSelection(a, 3, IDS, { shift: false, meta: true });
    expect(selectedArray(b)).toEqual(["r1", "r3"]);
    const c = nextSelection(b, 1, IDS, { shift: false, meta: true });
    expect(selectedArray(c)).toEqual(["r3"]);
  });

  it("shift click selects the inclusive range from the anchor", () => {
    const anchored = nextSelection(empty(), 1, IDS, { shift: false, meta: false });
    const ranged = nextSelection(anchored, 3, IDS, { shift: true, meta: false });
    expect(selectedArray(ranged)).toEqual(["r1", "r2", "r3"]);
    expect(ranged.anchor).toBe(1);
  });

  it("shift range works backwards (click before the anchor)", () => {
    const anchored = nextSelection(empty(), 3, IDS, { shift: false, meta: false });
    const ranged = nextSelection(anchored, 1, IDS, { shift: true, meta: false });
    expect(selectedArray(ranged)).toEqual(["r1", "r2", "r3"]);
  });

  it("shift with no anchor falls back to single selection", () => {
    const next = nextSelection(empty(), 2, IDS, { shift: true, meta: false });
    expect(selectedArray(next)).toEqual(["r2"]);
    expect(next.anchor).toBe(2);
  });

  it("shift range on a tree-visible preorder from e to e2", () => {
    const anchored = nextSelection(empty(), 1, TREE, { shift: false, meta: false });
    const ranged = nextSelection(anchored, 4, TREE, { shift: true, meta: false });
    expect(Array.from(ranged.selected)).toEqual(["e", "r1", "r2", "e2"]);
    expect(ranged.anchor).toBe(1);
  });
});
