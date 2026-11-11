import { describe, expect, it } from "@rstest/core";
import type { WorkspaceRunRow } from "@/app/runs/types";
import type { AssetSummary } from "@/app/types";
import { assetContext, contextSentence, groupAssets, importSource } from "./assetContext";
import { assetKindOf } from "./assetKinds";

const run = (id: string, over: Partial<WorkspaceRunRow> = {}): WorkspaceRunRow => ({
  id,
  name: id,
  workspaceKey: "ws",
  path: `projects/p/experiments/e/runs/${id}`,
  projectId: "p",
  projectName: "Project P",
  experimentId: "e",
  experimentName: "Experiment E",
  definitionHash: "sha256:x",
  experimentRevisionId: "rev",
  inputs: [],
  targetHint: null,
  statusSummary: { total: 1, active: 0, notStarted: false, byStatus: { succeeded: 1 } },
  parameters: {},
  createdAt: "2026-11-01T00:00:00Z",
  executions: [],
  ...over,
});

const asset = (id: string, over: Partial<AssetSummary> = {}): AssetSummary => ({
  id,
  name: `${id}.xyz`,
  kind: "asset",
  status: "active",
  summary: "",
  updatedAt: "2026-11-02T00:00:00Z",
  sizeBytes: 10,
  projectId: "p",
  origin: { kind: "execution", runId: "r1", executionId: "e01", task: "md", uri: null },
  ...over,
});

const imported = (id: string, uri: string): AssetSummary =>
  asset(id, {
    name: `${id}.csv`,
    origin: { kind: "import", runId: null, executionId: null, task: null, uri },
  });

describe("assetKindOf", () => {
  it("reads the name first, then the media type", () => {
    expect(assetKindOf("water.xyz")).toBe("structure");
    expect(assetKindOf("rdf.csv")).toBe("table");
    expect(assetKindOf("model.pt")).toBe("model");
    expect(assetKindOf("tg.png")).toBe("image");
    expect(assetKindOf("run.log")).toBe("text");
    expect(assetKindOf("blob", "image/png")).toBe("image");
    expect(assetKindOf("blob", "application/octet-stream")).toBe("data");
  });
});

describe("assetContext", () => {
  const runs = [
    run("r0"),
    run("r1", { inputs: ["in"] }),
    run("r2", { inputs: ["a"] }),
    run("r3", { inputs: ["a", "in"] }),
  ];
  const assets = [asset("a"), imported("in", "https://zenodo.org/records/1")];

  it("finds the producer, its inputs and the runs that use the asset", () => {
    const context = assetContext(assets[0] as AssetSummary, assets, runs);
    expect(context.producer?.id).toBe("r1");
    expect(context.inputs.map((item) => item.id)).toEqual(["in"]);
    expect(context.usedBy.map((item) => item.id)).toEqual(["r2", "r3"]);
    expect(context.imported).toBe(false);
  });

  it("says where it came from in one sentence", () => {
    const context = assetContext(assets[0] as AssetSummary, assets, runs);
    expect(contextSentence(context, (item) => item.name, 1)).toBe(
      "Structure from r1 in Experiment E · used by 2 runs · cited in 1 document",
    );
    const fromZenodo = assetContext(assets[1] as AssetSummary, assets, runs);
    expect(contextSentence(fromZenodo, (item) => item.name, 0)).toBe(
      "Imported from zenodo.org · used by 2 runs",
    );
  });

  it("names an import source by host, or by itself", () => {
    expect(importSource("https://zenodo.org/records/1")).toBe("zenodo.org");
    expect(importSource("data/ligands.csv")).toBe("data/ligands.csv");
    expect(importSource(null)).toBe("outside a run");
  });
});

describe("groupAssets", () => {
  const runs = [run("r1"), run("r2", { experimentId: "f", experimentName: "Experiment F" })];
  const assets = [
    asset("a", { updatedAt: "2026-11-03T00:00:00Z" }),
    asset("b", {
      origin: { kind: "execution", runId: "r2", executionId: "e01", task: null, uri: null },
    }),
    imported("c", "https://zenodo.org/records/1"),
    asset("d", {
      origin: { kind: "execution", runId: "gone", executionId: null, task: null, uri: null },
    }),
  ];

  it("groups by experiment, then by producing run; imports and unknown runs last", () => {
    const groups = groupAssets(assets, runs, "experiment", (id) => id);
    expect(groups.map((group) => group.title)).toEqual([
      "Experiment E",
      "Experiment F",
      "Run not loaded",
      "Imported",
    ]);
    expect(groups[0]?.where).toBe("Project P");
    expect(groups[0]?.blocks[0]?.run?.id).toBe("r1");
    expect(groups[3]?.blocks[0]?.source).toBe("https://zenodo.org/records/1");
  });

  it("groups by kind and by nothing", () => {
    expect(groupAssets(assets, runs, "kind", (id) => id).map((group) => group.title)).toEqual([
      "Structure",
      "Table",
    ]);
    const flat = groupAssets(assets, runs, "none", (id) => id);
    expect(flat).toHaveLength(1);
    expect(flat[0]?.blocks[0]?.assets[0]?.id).toBe("a");
  });
});
