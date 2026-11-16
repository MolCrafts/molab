import { strToU8, zipSync } from "fflate";
import { HttpResponse, http } from "msw";
import type { RunCreateRequest } from "../../src/api/generated/models/RunCreateRequest";
import type { ApiRunResponse } from "../../src/app/types";
import {
  createDirectory,
  type FileNode,
  getExperiment,
  getFile,
  getRun,
  getRunsByExperiment,
  mockRunSlug,
  setRun,
  writeFile,
} from "../db";
import { workspaceRoute } from "./workspaceRoute";

const BASE = "/api/projects/:projectId/experiments/:experimentId/runs";
export const runHandlers = [
  http.get(workspaceRoute(BASE), ({ params }) =>
    HttpResponse.json(
      getRunsByExperiment(String(params.experimentId)).filter(
        (r) => r.projectId === params.projectId,
      ),
    ),
  ),
  http.post(workspaceRoute(BASE), async ({ params, request }) => {
    const experiment = getExperiment(String(params.experimentId));
    if (!experiment || experiment.projectId !== params.projectId)
      return HttpResponse.json({ detail: "Experiment not found" }, { status: 404 });
    const body = (await request.json()) as RunCreateRequest;
    const id = `run-${crypto.randomUUID()}`;
    const name = mockRunSlug(id, body.params ?? {});
    const run: ApiRunResponse = {
      id,
      name,
      path: `${experiment.path}/runs/${name}`,
      projectId: experiment.projectId,
      experimentId: experiment.id,
      created: new Date().toISOString(),
      parameters: body.params ?? {},
      workflowSource: experiment.workflow ?? null,
      target: body.target ?? null,
      ref: `molab:experiment/${experiment.id}/run/${id}`,
      executions: [],
      status: "pending",
    };
    setRun(run);
    createDirectory(`/${run.path}`);
    writeFile(`/${run.path}/run.json`, JSON.stringify({ id, params: run.parameters }));
    return HttpResponse.json(getRun(id), { status: 201 });
  }),
  http.get(workspaceRoute(`${BASE}/:runId/export`), ({ params }) => {
    const run = getRun(String(params.runId));
    if (!run || run.projectId !== params.projectId || run.experimentId !== params.experimentId)
      return HttpResponse.json({ detail: "Run not found" }, { status: 404 });
    const archive: Record<string, Uint8Array> = {};
    const collect = (node: FileNode): void => {
      if (node.type === "folder") node.children?.forEach(collect);
      else
        archive[node.path.slice(run.path.length + 2)] = node.bytes ?? strToU8(node.content ?? "");
    };
    const root = getFile(run.path);
    if (root) collect(root);
    return new HttpResponse(new Blob([Uint8Array.from(zipSync(archive)).buffer]), {
      headers: {
        "Content-Type": "application/zip",
        "Content-Disposition": `attachment; filename="${run.id}.zip"`,
      },
    });
  }),
  http.get(workspaceRoute(`${BASE}/:runId`), ({ params }) => {
    const run = getRun(String(params.runId));
    return run && run.projectId === params.projectId && run.experimentId === params.experimentId
      ? HttpResponse.json(run)
      : HttpResponse.json({ detail: "Run not found" }, { status: 404 });
  }),
];
