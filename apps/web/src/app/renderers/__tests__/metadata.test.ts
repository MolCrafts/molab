import { describe, expect, it } from "@rstest/core";

import { buildMetadataFields } from "@/app/renderers/metadata";
import type { ExperimentSummary, RendererSnapshot, Selection } from "@/app/types";

function experiment(workflowKind: "document" | null): ExperimentSummary & {
  workflowKind: "document" | null;
} {
  return {
    id: "e1",
    name: "calc",
    path: "projects/p/experiments/calc",
    status: "active",
    summary: "",
    workflowFile: "",
    updatedAt: "2026-01-01",
    projectId: "p",
    parameterSpace: {},
    workflowSource: null,
    workflowKind,
  };
}

function snapshot(item: ExperimentSummary): RendererSnapshot {
  return {
    projects: [],
    experiments: [item],
    runs: [],
    assets: [],
    workflows: [],
    workspaces: [],
  };
}

const selection: Selection = { objectType: "experiment", objectId: "e1" };

describe("buildMetadataFields", () => {
  it("includes workflow kind when the experiment declares one", () => {
    const fields = buildMetadataFields(selection, snapshot(experiment("document")));
    expect(fields).toContainEqual({ label: "Workflow kind", value: "document" });
  });

  it("omits workflow kind when it is absent", () => {
    const fields = buildMetadataFields(selection, snapshot(experiment(null)));
    expect(fields.some((field) => field.label === "Workflow kind")).toBe(false);
  });
});
