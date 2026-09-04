import { PlansService } from "@/api/generated/services/PlansService";

export const plansApi = {
  listPlans: (projectId: string, experimentId: string) =>
    PlansService.listPlans(projectId, experimentId),
  listAllPlans: () => PlansService.listAllPlans(),
  getPlan: (projectId: string, experimentId: string, runId: string, executionId?: string | null) =>
    PlansService.getPlan(projectId, experimentId, runId, executionId),
};
