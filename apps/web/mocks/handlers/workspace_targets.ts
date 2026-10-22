/**
 * MSW mock handlers for the remote-workspace descriptor registry
 * (POST /api/workspace/targets and friends), plus the extended
 * POST /api/workspace/open that accepts a discriminated kind=remote
 * payload.
 *
 * The dev:mock store is in-memory — refreshing the page resets it.
 */

import { HttpResponse, http } from "msw";

import type { TargetTestResponse } from "@/api/generated/models/TargetTestResponse";
import type { WorkspaceTargetCreateRequest } from "@/api/generated/models/WorkspaceTargetCreateRequest";
import type { WorkspaceTargetResponse } from "@/api/generated/models/WorkspaceTargetResponse";

const API_BASE = "/api";

const targets = new Map<string, WorkspaceTargetResponse>();

const seed = (t: WorkspaceTargetResponse): void => {
  targets.set(t.name, t);
};

seed({
  name: "lab",
  registryId: "mock-registry",
  clusterId: "mock-hpc",
  rootPath: "/scratch/me/molab-lab",
});
seed({
  name: "hpc-allegro",
  registryId: "mock-registry",
  clusterId: "mock-hpc",
  rootPath: "/scratch/me/allegro",
});

const activeDescriptor: string | null = null;

export const workspaceTargetsHandlers = [
  http.get(`${API_BASE}/workspace/targets`, () => {
    return HttpResponse.json({
      targets: Array.from(targets.values()),
      total: targets.size,
    });
  }),

  http.post(`${API_BASE}/workspace/targets`, async ({ request }) => {
    const body = (await request.json()) as WorkspaceTargetCreateRequest;
    if (targets.has(body.name)) {
      return HttpResponse.json(
        { detail: `workspace target ${body.name} already exists` },
        { status: 409 },
      );
    }
    const created: WorkspaceTargetResponse = {
      name: body.name,
      registryId: body.registryId,
      clusterId: body.clusterId,
      rootPath: body.rootPath,
      cacheMode: body.cacheMode,
    };
    targets.set(created.name, created);
    return HttpResponse.json(created, { status: 201 });
  }),

  http.delete(`${API_BASE}/workspace/targets/:name`, ({ params }) => {
    const name = String(params.name);
    if (!targets.has(name)) {
      return HttpResponse.json({ detail: `workspace target ${name} not found` }, { status: 404 });
    }
    targets.delete(name);
    return new HttpResponse(null, { status: 204 });
  }),

  http.post(`${API_BASE}/workspace/targets/:name/test`, ({ params }) => {
    const name = String(params.name);
    if (!targets.has(name)) {
      return HttpResponse.json({ detail: `workspace target ${name} not found` }, { status: 404 });
    }
    // Deterministic happy/fail seeded by name: anything containing "fail" fails.
    const ok = !name.toLowerCase().includes("fail");
    const body: TargetTestResponse = ok
      ? {
          name,
          ok: true,
          checks: [
            { label: "mkdir rootPath", ok: true, detail: null },
            { label: "file round-trip", ok: true, detail: null },
          ],
          error: null,
        }
      : {
          name,
          ok: false,
          checks: [
            {
              label: "mkdir rootPath",
              ok: false,
              detail: "simulated mkdir failure (mock)",
            },
          ],
          error: "mkdir failed (mock)",
        };
    return HttpResponse.json(body);
  }),
];

export const mockWorkspaceTargetsMap = targets;

export const __mockActiveDescriptor = (): string | null => activeDescriptor;
