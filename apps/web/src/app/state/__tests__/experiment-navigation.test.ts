import { describe, expect, it } from "@rstest/core";
import { experimentPath, legacyCompareRedirect, projectPath, runPath } from "@/app/entities/paths";
import {
  buildSelectionFromLocation,
  getSelectionPath,
  hierarchyRouteContextFromPath,
} from "@/app/state/useNavigationState";
import type { WorkspaceSnapshot } from "@/app/types";

const snapshot: WorkspaceSnapshot = {
  workspaces: [],
  projects: [
    {
      id: "p 1",
      name: "Project",
      path: "projects/project",
      status: "active",
      summary: "",
      updatedAt: "2026-01-01",
    },
  ],
  experiments: [
    {
      id: "e/1",
      name: "Experiment",
      path: "projects/project/experiments/experiment",
      status: "active",
      summary: "",
      workflowFile: "workflow.json",
      updatedAt: "2026-01-01",
      projectId: "p 1",
      parameterSpace: {},
      workflowSource: null,
    },
  ],
  runs: [],
  assets: [],
  workflows: [
    {
      id: "wf-1",
      name: "Workflow",
      status: "active",
      summary: "",
      updatedAt: "2026-01-01",
      projectId: "p 1",
      experimentId: "e/1",
    },
  ],
  workspaceRoot: null,
  consoleEntries: [],
};

describe("experiment navigation", () => {
  it("builds canonical nested experiment view URLs", () => {
    expect(experimentPath("p 1", "e/1")).toBe("/projects/p%201/experiments/e%2F1");
    expect(experimentPath("p 1", "e/1", "workflow")).toBe(
      "/projects/p%201/experiments/e%2F1/workflow",
    );
    expect(experimentPath("p 1", "e/1", "notebook")).toBe(
      "/projects/p%201/experiments/e%2F1/notebook",
    );
  });

  it("redirects legacy compare URLs to /compare", () => {
    expect(legacyCompareRedirect("/runs", "tab=compare")).toBe("/compare");
    expect(legacyCompareRedirect("/projects/p/experiments/e/compare", "")).toBe("/compare");
    expect(legacyCompareRedirect("/runs", "")).toBeNull();
  });

  it("parses route-backed experiment tabs", () => {
    expect(
      buildSelectionFromLocation(
        "/projects/p%201/experiments/e%2F1/workflow",
        new URLSearchParams(),
      ),
    ).toEqual({ objectType: "experiment", objectId: "e/1", experimentView: "workflow" });
    expect(
      buildSelectionFromLocation(
        "/projects/p%201/experiments/e%2F1/notebook",
        new URLSearchParams(),
      ),
    ).toEqual({ objectType: "experiment", objectId: "e/1", experimentView: "notebook" });
  });

  it("routes workflow selections into their owning experiment", () => {
    expect(
      getSelectionPath({ objectType: "workflow", objectId: "wf-1", workflowId: "wf-1" }, snapshot),
    ).toBe("/projects/p%201/experiments/e%2F1/workflow");
  });

  it("extracts encoded parent coordinates before the lazy catalog is loaded", () => {
    expect(hierarchyRouteContextFromPath("/projects/p%201/experiments/e%2F1/runs/run%2F1")).toEqual(
      { projectId: "p 1", experimentId: "e/1" },
    );
    expect(hierarchyRouteContextFromPath("/runs")).toBeNull();
  });

  it("deep-links directly into contextual run plugins", () => {
    expect(runPath("p 1", "e/1", "r/1", "molvis")).toBe(
      "/projects/p%201/experiments/e%2F1/runs/r%2F1?tab=molvis",
    );
    expect(
      buildSelectionFromLocation(
        "/projects/p%201/experiments/e%2F1/runs/r%2F1",
        new URLSearchParams("tab=molq"),
      ),
    ).toEqual({ objectType: "run", objectId: "r/1", objectView: "molq" });
    expect(
      buildSelectionFromLocation(
        "/projects/p%201/experiments/e%2F1/runs/r%2F1",
        new URLSearchParams("tab=%3Cscript%3E"),
      ),
    ).toEqual({ objectType: "run", objectId: "r/1", objectView: undefined });
  });
});

describe("project navigation", () => {
  it("builds and parses route-backed project tabs", () => {
    expect(projectPath("p 1", "assets")).toBe("/projects/p%201/assets");
    expect(buildSelectionFromLocation("/projects/p%201/settings", new URLSearchParams())).toEqual({
      objectType: "project",
      objectId: "p 1",
      projectView: "settings",
    });
  });

  it("keeps the project overview at the short canonical URL", () => {
    expect(getSelectionPath({ objectType: "project", objectId: "p 1" }, snapshot)).toBe(
      "/projects/p%201",
    );
  });
});
