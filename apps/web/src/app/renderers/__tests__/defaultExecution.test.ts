import { describe, expect, it } from "@rstest/core";
import { defaultExecutionId } from "@/app/renderers/useRunViewer";

/**
 * A run must open on an attempt.
 *
 * Every file-discovered tab — molplot, molvis, tensorboard — takes its
 * coordinates from the selected execution. When none was selected the run
 * rendered with no plugin tabs at all, which is indistinguishable from the
 * plugins being broken. That is the regression this guards.
 */
describe("defaultExecutionId", () => {
  it("opens on the latest attempt", () => {
    expect(
      defaultExecutionId([{ executionId: "e01" }, { executionId: "e02" }, { executionId: "e03" }]),
    ).toBe("e03");
  });

  it("selects the only attempt when there is one", () => {
    expect(defaultExecutionId([{ executionId: "e01" }])).toBe("e01");
  });

  it("selects nothing for a run that has never been executed", () => {
    // Not a failure: there is genuinely no attempt to show files for.
    expect(defaultExecutionId([])).toBeNull();
    expect(defaultExecutionId(undefined)).toBeNull();
  });
});
