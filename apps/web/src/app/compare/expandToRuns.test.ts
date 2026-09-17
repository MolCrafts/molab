import { describe, expect, it } from "@rstest/core";

import { buildEmptySnapshot } from "@/app/state/api";
import type { ExperimentSummary, ProjectSummary, RunSummary } from "@/app/types";

import { ExpandIncompleteError, expandToRuns } from "./expandToRuns";
import type { CompareItem } from "./types";

const project = (id: string, experimentCount: number): ProjectSummary => ({
  id,
  name: id,
  path: `projects/${id}`,
  status: "active",
  summary: "",
  updatedAt: "2026-01-01",
  workspaceKey: "lab-v3",
  experimentCount,
});

const experiment = (id: string, projectId: string, runCount: number): ExperimentSummary => ({
  id,
  name: id,
  path: `projects/${projectId}/experiments/${id}`,
  status: "active",
  summary: "",
  workflowFile: "",
  updatedAt: "2026-01-01",
  projectId,
  parameterSpace: {},
  workflowSource: null,
  planRunId: null,
  runCount,
  workspaceKey: "lab-v3",
});

const run = (id: string, projectId: string, experimentId: string): RunSummary => ({
  id,
  name: id,
  path: `projects/${projectId}/experiments/${experimentId}/runs/${id}`,
  status: "succeeded",
  summary: "",
  updatedAt: "2026-01-01",
  projectId,
  experimentId,
  definitionHash: "",
  experimentRevisionId: "",
  statusSummary: { total: 1, active: 0, notStarted: false, byStatus: { succeeded: 1 } },
  parameters: {},
  workflowSource: null,
  workflowSnapshot: null,
  startedAt: null,
  finishedAt: null,
  executionHistory: [],
  errorMessage: null,
  workspaceKey: "lab-v3",
});

const item = (partial: CompareItem["ref"]): CompareItem => ({
  ref: partial,
  executionId: null,
  workspaceLabel: "lab-v3",
  projectName: partial.projectId,
  experimentName: partial.kind === "project" ? "" : partial.experimentId,
  runName: partial.kind === "run" ? partial.runId : "",
  parameters: {},
  category: null,
  addedAt: "2026-09-06T00:00:00.000Z",
});

describe("expandToRuns", () => {
  it("unfolds a loaded experiment into its runs", () => {
    const snapshot = buildEmptySnapshot();
    snapshot.projects = [project("peo-tg", 1)];
    snapshot.experiments = [experiment("n-series", "peo-tg", 2)];
    snapshot.runs = [run("r1", "peo-tg", "n-series"), run("r2", "peo-tg", "n-series")];

    const entries = expandToRuns(
      [
        item({
          kind: "experiment",
          workspaceKey: "lab-v3",
          projectId: "peo-tg",
          experimentId: "n-series",
        }),
      ],
      snapshot,
    );
    expect(entries.map((entry) => entry.ref.runId)).toEqual(["r1", "r2"]);
  });

  it("unfolds a loaded project into runs under it only", () => {
    const snapshot = buildEmptySnapshot();
    snapshot.projects = [project("peo-tg", 1), project("other", 1)];
    snapshot.experiments = [experiment("n-series", "peo-tg", 2), experiment("x", "other", 1)];
    snapshot.runs = [
      run("r1", "peo-tg", "n-series"),
      run("r2", "peo-tg", "n-series"),
      run("r3", "other", "x"),
    ];

    const entries = expandToRuns(
      [item({ kind: "project", workspaceKey: "lab-v3", projectId: "peo-tg" })],
      snapshot,
    );
    expect(entries.map((entry) => entry.ref.runId)).toEqual(["r1", "r2"]);
  });

  it("returns a run item as itself", () => {
    const snapshot = buildEmptySnapshot();
    const entries = expandToRuns(
      [
        item({
          kind: "run",
          workspaceKey: "lab-v3",
          projectId: "peo-tg",
          experimentId: "n-series",
          runId: "r1",
        }),
      ],
      snapshot,
    );
    expect(entries).toHaveLength(1);
    expect(entries[0].ref.runId).toBe("r1");
  });

  it("throws when the experiment is not in the snapshot", () => {
    const snapshot = buildEmptySnapshot();
    expect(() =>
      expandToRuns(
        [
          item({
            kind: "experiment",
            workspaceKey: "lab-v3",
            projectId: "peo-tg",
            experimentId: "missing",
          }),
        ],
        snapshot,
      ),
    ).toThrow(ExpandIncompleteError);
  });

  it("returns [] for a loaded experiment with runCount 0", () => {
    const snapshot = buildEmptySnapshot();
    snapshot.projects = [project("peo-tg", 1)];
    snapshot.experiments = [experiment("empty", "peo-tg", 0)];
    expect(
      expandToRuns(
        [
          item({
            kind: "experiment",
            workspaceKey: "lab-v3",
            projectId: "peo-tg",
            experimentId: "empty",
          }),
        ],
        snapshot,
      ),
    ).toEqual([]);
  });

  it("does not attribute another workspace's rows", () => {
    const snapshot = buildEmptySnapshot();
    snapshot.projects = [{ ...project("peo-tg", 1), workspaceKey: "lab-v3" }];
    snapshot.experiments = [experiment("n-series", "peo-tg", 1)];
    snapshot.runs = [run("r1", "peo-tg", "n-series")];
    expect(() =>
      expandToRuns(
        [item({ kind: "project", workspaceKey: "other-ws", projectId: "peo-tg" })],
        snapshot,
      ),
    ).toThrow(ExpandIncompleteError);
  });
});
