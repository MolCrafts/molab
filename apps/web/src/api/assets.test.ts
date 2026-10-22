import { describe, expect, it } from "@rstest/core";
import { assetVersionOrigin } from "@/api/assets";

describe("assetVersionOrigin", () => {
  it("shows an artifact origin ref", () => {
    expect(
      assetVersionOrigin({
        originKind: "artifact",
        originRef: "molab:experiment/e/run/r/artifact/a",
        sourceArtifactId: "a",
      }),
    ).toBe("molab:experiment/e/run/r/artifact/a");
  });

  it("falls back to the source artifact id", () => {
    expect(
      assetVersionOrigin({
        originKind: "artifact",
        originRef: null,
        sourceArtifactId: "a",
      }),
    ).toBe("a");
  });

  it("shows an import as action and uri", () => {
    expect(
      assetVersionOrigin({
        originKind: "import",
        importAction: "copy",
        originUri: "/data/qm9",
      }),
    ).toBe("copy: /data/qm9");
  });

  it("shows an em dash when nothing is known", () => {
    expect(assetVersionOrigin({})).toBe("—");
  });
});
