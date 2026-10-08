/**
 * Cross-feature fixtures for `npm run dev:web` (leaf `npm run dev`).
 *
 * Domain handlers own entity CRUD. This file fills the small read models that
 * span domains (knowledge, cache and workspaces),
 * so every navigation destination can be exercised without a Python server.
 */

import { http, HttpResponse } from "msw";

interface ShowcaseNote {
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

const noteSummary = (note: ShowcaseNote) => ({
  name: note.name,
  relPath: note.relPath,
  hostPath: note.hostPath,
  excerpt: note.excerpt,
  status: note.status,
  tags: note.tags,
});


export const featureShowcaseHandlers = [
  http.get("/api/workspaces", () =>
    HttpResponse.json([
      {
        key: "feature-showcase",
        label: "Feature showcase",
        isRemote: false,
        path: "/mock-workspace",
        active: true,
        unreachable: false,
      },
    ]),
  ),

  http.get("/api/knowledge", ({ request }) => {
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

  http.get("/api/knowledge/search", ({ request }) => {
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

  http.put("/api/knowledge/doc", async ({ request }) => {
    const url = new URL(request.url);
    const path = url.searchParams.get("path") ?? "";
    const note = notes.get(path);
    if (!note) return HttpResponse.json({ detail: "Note not found" }, { status: 404 });
    const body = (await request.json()) as { body?: string };
    note.body = body.body ?? note.body;
    return HttpResponse.json({
      name: note.name,
      relPath: note.relPath,
      body: note.body,
      links: note.links,
      cards: [],
    });
  }),

  http.patch("/api/knowledge/doc/meta", async ({ request }) => {
    const url = new URL(request.url);
    const path = url.searchParams.get("path") ?? "";
    const note = notes.get(path);
    if (!note) return HttpResponse.json({ detail: "Note not found" }, { status: 404 });
    const body = (await request.json()) as { tags?: string[]; status?: string };
    if (body.tags) note.tags = body.tags;
    if (body.status) note.status = body.status;
    return HttpResponse.json(noteSummary(note));
  }),

  http.post("/api/knowledge/doc", async ({ request }) => {
    const body = (await request.json()) as { name?: string; body?: string; hostPath?: string | null };
    const name = body.name ?? "note";
    const hostPath = body.hostPath ?? "";
    const relPath = documentRelPath(hostPath, name);
    const note: ShowcaseNote = {
      name,
      relPath,
      hostPath,
      excerpt: body.body ?? "",
      status: "active",
      tags: [],
      body: body.body ?? "",
      links: [],
    };
    notes.set(relPath, note);
    return HttpResponse.json(noteSummary(note), { status: 201 });
  }),

  http.patch("/api/knowledge/doc", async ({ request }) => {
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
      note.hostPath = hostPath;
      note.relPath = relPath;
      notes.set(relPath, note);
    }
    return HttpResponse.json(noteSummary(note));
  }),

  http.delete("/api/knowledge/doc", ({ request }) => {
    const path = new URL(request.url).searchParams.get("path") ?? "";
    notes.delete(path);
    return HttpResponse.json({ message: `note ${path} deleted` });
  }),

  http.post("/api/knowledge/doc/embed", async ({ request }) => {
    const body = (await request.json()) as { role?: string; target?: string };
    const srcPath = new URL(request.url).searchParams.get("path") ?? "";
    return HttpResponse.json({
      srcPath,
      target: body.target ?? "run-001",
      role: body.role ?? "references",
    });
  }),
];
