/**
 * Mock handlers for Workspace API endpoints
 */

import { HttpResponse, http } from "msw";
import type { FileNode } from "../db";
import {
  createDirectory,
  deleteFile,
  getAllAssets,
  getAllProjects,
  getExperimentsByProject,
  getFile,
  getFileTree,
  getRunsByExperiment,
  writeFile,
} from "../db";
import { workspaceRoute } from "./workspaceRoute";

const API_BASE = "/api";

// Local-path opens mirror the server's create_if_missing semantics
// (src/molab/server/routes/workspace.py): unknown path + no flag → 404;
// flag → "create" the path by adding it to the known set.
const knownWorkspacePaths = new Set<string>(["/mock-workspace"]);

/**
 * Build nested file tree from flat file map
 */
function buildNestedTree(path: string): { path: string; children: FileNode[] } {
  if (path === "/" || path === "") {
    // Root level
    const rootFiles = getFileTree();
    return {
      path: "/",
      children: rootFiles,
    };
  }

  // Find the requested node
  const node = getFile(path);
  if (!node) {
    return { path, children: [] };
  }

  if (node.type === "file") {
    return { path, children: [] };
  }

  return {
    path,
    children: node.children || [],
  };
}

/** Derive dashboard rows from the exact attempts returned by the run detail API. */
function buildMockWorkspaceRuns() {
  return getAllProjects().flatMap((project) =>
    getExperimentsByProject(project.id).flatMap((experiment) =>
      getRunsByExperiment(experiment.id).map((run) => ({
        id: run.id,
        name: run.name,
        path: run.path,
        projectId: project.id,
        projectName: project.name,
        experimentId: experiment.id,
        experimentName: experiment.name,
        definitionHash: run.definitionHash,
        experimentRevisionId: run.experimentRevisionId,
        inputAssetIds: [],
        targetHint: run.target ?? null,
        statusSummary: run.statusSummary,
        parameters: run.parameters ?? {},
        createdAt: run.created,
        executions: (run.executions ?? []).map((e) => ({
          executionId: e.id,
          runId: run.id,
          mode: e.mode,
          status: e.status,
          createdAt: e.createdAt,
          startedAt: e.startedAt,
          finishedAt: e.finishedAt,
          basedOnExecutionId: e.basedOnExecutionId,
          checkpointArtifactId: e.checkpointArtifactId,
          durationSeconds:
            e.startedAt && e.finishedAt
              ? (Date.parse(e.finishedAt) - Date.parse(e.startedAt)) / 1000
              : null,
          schedulerJobId: e.executor?.scheduler_job_id ?? null,
          backend: e.executor?.backend ?? "local",
          backendMetadata: e.executor ?? {},
        })),
      })),
    ),
  );
}

export const workspaceHandlers = [
  http.get(workspaceRoute(`${API_BASE}/workspace/scope`), () => {
    return HttpResponse.json({
      kind: "workspace.root",
      id: "mock-workspace",
      name: "Mock workspace",
    });
  }),

  http.get(workspaceRoute(`${API_BASE}/workspace/cache/status`), () =>
    HttpResponse.json({
      cached: false,
      connected: true,
      indexed: true,
      ready: true,
      indexing: false,
      phase: "idle",
      message: "Local example ready",
    }),
  ),
  http.get(workspaceRoute(`${API_BASE}/workspace/context`), () =>
    HttpResponse.json({
      workspace: { id: "mock-workspace", name: "Feature showcase", path: "/mock-workspace" },
      projects: getAllProjects(),
      mock: true,
    }),
  ),
  http.post(workspaceRoute(`${API_BASE}/workspace/file/upload`), async ({ request }) => {
    const path = new URL(request.url).searchParams.get("path") ?? "";
    if (!path || path.split("/").includes(".."))
      return HttpResponse.json({ detail: "Invalid upload path" }, { status: 400 });
    writeFile(path, new Uint8Array(await request.arrayBuffer()));
    return HttpResponse.json({ path }, { status: 201 });
  }),
  http.get(workspaceRoute(`${API_BASE}/history`), ({ request }) => {
    const url = new URL(request.url);
    const entity = url.searchParams.get("entity");
    const event = url.searchParams.get("event");
    const facts = getAllProjects()
      .flatMap((project) =>
        getExperimentsByProject(project.id).flatMap((experiment) =>
          getRunsByExperiment(experiment.id).flatMap((run) =>
            (run.executions ?? []).map((e) => ({
              commit: `mock-${e.id}-${run.id}`,
              event: `execution.${e.status}`,
              subjectType: "execution",
              subjectId: e.id,
              summary: `${experiment.name} · ${run.name} · ${e.status}`,
              occurredAt: e.finishedAt ?? e.createdAt,
            })),
          ),
        ),
      )
      .filter((f) => (!entity || f.subjectId === entity) && (!event || f.event === event));
    return HttpResponse.json(
      facts
        .sort((a, b) => b.occurredAt.localeCompare(a.occurredAt))
        .slice(0, Number(url.searchParams.get("limit") ?? 50)),
    );
  }),
  http.post(workspaceRoute(`${API_BASE}/history/sync`), () => HttpResponse.json({ commit: null })),
  http.post(workspaceRoute(`${API_BASE}/history/push`), () => HttpResponse.json({ commit: null })),

  // GET /api/workspace/info - Get workspace metadata
  http.get(workspaceRoute(`${API_BASE}/workspace/info`), () => {
    const projects = getAllProjects();
    const assets = getAllAssets();

    return HttpResponse.json({
      root: "/mock-workspace",
      projectCount: projects.length,
      assetCount: assets.length,
    });
  }),

  // GET /api/workspace/runs - Cross-experiment runs aggregator
  http.get(workspaceRoute(`${API_BASE}/workspace/runs`), ({ request }) => {
    const url = new URL(request.url);
    const projectFilter = url.searchParams.get("projectId");
    const experimentFilter = url.searchParams.get("experimentId");
    const backendFilter = url.searchParams.get("backend");
    const statusFilter = url.searchParams.get("status");
    const offset = Math.max(0, Number(url.searchParams.get("offset") ?? 0));
    const limit = Math.max(1, Number(url.searchParams.get("limit") ?? 500));

    const allRuns = buildMockWorkspaceRuns();
    const filtered = allRuns.filter((row) => {
      if (projectFilter && row.projectId !== projectFilter) return false;
      if (experimentFilter && row.experimentId !== experimentFilter) return false;
      if (backendFilter && !row.executions.some((e) => e.backend === backendFilter)) return false;
      if (statusFilter && !(row.statusSummary?.byStatus?.[statusFilter] ?? 0)) return false;
      return true;
    });

    const page = filtered.slice(offset, offset + limit);
    return HttpResponse.json({
      runs: page,
      stats: {
        totalRuns: filtered.length,
        totalExecutions: filtered.reduce((sum, r) => sum + r.executions.length, 0),
        activeExecutions: filtered.reduce((sum, r) => sum + (r.statusSummary?.active ?? 0), 0),
        byStatus: filtered
          .flatMap((r) => r.executions)
          .reduce<Record<string, number>>((counts, e) => {
            counts[e.status] = (counts[e.status] ?? 0) + 1;
            return counts;
          }, {}),
      },
      total: filtered.length,
      truncated: offset + page.length < filtered.length,
    });
  }),

  // GET /api/workspace/files - List workspace files
  http.get(workspaceRoute(`${API_BASE}/workspace/files`), ({ request }) => {
    const url = new URL(request.url);
    const path = `/${(url.searchParams.get("path") ?? "").replace(/^\/+/, "")}`;

    const tree = buildNestedTree(path);
    const maxDepth = Math.max(
      1,
      Number(url.searchParams.get("max_depth") ?? url.searchParams.get("maxDepth") ?? 1),
    );
    const trim = (node: FileNode, depth: number): FileNode => {
      const { content: _content, bytes: _bytes, children, ...entry } = node;
      return {
        ...entry,
        ...(children && depth > 1 ? { children: children.map((n) => trim(n, depth - 1)) } : {}),
      };
    };
    return HttpResponse.json({ path, children: tree.children.map((n) => trim(n, maxDepth)) });
  }),

  // GET /api/workspace/file - Read file content (text)
  http.get(workspaceRoute(`${API_BASE}/workspace/file`), ({ request }) => {
    const url = new URL(request.url);
    const path = url.searchParams.get("path") || "";

    const file = getFile(path);
    if (file?.type !== "file") {
      return HttpResponse.json({ message: "File not found" }, { status: 404 });
    }

    return HttpResponse.json({
      content: file.content || "",
    });
  }),

  // GET /api/files - Compatibility endpoint used by document resolvers
  http.get(workspaceRoute(`${API_BASE}/files`), ({ request }) => {
    const url = new URL(request.url);
    const path = url.searchParams.get("path") || "";
    const file = getFile(path);

    if (file?.type !== "file") {
      return HttpResponse.json({ message: "File not found" }, { status: 404 });
    }

    const content = file.content || "";
    const trimmed = content.trim();

    if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
      try {
        return HttpResponse.json(JSON.parse(content));
      } catch {
        return HttpResponse.json({ content });
      }
    }

    return HttpResponse.json({ content });
  }),

  // GET /api/workspace/file/blob - Read file content (binary)
  http.get(workspaceRoute(`${API_BASE}/workspace/file/blob`), ({ request }) => {
    const url = new URL(request.url);
    const path = url.searchParams.get("path") || "";

    const file = getFile(path);
    if (file?.type !== "file") {
      return HttpResponse.json({ message: "File not found" }, { status: 404 });
    }

    const lowerPath = path.toLowerCase();
    const isImage =
      lowerPath.endsWith(".png") || lowerPath.endsWith(".jpg") || lowerPath.endsWith(".jpeg");

    return new HttpResponse(new Blob([file.bytes ?? file.content ?? ""]), {
      headers: {
        "Content-Type": isImage ? "image/png" : "application/octet-stream",
      },
    });
  }),

  // POST /api/workspace/open - Set workspace path (discriminated: local | remote)
  http.post(workspaceRoute(`${API_BASE}/workspace/open`), async ({ request }) => {
    const body = (await request.json()) as Record<string, unknown>;
    const kind = (body.kind as string | undefined) ?? "local";

    if (kind === "remote") {
      const name = String(body.name ?? "");
      // Defer to the workspace-target mock store registered in
      // workspace_targets.ts.  We import lazily to avoid a circular
      // module load.
      const { mockWorkspaceTargetsMap } = await import("./workspace_targets");
      const target = mockWorkspaceTargetsMap.get(name);
      if (!target) {
        return HttpResponse.json({ detail: `workspace target ${name} not found` }, { status: 404 });
      }
      // For dev:mock, a remote workspace exposes its own empty
      // project/asset set — distinguishable from the local mock store.
      return HttpResponse.json({
        root: target.rootPath,
        projectCount: 0,
        assetCount: 0,
        warnings: [],
      });
    }

    const path = String(body.path ?? "");
    if (!knownWorkspacePaths.has(path)) {
      if (body.create_if_missing !== true) {
        return HttpResponse.json({ detail: "Workspace path not found" }, { status: 404 });
      }
      knownWorkspacePaths.add(path);
    }
    const projects = getAllProjects();
    const assets = getAllAssets();
    return HttpResponse.json({
      root: path,
      projectCount: projects.length,
      assetCount: assets.length,
      warnings: [],
    });
  }),

  // POST /api/workspace/cache/invalidate — drops cache entries on the
  // active workspace's CachedRemoteFileSystem.  Mock always responds
  // success because dev:mock has no real cache layer; production paths
  // 409 when the active workspace is local.
  http.post(workspaceRoute(`${API_BASE}/workspace/cache/invalidate`), async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as {
      path?: string | null;
      scope?: string;
    };
    const scope = body.scope ?? "all";
    // Pretend we dropped one entry per "indices", more for "all".
    const dropped = body.path ? 1 : scope === "indices" ? 3 : 7;
    return HttpResponse.json({ dropped, warnings: [] });
  }),

  // POST /api/workspace/cache/refresh — invalidate + re-prefetch.
  http.post(workspaceRoute(`${API_BASE}/workspace/cache/refresh`), async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as {
      path?: string | null;
      scope?: string;
    };
    const scope = body.scope ?? "all";
    const dropped = body.path ? 1 : scope === "indices" ? 3 : 7;
    return HttpResponse.json({ dropped, warnings: [] });
  }),

  // POST /api/workspace/directories - Create directory
  http.post(workspaceRoute(`${API_BASE}/workspace/directories`), async ({ request }) => {
    const body = (await request.json()) as { folder_id: string; path: string };

    createDirectory(body.path);

    return HttpResponse.json({
      path: body.path,
    });
  }),

  // PUT /api/workspace/files - Write file content
  http.put(workspaceRoute(`${API_BASE}/workspace/files`), async ({ request }) => {
    const body = (await request.json()) as {
      folder_id: string;
      path: string;
      content: string;
    };

    writeFile(body.path, body.content);

    return HttpResponse.json({
      path: body.path,
    });
  }),

  // DELETE /api/workspace/files - Optional file deletion used by explorer actions
  http.delete(workspaceRoute(`${API_BASE}/workspace/files`), ({ request }) => {
    const url = new URL(request.url);
    const path = url.searchParams.get("path") || "";
    const deleted = deleteFile(path);

    if (!deleted) {
      return HttpResponse.json({ message: "File not found" }, { status: 404 });
    }

    return HttpResponse.json({ path });
  }),
];
