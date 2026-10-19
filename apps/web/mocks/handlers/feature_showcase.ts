/**
 * Cross-feature fixtures for `npm run dev:web` (leaf `npm run dev`).
 *
 * Domain handlers own entity CRUD. This file fills the small read models that
 * span domains (knowledge, cache and workspaces),
 * so every navigation destination can be exercised without a Python server.
 */

import { strToU8, zipSync } from "fflate";
import { HttpResponse, http } from "msw";
import {
  deleteFile,
  getAllProjects,
  getExperiment,
  getExperimentsByProject,
  getFile,
  getRun,
  getRunsByExperiment,
  writeFile,
} from "../db";
import { workspaceRoute } from "./workspaceRoute";

interface ShowcaseNote {
  cls?: string;
  name: string;
  relPath: string;
  hostPath: string;
  excerpt: string;
  status: string;
  tags: string[];
  body: string;
  links: string[];
}

const documentSlug = (name: string): string => {
  const slug = name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
  return slug || name;
};

const documentRelPath = (hostPath: string, name: string): string => {
  const file = `${documentSlug(name)}.md`;
  return hostPath === "" ? `knowledges/${file}` : `${hostPath}/knowledges/${file}`;
};

const notes = new Map<string, ShowcaseNote>(
  [
    {
      name: "AlphaFold benchmark findings",
      relPath: "knowledges/alphafold-benchmark.md",
      hostPath: "",
      excerpt: "The bf16 baseline converged fastest while preserving mean pLDDT.",
      status: "published",
      tags: ["protein-folding", "benchmark"],
      body: [
        "# AlphaFold benchmark findings",
        "",
        "The `bf16` baseline converged fastest while preserving mean pLDDT.",
        "",
        "| run | batch | pLDDT | status |",
        "| --- | ---: | ---: | --- |",
        "| run-001 | 32 | 87.4 | succeeded |",
        "| run-002 | 64 | — | running |",
        "",
        "> Linked to experiment `exp-001` and checkpoint `asset-003`.",
      ].join("\n"),
      links: ["knowledges/gpu-retry-playbook.md"],
    },
    {
      name: "GPU retry playbook",
      relPath: "knowledges/gpu-retry-playbook.md",
      hostPath: "",
      excerpt: "Operational notes for recovering failed MolQ and Slurm attempts.",
      status: "draft",
      tags: ["operations", "molq", "gpu"],
      body: [
        "# GPU retry playbook",
        "",
        "1. Inspect the failed execution log.",
        "2. Reduce `batch_size` by half.",
        "3. Resume with the same config hash for provenance continuity.",
      ].join("\n"),
      links: ["knowledges/alphafold-benchmark.md"],
    },
  ].map((note) => [note.relPath, note]),
);

for (const [cls, name, excerpt, hostPath] of [
  [
    "Finding",
    "Integrator energy conservation",
    "The 0.5 fs examples conserve energy most closely.",
    "projects/nve-drift/experiments/integrator-benchmark",
  ],
  [
    "Observation",
    "Temperature stability",
    "The thermostat examples stay near 300 K.",
    "projects/nve-drift",
  ],
  [
    "Report",
    "GPU memory failure",
    "Batch size 128 exceeded available memory. Retry with 32.",
    "projects/protein-folding/experiments/alphafold-baseline",
  ],
  [
    "Plan",
    "Thermostat validation",
    "Bind a workflow, then compare thermostat relaxation times.",
    "projects/nve-drift/experiments/thermostat-validation",
  ],
  [
    "Literature",
    "Molecular simulation methods",
    "Background reading for integration and energy conservation.",
    "",
  ],
]) {
  const relPath = documentRelPath(hostPath, name);
  const note: ShowcaseNote = {
    cls,
    name,
    relPath,
    hostPath,
    excerpt,
    status: "active",
    tags: ["example", cls.toLowerCase()],
    body: `# ${name}\n\n${excerpt}\n\nSynthetic example for interface exploration.\n\n[@records benchmark](molab:experiment/exp-nve/run/md-001)`,
    links: [],
  };
  notes.set(relPath, note);
}
const manuscript = getFile("manuscript/main.tex");
if (manuscript?.content)
  notes.set("manuscript/main.tex", {
    name: "Integrator benchmark.tex",
    relPath: "manuscript/main.tex",
    hostPath: "",
    cls: "Note",
    excerpt: "TeX manuscript with a results table",
    status: "draft",
    tags: ["example", "manuscript"],
    body: manuscript.content,
    links: [],
  });
for (const note of notes.values()) writeFile(note.relPath, note.body);

const noteSummary = (note: ShowcaseNote) => ({
  cls: note.cls ?? "Note",
  name: note.name,
  relPath: note.relPath,
  hostPath: note.hostPath,
  excerpt: note.excerpt,
  status: note.status,
  tags: note.tags,
});

const servedWorkspaces = [
  {
    key: "feature-showcase",
    label: "Feature showcase",
    isRemote: false,
    path: "/mock-workspace",
    active: true,
    unreachable: false,
    needsAuth: false,
  },
];

export const featureShowcaseHandlers = [
  http.get("/api/workspaces", () => HttpResponse.json(servedWorkspaces)),
  http.post("/api/workspaces", () =>
    HttpResponse.json(
      {
        detail:
          "The offline showcase serves /mock-workspace. Use a real server to add another workspace.",
      },
      { status: 409 },
    ),
  ),
  http.delete("/api/workspaces/:key", () =>
    HttpResponse.json({ detail: "The showcase workspace must remain served" }, { status: 409 }),
  ),
  http.get("/api/health", () => HttpResponse.json({ status: "ok", mock: true })),
  http.get("/api/workspace/copilot", () => {
    const runs = getAllProjects().flatMap((p) =>
      getExperimentsByProject(p.id).flatMap((e) => getRunsByExperiment(e.id)),
    );
    const failed = runs.filter((r) => r.status === "failed");
    const running = runs.filter((r) => r.status === "running");
    const ref = (r: (typeof runs)[number]) => ({
      id: r.id,
      name: r.name,
      projectId: r.projectId,
      experimentId: r.experimentId,
      status: r.status,
    });
    return HttpResponse.json({
      workspace: { id: "mock-workspace", name: "Feature showcase", root: "/mock-workspace" },
      headline: "Synthetic workspace examples",
      counts: {
        projects: getAllProjects().length,
        runs: runs.length,
        failed: failed.length,
        running: running.length,
      },
      failedRuns: failed.map(ref),
      runningRuns: running.map(ref),
      healthFlags: [],
      relevantKnowledge: [],
      nextActions: failed.slice(0, 2).map((r) => ({
        kind: "diagnose_failed_run",
        target: r.id,
        rationale: "Inspect the failed attempt and record its evidence.",
        op: "analyze_failure",
        advisory: true,
      })),
    });
  }),

  http.get(workspaceRoute("/api/knowledge"), ({ request }) => {
    const url = new URL(request.url);
    const tag = url.searchParams.get("tag");
    const status = url.searchParams.get("status");
    const filtered = [...notes.values()].filter(
      (note) => (!tag || note.tags.includes(tag)) && (!status || note.status === status),
    );
    return HttpResponse.json({
      notes: filtered.map(noteSummary),
      references: [
        {
          name: "alphafold-paper",
          relPath: "references/alphafold-paper",
          title: "Highly accurate protein structure prediction with AlphaFold",
          authors: ["Jumper et al."],
          venue: "Nature",
          year: 2021,
          doi: "10.1038/s41586-021-03819-2",
          url: "https://doi.org/10.1038/s41586-021-03819-2",
        },
      ],
      total: filtered.length + 1,
    });
  }),

  http.get("/api/knowledge/note", ({ request }) => {
    const path = new URL(request.url).searchParams.get("path") ?? "";
    const note = notes.get(path);
    if (!note) return HttpResponse.json({ detail: "Note not found" }, { status: 404 });
    return HttpResponse.json({
      name: note.name,
      relPath: note.relPath,
      body: note.body,
      links: note.links,
      cards: [
        { kind: "experiment", id: "exp-001", title: "AlphaFold Baseline", status: "active" },
        { kind: "run", id: "run-001", title: "run-001", status: "succeeded" },
        { kind: "asset", id: "asset-003", title: "alphafold.pt", status: "active" },
        {
          kind: "run",
          id: "deadbeef",
          title: "missing run",
          ref: "molab:experiment/exp-001/run/deadbeef",
          missing: true,
          status: null,
        },
      ],
    });
  }),

  http.get(workspaceRoute("/api/knowledge/search"), ({ request }) => {
    const query = (new URL(request.url).searchParams.get("q") ?? "").toLowerCase();
    const hits = [...notes.values()]
      .filter((note) => `${note.name} ${note.body}`.toLowerCase().includes(query))
      .map((note) => ({
        path: note.relPath,
        title: note.name,
        type: "note",
        snippet: note.excerpt,
        tags: note.tags,
      }));
    return HttpResponse.json({ hits, truncated: false });
  }),

  http.get("/api/knowledge/backlinks", () =>
    HttpResponse.json({ backlinks: [...notes.values()].slice(0, 1).map(noteSummary) }),
  ),

  http.get("/api/knowledge/entity-backlinks", ({ request }) => {
    const url = new URL(request.url);
    const entity =
      url.searchParams.get("run_id") ??
      url.searchParams.get("experiment_id") ??
      url.searchParams.get("project_id") ??
      "entity";
    return HttpResponse.json({
      entity,
      backlinks: [
        {
          path: "knowledges/alphafold-benchmark.md",
          title: "AlphaFold benchmark findings",
          type: "note",
          role: "records",
        },
      ],
    });
  }),

  http.put(workspaceRoute("/api/knowledge/doc"), async ({ request }) => {
    const url = new URL(request.url);
    const path = url.searchParams.get("path") ?? "";
    const note = notes.get(path);
    if (!note) return HttpResponse.json({ detail: "Note not found" }, { status: 404 });
    const body = (await request.json()) as { body?: string };
    note.body = body.body ?? note.body;
    note.excerpt = note.body.slice(0, 160);
    writeFile(note.relPath, note.body);
    return HttpResponse.json({
      name: note.name,
      relPath: note.relPath,
      body: note.body,
      links: note.links,
      cards: [],
    });
  }),

  http.patch(workspaceRoute("/api/knowledge/doc/meta"), async ({ request }) => {
    const url = new URL(request.url);
    const path = url.searchParams.get("path") ?? "";
    const note = notes.get(path);
    if (!note) return HttpResponse.json({ detail: "Note not found" }, { status: 404 });
    const body = (await request.json()) as { tags?: string[]; status?: string };
    if (body.tags) note.tags = body.tags;
    if (body.status) note.status = body.status;
    return HttpResponse.json(noteSummary(note));
  }),

  http.post(workspaceRoute("/api/knowledge/doc"), async ({ request }) => {
    const body = (await request.json()) as {
      name?: string;
      body?: string;
      hostPath?: string | null;
      cls?: string;
    };
    const name = body.name ?? "note";
    const hostPath = body.hostPath ?? "";
    const relPath = documentRelPath(hostPath, name);
    const note: ShowcaseNote = {
      cls: body.cls ?? "Note",
      name,
      relPath,
      hostPath,
      excerpt: body.body ?? "",
      status: "active",
      tags: [],
      body: body.body ?? "",
      links: [],
    };
    if (notes.has(relPath))
      return HttpResponse.json({ detail: "Document already exists" }, { status: 409 });
    notes.set(relPath, note);
    writeFile(relPath, note.body);
    return HttpResponse.json(noteSummary(note), { status: 201 });
  }),

  http.patch(workspaceRoute("/api/knowledge/doc"), async ({ request }) => {
    const path = new URL(request.url).searchParams.get("path") ?? "";
    const note = notes.get(path);
    if (!note) return HttpResponse.json({ detail: "Note not found" }, { status: 404 });
    const body = (await request.json()) as { name?: string | null; hostPath?: string | null };
    if (body.name) note.name = body.name;
    if (body.hostPath !== undefined && body.hostPath !== null && body.hostPath !== note.hostPath) {
      const file = note.relPath.split("/").pop() ?? `${documentSlug(note.name)}.md`;
      const hostPath = body.hostPath;
      const relPath = hostPath === "" ? `knowledges/${file}` : `${hostPath}/knowledges/${file}`;
      notes.delete(path);
      deleteFile(path);
      note.hostPath = hostPath;
      note.relPath = relPath;
      notes.set(relPath, note);
      writeFile(relPath, note.body);
    }
    return HttpResponse.json(noteSummary(note));
  }),

  http.delete(workspaceRoute("/api/knowledge/doc"), ({ request }) => {
    const path = new URL(request.url).searchParams.get("path") ?? "";
    notes.delete(path);
    deleteFile(path);
    return HttpResponse.json({ message: `note ${path} deleted` });
  }),

  http.post(workspaceRoute("/api/knowledge/doc/embed"), async ({ request }) => {
    const body = (await request.json()) as { role?: string; target?: string; text?: string };
    const srcPath = new URL(request.url).searchParams.get("path") ?? "";
    const note = notes.get(srcPath);
    if (!note) return HttpResponse.json({ detail: "Note not found" }, { status: 404 });
    const target = body.target ?? "run-001";
    note.body += `\n[@${body.role ?? "references"} ${body.text ?? target}](${target})\n`;
    note.links.push(target);
    writeFile(srcPath, note.body);
    return HttpResponse.json({
      srcPath,
      target: body.target ?? "run-001",
      role: body.role ?? "references",
    });
  }),
  http.get(workspaceRoute("/api/knowledge/doc/export"), ({ request }) => {
    const note = notes.get(new URL(request.url).searchParams.get("path") ?? "");
    return note
      ? new HttpResponse(note.body, {
          headers: {
            "Content-Type": "text/markdown; charset=utf-8",
            "Content-Disposition": `attachment; filename="${note.relPath.split("/").pop()}"`,
          },
        })
      : HttpResponse.json({ detail: "Note not found" }, { status: 404 });
  }),
  http.get(workspaceRoute("/api/knowledge/export"), ({ request }) => {
    const hostPath = new URL(request.url).searchParams.get("hostPath");
    const archive = Object.fromEntries(
      [...notes.values()]
        .filter((n) => hostPath == null || n.hostPath === hostPath)
        .map((n) => [n.relPath, strToU8(n.body)]),
    );
    return new HttpResponse(new Blob([Uint8Array.from(zipSync(archive)).buffer]), {
      headers: {
        "Content-Type": "application/zip",
        "Content-Disposition": 'attachment; filename="knowledge.zip"',
      },
    });
  }),
  http.post(workspaceRoute("/api/knowledge/doc/media"), async ({ request }) => {
    const path = new URL(request.url).searchParams.get("path") ?? "";
    if (!notes.has(path)) return HttpResponse.json({ detail: "Note not found" }, { status: 404 });
    const form = await request.formData();
    const file = form.get("file") as File | null;
    if (!file) return HttpResponse.json({ detail: "Missing media file" }, { status: 400 });
    const mediaPath = `${path}.media/${file.name}`;
    writeFile(mediaPath, new Uint8Array(await file.arrayBuffer()));
    return HttpResponse.json({ path: mediaPath }, { status: 201 });
  }),
  http.post(
    workspaceRoute("/api/projects/:projectId/experiments/:experimentId/runs/:runId/:operation"),
    async ({ params, request }) => {
      if (!["harvest", "analyze-failure"].includes(String(params.operation))) return;
      const run = getRun(String(params.runId));
      if (!run || run.projectId !== params.projectId || run.experimentId !== params.experimentId)
        return HttpResponse.json({ detail: "Run not found" }, { status: 404 });
      const body = (await request.json()) as { name?: string; narrative?: string; cls?: string };
      const hostPath = getExperiment(run.experimentId)?.path ?? "";
      const name = body.name ?? `${run.id}-${params.operation}`;
      const relPath = documentRelPath(hostPath, name);
      const narrative =
        body.narrative ??
        "The synthetic execution exceeded GPU memory. Reduce batch size and retry.";
      const reportBody = `# ${name}\n\n${narrative}\n\n[@records ${run.id}](${run.ref})`;
      notes.set(relPath, {
        cls: params.operation === "analyze-failure" ? "Report" : (body.cls ?? "Finding"),
        name,
        relPath,
        hostPath,
        status: "active",
        tags: ["example"],
        excerpt: narrative,
        body: reportBody,
        links: [run.ref ?? ""],
      });
      writeFile(relPath, reportBody);
      return HttpResponse.json({ name, path: relPath }, { status: 201 });
    },
  ),
];
