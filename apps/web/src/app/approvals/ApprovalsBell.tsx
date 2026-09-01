/**
 * Global pending-approvals badge — list-only drawer.
 * Full review happens on the agent task surface (not duplicated here).
 */

import { useQueryClient } from "@tanstack/react-query";
import { Bell, Loader2 } from "lucide-react";
import { type JSX, useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { PendingApprovalItem } from "@/api/generated/models/PendingApprovalItem";
import { approvalKeys, usePendingApprovalsQuery } from "@/app/approvals/queries";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import {
  WorkbenchIconAction,
  WorkbenchOperationState,
  WorkbenchRetryAction,
} from "@/components/workbench";
import { cn } from "@/lib/utils";
import { ApprovalsInbox } from "./ApprovalsInbox";

export function ApprovalsBell(): JSX.Element {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const approvalsQuery = usePendingApprovalsQuery();
  const count = approvalsQuery.data?.items.length ?? 0;
  const countLoading = approvalsQuery.isLoading;
  const countError = approvalsQuery.error
    ? approvalsQuery.error instanceof Error
      ? approvalsQuery.error.message
      : "Failed to load approval count."
    : null;
  const [countAnnouncement, setCountAnnouncement] = useState<string | null>(null);
  const [streamError, setStreamError] = useState(false);
  const [open, setOpen] = useState(false);
  const countRef = useRef(0);

  useEffect(() => {
    if (!approvalsQuery.data) return;
    const nextCount = approvalsQuery.data.items.length;
    if (nextCount === countRef.current) return;
    setCountAnnouncement(
      `Approval count updated: ${nextCount} pending approval${nextCount === 1 ? "" : "s"}.`,
    );
    countRef.current = nextCount;
  }, [approvalsQuery.data]);

  useEffect(() => {
    const source = new EventSource("/api/approvals/events");
    const onChanged = (): void => {
      setStreamError(false);
      void queryClient.invalidateQueries({ queryKey: approvalKeys.pending() });
    };
    source.addEventListener("changed", onChanged);
    source.onmessage = onChanged;
    source.onopen = () => {
      setStreamError(false);
    };
    source.onerror = () => {
      setStreamError(true);
    };
    return () => {
      source.removeEventListener("changed", onChanged);
      source.close();
    };
  }, [queryClient]);

  useEffect(() => {
    if (!countAnnouncement) return;
    const handle = window.setTimeout(() => setCountAnnouncement(null), 3000);
    return () => window.clearTimeout(handle);
  }, [countAnnouncement]);

  const openItem = useCallback(
    (item: PendingApprovalItem) => {
      setOpen(false);
      // taskId is the single public conversation id (agent-task / plan session).
      navigate(`/agent-tasks/${encodeURIComponent(item.taskId)}`);
    },
    [navigate],
  );

  const tooltipLabel = countLoading
    ? "Loading approvals…"
    : countError
      ? "Approval count unavailable"
      : count > 0
        ? `${count} pending approval(s)`
        : "Approvals";

  return (
    <>
      {countLoading && (
        <WorkbenchOperationState
          kind="loading"
          density="inline"
          title="Loading approval count…"
          className="sr-only"
        />
      )}
      {countAnnouncement && (
        <WorkbenchOperationState
          kind="success"
          density="inline"
          title={countAnnouncement}
          className="sr-only"
        />
      )}
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <WorkbenchIconAction
              label={tooltipLabel}
              kind="ghost"
              className={cn("relative flex-none", countError && "text-status-failed-foreground")}
              onClick={() => setOpen(true)}
              aria-busy={countLoading}
            >
              {countLoading ? (
                <Loader2
                  className="mol-motion-progress-spin h-4 w-4 text-status-running"
                  aria-hidden
                />
              ) : (
                <Bell className="h-4 w-4" />
              )}
              {count > 0 && (
                <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-info px-1 text-micro font-medium text-info-foreground">
                  {count > 99 ? "99+" : count}
                </span>
              )}
              {countError && count === 0 && (
                <span
                  className="absolute right-0 top-0 h-1.5 w-1.5 rounded-full bg-status-failed"
                  aria-hidden
                />
              )}
            </WorkbenchIconAction>
          </TooltipTrigger>
          <TooltipContent side="bottom">{tooltipLabel}</TooltipContent>
        </Tooltip>
      </TooltipProvider>

      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent className="flex w-full flex-col sm:max-w-sm">
          <SheetHeader>
            <SheetTitle>Approvals</SheetTitle>
            <SheetDescription>Open a task to review and decide.</SheetDescription>
          </SheetHeader>
          <div className="mt-4 min-h-0 flex-1 space-y-3 overflow-y-auto">
            {countError && (
              <WorkbenchOperationState
                kind="error"
                density="compact"
                title="Unavailable"
                detail={countError}
                action={<WorkbenchRetryAction onClick={() => void approvalsQuery.refetch()} />}
              />
            )}
            {streamError && (
              <WorkbenchOperationState kind="running" density="compact" title="Reconnecting…" />
            )}
            <ApprovalsInbox variant="list" onOpenItem={openItem} />
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
}
