/**
 * Mock handlers for Project API endpoints
 */

import { HttpResponse, http } from "msw";
import type { ProjectCreateRequest } from "../../src/api/generated/models/ProjectCreateRequest";
import type { ApiProjectResponse } from "../../src/app/types";
import {
  deleteProject,
  getAllProjects,
  getAsset,
  getAssetsByProject,
  getAssetVersions,
  getExperimentsByProject,
  getFile,
  getProject,
  setProject,
} from "../db";
import { workspaceRoute } from "./workspaceRoute";

const API_BASE = "/api";

/**
 * A directory name derived from a display name — the same shape the server
 * produces, so the mock shows a path a person would recognise.
 */
const slugify = (name: string): string =>
  name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "") || "unnamed";

export const projectHandlers = [
  // GET /api/projects - List all projects
  http.get(workspaceRoute(`${API_BASE}/projects`), () => {
    const projects = getAllProjects();
    return HttpResponse.json(
      projects.map((p) => ({ ...p, experimentCount: getExperimentsByProject(p.id).length })),
    );
  }),

  // GET /api/projects - List all projects
  http.get(workspaceRoute(`${API_BASE}/projects/:id`), ({ params }) => {
    const { id } = params;
    const project = getProject(id as string);

    if (!project) {
      return HttpResponse.json({ message: `Project ${id} not found` }, { status: 404 });
    }

    return HttpResponse.json({
      ...project,
      experimentCount: getExperimentsByProject(project.id).length,
    });
  }),

  // GET /api/projects/:id/assets - Get project assets
  http.get(workspaceRoute(`${API_BASE}/projects/:id/assets`), ({ params }) => {
    const assets = getAssetsByProject(params.id as string);
    return HttpResponse.json(
      assets.map((asset) => ({
        id: asset.id,
        projectId: asset.projectId,
        title: asset.title ?? asset.name,
        createdAt: asset.createdAt,
        versionCount: getAssetVersions(asset.id).length,
        ref: `molab:project/${asset.projectId}/asset/${asset.id}`,
      })),
    );
  }),

  http.get(workspaceRoute(`${API_BASE}/projects/:projectId/assets/:assetId`), ({ params }) => {
    const asset = getAsset(String(params.assetId));
    if (!asset || asset.projectId !== params.projectId)
      return HttpResponse.json({ detail: "Asset not found" }, { status: 404 });
    return HttpResponse.json({
      id: asset.id,
      projectId: asset.projectId,
      title: asset.title ?? asset.name,
      createdAt: asset.createdAt,
      versionCount: getAssetVersions(asset.id).length,
      ref: `molab:project/${asset.projectId}/asset/${asset.id}`,
    });
  }),
  http.get(
    workspaceRoute(`${API_BASE}/projects/:projectId/assets/:assetId/versions`),
    ({ params }) => {
      const asset = getAsset(String(params.assetId));
      if (!asset || asset.projectId !== params.projectId)
        return HttpResponse.json({ detail: "Asset not found" }, { status: 404 });
      return HttpResponse.json(getAssetVersions(asset.id));
    },
  ),
  http.get(
    workspaceRoute(`${API_BASE}/projects/:projectId/assets/:assetId/download`),
    ({ params }) => {
      const asset = getAsset(String(params.assetId));
      if (!asset || asset.projectId !== params.projectId)
        return HttpResponse.json({ detail: "Asset not found" }, { status: 404 });
      return new HttpResponse(
        new Blob([
          getFile(`/managed-assets/${asset.id}/payload`)?.bytes ??
            getFile(`/managed-assets/${asset.id}/payload`)?.content ??
            "",
        ]),
        {
          headers: {
            "Content-Type": String(asset.extra?.mime ?? "application/octet-stream"),
            "Content-Disposition": `attachment; filename="${asset.name}"`,
          },
        },
      );
    },
  ),
  // POST /api/projects - Create new project
  http.post(workspaceRoute(`${API_BASE}/projects`), async ({ request }) => {
    const body = (await request.json()) as ProjectCreateRequest;

    const id = body.name?.toLowerCase().replace(/\s+/g, "-") || `project-${Date.now()}`;
    const newProject: ApiProjectResponse = {
      id,
      name: body.name || "New Project",
      path: `projects/${slugify(body.name || "New Project")}`,
      description: body.description || "",
      owner: body.owner || "molab",
      tags: body.tags || [],
      config: {},
      created: new Date().toISOString(),
      experimentCount: 0,
      ref: `molab:project/${id}`,
    };

    setProject(newProject);

    return HttpResponse.json(newProject, { status: 201 });
  }),

  // DELETE /api/projects/:id - Delete project
  http.delete(workspaceRoute(`${API_BASE}/projects/:id`), ({ params }) => {
    const { id } = params;
    const deleted = deleteProject(id as string);

    if (!deleted) {
      return HttpResponse.json({ message: `Project ${id} not found` }, { status: 404 });
    }

    return HttpResponse.json({ message: "Project deleted" });
  }),
];
