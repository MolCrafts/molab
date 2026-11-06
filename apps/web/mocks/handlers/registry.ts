/**
 * Mock handlers for Registry API endpoints.
 *
 * After spec 07: ``GET /api/plugins`` returns only third-party UI
 * bundles, each as ``{id, manifestUrl, entryUrl}``. Built-in plugins
 * (``core``, ``metrics``, ``molq``, ``molvis``) are statically imported
 * on the frontend and do NOT appear here. Per-plugin
 * ``manifest.json`` files are served from
 * ``GET /api/plugins/<id>/manifest.json``.
 */

import { HttpResponse, http } from "msw";

const API_BASE = "/api";

interface MockBundle {
  id: string;
  name: string;
  version: string;
  capabilities?: string[];
}

const MOCK_BUNDLES: MockBundle[] = [
  {
    id: "example",
    name: "Example Plugin",
    version: "0.0.1",
    capabilities: ["example_renderer"],
  },
];

const taskTypes = [
  { slug: "dataset.prepare", description: "Validate and prepare input data" },
  { slug: "model.alphafold", description: "Predict protein structures" },
  { slug: "simulation.gromacs", description: "Run molecular dynamics" },
  { slug: "simulation.lammps", description: "Run a LAMMPS simulation" },
  { slug: "simulation.dft", description: "Compute electronic structure" },
  { slug: "structure.prepare", description: "Prepare a simulation structure" },
  { slug: "metrics.evaluate", description: "Evaluate scientific observables" },
  { slug: "artifact.publish", description: "Register output artifacts" },
];

export const registryHandlers = [
  http.get(`${API_BASE}/plugins`, () => {
    return HttpResponse.json({
      plugins: MOCK_BUNDLES.map((b) => ({
        id: b.id,
        manifestUrl: `${API_BASE}/plugins/${b.id}/manifest.json`,
        entryUrl: `${API_BASE}/plugins/${b.id}/index.js`,
      })),
      total: MOCK_BUNDLES.length,
    });
  }),

  http.get(`${API_BASE}/plugins/:id/manifest.json`, ({ params }) => {
    const id = params.id as string;
    const bundle = MOCK_BUNDLES.find((b) => b.id === id);
    if (!bundle) {
      return new HttpResponse(null, { status: 404 });
    }
    return HttpResponse.json({
      id: bundle.id,
      name: bundle.name,
      version: bundle.version,
      api_version: "1",
      entry: "index.js",
      capabilities: bundle.capabilities ?? [],
    });
  }),

  http.get(`${API_BASE}/plugins/:id/index.js`, ({ params }) => {
    const id = params.id as string;
    const bundle = MOCK_BUNDLES.find((b) => b.id === id);
    if (!bundle) {
      return new HttpResponse(null, { status: 404 });
    }
    // Minimal ESM module that satisfies UiPluginModule shape and bumps a
    // global flag the runtime evaluator can assert on. dev:mock has no
    // real bundle file behind the URL, so we synthesize one here.
    const source = `
const plugin = {
  id: ${JSON.stringify(bundle.id)},
  register() {
    if (typeof globalThis !== "undefined") {
      const w = globalThis;
      w.__molabMockPluginRegistered ??= [];
      w.__molabMockPluginRegistered.push(${JSON.stringify(bundle.id)});
    }
  },
};
export default plugin;
`;
    return new HttpResponse(source, {
      status: 200,
      headers: { "Content-Type": "application/javascript" },
    });
  }),

  http.get(`${API_BASE}/tasks`, () => HttpResponse.json({ taskTypes, total: taskTypes.length })),
  http.get(`${API_BASE}/tasks/:nodeId`, ({ params }) => {
    const task = taskTypes.find((task) => task.slug === params.nodeId);
    return task
      ? HttpResponse.json(task)
      : HttpResponse.json({ detail: "Task not found" }, { status: 404 });
  }),
];
