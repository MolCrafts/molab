import { describe, expect, it } from "@rstest/core";
import { assetOriginText, projectAssetView } from "@/api/assets";
import type { ManagedAssetResponse } from "@/api/generated/models/ManagedAssetResponse";
import { mapAssets } from "@/app/state/api";

describe("assetOriginText", () => {
  it("names the attempt and task that registered the file", () => {
    expect(
      assetOriginText({
        originKind: "execution",
        runId: "run-1",
        executionId: "e01",
        task: "simulate",
      }),
    ).toBe("run-1 / e01 / simulate");
  });

  it("shows an import uri", () => {
    expect(assetOriginText({ originKind: "import", uri: "/data/qm9" })).toBe("/data/qm9");
  });

  it("shows an em dash when nothing is known", () => {
    expect(assetOriginText({})).toBe("—");
  });
});

describe("asset producing scope", () => {
  it("preserves immutable producer ids through both wire adapters independently of asset owner", () => {
    const wire: ManagedAssetResponse = {
      id: "asset",
      projectId: "owner",
      title: "Source",
      createdAt: "2026-01-01",
      ref: "molab:asset/asset",
      digest: "sha256:x",
      size: 1,
      file: "source.csv",
      originKind: "execution",
      originProjectId: "producer-project",
      originExperimentId: "producer-experiment",
      runId: "r1",
      executionId: "e01",
    };
    const direct = mapAssets([wire])[0];
    const adapted = mapAssets([projectAssetView(wire)])[0];
    for (const result of [direct, adapted]) {
      expect(result.projectId).toBe("owner");
      expect(result.origin).toMatchObject({
        projectId: "producer-project",
        experimentId: "producer-experiment",
        runId: "r1",
        executionId: "e01",
      });
    }
  });
});
