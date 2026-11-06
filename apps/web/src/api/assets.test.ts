import { describe, expect, it } from "@rstest/core";
import { assetOriginText } from "@/api/assets";

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
