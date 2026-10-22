import { describe, expect, it } from "@rstest/core";
import {
  fixtureExperimentSummary,
  fixtureProjectSummary,
  fixtureRunSummary,
} from "@/__fixtures__/api";
import { buildMolabRefIndex } from "@/lib/entity-linkify";

describe("buildMolabRefIndex", () => {
  it("indexes server refs and skips an entity with none", () => {
    const index = buildMolabRefIndex({
      projects: [{ ...fixtureProjectSummary, id: "P1", name: "PEO", ref: "molab:project/P1" }],
      experiments: [
        {
          ...fixtureExperimentSummary,
          id: "E1",
          name: "Tg",
          projectId: "P1",
          ref: "molab:experiment/E1",
        },
        {
          ...fixtureExperimentSummary,
          id: "E2",
          name: "Cooling",
          projectId: "P1",
          ref: "molab:experiment/E2",
        },
        { ...fixtureExperimentSummary, id: "E3", name: "Unlinked", projectId: "P1" },
      ],
      runs: [
        {
          ...fixtureRunSummary,
          id: "R1",
          name: "n=8",
          projectId: "P1",
          experimentId: "E1",
          ref: "molab:experiment/E1/run/R1",
        },
        {
          ...fixtureRunSummary,
          id: "R1",
          name: "n=8",
          projectId: "P1",
          experimentId: "E2",
          ref: "molab:experiment/E2/run/R1",
        },
      ],
    });

    expect(index.size).toBe(5);
    expect(index.get("molab:experiment/E2/run/R1")?.path).toBe(
      "/projects/P1/experiments/E2/runs/R1",
    );
    expect(index.get("molab:project/P1")).toEqual({
      kind: "project",
      label: "PEO",
      path: "/projects/P1",
    });
  });
});
