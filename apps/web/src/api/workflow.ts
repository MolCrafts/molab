import { WorkflowService } from "@/api/generated/services/WorkflowService";

export const workflowApi = {
  save: async (
    projectId: string,
    experimentId: string,
    document: Record<string, unknown>,
  ): Promise<Record<string, unknown>> => {
    const response = await WorkflowService.putWorkflowDocument(projectId, experimentId, {
      document,
    });
    return response.document as Record<string, unknown>;
  },
};
