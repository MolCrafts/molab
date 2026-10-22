/**
 * Mock handlers for the Remote Operations (molq plugin) endpoints.
 */

import { HttpResponse, http } from "msw";
import { getAllProjects, getExperimentsByProject, getRunLogs, getRunsByExperiment } from "../db";

const API_BASE = "/api/plugins/molq";

const now = () => new Date().toISOString();

const targets = [
  {
    name: "hpc-slurm",
    scheduler: "slurm",
    clusterName: "mock-hpc",
    jobsDir: "/scratch/mock/jobs",
    healthy: true,
    healthReason: null,
    activeJobs: 0,
  },
  {
    name: "offline-example",
    scheduler: "slurm",
    clusterName: "offline.invalid",
    jobsDir: null,
    healthy: false,
    healthReason: "Simulated unavailable destination",
    activeJobs: 0,
  },
];
const buildJobs = () =>
  getAllProjects().flatMap((p) =>
    getExperimentsByProject(p.id).flatMap((e) =>
      getRunsByExperiment(e.id).flatMap((run) =>
        (run.executions ?? [])
          .filter((execution) => execution.executor?.backend === "molq")
          .map((execution) => ({
            target: "hpc-slurm",
            jobId: String(execution.executor?.scheduler_job_id ?? execution.id),
            schedulerJobId: String(execution.executor?.scheduler_job_id ?? execution.id),
            clusterName: "mock-hpc",
            scheduler: "slurm",
            name: `${e.name} · ${run.name}`,
            state: execution.status,
            submittedAt: execution.createdAt,
            startedAt: execution.startedAt ?? null,
            finishedAt: execution.finishedAt ?? null,
            exitCode:
              execution.status === "succeeded" ? 0 : execution.status === "failed" ? 1 : null,
            durationSeconds: execution.startedAt
              ? ((execution.finishedAt ? Date.parse(execution.finishedAt) : Date.now()) -
                  Date.parse(execution.startedAt)) /
                1000
              : null,
            cwd: `/${run.path}/executions/${execution.id}`,
            runId: run.id,
            executionId: execution.id,
          })),
      ),
    ),
  );

const computeStats = (jobs: ReturnType<typeof buildJobs>) => {
  const running = jobs.filter((j) => j.state === "running").length;
  const pending = jobs.filter((j) => ["queued", "submitted", "created"].includes(j.state)).length;
  const failed = jobs.filter((j) =>
    ["failed", "timed_out", "cancelled", "lost"].includes(j.state),
  ).length;
  const succeeded = jobs.filter((j) => j.state === "succeeded").length;
  const waits = jobs
    .filter((j) => j.startedAt && j.submittedAt)
    .map(
      (j) =>
        (new Date(j.startedAt as string).getTime() - new Date(j.submittedAt as string).getTime()) /
        1000,
    );
  const avgWaitSeconds = waits.length ? waits.reduce((a, b) => a + b, 0) / waits.length : null;
  return { running, pending, failed, succeeded, avgWaitSeconds };
};

export const molqHandlers = [
  http.get(`${API_BASE}/targets`, () => {
    return HttpResponse.json({
      targets: targets.map((t) => ({
        ...t,
        activeJobs: buildJobs().filter(
          (j) => j.target === t.name && ["queued", "running", "finalizing"].includes(j.state),
        ).length,
      })),
      total: targets.length,
    });
  }),

  http.get(`${API_BASE}/jobs`, ({ request }) => {
    const url = new URL(request.url);
    const target = url.searchParams.get("target");
    const all = buildJobs();
    const filtered = target ? all.filter((j) => j.target === target) : all;
    return HttpResponse.json({
      jobs: filtered,
      stats: computeStats(filtered),
      total: filtered.length,
    });
  }),

  http.get(`${API_BASE}/jobs/:jobId`, ({ params, request }) => {
    const url = new URL(request.url);
    const target = url.searchParams.get("target");
    const job = buildJobs().find(
      (j) => j.jobId === (params.jobId as string) && (!target || j.target === target),
    );
    if (!job) {
      return HttpResponse.json({ detail: "Job not found" }, { status: 404 });
    }
    return HttpResponse.json({
      ...job,
      failureReason: job.state === "failed" ? "Exit code 1" : null,
      metadata: { run_id: job.runId, execution_id: job.executionId, mock: "true" },
      commandDisplay: `python -m molab.cli execute /scratch/${job.jobId}`,
      transitions: [
        {
          timestamp: job.submittedAt ?? now(),
          fromState: null,
          toState: "created",
          reason: "job created",
        },
        {
          timestamp: job.submittedAt ?? now(),
          fromState: "created",
          toState: "submitted",
          reason: null,
        },
        ...(job.startedAt
          ? [
              {
                timestamp: job.startedAt,
                fromState: "submitted",
                toState: "running",
                reason: null,
              },
            ]
          : []),
        ...(job.finishedAt
          ? [
              {
                timestamp: job.finishedAt,
                fromState: "running",
                toState: job.state,
                reason: null,
              },
            ]
          : []),
      ],
      upstreamTotal: 0,
      upstreamSatisfied: 0,
      downstreamTotal: 0,
    });
  }),

  http.get(`${API_BASE}/jobs/:jobId/logs`, ({ params, request }) => {
    const target = new URL(request.url).searchParams.get("target");
    const job = buildJobs().find(
      (j) => j.jobId === params.jobId && (!target || j.target === target),
    );
    if (!job) return HttpResponse.json({ detail: "Job not found" }, { status: 404 });
    const lines = [...getRunLogs(job.runId), "[stream closed]"];
    return new HttpResponse(lines.map((line) => `data: ${JSON.stringify({ line })}\n\n`).join(""), {
      headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
    });
  }),
];
