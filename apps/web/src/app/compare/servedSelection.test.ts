import { describe, expect, it } from "@rstest/core";

import { compareEntriesForWorkspaces } from "./servedSelection";

describe("compareEntriesForWorkspaces", () => {
  const entry = (workspaceKey: string) => ({
    ref: { workspaceKey, projectId: "peo-tg" },
  });

  it("drops a selection from a workspace this serve is not hosting", () => {
    expect(
      compareEntriesForWorkspaces(
        [entry("local-lab"), entry("remote-arrhenius-lab")],
        ["remote-arrhenius-lab"],
      ).map((item) => item.ref.workspaceKey),
    ).toEqual(["remote-arrhenius-lab"]);
  });

  it("hides the dock until the served set is known", () => {
    expect(compareEntriesForWorkspaces([entry("local-lab")], [])).toEqual([]);
  });
});
