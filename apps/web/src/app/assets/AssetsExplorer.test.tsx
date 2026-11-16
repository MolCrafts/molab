import { describe, expect, it } from "@rstest/core";
import { buildEmptySnapshot } from "@/app/state/api";
import type { AssetSummary } from "@/app/types";
import { buildAssetExplorerNodes } from "./AssetsExplorer";

const ASSET: AssetSummary = {
  id: "asset-1",
  name: "Result table",
  kind: "artifact",
  status: "succeeded",
  summary: "Final measurements",
  updatedAt: "2026-08-30T12:00:00Z",
  sizeBytes: 42,
};

describe("buildAssetExplorerNodes", () => {
  it("deduplicates overlapping catalog rows and groups workspace assets", () => {
    const snapshot = buildEmptySnapshot();
    snapshot.assets = [ASSET, { ...ASSET }];

    const nodes = buildAssetExplorerNodes({
      snapshot,
      searchQuery: "",
      onSelect: () => undefined,
    });

    expect(nodes).toHaveLength(1);
    expect(nodes[0]?.id).toBe("asset-workspace");
    expect(nodes[0]?.children).toHaveLength(1);
    expect(nodes[0]?.children?.[0]?.id).toBe(ASSET.id);
  });

  it("filters by name or summary before grouping", () => {
    const snapshot = buildEmptySnapshot();
    snapshot.assets = [ASSET];

    expect(
      buildAssetExplorerNodes({ snapshot, searchQuery: "measurements", onSelect: () => undefined }),
    ).toHaveLength(1);
    expect(
      buildAssetExplorerNodes({ snapshot, searchQuery: "missing", onSelect: () => undefined }),
    ).toEqual([]);
  });
});
