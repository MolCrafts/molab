/**
 * Shared fixture data for unit tests.
 * Equivalent role to Python's conftest.py — import from here, do not inline in test files.
 */

import type { ExperimentResponse } from "@/api/generated/models/ExperimentResponse";
import type { ProjectResponse } from "@/api/generated/models/ProjectResponse";
import type {
  ApiAssetResponse,
  ApiRunResponse,
  ExperimentSummary,
  ProjectSummary,
  RunSummary,
} from "@/app/types";

export const fixtureProject: ProjectResponse = {
  id: "proj-alpha",
  name: "Alpha Project",
  path: "projects/alpha-project",
  created: "2026-03-01T00:00:00Z",
  description: "First project",
};

export const fixtureProjectNoDescription: ProjectResponse = {
  id: "proj-beta",
  name: "Beta Project",
  path: "projects/beta-project",
  created: "2026-03-02T00:00:00Z",
};

export const fixtureExperiment: ExperimentResponse = {
  id: "exp-001",
  projectId: "proj-alpha",
  name: "Baseline",
  path: "projects/alpha-project/experiments/baseline",
  created: "2026-03-01T10:00:00Z",
  workflow: "workflow.py",
  description: "Baseline experiment",
};

export const fixtureExperimentNoDescription: ExperimentResponse = {
  id: "exp-002",
  projectId: "proj-alpha",
  name: "Variant",
  path: "projects/alpha-project/experiments/variant",
  created: "2026-03-02T10:00:00Z",
  workflow: "variant.py",
};

const fixtureStatus = (status: string) => ({
  total: status === "pending" ? 0 : 1,
  active: status === "running" ? 1 : 0,
  notStarted: status === "pending",
  byStatus: status === "pending" ? {} : { [status]: 1 },
});

export const fixtureRun: ApiRunResponse = {
  id: "run-abc",
  name: "lr=0.001",
  path: "projects/proj-alpha/experiments/exp-001/runs/lr=0.001",
  projectId: "proj-alpha",
  experimentId: "exp-001",
  definitionHash: "def-run-abc",
  experimentRevisionId: "rev-exp-001",
  statusSummary: fixtureStatus("succeeded"),
  created: "2026-03-01T11:00:00Z",
  finished: "2026-03-01T12:00:00Z",
  parameters: { lr: 0.001 },
};

export const fixtureRunPending: ApiRunResponse = {
  id: "run-def",
  name: "lr=0.01",
  path: "projects/proj-alpha/experiments/exp-001/runs/lr=0.01",
  projectId: "proj-alpha",
  experimentId: "exp-001",
  definitionHash: "def-run-def",
  experimentRevisionId: "rev-exp-001",
  statusSummary: fixtureStatus("pending"),
  created: "2026-03-01T13:00:00Z",
};

export const fixtureRunFailed: ApiRunResponse = {
  id: "run-ghi",
  name: "lr=0.1",
  path: "projects/proj-alpha/experiments/exp-001/runs/lr=0.1",
  projectId: "proj-alpha",
  experimentId: "exp-001",
  definitionHash: "def-run-ghi",
  experimentRevisionId: "rev-exp-001",
  statusSummary: fixtureStatus("failed"),
  created: "2026-03-01T14:00:00Z",
};

export const fixtureRunCancelled: ApiRunResponse = {
  id: "run-jkl",
  name: "lr=1",
  path: "projects/proj-alpha/experiments/exp-001/runs/lr=1",
  projectId: "proj-alpha",
  experimentId: "exp-001",
  definitionHash: "def-run-jkl",
  experimentRevisionId: "rev-exp-001",
  statusSummary: fixtureStatus("cancelled"),
  created: "2026-03-01T15:00:00Z",
};

export const fixtureAsset: ApiAssetResponse = {
  id: "asset-001",
  projectId: "proj-alpha",
  title: "checkpoint.pt",
  name: "checkpoint.pt",
  kind: "artifact",
  scopeKind: "run",
  scopeIds: ["proj-alpha", "exp-001", "run-abc"],
  path: "artifacts/checkpoint.pt",
  createdAt: "2026-03-01T16:00:00Z",
  updatedAt: "2026-03-01T16:00:00Z",
  producer: {
    run_id: "run-abc",
    execution_id: "exec-001",
    task_id: null,
  },
  tags: {},
  extra: {
    mime: "application/octet-stream",
    size: 1024,
  },
};

export const fixtureProjectSummary: ProjectSummary = {
  id: "proj-alpha",
  name: "Alpha Project",
  path: "projects/alpha-project",
  status: "active",
  summary: "First project",
  updatedAt: "2026-03-01T00:00:00Z",
};

export const fixtureExperimentSummary: ExperimentSummary = {
  id: "exp-001",
  name: "Baseline",
  path: "projects/alpha-project/experiments/baseline",
  status: "active",
  summary: "Baseline experiment",
  workflowFile: "workflow.py",
  updatedAt: "2026-03-01T10:00:00Z",
  projectId: "proj-alpha",
  parameterSpace: {},
  workflowSource: "workflow.py",
};

export const fixtureRunSummary: RunSummary = {
  id: "run-abc",
  name: "lr=0.001",
  path: "projects/proj-alpha/experiments/exp-001/runs/lr=0.001",
  status: "succeeded",
  summary: "Status: succeeded",
  updatedAt: "2026-03-01T12:00:00Z",
  projectId: "proj-alpha",
  experimentId: "exp-001",
  definitionHash: "def-run-abc",
  experimentRevisionId: "rev-exp-001",
  statusSummary: { total: 1, active: 0, notStarted: false, byStatus: { succeeded: 1 } },
  parameters: {},
  workflowSource: "workflow.py",
  workflowSnapshot: null,
  startedAt: "2026-03-01T12:00:00Z",
  finishedAt: "2026-03-01T12:00:00Z",
  executionHistory: [],
  errorMessage: null,
};
