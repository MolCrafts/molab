import { beforeEach, describe, expect, it } from "@rstest/core";
import { applicableRunViews } from "@/app/renderers/run/useRunViews";
import { listRunViewContributions } from "@/lib/contribution-runtime";
import { createPluginAPI } from "@/plugins/api/create_api";
import { resetContributionRuntimeForTests } from "@/plugins/contribution-runtime";
import molvisPlugin from "@/plugins/molvis";
import type { FileMatchContext } from "@/plugins/types";

const ctx = (relPath: string, overrides: Partial<FileMatchContext> = {}): FileMatchContext => ({
  name: relPath.split("/").pop() ?? relPath,
  relPath,
  size: 1024,
  type: "file",
  ...overrides,
});

beforeEach(() => {
  resetContributionRuntimeForTests();
  void molvisPlugin.activate(createPluginAPI("molvis").api);
});

const molvisView = (file: FileMatchContext) =>
  applicableRunViews(listRunViewContributions(), [file]).find(
    (view) => view.contribution.id === "molvis",
  );

describe("sidecar-backed dataset discovery", () => {
  it("does not put sidecar datasets on the MolVis run view", () => {
    const file = ctx("data/qm9.tar.bz2", { hasPreviewSidecar: true });
    expect(molvisView(file)).toBeUndefined();
  });

  it("does not discover an unflagged, non-matching file", () => {
    const file = ctx("data/qm9.tar.bz2", { hasPreviewSidecar: false });
    expect(molvisView(file)).toBeUndefined();
  });

  it("still discovers extension-matched trajectories without the flag", () => {
    const file = ctx("run/traj.lammpstrj");
    const molvis = molvisView(file);
    expect(molvis).toBeDefined();
    expect(molvis?.files.map((f) => f.relPath)).toContain("run/traj.lammpstrj");
  });
});
