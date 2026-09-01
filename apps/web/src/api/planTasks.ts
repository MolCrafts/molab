import type { PlanTaskCreateRequest } from "@/api/generated/models/PlanTaskCreateRequest";
import { PlanTasksService } from "@/api/generated/services/PlanTasksService";

export const planTasksApi = {
  createPlanTask: (projectId: string, experimentId: string, data: PlanTaskCreateRequest) =>
    PlanTasksService.createPlanTask(projectId, experimentId, data),
  getPlanTask: (projectId: string, experimentId: string, taskId: string) =>
    PlanTasksService.getPlanTask(projectId, experimentId, taskId),
};
