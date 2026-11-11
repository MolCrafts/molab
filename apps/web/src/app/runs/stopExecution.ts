/**
 * Stop one attempt, after asking. One path for every place that offers it
 * (the run page toolbar, the Preview's primary action).
 */

import { runsApi } from "@/api";
import type { ExecutionRecordSummary, RunSummary } from "@/app/types";
import type { UseAlertReturn, UseConfirmReturn } from "@/components/ConfirmDialog";
import { canCancel } from "./runLifecycle";

export const confirmAndStopExecution = async ({
  run,
  execution,
  confirm,
  alert,
  onStopped,
}: {
  run: Pick<RunSummary, "projectId" | "experimentId" | "id">;
  execution: Pick<ExecutionRecordSummary, "executionId" | "status">;
  confirm: UseConfirmReturn["confirm"];
  alert: UseAlertReturn["alert"];
  onStopped: () => void;
}): Promise<void> => {
  if (!canCancel(execution.status)) return;
  const confirmed = await confirm({
    title: `Stop ${execution.executionId}?`,
    description: "The attempt stops. Dismiss leaves it running.",
    confirmLabel: `Stop ${execution.executionId}`,
    cancelLabel: "Keep running",
    destructive: true,
  });
  if (!confirmed) return;
  try {
    await runsApi.cancelExecution(run.projectId, run.experimentId, run.id, execution.executionId);
    onStopped();
  } catch (error) {
    void alert({
      title: "Stop failed",
      description: error instanceof Error ? error.message : String(error),
    });
  }
};
