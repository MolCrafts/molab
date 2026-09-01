import { queryOptions, useQuery } from "@tanstack/react-query";
import { ApprovalsService } from "@/api/generated/services/ApprovalsService";

export const approvalKeys = {
  all: ["approvals"] as const,
  pending: () => [...approvalKeys.all, "pending"] as const,
};

export const pendingApprovalsQueryOptions = queryOptions({
  queryKey: approvalKeys.pending(),
  queryFn: () => ApprovalsService.listPendingApprovals(),
  staleTime: 15_000,
});

/** Shared server-state query for the bell, Dashboard, and task review surfaces. */
export const usePendingApprovalsQuery = () => useQuery(pendingApprovalsQueryOptions);
