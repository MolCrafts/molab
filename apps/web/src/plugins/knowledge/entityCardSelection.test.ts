import { describe, expect, it } from "@rstest/core";
import type { EntityCard } from "@/api/generated/models/EntityCard";
import { toSelection } from "@/plugins/knowledge/entityCardSelection";

const card = (fields: Partial<EntityCard> & Pick<EntityCard, "kind" | "id">): EntityCard => ({
  title: "t",
  relPath: null,
  status: null,
  ...fields,
});

describe("toSelection", () => {
  it("opens an asset the snapshot knows", () => {
    expect(toSelection(card({ kind: "asset", id: "a1" }), new Set(["a1"]))).toEqual({
      objectType: "asset",
      objectId: "a1",
    });
  });

  it("does not open an unknown asset with no path", () => {
    expect(toSelection(card({ kind: "asset", id: "a1" }), new Set())).toBeNull();
  });

  it("opens an unknown asset path as knowledge", () => {
    expect(
      toSelection(card({ kind: "asset", id: "a1", relPath: "knowledges/idea.md" }), new Set()),
    ).toEqual({ objectType: "knowledge", objectId: "knowledges/idea.md" });
  });

  it("opens a run by id", () => {
    expect(toSelection(card({ kind: "run", id: "r1" }), new Set())).toEqual({
      objectType: "run",
      objectId: "r1",
    });
  });

  it("does not open a missing card", () => {
    expect(toSelection(card({ kind: "run", id: "R1", missing: true }), new Set())).toBeNull();
  });

  it("does not open a legacy path card", () => {
    expect(toSelection(card({ kind: "path", id: "x", relPath: "runs/x" }), new Set())).toBeNull();
  });
});
