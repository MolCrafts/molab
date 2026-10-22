import { ExperimentsService } from "@/api/generated/services/ExperimentsService";
import type { ExperimentCreateRequest } from "@/app/types";

export const experimentsApi = {
  listExperiments: (projectId: string) => ExperimentsService.listExperiments(projectId),
  createExperiment: (projectId: string, data: ExperimentCreateRequest) =>
    ExperimentsService.createExperiment(projectId, data),
  deleteExperiment: async (projectId: string, experimentId: string): Promise<void> => {
    await ExperimentsService.deleteExperiment(projectId, experimentId);
  },
  getExperiment: (projectId: string, experimentId: string) =>
    ExperimentsService.getExperiment(projectId, experimentId),
  getExperimentComparison: (projectId: string, experimentId: string) =>
    ExperimentsService.getExperimentComparison(projectId, experimentId),
};
