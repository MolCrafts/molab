import { beforeEach, describe, expect, it } from "@rstest/core";
import { strFromU8, unzipSync } from "fflate";
import { getResponse } from "msw";
import type { AssetVersionResponse } from "../../../src/api/generated/models/AssetVersionResponse";
import type { ExecutionOutputsResponse } from "../../../src/api/generated/models/ExecutionOutputsResponse";
import type { ExecutionResponse } from "../../../src/api/generated/models/ExecutionResponse";
import type { RunResponse } from "../../../src/api/generated/models/RunResponse";
import {
  getAllProjects,
  getExperimentsByProject,
  getRunsByExperiment,
  resetDatabase,
} from "../../db";
import { handlers } from "../index";

Reflect.set(globalThis, "location", new URL("http://localhost/"));
const request = async (path: string, init?: RequestInit): Promise<Response> => {
  const response = await getResponse(handlers, new Request(`http://localhost/api${path}`, init));
  if (!response) throw new Error(`No mock response for ${path}`);
  return response;
};
const json = async <T>(path: string): Promise<T> => {
  const response = await request(path);
  expect(response.status).toBe(200);
  return response.json() as Promise<T>;
};
const post = (data: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(data),
});
const base = "/projects/protein-folding/experiments/exp-001/runs/run-001";
const attempt = `${base}/executions/exec-run-001-01`;

describe("offline showcase contracts", () => {
  beforeEach(() => resetDatabase());

  it("exposes every seeded run and attempt through the current API, including explicit workspace reads", async () => {
    for (const project of getAllProjects()) {
      for (const exp of getExperimentsByProject(project.id)) {
        const path = `/projects/${project.id}/experiments/${exp.id}`;
        const runs = await json<RunResponse[]>(`${path}/runs`);
        expect(runs).toHaveLength(getRunsByExperiment(exp.id).length);
        for (const run of runs) {
          const executions = await json<ExecutionResponse[]>(`${path}/runs/${run.id}/executions`);
          expect(executions).toEqual(run.executions);
          expect(run.statusSummary.total).toBe(executions.length);
          for (const execution of executions) {
            const outputs = await json<ExecutionOutputsResponse>(
              `${path}/runs/${run.id}/executions/${execution.id}/outputs`,
            );
            expect(outputs.executionId).toBe(execution.id);
            for (const artifact of outputs.artifacts ?? []) {
              const content = await request(
                `${path}/runs/${run.id}/executions/${execution.id}/artifacts/${artifact.id}/content`,
              );
              expect((await content.arrayBuffer()).byteLength).toBe(artifact.size);
            }
          }
        }
      }
    }
    const flat = await json(`${attempt}/files`);
    expect(await json(`/workspaces/feature-showcase${attempt}/files`)).toEqual(flat);
    expect((await request(`/workspaces/not-served${attempt}/files`)).status).toBe(501);
  });

  it("has comparable scientific results and a genuine empty experiment", async () => {
    const runs = await json<RunResponse[]>("/projects/nve-drift/experiments/exp-nve/runs");
    expect(runs).toHaveLength(12);
    expect(new Set(runs.map((r) => r.parameters?.driver))).toEqual(new Set(["ase", "lib_md3"]));
    expect(new Set(runs.map((r) => r.parameters?.timestep_fs))).toEqual(new Set([0.5, 1, 2]));
    expect(await json("/projects/nve-drift/experiments/exp-planned/runs")).toEqual([]);
    const outputs = await json<ExecutionOutputsResponse>(
      "/projects/nve-drift/experiments/exp-nve/runs/md-001/executions/exec-md-001-01/outputs",
    );
    expect(outputs.results?.energy_drift).toBe(0.000037);
  });

  it("reads a journal, failed evidence, raw plots and multi-frame structures without fallback data", async () => {
    const journal = await json<{ workflow: { task_configs: Array<{ status: string }> } }>(
      `${attempt}/workflow`,
    );
    expect(journal.workflow.task_configs.every((t) => t.status === "completed")).toBe(true);
    const outputs = await json<ExecutionOutputsResponse>(
      "/projects/protein-folding/experiments/exp-001/runs/run-003/executions/exec-run-003-01/outputs",
    );
    expect(outputs.stderr).toContain("CUDA out of memory");
    expect(outputs.evidence?.some((e) => e.path === "traceback.txt")).toBe(true);
    const xyz = await json<{ content: string; size: number }>(
      `${attempt}/file/text?path=out/trajectory.xyz`,
    );
    expect(xyz.content.match(/frame /g)).toHaveLength(12);
    expect(new TextEncoder().encode(xyz.content).byteLength).toBe(xyz.size);
    const plot = await json<{ content: string }>(
      `${attempt}/file/text?path=out/observables/energy.mlp.vl.json`,
    );
    expect(JSON.parse(plot.content).data.values).toHaveLength(51);
    expect((await request(`${attempt}/file/text?path=../../secret`)).status).toBe(403);
    expect((await request(`${attempt}/file/text?path=missing.txt`)).status).toBe(404);
  });

  it("round-trips binary uploads and exports valid ZIPs containing the same files", async () => {
    const bytes = new Uint8Array([0, 255, 128, 65, 0, 13]);
    expect(
      (
        await request("/workspace/file/upload?path=uploads/example.bin", {
          method: "POST",
          body: bytes,
        })
      ).status,
    ).toBe(201);
    const downloaded = await request("/workspace/file/blob?path=uploads/example.bin");
    expect(new Uint8Array(await downloaded.arrayBuffer())).toEqual(bytes);
    const files = await json<{ children: Array<{ path: string }> }>(
      "/workspace/files?path=uploads",
    );
    expect(files.children.map((f) => f.path)).toContain("/uploads/example.bin");
    const archive = unzipSync(
      new Uint8Array(await (await request(`${base}/export`)).arrayBuffer()),
    );
    expect(JSON.parse(strFromU8(archive["run.json"])).id).toBe("run-001");
    expect(strFromU8(archive["executions/exec-run-001-01/out/trajectory.xyz"])).toContain(
      "frame 12",
    );
  });

  it("creates and cancels a retry while keeping dashboard attempts consistent", async () => {
    const response = await request(
      `${base}/executions`,
      post({ mode: "retry", basedOnExecutionId: "exec-run-001-01", target: "laptop" }),
    );
    expect(response.status).toBe(201);
    const execution = (await response.json()) as ExecutionResponse;
    expect(execution.mode).toBe("retry");
    expect((await request(`${base}/executions/${execution.id}/cancel`, post({}))).status).toBe(200);
    const run = await json<RunResponse>(base);
    expect(run.executions?.find((e) => e.id === execution.id)?.status).toBe("cancelled");
    expect(run.statusSummary.byStatus).toEqual({ succeeded: 1, cancelled: 1 });
    const dashboard = await json<{
      runs: Array<{ id: string; executions: Array<{ executionId: string; status: string }> }>;
    }>("/workspace/runs");
    expect(
      dashboard.runs
        .find((r) => r.id === "run-001")
        ?.executions.find((e) => e.executionId === execution.id)?.status,
    ).toBe("cancelled");
    expect((await request(`${base}/executions/${execution.id}/cancel`, post({}))).status).toBe(409);
  });

  it("promotes artifact bytes into versioned project assets", async () => {
    const versions = await json<AssetVersionResponse[]>(
      "/projects/protein-folding/assets/asset-003/versions",
    );
    expect(versions.map((v) => v.version)).toEqual([1, 2]);
    const response = await request(
      `${attempt}/artifacts/exec-run-001-01-metrics/promote`,
      post({ title: "Benchmark metrics", intoAssetId: "asset-003" }),
    );
    expect(response.status).toBe(201);
    const promoted = await json<AssetVersionResponse[]>(
      "/projects/protein-folding/assets/asset-003/versions",
    );
    expect(promoted).toHaveLength(3);
    expect(promoted[2].sourceArtifactId).toBe("exec-run-001-01-metrics");
    const content = await request("/projects/protein-folding/assets/asset-003/download");
    expect((await content.json()).plddt_mean).toBe(87.4);
  });

  it("covers knowledge classes, search, harvest, task registry and notebook export", async () => {
    const knowledge = await json<{ notes: Array<{ cls: string }> }>("/knowledge");
    expect(new Set(knowledge.notes.map((n) => n.cls))).toEqual(
      new Set(["Note", "Finding", "Observation", "Report", "Plan", "Literature"]),
    );
    const search = await json<{ hits: unknown[] }>("/knowledge/search?q=energy");
    expect(search.hits.length).toBeGreaterThan(0);
    const harvested = await request(
      `${base}/harvest`,
      post({ narrative: "Stable baseline", name: "contract-harvest" }),
    );
    expect(harvested.status).toBe(201);
    const doc = (await harvested.json()) as { path: string };
    const note = await json<{ body: string }>(
      `/knowledge/note?path=${encodeURIComponent(doc.path)}`,
    );
    expect(note.body).toContain("Stable baseline");
    const archive = unzipSync(
      new Uint8Array(await (await request("/knowledge/export")).arrayBuffer()),
    );
    expect(archive[doc.path]).toBeDefined();
    const registry = await json<{ total: number; taskTypes: Array<{ slug: string }> }>("/tasks");
    expect(registry.total).toBeGreaterThan(0);
    for (const task of registry.taskTypes)
      expect((await request(`/tasks/${task.slug}`)).status).toBe(200);
  });

  it("keeps CRUD counts and filesystem branches consistent", async () => {
    const deleted = await request("/projects/nve-drift/experiments/exp-nve", { method: "DELETE" });
    expect(deleted.status).toBe(200);
    expect(getRunsByExperiment("exp-nve")).toHaveLength(0);
    const project = await json<{ experimentCount: number }>("/projects/nve-drift");
    expect(project.experimentCount).toBe(1);
    expect((await request("/projects/nve-drift/experiments/exp-nve/runs/md-001")).status).toBe(404);
    const listing = await json<{ children: Array<{ name: string }> }>(
      "/workspace/files?path=projects/nve-drift/experiments",
    );
    expect(listing.children.map((n) => n.name)).toEqual(["thermostat-validation"]);
    expect(
      (
        await request("/workspace/file/upload?path=uploads/note.txt", {
          method: "POST",
          body: "Uploaded text",
        })
      ).status,
    ).toBe(201);
    expect((await json<{ content: string }>("/workspace/file?path=uploads/note.txt")).content).toBe(
      "Uploaded text",
    );
  });

  it("links queue jobs to the same executions and exposes logs and history", async () => {
    const queue = await json<{
      jobs: Array<{ jobId: string; runId: string; executionId: string }>;
    }>("/plugins/molq/jobs");
    expect(queue.jobs.length).toBeGreaterThan(0);
    for (const job of queue.jobs) {
      const detail = await json<{ metadata: { run_id: string } }>(
        `/plugins/molq/jobs/${job.jobId}`,
      );
      expect(detail.metadata.run_id).toBe(job.runId);
    }
    expect(
      await (await request(`/plugins/molq/jobs/${queue.jobs[0].jobId}/logs`)).text(),
    ).toContain("data:");
    const history = await json<unknown[]>("/history");
    expect(history.length).toBeGreaterThan(10);
    const scalar = await json<{ series: Array<{ points: unknown[] }> }>(
      `${base}/tensorboard/scalars?tag=loss/train`,
    );
    expect(scalar.series).toHaveLength(1);
    expect(scalar.series[0].points).toHaveLength(60);
  });
});
