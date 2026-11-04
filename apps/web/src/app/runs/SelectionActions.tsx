/**
 * Verbs for the runs currently selected in one list.
 *
 * Compare and clear stay with the caller. Start, cancel, resume, and rerun
 * come from {@link planSelection} and run one request per run.
 */

import { type JSX, useState } from "react";
import { runsApi } from "@/api";
import { apiErrorMessage } from "@/api/errors";
import type { ExecutionAttemptCreateRequest } from "@/api/generated/models/ExecutionAttemptCreateRequest";
import type { RunSummary } from "@/app/types";
import { toast } from "@/components/ui/toast";
import { WorkbenchAction } from "@/components/workbench";
import { type PlannedAttempt, planSelection, type SelectionMode } from "./selectionVerbs";

export interface SelectionActionsProps {
  runs: readonly RunSummary[];
  compareDisabledReason: string | null;
  onCompare: () => void;
  onClear: () => void;
  onChanged: () => void;
}

const countLabel = (label: string, count: number): string =>
  count > 0 ? `${label} ${count}` : label;

const applyOne = async (item: PlannedAttempt): Promise<void> => {
  if (item.mode === "cancel") {
    if (!item.executionId) return;
    await runsApi.cancelExecution(item.projectId, item.experimentId, item.runId, item.executionId);
    return;
  }
  await runsApi.createExecution(item.projectId, item.experimentId, item.runId, {
    mode: item.mode as ExecutionAttemptCreateRequest.mode,
    ...(item.executionId ? { basedOnExecutionId: item.executionId } : {}),
    target: "local",
  });
};

export const SelectionActions = ({
  runs,
  compareDisabledReason,
  onCompare,
  onClear,
  onChanged,
}: SelectionActionsProps): JSX.Element => {
  const plan = planSelection(runs);
  const [busy, setBusy] = useState<SelectionMode | null>(null);

  const apply = async (
    items: PlannedAttempt[],
    mode: SelectionMode,
    done: string,
  ): Promise<void> => {
    setBusy(mode);
    const failures: string[] = [];
    for (const item of items) {
      try {
        await applyOne(item);
      } catch (err) {
        failures.push(apiErrorMessage(err, item.runId));
      }
    }
    setBusy(null);
    if (failures.length > 0) toast.error(`${failures.length} of ${items.length} failed`);
    else toast.success(done);
    onChanged();
  };

  return (
    <>
      <span className="text-label text-muted-foreground">{runs.length} selected</span>
      <WorkbenchAction
        kind="secondary"
        size="compact"
        type="button"
        disabled={busy !== null || plan.start.length === 0}
        onClick={() => void apply(plan.start, "initial", `${plan.start.length} started`)}
      >
        {countLabel("Start", plan.start.length)}
      </WorkbenchAction>
      <WorkbenchAction
        kind="secondary"
        size="compact"
        type="button"
        disabled={busy !== null || plan.cancel.length === 0}
        onClick={() => void apply(plan.cancel, "cancel", `${plan.cancel.length} cancelled`)}
      >
        {countLabel("Cancel", plan.cancel.length)}
      </WorkbenchAction>
      <WorkbenchAction
        kind="secondary"
        size="compact"
        type="button"
        disabled={busy !== null || plan.resume.length === 0}
        onClick={() => void apply(plan.resume, "resume", `${plan.resume.length} resumed`)}
      >
        {countLabel("Resume", plan.resume.length)}
      </WorkbenchAction>
      <WorkbenchAction
        kind="secondary"
        size="compact"
        type="button"
        disabled={busy !== null || plan.rerun.length === 0}
        onClick={() => void apply(plan.rerun, "rerun", `${plan.rerun.length} rerun`)}
      >
        {countLabel("Rerun", plan.rerun.length)}
      </WorkbenchAction>
      <WorkbenchAction
        kind="secondary"
        size="compact"
        type="button"
        disabled={runs.length === 0 || compareDisabledReason !== null}
        deniedReason={compareDisabledReason}
        onClick={onCompare}
      >
        Add to selection
      </WorkbenchAction>
      <WorkbenchAction
        kind="ghost"
        size="compact"
        type="button"
        disabled={runs.length === 0}
        onClick={onClear}
      >
        Clear
      </WorkbenchAction>
    </>
  );
};
