/**
 * MSW mock handlers for the workspace ComputeTarget registry.
 *
 * The dev:mock store is in-memory — refreshing the page resets it.
 */

import { HttpResponse, http } from "msw";
import type { TargetCreateRequest } from "@/api/generated/models/TargetCreateRequest";
import type { TargetResponse } from "@/api/generated/models/TargetResponse";

const API_BASE = "/api";

const targets = new Map<string, TargetResponse>();

targets.set("laptop", { name: "laptop", scratchRoot: "/tmp/molab", isRemote: false });
targets.set("hpc-slurm", {
  name: "hpc-slurm",
  scratchRoot: "/scratch/me/molab",
  isRemote: true,
  registryId: "mock-registry",
  clusterId: "mock-hpc",
});

const toResponse = (t: TargetResponse) => t;

export const targetsHandlers = [
  http.get(`${API_BASE}/plugins/molq/destinations`, () =>
    HttpResponse.json({
      registryId: "mock-registry",
      destinations: [{ id: "mock-hpc", name: "hpc-slurm", scheduler: "slurm" }],
    }),
  ),
  http.get(`${API_BASE}/targets`, () => {
    const list = Array.from(targets.values()).map(toResponse);
    return HttpResponse.json({ targets: list, total: list.length });
  }),

  http.post(`${API_BASE}/targets`, async ({ request }) => {
    const body = (await request.json()) as TargetCreateRequest;
    if (targets.has(body.name)) {
      return HttpResponse.json(
        { detail: `compute target '${body.name}' already exists` },
        { status: 409 },
      );
    }
    const created: TargetResponse = {
      name: body.name,
      scratchRoot: body.scratchRoot,
      registryId: body.registryId,
      clusterId: body.clusterId,
      isRemote: body.clusterId != null,
    };
    targets.set(created.name, created);
    return HttpResponse.json(created, { status: 201 });
  }),

  http.delete(`${API_BASE}/targets/:name`, ({ params }) => {
    const name = String(params.name);
    if (!targets.has(name)) {
      return HttpResponse.json({ detail: `no compute target named '${name}'` }, { status: 404 });
    }
    targets.delete(name);
    return new HttpResponse(null, { status: 204 });
  }),

  http.post(`${API_BASE}/targets/:name/test`, ({ params }) => {
    const name = String(params.name);
    const target = targets.get(name);
    if (!target) {
      return HttpResponse.json({ detail: `no compute target named '${name}'` }, { status: 404 });
    }
    if (target.isRemote) {
      return HttpResponse.json({
        name,
        ok: false,
        error: "mock environment cannot reach remote hosts",
        checks: [{ label: "command execution", ok: false, detail: "ssh disabled in mock" }],
      });
    }
    return HttpResponse.json({
      name,
      ok: true,
      error: null,
      checks: [
        { label: "command execution", ok: true, detail: null },
        { label: `mkdir ${target.scratchRoot}`, ok: true, detail: null },
        { label: "file round-trip", ok: true, detail: null },
      ],
    });
  }),
];
