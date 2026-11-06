/**
 * Mock handlers for Experiment API endpoints
 */

import { HttpResponse, http } from "msw";
import type { ExperimentCreateRequest } from "../../src/api/generated/models/ExperimentCreateRequest";
import type { ApiExperimentResponse } from "../../src/app/types";
import {
  deleteExperiment,
  getExperiment,
  getExperimentsByProject,
  getRunsByExperiment,
  setExperiment,
} from "../db";
import { workspaceRoute } from "./workspaceRoute";

const API_BASE = "/api";

/**
 * A directory name derived from a display name — the same shape the server
 * produces, so the mock shows a path a person would recognise.
 */
const slugify = (name: string): string =>
  name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "") || "unnamed";

export const experimentHandlers = [
  // GET /api/projects/:projectId/experiments - List experiments for a project
  http.get(workspaceRoute(`${API_BASE}/projects/:projectId/experiments`), ({ params }) => {
    const { projectId } = params;
    const experiments = getExperimentsByProject(projectId as string);
    return HttpResponse.json(
      experiments.map((e) => ({ ...e, runCount: getRunsByExperiment(e.id).length })),
    );
  }),
  http.get(
    workspaceRoute(`${API_BASE}/projects/:projectId/experiments/:experimentId`),
    ({ params }) => {
      const experiment = getExperiment(String(params.experimentId));
      if (!experiment || experiment.projectId !== params.projectId)
        return HttpResponse.json({ detail: "Experiment not found" }, { status: 404 });
      const runs = getRunsByExperiment(experiment.id);
      return HttpResponse.json({
        ...experiment,
        runCount: runs.length,
        runs: runs.map((r) => ({
          id: r.id,
          statusSummary: r.statusSummary,
          created: r.created,
          finished: r.finished,
          parameters: r.parameters,
        })),
      });
    },
  ),
  // POST /api/projects/:projectId/experiments - Create new experiment
  http.post(
    workspaceRoute(`${API_BASE}/projects/:projectId/experiments`),
    async ({ request, params }) => {
      const { projectId } = params;
      const body = (await request.json()) as ExperimentCreateRequest;

      const experimentId = body.name?.toLowerCase().replace(/\s+/g, "-") || `exp-${Date.now()}`;
      const newExperiment: ApiExperimentResponse = {
        id: experimentId,
        projectId: projectId as string,
        name: body.name,
        path: `projects/${projectId}/experiments/${slugify(body.name)}`,
        description: body.description || "",
        workflow: body.workflowSource ? JSON.stringify(body.workflowSource) : null,
        workflowKind: "document",
        gitCommit: null,
        parameterSpace: body.parameterSpace || {},
        runCount: 0,
        runs: [],
        created: new Date().toISOString(),
        ref: `molab:experiment/${experimentId}`,
      };

      setExperiment(newExperiment);
      return HttpResponse.json(newExperiment, { status: 201 });
    },
  ),

  http.get(
    workspaceRoute(`${API_BASE}/projects/:projectId/experiments/:experimentId/workflow`),
    ({ params }) => {
      const experiment = getExperiment(String(params.experimentId));
      if (!experiment || experiment.projectId !== params.projectId)
        return HttpResponse.json({ detail: "Experiment not found" }, { status: 404 });
      return HttpResponse.json({
        project_id: params.projectId,
        experiment_id: experiment.id,
        document: experiment.workflow ? JSON.parse(experiment.workflow) : null,
      });
    },
  ),
  // PUT /api/projects/:projectId/experiments/:experimentId/workflow - Persist
  // workflow IR onto the experiment (no codec normalization in mock mode; the
  // raw document round-trips so mapWorkflows parses it after a refresh).
  http.put(
    workspaceRoute(`${API_BASE}/projects/:projectId/experiments/:experimentId/workflow`),
    async ({ request, params }) => {
      const { projectId, experimentId } = params;
      const experiment = getExperiment(experimentId as string);
      if (!experiment) {
        return HttpResponse.json(
          { message: `Experiment ${experimentId} not found` },
          { status: 404 },
        );
      }
      const body = (await request.json()) as { document: Record<string, unknown> };
      setExperiment({ ...experiment, workflow: JSON.stringify(body.document) });
      return HttpResponse.json({
        project_id: projectId as string,
        experiment_id: experimentId as string,
        document: body.document,
      });
    },
  ),

  // GET /api/projects/:projectId/experiments/:experimentId/comparison - Sweep matrix
  http.get(
    workspaceRoute(`${API_BASE}/projects/:projectId/experiments/:experimentId/comparison`),
    ({ params }) => {
      const { projectId, experimentId } = params;
      const runs = getRunsByExperiment(experimentId as string);
      const paramKeys = new Set<string>();
      for (const r of runs) {
        for (const key of Object.keys(r.parameters ?? {})) paramKeys.add(key);
      }
      const metricKeys = [...new Set(runs.flatMap((r) => Object.keys(r.results ?? {})))];
      return HttpResponse.json({
        experimentId: experimentId as string,
        projectId: projectId as string,
        paramKeys: Array.from(paramKeys).sort(),
        metricKeys,
        runs: runs.map((r) => {
          const finished = r.finished ? new Date(r.finished).getTime() : null;
          const created = new Date(r.created).getTime();
          const durationSec = finished !== null ? Math.max(0, (finished - created) / 1000) : null;
          return {
            runId: r.id,
            status: r.status,
            parameters: r.parameters,
            metrics: r.results ?? {},
            durationSec,
            created: r.created,
            finished: r.finished ?? null,
            error: null,
          };
        }),
      });
    },
  ),

  // DELETE /api/projects/:projectId/experiments/:experimentId - Delete experiment
  http.delete(
    workspaceRoute(`${API_BASE}/projects/:projectId/experiments/:experimentId`),
    ({ params }) => {
      const { experimentId } = params;
      const deleted = deleteExperiment(experimentId as string);

      if (!deleted) {
        return HttpResponse.json(
          { message: `Experiment ${experimentId} not found` },
          { status: 404 },
        );
      }

      return HttpResponse.json({ message: "Experiment deleted" });
    },
  ),
];
