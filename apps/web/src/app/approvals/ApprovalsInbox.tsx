/**
 * Approval feature inbox — pending plan/curate decisions.
 *
 * * ``variant="detail"`` (default when ``taskId`` is set): full review card for
 *   the active task (main work surface).
 * * ``variant="list"``: compact rows for the bell sheet — open the task instead
 *   of duplicating the full form in a narrow drawer.
 */

import { CheckCircle2, ChevronRight, Pencil, ShieldQuestion, XCircle } from "lucide-react";
import { type JSX, useEffect, useMemo, useState } from "react";
import type { PendingApprovalItem } from "@/api/generated/models/PendingApprovalItem";
import { humanApprovalTitle } from "@/app/approvals/presentation";
import { usePendingApprovalsQuery } from "@/app/approvals/queries";
import { MarkdownContent } from "@/components/ui/markdown";
import { Textarea } from "@/components/ui/textarea";
import {
  WorkbenchAction,
  WorkbenchOperationState,
  WorkbenchRetryAction,
  WorkbenchTag,
} from "@/components/workbench";
import { formatDateTime } from "@/lib/datetime";
import { cn } from "@/lib/utils";
import { type ApprovalAction, useApprovalDecision } from "./commands";
import { collectFieldValues, type FormDocumentWire } from "./formDocument";
import { ReviewSurface } from "./ReviewSurface";

const cleanBlurb = (raw: string | null | undefined, max = 160): string => {
  if (!raw) return "";
  let text = raw.replace(/\s+/g, " ").trim();
  const lower = text.toLowerCase();
  if (lower.startsWith("original request:")) {
    text = text.slice("original request:".length).trim();
  }
  const rev = text.toLowerCase().indexOf("revise the previous plan");
  if (rev > 0) text = text.slice(0, rev).trim();
  if (text.length > max) text = `${text.slice(0, max - 1)}…`;
  return text;
};

const ApprovalListRow = ({
  item,
  onOpen,
}: {
  item: PendingApprovalItem;
  onOpen?: (item: PendingApprovalItem) => void;
}): JSX.Element => {
  const formDoc = item.formDocument as FormDocumentWire | null | undefined;
  const title = humanApprovalTitle(item.intent, formDoc?.title);
  const isPlan =
    item.taskKind === "plan" || item.intent.includes("plan") || item.intent.includes("experiment");

  return (
    <WorkbenchAction
      kind="ghost"
      size="content"
      type="button"
      onClick={() => onOpen?.(item)}
      className={cn(
        "flex w-full items-start gap-3 rounded-panel px-3 py-3 text-left transition-colors",
        "bg-muted/40 hover:bg-muted/70",
        isPlan && "bg-info-soft/25 hover:bg-info-soft/40",
      )}
    >
      <ShieldQuestion
        className={cn("mt-0.5 h-4 w-4 flex-none", isPlan ? "text-info" : "text-warning")}
      />
      <div className="min-w-0 flex-1 space-y-0.5">
        <p className="text-body-lg font-medium text-foreground">{title}</p>
        <p className="truncate text-label text-muted-foreground">
          {item.projectId}/{item.experimentId}
          <span className="text-muted-foreground/70"> · {formatDateTime(item.requestedAt)}</span>
        </p>
        {item.reason ? (
          <p className="line-clamp-2 text-label text-muted-foreground">{item.reason}</p>
        ) : null}
      </div>
      <ChevronRight className="mt-1 h-4 w-4 flex-none text-muted-foreground" />
    </WorkbenchAction>
  );
};

const ApprovalCard = ({
  item,
  onDecided,
}: {
  item: PendingApprovalItem;
  onDecided: (message: string) => void;
}): JSX.Element => {
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const [busyAction, setBusyAction] = useState<"approve" | "reject" | "revise" | null>(null);
  const [lastAction, setLastAction] = useState<"approve" | "reject" | "revise" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const decision = useApprovalDecision();
  const busy = busyAction !== null;
  const formDoc = item.formDocument as FormDocumentWire | null | undefined;
  const hasForm = Boolean(formDoc && (formDoc.fields?.length ?? 0) > 0);
  const initial = useMemo(() => collectFieldValues(formDoc), [formDoc]);
  const [fieldValues, setFieldValues] = useState<Record<string, unknown>>(initial);

  const title = humanApprovalTitle(item.intent, formDoc?.title);
  // Gate reason only — form description_md is often the raw draft (same as title).
  const gateReason = cleanBlurb(item.reason, 200);
  const blurb =
    gateReason &&
    gateReason.trim().toLowerCase() !== title.trim().toLowerCase() &&
    !title.includes(gateReason.slice(0, Math.min(24, gateReason.length)))
      ? gateReason
      : item.intent.includes("experiment_plan") || item.intent.includes("approve_plan")
        ? "Review the draft plan below, then Approve to freeze & realize (or Revise to re-plan)."
        : gateReason;
  const isPlanReview =
    item.taskKind === "plan" ||
    item.intent.includes("plan") ||
    item.intent.includes("experiment_plan") ||
    item.intent.includes("experiment_spec");

  const decide = async (action: ApprovalAction): Promise<void> => {
    setBusyAction(action);
    setLastAction(action);
    setError(null);
    try {
      await decision.mutateAsync({
        item,
        action,
        reason: reason.trim() || undefined,
        // Always send form values so Comment is recorded on approve/revise.
        fieldValues: Object.keys(fieldValues).length > 0 ? fieldValues : undefined,
      });
      onDecided(
        action === "approve"
          ? "Approval recorded."
          : action === "reject"
            ? "Rejection recorded."
            : "Revision recorded.",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to record the decision.");
    } finally {
      setBusyAction(null);
    }
  };

  return (
    <div
      className={cn(
        "space-y-3 rounded-panel bg-muted/30 px-4 py-4",
        isPlanReview && "bg-info-soft/20",
      )}
      aria-busy={busy}
    >
      <header className="space-y-1">
        <div className="flex items-start gap-2">
          <ShieldQuestion
            className={cn("mt-0.5 h-4 w-4 flex-none", isPlanReview ? "text-info" : "text-warning")}
          />
          <div className="min-w-0 flex-1">
            <h3 className="text-body-lg font-semibold text-foreground">{title}</h3>
            <p className="text-label text-muted-foreground">
              {item.projectId}/{item.experimentId}
              {item.runId ? (
                <span className="text-muted-foreground/70"> · run {item.runId}</span>
              ) : null}
              <span className="text-muted-foreground/70">
                {" "}
                · {formatDateTime(item.requestedAt)}
              </span>
            </p>
          </div>
        </div>
        {blurb ? <p className="text-body-lg text-muted-foreground">{blurb}</p> : null}
      </header>

      {/* Plan book is the agent chat answer — not duplicated here. Bell sheet only. */}
      {!isPlanReview && item.preview ? (
        <div className="max-h-48 overflow-auto rounded-control border border-border/50 bg-card px-3 py-2 text-label">
          <MarkdownContent text={item.preview} />
        </div>
      ) : null}

      {hasForm && !isPlanReview ? (
        <ReviewSurface
          formDocument={formDoc}
          values={fieldValues}
          onChange={setFieldValues}
          disabled={busy}
          compact
        />
      ) : null}

      {rejecting && (
        <Textarea
          placeholder="Why reject? (optional)"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          rows={2}
          disabled={busy}
          className="border-0 bg-muted/50 shadow-none"
        />
      )}
      {busyAction && (
        <WorkbenchOperationState
          kind="running"
          density="compact"
          title={
            busyAction === "approve"
              ? "Recording approval…"
              : busyAction === "reject"
                ? "Recording rejection…"
                : "Recording revision…"
          }
        />
      )}
      {error && (
        <WorkbenchOperationState
          kind="error"
          density="compact"
          title="Could not record decision"
          detail={error}
          action={
            lastAction ? (
              <WorkbenchRetryAction disabled={busy} onClick={() => void decide(lastAction)} />
            ) : undefined
          }
        />
      )}
      <div className="flex items-center justify-end gap-2 pt-1">
        {rejecting ? (
          <>
            <WorkbenchAction
              kind="ghost"
              size="compact"
              disabled={busy}
              onClick={() => setRejecting(false)}
            >
              Back
            </WorkbenchAction>
            <WorkbenchAction
              kind="danger"
              size="compact"
              disabled={busy}
              onClick={() => void decide("reject")}
            >
              <XCircle className="h-3.5 w-3.5" />
              Confirm reject
            </WorkbenchAction>
          </>
        ) : (
          <>
            <WorkbenchAction
              kind="ghost"
              size="compact"
              disabled={busy}
              onClick={() => setRejecting(true)}
            >
              Reject
            </WorkbenchAction>
            {hasForm ? (
              <WorkbenchAction
                kind="secondary"
                size="compact"
                disabled={busy}
                onClick={() => void decide("revise")}
              >
                <Pencil className="h-3.5 w-3.5" />
                Revise
              </WorkbenchAction>
            ) : null}
            <WorkbenchAction
              kind="primary"
              size="compact"
              disabled={busy}
              onClick={() => void decide("approve")}
            >
              <CheckCircle2 className="h-3.5 w-3.5" />
              Approve
            </WorkbenchAction>
          </>
        )}
      </div>
    </div>
  );
};

export const ApprovalsInbox = ({
  taskId,
  onDecided,
  variant,
  onOpenItem,
}: {
  /** Narrow to one task's pending requests (inline task-view banner). */
  taskId?: string;
  /** Extra callback after a decision landed (e.g. resume status polling). */
  onDecided?: () => void;
  /**
   * ``list`` = compact rows for the bell sheet (navigate away to review).
   * ``detail`` = full review cards (default when ``taskId`` is set).
   */
  variant?: "list" | "detail";
  /** List-row click — open the owning agent/plan task in the main surface. */
  onOpenItem?: (item: PendingApprovalItem) => void;
}): JSX.Element => {
  const approvalsQuery = usePendingApprovalsQuery();
  const items = approvalsQuery.data?.items ?? [];
  const error = approvalsQuery.error
    ? approvalsQuery.error instanceof Error
      ? approvalsQuery.error.message
      : "Failed to load pending approvals."
    : null;
  const [decisionSuccess, setDecisionSuccess] = useState<string | null>(null);
  const visible = taskId ? items.filter((item) => item.taskId === taskId) : items;
  const mode = variant ?? (taskId ? "detail" : "list");

  useEffect(() => {
    if (!decisionSuccess) return;
    const handle = window.setTimeout(() => setDecisionSuccess(null), 3000);
    return () => window.clearTimeout(handle);
  }, [decisionSuccess]);

  const handleDecided = (message: string): void => {
    setDecisionSuccess(message);
    onDecided?.();
  };

  if (approvalsQuery.isLoading && items.length === 0 && !error) {
    return (
      <WorkbenchOperationState
        kind="loading"
        density="compact"
        title="Loading pending approvals…"
        skeletonRows={3}
      />
    );
  }

  if (error && items.length === 0) {
    return (
      <WorkbenchOperationState
        kind="error"
        density="compact"
        title="Could not load pending approvals"
        detail={error}
        action={<WorkbenchRetryAction onClick={() => void approvalsQuery.refetch()} />}
      />
    );
  }

  return (
    <div className="space-y-2" aria-busy={approvalsQuery.isFetching}>
      {approvalsQuery.isFetching && items.length > 0 && (
        <WorkbenchOperationState kind="running" density="compact" title="Refreshing…" />
      )}
      {error && items.length > 0 && (
        <WorkbenchOperationState
          kind="error"
          density="compact"
          title="Could not refresh"
          detail={error}
          action={<WorkbenchRetryAction onClick={() => void approvalsQuery.refetch()} />}
        />
      )}
      {decisionSuccess && (
        <WorkbenchOperationState kind="success" density="compact" title={decisionSuccess} />
      )}
      {visible.length === 0 ? (
        <WorkbenchOperationState
          kind="empty"
          density="compact"
          title={taskId ? "No approval for this task" : "No pending approvals"}
          detail={taskId ? undefined : "New requests appear here automatically."}
        />
      ) : mode === "list" ? (
        <div className="space-y-2">
          <div className="flex items-center gap-2 px-1">
            <p className="text-label font-medium text-muted-foreground">Pending</p>
            <WorkbenchTag className="bg-info-soft px-2 py-0 text-micro text-info-foreground">
              {visible.length}
            </WorkbenchTag>
          </div>
          {visible.map((item) => (
            <ApprovalListRow
              key={`${item.taskId}:${item.requestId}`}
              item={item}
              onOpen={onOpenItem}
            />
          ))}
        </div>
      ) : (
        <div className="space-y-3">
          {taskId ? (
            <p className="px-1 text-label font-medium text-muted-foreground">
              Waiting for approval
            </p>
          ) : null}
          {visible.map((item) => (
            <ApprovalCard
              key={`${item.taskId}:${item.requestId}`}
              item={item}
              onDecided={handleDecided}
            />
          ))}
        </div>
      )}
    </div>
  );
};
