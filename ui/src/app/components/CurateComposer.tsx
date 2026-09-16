/**
 * NL workspace curation — POST curate-tasks → poll → ApprovalsInbox.
 */

import { useEffect, useState } from "react";
import type { CurateTaskResponse } from "@/api/generated/models/CurateTaskResponse";
import { CurateTasksService } from "@/api/generated/services/CurateTasksService";
import { ApprovalsInbox } from "@/app/renderers/agent/ApprovalsInbox";
import { useCurateTaskQuery } from "@/app/state/queries";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "@/components/ui/toast";
import { WorkbenchAction, WorkbenchTag } from "@/components/workbench";

interface CurateComposerProps {
  projectId: string;
  experimentId: string;
  onComplete?: (task: CurateTaskResponse) => void;
}

export function CurateComposer({
  projectId,
  experimentId,
  onComplete,
}: CurateComposerProps): JSX.Element {
  const [request, setRequest] = useState("");
  const [task, setTask] = useState<CurateTaskResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const taskId = task?.taskId ?? null;
  const isRunning = task?.status === "running";
  const isWaitingApproval = task?.status === "waiting_approval";
  const inFlight = isRunning || isWaitingApproval;

  // Poll only while the task is actually in flight; the query stops itself at
  // a terminal status instead of relying on this component to clear a timer.
  const taskQuery = useCurateTaskQuery(taskId ? { projectId, experimentId, taskId } : null, {
    enabled: Boolean(taskId) && inFlight,
  });

  const polled = taskQuery.data ?? null;
  useEffect(() => {
    if (!polled) return;
    setTask(polled);
    if (polled.status === "completed") {
      toast.success("Curated");
      onComplete?.(polled);
    } else if (polled.status === "failed" || polled.status === "cancelled") {
      setError(polled.error ?? `Curate ${polled.status}.`);
    }
  }, [polled, onComplete]);

  const submit = async (): Promise<void> => {
    const text = request.trim();
    if (!text) return;
    setSubmitting(true);
    setError(null);
    try {
      const created =
        await CurateTasksService.createCurateTaskApiProjectsProjectIdExperimentsExperimentIdCurateTasksPost(
          projectId,
          experimentId,
          { request: text },
        );
      setTask(created);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <span className="text-label font-medium text-muted-foreground">Curate</span>
        {task && <WorkbenchTag className="font-mono text-micro">{task.status}</WorkbenchTag>}
      </div>
      <Textarea
        value={request}
        onChange={(e) => setRequest(e.target.value)}
        placeholder='e.g. "Move run abc into baseline"'
        rows={2}
        disabled={inFlight || submitting}
      />
      <div className="flex items-center justify-end">
        <WorkbenchAction
          kind="primary"
          size="compact"
          className="h-control-compact"
          disabled={!request.trim() || inFlight || submitting}
          onClick={() => void submit()}
        >
          {submitting || isRunning ? "…" : "Run"}
        </WorkbenchAction>
      </div>
      {error && <p className="text-body-lg text-destructive">{error}</p>}
      {isWaitingApproval && taskId && (
        <ApprovalsInbox variant="detail" taskId={taskId} onDecided={() => undefined} />
      )}
    </div>
  );
}
