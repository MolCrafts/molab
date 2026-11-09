/**
 * Cross-feature fixtures for `npm run dev:web` (leaf `npm run dev`).
 *
 * Domain handlers own entity CRUD. This file fills the small read models that
 * span domains (knowledge, cache and workspaces),
 * so every navigation destination can be exercised without a Python server.
 */

import { strToU8, zipSync } from "fflate";
import { HttpResponse, http } from "msw";
import { deleteFile, getExperiment, getFile, getRun, writeFile } from "../db";
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
  record?: Record<string, unknown>;
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

const thermostat =
  "projects/nve-drift/experiments/thermostat-validation/knowledges/thermostat-validation.md";
for (const note of [
  {
    cls: "Roadmap",
    name: "Thermostat roadmap",
    excerpt: "Bind the workflow, then compare relaxation times.",
    record: {
      stages: [
        { id: "bind", title: "Bind the workflow", experiment: "thermostat-validation" },
        {
          id: "compare",
          title: "Compare relaxation times",
          experiment: "thermostat-validation",
          depends_on: ["bind"],
        },
      ],
    },
  },
  {
    cls: "Todo",
    name: "Thermostat todo",
    excerpt: "The comparison stays blocked until the workflow is bound.",
    record: {
      items: [
        { id: "bind-workflow", title: "Bind a workflow", status: "open", stage: "bind" },
        {
          id: "compare-times",
          title: "Compare relaxation times",
          status: "blocked",
          stage: "compare",
        },
      ],
    },
  },
  {
    cls: "Milestone",
    name: "Relaxation times compared",
    excerpt: "The thermostat examples have been compared.",
    record: {
      stage: "compare",
      criterion: "Relaxation times are compared for the thermostat examples.",
      status: "open",
    },
  },
  {
    cls: "Delegation",
    name: "Thermostat check",
    excerpt: "Check that the thermostat examples stay near 300 K.",
    record: {
      goal: "Check that the thermostat examples stay near 300 K.",
      scope: "projects/nve-drift",
      state: "open",
    },
  },
] satisfies Array<{
  cls: string;
  name: string;
  excerpt: string;
  record: Record<string, unknown>;
}>) {
  const relPath = documentRelPath(
    "projects/nve-drift/experiments/thermostat-validation",
    note.name,
  );
  notes.set(relPath, {
    cls: note.cls,
    name: note.name,
    relPath,
    hostPath: "projects/nve-drift/experiments/thermostat-validation",
    excerpt: note.excerpt,
    status: "active",
    tags: ["example", note.cls.toLowerCase()],
    body: `# ${note.name}\n\n${note.excerpt}\n\nCites [${thermostat}](${thermostat}).\n`,
    links: [thermostat],
    record: note.record,
  });
}

// L10: one document stored as HTML — prose in <molab-markdown>, components as elements.
notes.set("knowledges/integrator-glossary.html", {
  cls: "Note",
  name: "Integrator glossary",
  relPath: "knowledges/integrator-glossary.html",
  hostPath: "",
  excerpt: "Terms used across the integrator benchmark.",
  status: "active",
  tags: ["glossary"],
  body: [
    "<molab-markdown>",
    "Terms used across the integrator benchmark. This document is stored as **HTML**.",
    "",
    "## Energy drift",
    "",
    "The slope of total energy over time, per atom, in eV/atom/ps.",
    "</molab-markdown>",
    '<molab-run-table experiment="molab:experiment/exp-nve" columns="timestep_fs,driver,energy_drift" where="ensemble=nve"></molab-run-table>',
    "<molab-markdown>",
    "## Timestep",
    "",
    '!!! tip "Rule of thumb"',
    "    Flexible O–H bonds need about 1 fs.",
    "</molab-markdown>",
  ].join("\n"),
  links: [],
});

// L10 v3: the showcase documents use their class templates (MkDocs blocks + <molab-…> components).
const EXP_NVE = "molab:experiment/exp-nve";
const RUN_FAILED = "molab:experiment/exp-nve/run/md-009";
const TEMPLATE_BODIES: Record<string, string> = {
  "AlphaFold benchmark findings": [
    "# AlphaFold benchmark findings",
    "",
    "The `bf16` baseline converged fastest while preserving mean pLDDT. It ran in [AlphaFold Baseline](molab:experiment/exp-001).",
    "",
    "## Results",
    "",
    "| run | batch | pLDDT |",
    "| --- | ---: | ---: |",
    "| run-001 | 32 | 87.4 |",
    "| run-002 | 64 | — |",
    "",
    "## Next steps",
    "",
    '!!! tip "Rerun at batch 64"',
    "    Once the memory fix lands, rerun with the same seeds and compare pLDDT per target.",
  ].join("\n"),
  "Integrator energy conservation": [
    '!!! success "Claim"',
    "    Energy drift grows about four-fold for each doubling of the timestep; 0.5 fs keeps it under 4·10⁻⁵ eV/atom/ps for both drivers.",
    "",
    "## Evidence",
    "",
    '=== "Chart"',
    "",
    `    ::molab-metric-chart{experiment=${EXP_NVE} y=energy_drift x=timestep_fs by=driver}`,
    "",
    '=== "Runs"',
    "",
    `    ::molab-run-table{experiment=${EXP_NVE} columns=timestep_fs,driver,energy_drift where="ensemble=nve"}`,
    "",
    "## Holds under",
    "",
    '::molab-params{ensemble="nve, nvt" steps=500 system=water-216}',
    "",
    "## Builds on",
    "",
    "[Molecular simulation methods](knowledges/molecular-simulation-methods.md)",
  ].join("\n"),
  "GPU memory failure": [
    '!!! failure "Molecular dynamics failed"',
    "    Energy drift exceeded the tolerance at 2 fs.",
    "",
    `::molab-run-ref{ref=${RUN_FAILED}}`,
    "",
    "## Evidence",
    "",
    `::molab-log{run=${RUN_FAILED}}`,
    "",
    "## Cause",
    "",
    "The timestep exceeds the stability limit for the O–H stretch; the drift grows quadratically with the timestep.",
    "",
    "## Remedy",
    "",
    "- [x] Rerun at 1 fs",
    "- [ ] Add SHAKE constraints and retry 2 fs",
  ].join("\n"),
  "Temperature stability": [
    "The thermostat examples stay within **2 K of 300 K** after 5 ps, for both thermostats.",
    "",
    "## Seen in",
    "",
    '::molab-run-ref{refs="molab:experiment/exp-nve/run/md-002 molab:experiment/exp-nve/run/md-004"}',
    "",
    "## Untested",
    "",
    '!!! warning "Not yet tested at 2 fs"',
    "    The 2 fs runs failed on energy drift before equilibrating.",
  ].join("\n"),
  "Thermostat validation": [
    '!!! abstract "Goal"',
    "    Pick the largest timestep that keeps NVE energy drift below 1·10⁻⁴ eV/atom/ps.",
    "",
    "## Roadmap",
    "",
    "::molab-stage-track",
    "",
    "## Next",
    "",
    "- [x] Baseline at 0.5 fs",
    "- [ ] Sweep 0.5 / 1 / 2 fs × two drivers",
    "- [ ] Write the finding",
  ].join("\n"),
  "Molecular simulation methods": [
    '::molab-citation{title="Verlet integrators, revisited: energy drift at large timesteps" authors="A. Leimkuhler, C. Matthews" year=2015 venue="Molecular Physics 113(4)" doi=10.1080/00268976.2014.987}',
    "",
    '??? abstract "Abstract"',
    "    We study long-time energy drift of velocity-Verlet in molecular dynamics and show that drift scales with the square of the timestep for smooth potentials.",
    "",
    "## Key points",
    "",
    "- Drift ∝ Δt² below the stability limit.",
    "- Constraint algorithms add a linear term.",
    "",
    "## Notes",
    "",
    '!!! quote "§4.2"',
    "    For water with flexible O–H bonds the stable limit is near 1 fs.",
  ].join("\n"),
  "Thermostat roadmap": [
    "::molab-stage-track",
    "",
    "## Stages",
    "",
    "### Bind the workflow",
    "",
    "Bind a code workflow and run one smoke test.",
    "",
    "### Compare relaxation times",
    "",
    '!!! warning "Blocked"',
    "    Waits for **Bind the workflow**.",
  ].join("\n"),
  "Thermostat todo": [
    "::molab-todo-list",
    "",
    "## Notes",
    "",
    "Use the same seeds as the integrator benchmark.",
  ].join("\n"),
  "Relaxation times compared": [
    `::molab-milestone{evidence="molab:experiment/exp-nve/run/md-002 molab:experiment/exp-nve/run/md-011"}`,
    "",
    "## On the roadmap",
    "",
    "Stage 2 of 2 of the thermostat roadmap.",
  ].join("\n"),
  "Thermostat check": [
    '!!! note "Brief"',
    "    Check that the thermostat examples stay near 300 K at 1 and 2 fs; report any run that drifts more than 5 K.",
    "",
    "## Asks",
    "",
    "::molab-approval{gate=plan}",
    "",
    "## Scope",
    "",
    '::molab-params{experiment="Thermostat Validation" may_run_on=hpc-slurm budget="4 GPU-hours"}',
  ].join("\n"),
};
for (const note of notes.values()) {
  const body = TEMPLATE_BODIES[note.name];
  if (body) note.body = body;
  if (note.cls === "Delegation" && note.record) {
    note.record = { ...note.record, state: "blocked", questions: ["Run 4 jobs on hpc-slurm?"] };
  }
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

/** A stable, spread-out edit history so the landing's Writing gauge has days to draw. */
const showcaseTimes = (relPath: string): { updatedAt: string; createdAt: string } => {
  let hash = 0;
  for (const char of relPath) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  const day = 86_400_000;
  const updated = Date.now() - (hash % 13) * day - (hash % 7) * 3_600_000;
  return {
    updatedAt: new Date(updated).toISOString(),
    createdAt: new Date(updated - ((hash >> 3) % 9) * day).toISOString(),
  };
};

const noteSummary = (note: ShowcaseNote) => ({
  cls: note.cls ?? "Note",
  name: note.name,
  relPath: note.relPath,
  hostPath: note.hostPath,
  excerpt: note.excerpt,
  status: note.status,
  tags: note.tags,
  format: note.relPath.endsWith(".html") ? "html" : "md",
  ...showcaseTimes(note.relPath),
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
      record: note.record ?? {},
      format: note.relPath.endsWith(".html") ? "html" : "md",
      ...showcaseTimes(note.relPath),
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
    const kind = url.searchParams.get("kind");
    if (kind === "asset") {
      const assetId = url.searchParams.get("assetId") ?? "";
      // The water trajectory is cited by the NVE finding; nothing else is.
      const backlinks =
        assetId === "asset-nve-trajectory"
          ? [
              {
                path: "knowledges/alphafold-benchmark.md",
                title: "Energy drift stays flat under NVE at 0.5 fs",
                type: "finding",
                role: "cites",
              },
            ]
          : [];
      return HttpResponse.json({ entity: `asset:${assetId}`, backlinks });
    }
    const entity =
      url.searchParams.get("runId") ??
      url.searchParams.get("experimentId") ??
      url.searchParams.get("projectId") ??
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
      record: note.record ?? {},
      format: note.relPath.endsWith(".html") ? "html" : "md",
      updatedAt: new Date().toISOString(),
      createdAt: showcaseTimes(note.relPath).createdAt,
      cards: [],
    });
  }),

  http.patch(workspaceRoute("/api/knowledge/doc/record"), async ({ request }) => {
    const path = new URL(request.url).searchParams.get("path") ?? "";
    const note = notes.get(path);
    if (!note) return HttpResponse.json({ detail: "Note not found" }, { status: 404 });
    const payload = (await request.json()) as { record?: Record<string, unknown> };
    note.record = payload.record ?? {};
    return HttpResponse.json({
      relPath: note.relPath,
      cls: note.cls ?? "Note",
      record: note.record,
      digest: `sha256:${Date.now().toString(16)}`,
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
      record?: Record<string, unknown>;
      format?: "md" | "html";
    };
    const name = body.name ?? "note";
    const hostPath = body.hostPath ?? "";
    const mdPath = documentRelPath(hostPath, name);
    const relPath = body.format === "html" ? mdPath.replace(/\.md$/, ".html") : mdPath;
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
      record: body.record,
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
      if (params.operation !== "harvest") return;
      const run = getRun(String(params.runId));
      if (!run || run.projectId !== params.projectId || run.experimentId !== params.experimentId)
        return HttpResponse.json({ detail: "Run not found" }, { status: 404 });
      const body = (await request.json()) as { name?: string; narrative?: string; cls?: string };
      const narrative = body.narrative?.trim() ?? "";
      if (!narrative) {
        return HttpResponse.json({ detail: "narrative required" }, { status: 400 });
      }
      const hostPath = getExperiment(run.experimentId)?.path ?? "";
      const name = body.name ?? `${run.id}-${params.operation}`;
      const relPath = documentRelPath(hostPath, name);
      const reportBody = `# ${name}\n\n${narrative}\n\n[@records ${run.id}](${run.ref})`;
      notes.set(relPath, {
        cls: body.cls ?? "Finding",
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
