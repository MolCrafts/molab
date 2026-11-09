import type { AttemptFile, RunAttempt } from "@molcrafts/molab-plugin";
import { beforeEach, describe, expect, it } from "@rstest/core";
import { applicableRunViews } from "@/app/renderers/run/useRunViews";
import { listRunViewContributions } from "@/lib/contribution-runtime";
import { createPluginAPI } from "@/plugins/api/create_api";
import { resetContributionRuntimeForTests } from "@/plugins/contribution-runtime";
import molvisPlugin from "./plugin";

const file = (relPath: string): AttemptFile => ({
  name: relPath.split("/").pop() ?? relPath,
  relPath,
  size: 939,
  type: "file",
});

const attempt: RunAttempt = {
  projectId: "p",
  experimentId: "e",
  runId: "r",
  executionId: "e01",
  status: "succeeded",
  isLatest: true,
  isRunResult: true,
  dir: "projects/p/experiments/e/runs/r/executions/e01",
};

beforeEach(() => {
  resetContributionRuntimeForTests();
  void molvisPlugin.activate(createPluginAPI("molvis").api);
});

const molvis = (files: AttemptFile[]) =>
  applicableRunViews(listRunViewContributions(), files).find(
    (view) => view.contribution.id === "molvis",
  );

describe("MolVis run view", () => {
  it("is a run view after the core views, not a file-type tab", () => {
    const view = molvis([file("out/trajectory.xyz")]);
    expect(view?.contribution.label).toBe("MolVis");
    expect(view?.contribution.order).toBe(20);
  });

  it("takes structures, dumps and *.mrec stores, and leaves logs to molplot", () => {
    const view = molvis([
      file("out/trajectory.xyz"),
      file("out/dump.lammpstrj"),
      file("growth.mrec/zarr.json"),
      file("growth.mrec/frame/zarr.json"),
      file("log.lammps"),
      file("metrics.mlp.zarr/zarr.json"),
    ]);
    expect(view?.files.map((f) => f.relPath)).toEqual([
      "out/trajectory.xyz",
      "out/dump.lammpstrj",
      "growth.mrec/zarr.json",
      "growth.mrec/frame/zarr.json",
    ]);
  });

  it("counts a store once, however many markers it lists", async () => {
    const view = molvis([
      file("out/trajectory.xyz"),
      file("growth.mrec/zarr.json"),
      file("growth.mrec/frame/zarr.json"),
    ]);
    expect(await view?.contribution.count?.(attempt, view.files)).toBe(2);
  });

  it("does not exist for an attempt without a structure", () => {
    expect(molvis([file("run.log"), file("metrics.mlp.jsonl")])).toBeUndefined();
  });
});
