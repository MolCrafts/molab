import { describe, expect, it } from "@rstest/core";
import { buildEmbedGroups } from "@/plugins/knowledge/embedGroups";

describe("buildEmbedGroups", () => {
  it("embeds a run by its ref and drops a run without one", () => {
    const groups = buildEmbedGroups({
      experiments: [{ id: "E1", name: "sweep" }],
      runs: [
        { id: "R1", ref: "molab:experiment/E1/run/R1", name: "x=1" },
        { id: "R2", name: "bare" },
      ],
      assets: [],
    });
    const runs = groups.find((group) => group.kind === "run");
    const experiments = groups.find((group) => group.kind === "experiment");
    expect(runs?.items).toEqual([{ id: "R1", label: "x=1", target: "molab:experiment/E1/run/R1" }]);
    expect(experiments?.items[0]?.target).toBe("E1");
    expect(groups.some((group) => group.kind === "asset")).toBe(false);
  });
});
