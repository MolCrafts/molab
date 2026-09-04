import { ProjectsService } from "@/api/generated/services/ProjectsService";
import type { ProjectCreateRequest } from "@/app/types";
import { projectAssetView } from "@/api/assets";

/** Active-workspace projects (`GET/POST /api/projects`). */
export const projectsApi = {
  listProjects: () => ProjectsService.listProjects(),
  createProject: (data: ProjectCreateRequest) => ProjectsService.createProject(data),
  deleteProject: async (projectId: string): Promise<void> => {
    await ProjectsService.deleteProject(projectId);
  },
  getProject: (projectId: string) => ProjectsService.getProject(projectId),
  listProjectAssets: async (projectId: string) =>
    (await ProjectsService.listProjectAssets(projectId)).map(projectAssetView),
};

/** Named served workspace (`GET /api/workspaces/{ws}/projects`). */
export const projectsWsApi = {
  listProjects: (workspaceKey: string) => ProjectsService.listProjectsWs(workspaceKey),
};
