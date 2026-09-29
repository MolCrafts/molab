/**
 * Tests for app/state/api.ts — pure mapping functions.
 *
 * Per project convention:
 * - describe('functionName') wraps each exported function
 * - it('...') covers one behaviour per case
 * - shared mock data lives in src/__fixtures__/api.ts
 */

import { describe, expect, it } from "@rstest/core";
import {
  fixtureAsset,
  fixtureExperiment,
  fixtureExperimentNoDescription,
  fixtureProject,
  fixtureProjectNoDescription,
  fixtureRun,
  fixtureRunCancelled,
  fixtureRunFailed,
  fixtureRunPending,
} from "@/__fixtures__/api";
import {
  buildEmptySnapshot,
  mapAssets,
  mapExperiments,
  mapProjects,
  mapRuns,
  mapWorkflows,
  mapWorkspaceTree,
} from "@/app/state/api";

describe("buildEmptySnapshot", () => {
  it("returns empty collections and a null workspaceRoot", () => {
    const snap = buildEmptySnapshot();
    expect(snap.projects).toEqual([]);
    expect(snap.experiments).toEqual([]);
    expect(snap.runs).toEqual([]);
    expect(snap.assets).toEqual([]);
    expect(snap.workflows).toEqual([]);
    expect(snap.consoleEntries).toEqual([]);
    expect(snap.workspaceRoot).toBeNull();
  });
});

describe("mapProjects", () => {
  it("maps id, name, summary, status, and updatedAt from the API response", () => {
    const [result] = mapProjects([fixtureProject]);
    expect(result.id).toBe("proj-alpha");
    expect(result.name).toBe("Alpha Project");
    expect(result.summary).toBe("First project");
    expect(result.status).toBe("active");
    expect(result.updatedAt).toBe(fixtureProject.created);
  });

  it("falls back to 'No description' when description is absent", () => {
    const [result] = mapProjects([fixtureProjectNoDescription]);
    expect(result.summary).toBe("No description");
  });

  it("preserves order of multiple projects", () => {
    const results = mapProjects([fixtureProject, fixtureProjectNoDescription]);
    expect(results[0].id).toBe("proj-alpha");
    expect(results[1].id).toBe("proj-beta");
  });
});

describe("mapExperiments", () => {
  it("maps id, name, projectId, summary, and workflowFile", () => {
    const [result] = mapExperiments("proj-alpha", [fixtureExperiment]);
    expect(result.id).toBe("exp-001");
    expect(result.name).toBe("Baseline");
    expect(result.projectId).toBe("proj-alpha");
    expect(result.summary).toBe("Baseline experiment");
    expect(result.workflowFile).toBe("workflow.py");
  });

  it("never exposes the workflow (even inline JSON) as summary when description is absent", () => {
    const [plain] = mapExperiments("proj-alpha", [fixtureExperimentNoDescription]);
    expect(plain.summary).toBe("");
    const [inline] = mapExperiments("proj-alpha", [
      {
        ...fixtureExperimentNoDescription,
        workflow: JSON.stringify({ task_configs: [{ id: "build" }], links: [] }),
      },
    ]);
    expect(inline.summary).toBe("");
  });

  it("does not put inline workflow IR JSON into workflowFile", () => {
    const [inline] = mapExperiments("proj-alpha", [
      {
        ...fixtureExperiment,
        workflow: JSON.stringify({
          name: "structure-sweep",
          task_configs: [{ id: "build" }],
          links: [],
        }),
      },
    ]);
    expect(inline.workflowFile).toBe("structure-sweep");
    expect(inline.workflowSource?.startsWith("{")).toBe(true);
    expect(inline.workflowFile.includes("task_configs")).toBe(false);
  });
});

describe("mapRuns", () => {
  it("takes the name and directory from the server, never from the id", () => {
    const [result] = mapRuns("proj-alpha", "exp-001", [fixtureRun]);
    expect(result.id).toBe("run-abc");
    // What a run is called is its parameters, and where it lives is a path of
    // names. Neither is derivable here, so neither is invented here.
    expect(result.name).toBe("lr=0.001");
    expect(result.path).toBe("projects/proj-alpha/experiments/exp-001/runs/lr=0.001");
    expect(result.projectId).toBe("proj-alpha");
    expect(result.experimentId).toBe("exp-001");
  });

  it("maps every run status", () => {
    const [succeeded] = mapRuns("p", "e", [fixtureRun]);
    const [pending] = mapRuns("p", "e", [fixtureRunPending]);
    const [failed] = mapRuns("p", "e", [fixtureRunFailed]);
    const [cancelled] = mapRuns("p", "e", [fixtureRunCancelled]);
    expect(succeeded.status).toBe("succeeded");
    expect(pending.status).toBe("pending");
    expect(failed.status).toBe("failed");
    expect(cancelled.status).toBe("cancelled");
  });

  it("uses finished for updatedAt, falling back to created", () => {
    const [finished] = mapRuns("p", "e", [fixtureRun]);
    expect(finished.updatedAt).toBe("2026-03-01T12:00:00Z");
    const [unfinished] = mapRuns("p", "e", [fixtureRunPending]);
    expect(unfinished.updatedAt).toBe(fixtureRunPending.created);
  });

  it("maps immutable Run identity fields", () => {
    const [result] = mapRuns("p", "e", [fixtureRun]);
    expect(result.definitionHash).toBe("def-run-abc");
    expect(result.experimentRevisionId).toBe("rev-exp-001");
  });
});

describe("mapAssets", () => {
  it("maps id, name, summary, size, timestamp, and scope from the asset record", () => {
    const [result] = mapAssets([fixtureAsset]);
    expect(result.id).toBe("asset-001");
    expect(result.name).toBe("checkpoint.pt");
    expect(result.summary).toBe("artifact · run scope");
    expect(result.sizeBytes).toBe(1024);
    expect(result.updatedAt).toBe("2026-03-01T16:00:00Z");
    expect(result.projectId).toBe("proj-alpha");
    expect(result.experimentId).toBe("exp-001");
    expect(result.runId).toBe("run-abc");
    expect(result.scopeKind).toBe("run");
  });

  it("returns null sizeBytes when extra.size is absent", () => {
    const [result] = mapAssets([{ ...fixtureAsset, extra: {} }]);
    expect(result.sizeBytes).toBeNull();
  });

  it("falls back to the projectId arg when the asset has no scope ids", () => {
    const [result] = mapAssets([{ ...fixtureAsset, scopeIds: [] }], "proj-fallback");
    expect(result.projectId).toBe("proj-fallback");
    expect(result.experimentId).toBeUndefined();
    expect(result.runId).toBeUndefined();
  });
});

describe("mapWorkflows", () => {
  it("derives id, name, and summary from the experiment", () => {
    const rawExp = [fixtureExperiment];
    const expSummaries = mapExperiments("proj-alpha", rawExp);
    const [result] = mapWorkflows(expSummaries, rawExp);
    expect(result.id).toBe("workflow:exp-001");
    expect(result.name).toBe("Baseline workflow");
    expect(result.summary).toBe("workflow.py");
  });
});

describe("mapWorkspaceTree", () => {
  it("uses response.path when present, keeping the fixed root id", () => {
    const result = mapWorkspaceTree("/fallback", { path: "/actual/path" });
    expect(result.id).toBe("workspace-root");
    expect(result.name).toBe("/actual/path");
    expect(result.path).toBe("/actual/path");
  });

  it("falls back to rootPath when response.path is absent", () => {
    const result = mapWorkspaceTree("/fallback", {});
    expect(result.name).toBe("/fallback");
  });

  it("maps children recursively, defaulting to an empty array", () => {
    const result = mapWorkspaceTree("/ws", {
      children: [
        { name: "src", path: "/ws/src", type: "directory" },
        { name: "main.py", path: "/ws/main.py", type: "file" },
      ],
    });
    expect(result.children).toHaveLength(2);
    expect(result.children[0].kind).toBe("directory");
    expect(result.children[1].kind).toBe("file");
    expect(mapWorkspaceTree("/ws", {}).children).toEqual([]);
  });
});
