/** Physical attempts and their products share the mock filesystem used by the explorer. */
import { HttpResponse, http, type PathParams } from "msw";
import type { ExecutionAttemptCreateRequest } from "../../src/api/generated/models/ExecutionAttemptCreateRequest";
import type { ExecutionResponse } from "../../src/api/generated/models/ExecutionResponse";
import type { ManagedAssetResponse } from "../../src/api/generated/models/ManagedAssetResponse";
import type { RunFileNode } from "../../src/api/generated/models/RunFileNode";
import { createDirectory, type FileNode, getFile, getRun, setRun, writeFile } from "../db";
import { workspaceRoute } from "./workspaceRoute";

const RUN = "/api/projects/:projectId/experiments/:experimentId/runs/:runId";
const ATTEMPT = `${RUN}/executions/:executionId`;

const findRun = (params: PathParams) => {
  const run = getRun(String(params.runId));
  return run && run.projectId === params.projectId && run.experimentId === params.experimentId
    ? run
    : undefined;
};
const missing = () => HttpResponse.json({ detail: "Run or execution not found" }, { status: 404 });

/** Files the showcase treats as registered. A checkpoint stays a path, not an asset. */
const assetsFor = (runId: string, executionId: string): ManagedAssetResponse[] => {
  const run = getRun(runId);
  if (!run || !(run.executions ?? []).some((e) => e.id === executionId)) return [];
  return [
    {
      suffix: "metrics",
      path: "out/metrics.json",
      mediaType: "application/json",
      task: "analyze",
    },
    {
      suffix: "trajectory",
      path: "out/trajectory.xyz",
      mediaType: "chemical/x-xyz",
      task: "simulate",
    },
  ].flatMap((item) => {
    const file = getFile(`${run.path}/executions/${executionId}/${item.path}`);
    if (!file) return [];
    const id = `${executionId}-${item.suffix}`;
    return [
      {
        id,
        projectId: run.projectId,
        title: file.name,
        createdAt: run.created,
        ref: `molab:asset/${id}`,
        mediaType: item.mediaType,
        digest: `sha256:mock-${id}`,
        size: file.size ?? 0,
        file: item.path,
        originKind: "execution",
        runId,
        executionId,
        task: item.task,
        uri: null,
      },
    ];
  });
};

const fileNodes = (node: FileNode, root: string): RunFileNode => ({
  name: node.name,
  relPath: node.path.slice(root.length + 1),
  type: node.type,
  size: node.size,
  modified: node.modified ? Date.parse(node.modified) / 1000 : null,
  children: node.children?.map((child) => fileNodes(child, root)),
});

export const executionHandlers = [
  http.get(workspaceRoute(`${RUN}/executions`), ({ params }) => {
    const run = findRun(params);
    return run ? HttpResponse.json(run.executions ?? []) : missing();
  }),
  http.post(workspaceRoute(`${RUN}/executions`), async ({ params, request }) => {
    const run = findRun(params);
    if (!run) return missing();
    const body = (await request.json()) as ExecutionAttemptCreateRequest;
    if (
      (run.executions ?? []).some((e) => ["running", "queued", "finalizing"].includes(e.status))
    ) {
      return HttpResponse.json({ detail: "Run already has an active execution" }, { status: 409 });
    }
    if (body.basedOnExecutionId && !run.executions?.some((e) => e.id === body.basedOnExecutionId))
      return missing();
    const id = `e${String((run.executions?.length ?? 0) + 1).padStart(2, "0")}`;
    const createdAt = new Date().toISOString();
    const execution: ExecutionResponse = {
      id,
      runId: run.id,
      mode: body.mode ?? "initial",
      status: "running",
      createdAt,
      startedAt: createdAt,
      finishedAt: null,
      basedOnExecutionId: body.basedOnExecutionId ?? null,
      executor: {
        backend: body.target === "hpc-slurm" ? "molq" : "local",
        target: body.target ?? "laptop",
      },
      environment: { mock: true },
      error: null,
    };
    setRun({
      ...run,
      status: execution.status,
      finished: null,
      executions: [...(run.executions ?? []), execution],
    });
    const root = `/${run.path}/executions/${id}`;
    createDirectory(root);
    writeFile(`${root}/execution.json`, JSON.stringify(execution));
    writeFile(
      `${root}/run.log`,
      `INFO Synthetic ${execution.mode} execution started\nINFO prepare: running`,
    );
    if (run.workflowSource) {
      const graph = JSON.parse(run.workflowSource);
      graph.task_configs = graph.task_configs.map((task: Record<string, unknown>, i: number) => ({
        ...task,
        status: i === 0 ? "running" : "pending",
      }));
      writeFile(`${root}/workflow.json`, JSON.stringify(graph));
    }
    return HttpResponse.json(execution, { status: 201 });
  }),
  http.get(workspaceRoute(ATTEMPT), ({ params }) => {
    const execution = findRun(params)?.executions?.find((e) => e.id === params.executionId);
    return execution ? HttpResponse.json(execution) : missing();
  }),
  http.get(workspaceRoute(`${ATTEMPT}/outputs`), ({ params }) => {
    const run = findRun(params);
    const execution = run?.executions?.find((e) => e.id === params.executionId);
    if (!run || !execution) return missing();
    const root = `/${run.path}/executions/${execution.id}`;
    const assets = assetsFor(run.id, execution.id);
    const registered = new Set(assets.map((asset) => asset.file));
    const flatten = (node: FileNode): RunFileNode[] =>
      node.type === "folder" ? (node.children ?? []).flatMap(flatten) : [fileNodes(node, root)];
    const products = getFile(`${root}/out`);
    return HttpResponse.json({
      executionId: execution.id,
      stdout: getFile(`${root}/run.log`)?.content ?? null,
      stderr: getFile(`${root}/traceback.txt`)?.content ?? null,
      runtime: `Synthetic example · ${execution.executor?.target ?? "laptop"} · Python 3.13`,
      assets,
      evidence: ["execution.json", "workflow.json", "run.log", "traceback.txt"].flatMap((path) => {
        const file = getFile(`${root}/${path}`);
        return file
          ? [{ kind: path.endsWith(".json") ? "record" : "log", path, size: file.size ?? 0 }]
          : [];
      }),
      unregistered: products ? flatten(products).filter((n) => !registered.has(n.relPath)) : [],
      results: run.results ?? {},
    });
  }),
  http.get(workspaceRoute(`${ATTEMPT}/logs`), ({ params }) => {
    const run = findRun(params);
    if (!run?.executions?.some((e) => e.id === params.executionId)) return missing();
    const root = `${run.path}/executions/${params.executionId}`;
    return HttpResponse.json({
      executionId: params.executionId,
      stdout: getFile(`${root}/run.log`)?.content ?? null,
      stderr: getFile(`${root}/traceback.txt`)?.content ?? null,
    });
  }),
  http.get(workspaceRoute(`${ATTEMPT}/workflow`), ({ params }) => {
    const run = findRun(params);
    const execution = run?.executions?.find((e) => e.id === params.executionId);
    if (!run || !execution) return missing();
    const content = getFile(`${run.path}/executions/${execution.id}/workflow.json`)?.content;
    return HttpResponse.json({
      executionId: execution.id,
      status: execution.status,
      workflow: content ? JSON.parse(content) : null,
    });
  }),
  http.get(workspaceRoute(`${ATTEMPT}/files`), ({ params }) => {
    const run = findRun(params);
    if (!run?.executions?.some((e) => e.id === params.executionId)) return missing();
    const root = `/${run.path}/executions/${params.executionId}`;
    return HttpResponse.json({
      runId: run.id,
      runDir: root,
      nodes: (getFile(root)?.children ?? []).map((n) => fileNodes(n, root)),
      dirs: [
        { name: "out", purpose: "Task products", products: true, versioned: false },
        { name: "checkpoints", purpose: "Resume state", products: false, versioned: true },
      ],
    });
  }),
  http.get(workspaceRoute(`${ATTEMPT}/file/text`), ({ params, request }) => {
    const run = findRun(params);
    if (!run?.executions?.some((e) => e.id === params.executionId)) return missing();
    const path = new URL(request.url).searchParams.get("path") ?? "";
    if (path.startsWith("/") || path.split("/").includes(".."))
      return HttpResponse.json({ detail: "Path outside execution" }, { status: 403 });
    const file = getFile(`${run.path}/executions/${params.executionId}/${path}`);
    if (file?.type !== "file")
      return HttpResponse.json({ detail: "File not found" }, { status: 404 });
    return HttpResponse.json({ path, content: file.content ?? "", size: file.size ?? 0 });
  }),
  http.post(workspaceRoute(`${ATTEMPT}/cancel`), ({ params }) => {
    const run = findRun(params);
    const execution = run?.executions?.find((e) => e.id === params.executionId);
    if (!run || !execution) return missing();
    if (!["running", "queued", "finalizing"].includes(execution.status))
      return HttpResponse.json({ detail: "Execution is already terminal" }, { status: 409 });
    const finishedAt = new Date().toISOString();
    setRun({
      ...run,
      status: "cancelled",
      finished: finishedAt,
      executions: run.executions?.map((e) =>
        e.id === execution.id ? { ...e, status: "cancelled", finishedAt } : e,
      ),
    });
    writeFile(
      `${run.path}/executions/${execution.id}/execution.json`,
      JSON.stringify(getRun(run.id)?.executions?.find((e) => e.id === execution.id)),
    );
    return HttpResponse.json({
      runId: run.id,
      executionId: execution.id,
      status: "cancelled",
      message: "Synthetic execution cancelled",
    });
  }),
  http.get(workspaceRoute(`${ATTEMPT}/assets/:assetId/content`), ({ params }) => {
    const run = findRun(params);
    const asset = assetsFor(String(params.runId), String(params.executionId)).find(
      (item) => item.id === params.assetId,
    );
    if (!run || !asset) return missing();
    const file = getFile(`${run.path}/executions/${params.executionId}/${asset.file}`);
    return new HttpResponse(file?.content ?? "", {
      headers: {
        "Content-Type": asset.mediaType ?? "application/octet-stream",
        "Content-Disposition": `attachment; filename="${asset.title}"`,
      },
    });
  }),
  http.post(workspaceRoute(`${ATTEMPT}/molplot/ingest`), ({ params }) =>
    findRun(params) ? HttpResponse.json({ ingested: 51, warnings: [] }) : missing(),
  ),
  http.get(workspaceRoute(`${RUN}/tensorboard/scalars`), ({ params, request }) => {
    const run = findRun(params);
    if (!run) return missing();
    const tags = new URL(request.url).searchParams.getAll("tag");
    return HttpResponse.json({
      runId: run.id,
      runDir: run.path,
      logdirs: ["tensorboard"],
      series: ["loss/train", "loss/validation"]
        .filter((tag) => !tags.length || tags.includes(tag))
        .map((tag, index) => ({
          logdir: "tensorboard",
          tag,
          points: Array.from({ length: 60 }, (_, i) => ({
            step: i * 100,
            wallTime: Date.parse(run.created) / 1000 + i,
            value: 0.1 + index * 0.03 + Math.exp(-i / 12) * 0.6 + Math.sin(i) * 0.01,
          })),
        })),
    });
  }),
];
