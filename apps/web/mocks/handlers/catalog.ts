/** Resolve known files through entity definitions; directory names are never treated as IDs. */
import { HttpResponse, http } from "msw";
import { getAllAssets, getAllProjects, getExperimentsByProject, getRunsByExperiment } from "../db";
import { workspaceRoute } from "./workspaceRoute";

export const catalogHandlers = [
  http.get(workspaceRoute("/api/catalog/by-path"), ({ request }) => {
    const rel = (new URL(request.url).searchParams.get("path") ?? "").replace(/^\/+/, "");
    const projects = getAllProjects();
    const project = projects.find((p) => rel === p.path || rel.startsWith(`${p.path}/`));
    const experiment = project
      ? getExperimentsByProject(project.id).find(
          (e) => rel === e.path || rel.startsWith(`${e.path}/`),
        )
      : undefined;
    const run = experiment
      ? getRunsByExperiment(experiment.id).find(
          (r) => rel === r.path || rel.startsWith(`${r.path}/`),
        )
      : undefined;
    const asset = getAllAssets().find((a) => rel === `managed-assets/${a.id}/payload`);
    return HttpResponse.json({
      matched: Boolean(asset),
      workspaceRelPath: rel,
      assetId: asset?.id ?? null,
      assetKind: asset?.kind ?? null,
      producer: asset?.producer
        ? {
            runId: asset.producer.run_id ?? null,
            taskId: asset.producer.task_id ?? null,
            executionId: asset.producer.executionId ?? null,
          }
        : null,
      scope: {
        kind: run ? "run" : experiment ? "experiment" : project ? "project" : "workspace",
        projectId: project?.id ?? null,
        experimentId: experiment?.id ?? null,
        runId: run?.id ?? null,
      },
      siblings: [],
    });
  }),
];
