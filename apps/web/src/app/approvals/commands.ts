import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { ApprovalDecisionRequest } from "@/api/generated/models/ApprovalDecisionRequest";
import type { PendingApprovalItem } from "@/api/generated/models/PendingApprovalItem";
import { ApprovalsService } from "@/api/generated/services/ApprovalsService";
import { approvalKeys } from "./queries";

export type ApprovalAction = "approve" | "reject" | "revise";

export interface ApprovalDecisionInput {
  item: Pick<PendingApprovalItem, "taskKind" | "taskId" | "requestId">;
  action: ApprovalAction;
  fieldValues?: Record<string, unknown>;
  reason?: string;
}

export const submitApprovalDecision = ({
  item,
  action,
  fieldValues,
  reason,
}: ApprovalDecisionInput) =>
  ApprovalsService.decideApproval(item.taskKind, item.taskId, {
    requestId: item.requestId,
    action: action as ApprovalDecisionRequest.action,
    fieldValues,
    reason,
  });

/** The approval feature owns mutation and invalidation for every consuming surface. */
export const useApprovalDecision = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: submitApprovalDecision,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: approvalKeys.pending() });
    },
  });
};
